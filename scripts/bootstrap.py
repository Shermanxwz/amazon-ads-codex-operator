#!/usr/bin/env python3
from __future__ import annotations

import getpass
import json
import os
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ads_autopilot.owner_store import OwnerStore
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.security import hash_password
from ads_autopilot.sealing import Sealer, bootstrap_key
from ads_autopilot.state import Store


def main() -> int:
    paths = RuntimePaths.resolve(ROOT)
    paths.ensure_directories()
    key_path = bootstrap_key(paths.signing_key)
    sealer = Sealer.from_path(key_path)
    owner = OwnerStore(paths.owner_db, sealer.key)

    try:
        owner.get_password_hash()
        initialized = True
    except RuntimeError:
        initialized = False

    policy_source = ROOT / "config/autonomy-policy.json"
    operator_source = ROOT / "config/operator.example.json"
    policy = json.loads(policy_source.read_text())
    operator = json.loads(operator_source.read_text())

    if not initialized:
        password = os.environ.get("ADS_CONTROL_PASSWORD")
        if not password:
            if not sys.stdin.isatty():
                raise RuntimeError("first bootstrap requires ADS_CONTROL_PASSWORD or an interactive terminal")
            password = getpass.getpass("Create Owner Web control password (>=12 chars): ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                raise RuntimeError("password confirmation does not match")
        owner.bootstrap(policy, operator, hash_password(password))
    else:
        audit = owner.verify_audit_chain()
        if not audit.get("ok"):
            raise RuntimeError(f"owner audit chain failed integrity check: {audit}")

    Store(paths.runtime_db)
    ensure_codex_config(paths)
    print(f"Owner home: {paths.owner_home}")
    print(f"Owner DB:   {paths.owner_db}")
    print(f"Runtime DB: {paths.runtime_db}")
    print(f"Signing key: {paths.signing_key} (mode 0600)")
    print(f"Codex home: {paths.codex_home}")
    print("Initial mode is OBSERVE. Configure account/profile + daily spend ceiling in Owner Web, then explicitly switch to AUTOPILOT.")
    return 0


def ensure_codex_config(paths: RuntimePaths) -> Path:
    config = paths.codex_home / "config.toml"
    desired = '''# Dedicated production Codex home for Amazon Ads Autopilot.\n# Planner/Verifier keep write tools gated; Executor overrides this to approve\n# only after deterministic HMAC sealing + PreToolUse exact-argument validation.\n\n[features]\nhooks = true\n\n[mcp_servers.amazon_ads]\nurl = "https://advertising-ai.amazon.com/mcp"\nauth = "oauth"\nenabled = true\nrequired = true\nstartup_timeout_sec = 30\ntool_timeout_sec = 180\ndefault_tools_approval_mode = "writes"\n'''
    config.write_text(desired)
    source_hook = paths.project_root / "scripts/codex_pretool_hook.py"
    shutil.copy2(source_hook, paths.trusted_hook_file)
    paths.trusted_hook_file.chmod(0o500)
    hook_command = f'/usr/bin/python3 "{paths.trusted_hook_file}"'
    hooks = {
        "description": "Owner-controlled Amazon Ads MCP pre-tool authorization",
        "hooks": {
            "PreToolUse": [{
                "matcher": ".*",
                "hooks": [{"type": "command", "command": hook_command, "timeout": 5, "statusMessage": "Validating Owner sealed action"}],
            }]
        },
    }
    hooks_path = paths.codex_home / "hooks.json"
    hooks_path.write_text(json.dumps(hooks, indent=2))
    try: hooks_path.chmod(0o600)
    except OSError: pass
    try: config.chmod(0o600)
    except OSError: pass
    return config


if __name__ == "__main__":
    raise SystemExit(main())
