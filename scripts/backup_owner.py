#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ads_autopilot.paths import RuntimePaths

UTC = timezone.utc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
        integrity = str(dst.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise RuntimeError(f"backup integrity failed for {source.name}: {integrity}")
    destination.chmod(0o600)


def copy_private(source: Path, destination: Path, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copy2(source, destination)
    destination.chmod(mode)


def create_backup(paths: RuntimePaths, destination_root: Path | None = None) -> Path:
    required = [paths.owner_db, paths.runtime_db, paths.signing_key]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"runtime is not initialized; missing: {missing}")

    backup_root = (
        destination_root.expanduser().resolve()
        if destination_root
        else (paths.owner_home / "backups").resolve()
    )
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup_root.chmod(0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = backup_root / stamp
    suffix = 0
    while destination.exists():
        suffix += 1
        destination = backup_root / f"{stamp}-{suffix}"
    destination.mkdir(mode=0o700)

    sqlite_backup(paths.owner_db, destination / "owner.db")
    sqlite_backup(paths.runtime_db, destination / "runtime.db")
    copy_private(
        paths.signing_key,
        destination / "secrets/operator_signing_key",
        0o600,
    )

    optional = [
        (paths.codex_home / "config.toml", destination / "codex-home/config.toml", 0o600),
        (paths.codex_home / "hooks.json", destination / "codex-home/hooks.json", 0o600),
        (paths.trusted_hook_file, destination / "trusted-hooks/codex_pretool_hook.py", 0o500),
    ]
    for source, target, mode in optional:
        if source.exists():
            copy_private(source, target, mode)

    files = []
    for path in sorted(destination.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        files.append(
            {
                "path": str(path.relative_to(destination)),
                "sha256": sha256(path),
                "size": path.stat().st_size,
                "mode": oct(path.stat().st_mode & 0o777),
            }
        )

    manifest = {
        "version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_owner_home": str(paths.owner_home),
        "contains_oauth_auth_store": False,
        "files": files,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    manifest_path.chmod(0o600)

    # Make the directory entry and manifest durable before reporting success.
    for directory in [destination, backup_root]:
        try:
            fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--destination-root",
        type=Path,
        help="Optional private directory in which to create the timestamped backup",
    )
    args = parser.parse_args()
    paths = RuntimePaths.resolve(ROOT)
    backup = create_backup(paths, args.destination_root)
    print(f"Backup created: {backup}")
    print("OAuth/auth.json is intentionally not copied; re-authenticate Codex/Amazon MCP after host recovery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
