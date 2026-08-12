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

from ads_autopilot.owner_store import OwnerStore
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.sealing import Sealer
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
    if int(manifest.get("version") or 0) != 1:
        raise RuntimeError("unsupported backup manifest version")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise RuntimeError("backup manifest contains no files")
    required = {"owner.db", "runtime.db", "secrets/operator_signing_key"}
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


def _atomic_copy(source: Path, target: Path, mode: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_name(target.name + ".restore-tmp")
    shutil.copy2(source, temporary)
    temporary.chmod(mode)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    target.chmod(mode)


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

    paths.ensure_directories()
    mode_by_path = {
        str(item["path"]): int(str(item.get("mode") or "0o600"), 8)
        for item in manifest["files"]
    }
    destinations = {
        "owner.db": paths.owner_db,
        "runtime.db": paths.runtime_db,
        "secrets/operator_signing_key": paths.signing_key,
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

    # A restored host starts from observation, not because AI authority is
    # reduced, but because OAuth and external Amazon state must be re-bound on
    # the new machine before unattended writes resume.
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
