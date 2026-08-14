#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import sys
import time

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
    # Direct/manual invocations have a short bounded wait. Production systemd
    # explicitly sets 7200 seconds so timer collisions serialize instead of
    # silently losing a daily/weekly run.
    wait_seconds = max(1.0, float(os.environ.get("ADS_CYCLE_LOCK_WAIT_SECONDS", "5")))
    deadline = time.monotonic() + wait_seconds
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "another Amazon Ads Codex cycle is already running; "
                        f"timed out after {wait_seconds:g}s waiting for the serialized execution slot"
                    )
                time.sleep(min(1.0, max(0.05, deadline - time.monotonic())))
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def owner_store() -> OwnerOverrideStore:
    paths = RuntimePaths.resolve(ROOT)
    return OwnerOverrideStore(paths.owner_db, Sealer.from_path(paths.signing_key).key)


def _scheduled_enabled(owner: OwnerOverrideStore, kind: str) -> tuple[bool, str]:
    key = {
        "hourly": "hourly_pacing",
        "daily": "daily_optimization",
        "weekly": "weekly_strategy",
    }.get(kind)
    if not key:
        return True, ""
    scheduling = owner.snapshot()["operator"].get("scheduling", {})
    value = scheduling.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"operator scheduling.{key} must be boolean")
    return value, key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["hourly", "daily", "weekly", "direct"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--instruction",
        help="Natural-language Owner command. Required for kind=direct and accepted only while Owner Direct Override is armed in the authenticated Control Plane.",
    )
    args = parser.parse_args()
    try:
        with single_instance():
            owner = owner_store()
            if args.kind == "direct":
                if not str(args.instruction or "").strip():
                    raise ValueError("direct cycle requires --instruction")
                command = owner.begin_direct_command(str(args.instruction))
                generation = int(command["generation"])
                try:
                    result = OwnerOverrideOptimizationController(ROOT).run(
                        "direct", args.dry_run
                    )
                finally:
                    owner.finish_direct_command(generation)
            else:
                if args.instruction:
                    raise ValueError("--instruction is only valid for kind=direct")
                enabled, key = _scheduled_enabled(owner, args.kind)
                if not enabled:
                    result = {
                        "status": "paused",
                        "reason": f"scheduled {args.kind} cycle disabled by Owner operator.scheduling.{key}",
                    }
                else:
                    window = owner.direct_override_state()
                    if window["armed"] and window["return_mode"] != "autopilot":
                        result = {
                            "status": "paused",
                            "reason": "Owner Direct Override is armed from a non-autopilot mode; scheduled autonomous cycles are suppressed while the direct-command window is open",
                            "direct_override": window,
                        }
                    else:
                        result = OwnerOverrideOptimizationController(ROOT).run(
                            args.kind, args.dry_run
                        )
    except Exception as exc:
        result = {
            "status": "exception",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"completed", "dry_run", "observed", "paused"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
