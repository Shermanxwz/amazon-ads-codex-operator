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
from ads_autopilot.optimization_controller import OptimizationController
from ads_autopilot.paths import RuntimePaths


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
        try: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally: handle.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=["hourly", "daily", "weekly"])
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    try:
        with single_instance():
            result = OptimizationController(ROOT).run(a.kind, a.dry_run)
    except Exception as exc:
        result = {"status": "exception", "error_type": type(exc).__name__, "error": str(exc)}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"completed", "dry_run", "observed", "paused"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
