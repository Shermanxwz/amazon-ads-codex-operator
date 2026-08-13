from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from ads_autopilot.codex_compat import active_identity, promote_candidate, register_candidate
from ads_autopilot.codex_compat.registry import load_registry
from ads_autopilot.owner_store import OwnerStore
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.security import hash_password
from ads_autopilot.sealing import Sealer, bootstrap_executor_grant_key, bootstrap_key
from ads_autopilot.state import Store

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_codex(path: Path, version: str) -> Path:
    tokens = "--strict-config --sandbox --ask-for-approval --dangerously-bypass-hook-trust --ephemeral --json --output-schema --output-last-message --config --model"
    script = f'''#!/bin/sh
set -eu
if [ "${{1:-}}" = "--version" ]; then echo "codex-cli {version}"; exit 0; fi
case "${{1:-}}" in
  exec) echo "{tokens}" ;;
  mcp) echo "list login" ;;
  plugin)
    if [ "${{2:-}}" = "marketplace" ]; then echo "add list upgrade remove"; else echo "list marketplace"; fi ;;
  features) echo "list" ;;
  sandbox) echo "sandbox" ;;
  doctor) echo "doctor" ;;
  update) echo "update" ;;
  *) echo "unknown"; exit 2 ;;
esac
'''
    path.write_text(script)
    path.chmod(0o755)
    return path


def bootstrap_runtime(owner_home: Path) -> RuntimePaths:
    paths = RuntimePaths.resolve(ROOT, owner_home)
    paths.ensure_directories()
    bootstrap_key(paths.signing_key)
    bootstrap_executor_grant_key(paths.signing_key, paths.grant_signing_key)
    sealer = Sealer.from_path(paths.signing_key)
    owner = OwnerStore(paths.owner_db, sealer.key)
    policy = json.loads((ROOT / "config/autonomy-policy.json").read_text())
    operator = json.loads((ROOT / "config/operator.example.json").read_text())
    owner.bootstrap(policy, operator, hash_password("archive-test-password"))
    runtime = Store(paths.runtime_db)
    runtime.create_cycle("test-cycle", "daily")
    runtime.finish_cycle("test-cycle", "completed", {"ok": True})
    (paths.codex_home / "config.toml").write_text("[features]\nhooks = true\n")
    (paths.codex_home / "hooks.json").write_text("{}")
    paths.trusted_hook_file.write_text("#!/usr/bin/env python3\n")
    paths.trusted_hook_file.chmod(0o500)

    contract = ROOT / "config/codex-compatibility.json"
    one = register_candidate(paths, fake_codex(owner_home.parent / "codex-one", "1.0"), contract)
    promote_candidate(paths, str(one["id"]), contract)
    two = register_candidate(paths, fake_codex(owner_home.parent / "codex-two", "2.0"), contract)
    promote_candidate(paths, str(two["id"]), contract)
    return paths


def test_backup_restore_roundtrip_preserves_integrity_and_codex_runtime(tmp_path: Path):
    backup_mod = load_script("backup_owner.py")
    restore_mod = load_script("restore_owner.py")

    source = bootstrap_runtime(tmp_path / "source-owner")
    source_registry = load_registry(source)
    backup = backup_mod.create_backup(source, tmp_path / "backups")
    manifest = restore_mod.verify_backup(backup)
    assert manifest["version"] == 2
    assert manifest["contains_oauth_auth_store"] is False
    assert manifest["codex_runtime_snapshot"]["active_id"] == source_registry["active"]["id"]
    assert manifest["codex_runtime_snapshot"]["previous_id"] == source_registry["previous"]["id"]
    assert {entry["path"] for entry in manifest["files"]} >= {
        "owner.db",
        "runtime.db",
        "secrets/operator_signing_key",
        "secrets/executor_grant_signing_key",
        "codex-home/config.toml",
        "codex-home/hooks.json",
        "trusted-hooks/codex_pretool_hook.py",
        "codex-runtimes/registry.json",
        f"codex-runtimes/slots/{source_registry['active']['id']}/codex",
        f"codex-runtimes/slots/{source_registry['previous']['id']}/codex",
    }

    target = RuntimePaths.resolve(ROOT, tmp_path / "restored-owner")
    (target.codex_home).mkdir(parents=True, exist_ok=True)
    (target.codex_home / "auth.json").write_text("must-not-survive")
    target.grant_root.mkdir(parents=True, exist_ok=True)
    (target.grant_root / "stale.json").write_text("must-not-survive")
    restore_mod.restore_backup(backup, target)

    restored_sealer = Sealer.from_path(target.signing_key)
    restored_owner = OwnerStore(target.owner_db, restored_sealer.key)
    assert restored_owner.verify_audit_chain()["ok"] is True
    assert restored_owner.snapshot()["mode"] == "observe"
    assert Store(target.runtime_db).integrity_check()["ok"] is True
    assert (target.codex_home / "config.toml").read_text().startswith("[features]")
    assert target.trusted_hook_file.exists()
    assert not (target.codex_home / "auth.json").exists()
    assert not (target.grant_root / "stale.json").exists()
    active = active_identity(target)
    assert active and active["integrity_ok"] is True
    assert active["version_text"] == "codex-cli 2.0"
    restored_registry = load_registry(target)
    assert restored_registry["previous"]["version_text"] == "codex-cli 1.0"
    assert Path(restored_registry["active"]["binary"]).is_relative_to(target.owner_home)


def test_verify_backup_keeps_v1_backward_compatibility(tmp_path: Path):
    restore_mod = load_script("restore_owner.py")
    backup = tmp_path / "legacy"
    (backup / "secrets").mkdir(parents=True)
    for relative, payload in (
        ("owner.db", b"owner"),
        ("runtime.db", b"runtime"),
        ("secrets/operator_signing_key", b"key"),
    ):
        path = backup / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    files = []
    for path in sorted(p for p in backup.rglob("*") if p.is_file()):
        files.append({"path": str(path.relative_to(backup)), "sha256": restore_mod.sha256(path), "size": path.stat().st_size, "mode": "0o600"})
    (backup / "manifest.json").write_text(json.dumps({"version": 1, "files": files}))
    assert restore_mod.verify_backup(backup)["version"] == 1
