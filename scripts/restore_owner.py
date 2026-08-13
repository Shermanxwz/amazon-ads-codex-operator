#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ads_autopilot.codex_compat import active_identity
from ads_autopilot.codex_compat.registry import save_registry, slots_root
from ads_autopilot.owner_store import OwnerStore
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.sealing import Sealer, bootstrap_executor_grant_key
from ads_autopilot.state import Store


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_backup(backup: Path) -> dict:
    backup = backup.expanduser().resolve()
    manifest_path = backup / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("backup manifest.json is missing")
    manifest = json.loads(manifest_path.read_text())
    version = int(manifest.get("version") or 0)
    if version not in {1, 2}:
        raise RuntimeError("unsupported backup manifest version")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise RuntimeError("backup manifest contains no files")
    required = {"owner.db", "runtime.db", "secrets/operator_signing_key"}
    if version >= 2:
        required.add("secrets/executor_grant_signing_key")
    listed = {str(item.get("path") or "") for item in files if isinstance(item, dict)}
    if not required.issubset(listed):
        raise RuntimeError(f"backup is incomplete; missing {sorted(required-listed)}")
    for item in files:
        if not isinstance(item, dict):
            raise RuntimeError("invalid backup manifest entry")
        relative = Path(str(item.get("path") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("unsafe backup manifest path")
        path = backup / relative
        if not path.is_file():
            raise RuntimeError(f"backup file missing: {relative}")
        if sha256(path) != str(item.get("sha256") or ""):
            raise RuntimeError(f"backup checksum mismatch: {relative}")
    if version >= 2 and manifest.get("codex_runtime_snapshot") is not None:
        if "codex-runtimes/registry.json" not in listed:
            raise RuntimeError("Codex runtime snapshot is missing registry.json")
        snapshot = manifest.get("codex_runtime_snapshot") or {}
        for runtime_id in snapshot.get("runtime_ids") or []:
            expected = f"codex-runtimes/slots/{runtime_id}/codex"
            if expected not in listed:
                raise RuntimeError(f"Codex runtime snapshot missing slot: {runtime_id}")
    return manifest


def _current_mode(owner_db: Path) -> str | None:
    if not owner_db.exists():
        return None
    try:
        with sqlite3.connect(owner_db, timeout=2) as conn:
            row = conn.execute("SELECT mode FROM control_state WHERE id=1").fetchone()
        return str(row[0]).lower() if row else None
    except Exception:
        return None


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _atomic_copy(source: Path, target: Path, mode: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_name(target.name + ".restore-tmp")
    shutil.copy2(source, temporary)
    temporary.chmod(mode)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    target.chmod(mode)
    _fsync_dir(target.parent)


def _remove_sqlite_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        try:
            Path(str(path) + suffix).unlink(missing_ok=True)
        except OSError:
            pass


def _reset_unrestored_surfaces(paths: RuntimePaths) -> None:
    # A force/in-place restore must not inherit authorization evidence, OAuth,
    # disposable model workspaces, or a different ACTIVE runtime from the old host state.
    for directory in (
        paths.codex_home,
        paths.grant_root,
        paths.run_root,
        paths.workspace_root,
        paths.trusted_hook_root,
        paths.owner_home / "codex-runtimes",
    ):
        if directory.exists():
            shutil.rmtree(directory)
    for db in (paths.owner_db, paths.runtime_db):
        _remove_sqlite_sidecars(db)
    try:
        paths.lock_file.unlink(missing_ok=True)
    except OSError:
        pass


def _rewrite_runtime_record(record: dict, paths: RuntimePaths) -> dict:
    value = dict(record)
    runtime_id = str(value.get("id") or "")
    if not runtime_id:
        raise RuntimeError("Codex runtime record has no id")
    target = slots_root(paths) / runtime_id / "codex"
    if not target.is_file():
        raise RuntimeError(f"restored Codex runtime slot missing: {runtime_id}")
    actual = sha256(target)
    expected = str(value.get("binary_sha256") or runtime_id)
    if actual != runtime_id or actual != expected:
        raise RuntimeError(
            f"restored Codex runtime fingerprint mismatch: id={runtime_id} expected={expected} actual={actual}"
        )
    value["binary"] = str(target)
    return value


def _restore_codex_runtimes(backup: Path, paths: RuntimePaths) -> None:
    registry_source = backup / "codex-runtimes/registry.json"
    if not registry_source.exists():
        return
    registry = json.loads(registry_source.read_text())
    candidates = registry.get("candidates") or {}
    if not isinstance(candidates, dict):
        raise RuntimeError("invalid backed-up Codex candidates registry")
    ids: set[str] = set(str(key) for key in candidates)
    for key in ("active", "previous"):
        value = registry.get(key)
        if isinstance(value, dict) and value.get("id"):
            ids.add(str(value["id"]))
    for runtime_id in sorted(ids):
        source = backup / "codex-runtimes" / "slots" / runtime_id / "codex"
        if not source.is_file():
            raise RuntimeError(f"backed-up Codex runtime slot missing: {runtime_id}")
        if sha256(source) != runtime_id:
            raise RuntimeError(f"backed-up Codex runtime hash does not match id: {runtime_id}")
        _atomic_copy(source, slots_root(paths) / runtime_id / "codex", 0o500)

    registry["candidates"] = {
        str(runtime_id): _rewrite_runtime_record(record, paths)
        for runtime_id, record in candidates.items()
        if isinstance(record, dict)
    }
    for key in ("active", "previous"):
        value = registry.get(key)
        if isinstance(value, dict):
            registry[key] = _rewrite_runtime_record(value, paths)
    save_registry(paths, registry)


def restore_backup(backup: Path, paths: RuntimePaths, *, force: bool = False) -> None:
    backup = backup.expanduser().resolve()
    manifest = verify_backup(backup)

    existing = [paths.owner_db, paths.runtime_db, paths.signing_key]
    if any(path.exists() for path in existing) and not force:
        raise RuntimeError("target runtime already exists; pass --force only after pausing/stopping services")
    mode = _current_mode(paths.owner_db)
    if force and mode not in {None, "paused", "observe"}:
        raise RuntimeError(
            f"refusing in-place restore while current Owner mode is {mode}; pause/observe first"
        )

    paths.owner_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    _reset_unrestored_surfaces(paths)
    paths.ensure_directories()
    mode_by_path = {
        str(item["path"]): int(str(item.get("mode") or "0o600"), 8)
        for item in manifest["files"]
    }
    destinations = {
        "owner.db": paths.owner_db,
        "runtime.db": paths.runtime_db,
        "secrets/operator_signing_key": paths.signing_key,
        "secrets/executor_grant_signing_key": paths.grant_signing_key,
        "codex-home/config.toml": paths.codex_home / "config.toml",
        "codex-home/hooks.json": paths.codex_home / "hooks.json",
        "trusted-hooks/codex_pretool_hook.py": paths.trusted_hook_file,
    }
    for relative, destination in destinations.items():
        source = backup / relative
        if not source.exists():
            continue
        default_mode = 0o500 if relative.endswith("codex_pretool_hook.py") else 0o600
        _atomic_copy(source, destination, mode_by_path.get(relative, default_mode))

    # Legacy v1 backups predate key separation. Re-derive the grant-only key
    # deterministically from the restored Owner master key when absent.
    bootstrap_executor_grant_key(paths.signing_key, paths.grant_signing_key)
    _restore_codex_runtimes(backup, paths)

    with sqlite3.connect(paths.owner_db) as conn:
        owner_integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    with sqlite3.connect(paths.runtime_db) as conn:
        runtime_integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    if owner_integrity.lower() != "ok" or runtime_integrity.lower() != "ok":
        raise RuntimeError(
            f"restored SQLite integrity failed: owner={owner_integrity}, runtime={runtime_integrity}"
        )

    sealer = Sealer.from_path(paths.signing_key)
    owner = OwnerStore(paths.owner_db, sealer.key)
    audit = owner.verify_audit_chain()
    if not audit.get("ok"):
        raise RuntimeError(f"restored Owner audit chain failed: {audit}")
    runtime = Store(paths.runtime_db)
    if not runtime.integrity_check().get("ok"):
        raise RuntimeError("restored runtime DB integrity/foreign-key check failed")

    snapshot = manifest.get("codex_runtime_snapshot") or {}
    if snapshot.get("active_id"):
        active = active_identity(paths)
        if active is None or not active.get("integrity_ok"):
            raise RuntimeError("restored ACTIVE Codex runtime failed integrity verification")
        if str(active.get("id") or "") != str(snapshot.get("active_id")):
            raise RuntimeError("restored ACTIVE Codex runtime identity differs from backup manifest")

    owner.set_mode("observe", actor="restore")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing paused/observe runtime after services are stopped",
    )
    parser.add_argument(
        "--owner-home",
        type=Path,
        help="Optional restore target; defaults to ADS_OWNER_HOME/standard Owner home",
    )
    args = parser.parse_args()
    paths = RuntimePaths.resolve(ROOT, args.owner_home)
    restore_backup(args.backup, paths, force=args.force)
    print(f"Restore verified: {paths.owner_home}")
    print("Owner mode is OBSERVE. Re-run Codex/Amazon MCP OAuth, preflight, and a dry-run before returning to AUTOPILOT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
