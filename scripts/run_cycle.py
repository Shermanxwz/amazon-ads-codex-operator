#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
import sys
try:
    import fcntl
except ImportError:
    fcntl = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ads_autopilot.override_controller import OwnerOverrideOptimizationController
from ads_autopilot.owner_override import OwnerOverrideStore
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.sealing import Sealer


@contextlib.contextmanager
def single_instance():
    paths = RuntimePaths.resolve(ROOT)
    paths.ensure_directories()
    handle = paths.lock_file.open("a+")
    if fcntl is None:
        raise RuntimeError("Linux fcntl is required for the production single-instance lock")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("another Amazon Ads Codex cycle is already running")
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def owner_store() -> OwnerOverrideStore:
    paths = RuntimePaths.resolve(ROOT)
    return OwnerOverrideStore(paths.owner_db, Sealer.from_path(paths.signing_key).key)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=["hourly", "daily", "weekly", "direct"])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--instruction", help="Natural-language Owner command. Required for kind=direct and accepted only while Owner Direct Override is armed in the authenticated Control Plane.")
    a = p.parse_args()
    try:
        with single_instance():
            owner = owner_store()
            if a.kind == "direct":
                if not str(a.instruction or "").strip():
                    raise ValueError("direct cycle requires --instruction")
                command = owner.begin_direct_command(str(a.instruction)); generation = int(command["generation"])
                try:
                    result = OwnerOverrideOptimizationController(ROOT).run("direct", a.dry_run)
                finally:
                    owner.finish_direct_command(generation)
            else:
                if a.instruction:
                    raise ValueError("--instruction is only valid for kind=direct")
                window = owner.direct_override_state()
                if window["armed"] and window["return_mode"] != "autopilot":
                    result = {"status": "paused", "reason": "Owner Direct Override is armed from a non-autopilot mode; scheduled autonomous cycles are suppressed while the direct-command window is open", "direct_override": window}
                else:
                    result = OwnerOverrideOptimizationController(ROOT).run(a.kind, a.dry_run)
    except Exception as exc:
        result = {"status": "exception", "error_type": type(exc).__name__, "error": str(exc)}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"completed", "dry_run", "observed", "paused"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
