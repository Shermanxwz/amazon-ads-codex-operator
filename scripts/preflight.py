#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ads_autopilot.codex_compat import active_identity
from ads_autopilot.owner_store import OwnerStore
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.sealing import Sealer
from ads_autopilot.state import Store

checks: list[tuple[bool, str]] = []


def add(ok: bool, msg: str) -> None:
    checks.append((bool(ok), msg))
    print(("[OK]   " if ok else "[FAIL] ") + msg)


def mode(path: Path) -> int | None:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return None


def main() -> int:
    paths = RuntimePaths.resolve(ROOT)
    system_codex = shutil.which("codex")
    if system_codex:
        print(f"[INFO] System/PATH Codex candidate: {system_codex}")
    else:
        print("[INFO] No PATH Codex candidate installed; production may still use Owner-pinned ACTIVE runtime")

    active = active_identity(paths)
    add(active is not None, "Owner-pinned ACTIVE Codex runtime configured")
    codex: str | None = None
    if active is not None:
        add(bool(active.get("integrity_ok")), f"ACTIVE Codex runtime fingerprint valid: {active.get('integrity_detail')}")
        binary = Path(str(active.get("binary") or ""))
        slot_root = paths.owner_home / "codex-runtimes" / "slots"
        add(binary.is_relative_to(slot_root), "ACTIVE Codex runtime is an Owner-owned immutable slot snapshot")
        codex = str(binary) if active.get("integrity_ok") else None
        print(f"[INFO] ACTIVE Codex version: {active.get('version_text') or 'unknown'}")
        print(f"[INFO] ACTIVE Codex runtime id: {active.get('id') or 'unknown'}")

    add(paths.owner_home.exists(), f"Owner home exists: {paths.owner_home}")
    add(paths.owner_db.exists(), "Owner DB initialized")
    add(paths.signing_key.exists(), "Controller signing key exists")
    add(mode(paths.signing_key) == 0o600, "Signing key permissions are 0600")
    add(
        mode(paths.owner_home) is not None and (mode(paths.owner_home) & 0o077) == 0,
        "Owner home is not group/world accessible",
    )
    add(
        paths.project_root not in paths.owner_home.parents
        and paths.owner_home not in paths.project_root.parents,
        "Git project and Owner home are separate filesystem trees",
    )
    add((paths.codex_home / "config.toml").exists(), "Dedicated production CODEX_HOME configured")
    add((paths.codex_home / "hooks.json").exists(), "Owner PreToolUse hooks.json configured")
    add(paths.trusted_hook_file.exists(), "Frozen Owner-controlled PreToolUse hook deployed")

    source_hook = ROOT / "scripts/codex_pretool_hook.py"
    if source_hook.exists() and paths.trusted_hook_file.exists():
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        add(digest(source_hook) == digest(paths.trusted_hook_file), "Deployed PreToolUse hook matches vetted project source")

    if (paths.codex_home / "config.toml").exists():
        cfg = (paths.codex_home / "config.toml").read_text()
        add("hooks = true" in cfg, "Codex hooks feature enabled")
        add('default_tools_approval_mode = "writes"' in cfg, "Base MCP policy keeps writes approval-gated")

    if paths.signing_key.exists() and paths.owner_db.exists():
        sealer = Sealer.from_path(paths.signing_key)
        owner = OwnerStore(paths.owner_db, sealer.key)
        snap = owner.snapshot()
        audit = owner.verify_audit_chain()
        add(bool(audit.get("ok")), f"Owner audit chain valid ({audit.get('entries', 0)} entries)")
        add(snap["policy"]["money"].get("owner_daily_spend_ceiling") is not None, "owner_daily_spend_ceiling configured")
        profiles = [str(value) for value in snap["operator"].get("profile_ids", []) if str(value) and str(value) != "REPLACE_ME"]
        add(bool(profiles), "At least one real Amazon Ads profile_id configured")
        add(str(snap["operator"].get("advertiser_account_id") or "") not in {"", "REPLACE_ME"}, "Advertiser account ID configured")
        add(snap["mode"] in {"observe", "paused", "autopilot"}, f"Owner control mode valid: {snap['mode']}")

    if paths.runtime_db.exists():
        runtime = Store(paths.runtime_db)
        add(runtime.integrity_check().get("ok", False), "Runtime SQLite integrity check passes")
    else:
        add(False, "Runtime DB initialized")

    if codex and (paths.codex_home / "config.toml").exists():
        env = dict(os.environ)
        env["CODEX_HOME"] = str(paths.codex_home)
        compatibility = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_codex_runtime.py"), "--binary", codex],
            text=True,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        print(compatibility.stdout.rstrip())
        add(compatibility.returncode == 0, "ACTIVE Codex satisfies the certified Evergreen capability contract")

        mcp = subprocess.run(
            [codex, "mcp", "list"],
            text=True,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        add(mcp.returncode == 0 and "amazon_ads" in mcp.stdout, "amazon_ads MCP configured in dedicated CODEX_HOME")

    return 0 if all(ok for ok, _ in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
