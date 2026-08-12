from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from ads_autopilot.owner_store import OwnerStore
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.security import hash_password
from ads_autopilot.sealing import Sealer, bootstrap_key
from ads_autopilot.state import Store

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bootstrap_runtime(owner_home: Path) -> RuntimePaths:
    paths = RuntimePaths.resolve(ROOT, owner_home)
    paths.ensure_directories()
    bootstrap_key(paths.signing_key)
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
    return paths


def test_backup_restore_roundtrip_preserves_integrity(tmp_path: Path):
    backup_mod = load_script("backup_owner.py")
    restore_mod = load_script("restore_owner.py")

    source = bootstrap_runtime(tmp_path / "source-owner")
    backup = backup_mod.create_backup(source, tmp_path / "backups")
    manifest = restore_mod.verify_backup(backup)
    assert manifest["contains_oauth_auth_store"] is False
    assert {entry["path"] for entry in manifest["files"]} >= {
        "owner.db",
        "runtime.db",
        "secrets/operator_signing_key",
        "codex-home/config.toml",
        "codex-home/hooks.json",
        "trusted-hooks/codex_pretool_hook.py",
    }

    target = RuntimePaths.resolve(ROOT, tmp_path / "restored-owner")
    restore_mod.restore_backup(backup, target)

    restored_sealer = Sealer.from_path(target.signing_key)
    restored_owner = OwnerStore(target.owner_db, restored_sealer.key)
    assert restored_owner.verify_audit_chain()["ok"] is True
    assert restored_owner.snapshot()["mode"] == "observe"
    assert Store(target.runtime_db).integrity_check()["ok"] is True
    assert (target.codex_home / "config.toml").read_text().startswith("[features]")
    assert target.trusted_hook_file.exists()
