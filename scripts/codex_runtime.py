#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
if ROOT.name != "scripts":
    ROOT = Path.cwd()
else:
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

from ads_autopilot.codex_compat import (
    CodexRuntimeError,
    probe_codex,
    promote_candidate,
    register_candidate,
    resolve_active_binary,
    rollback_runtime,
    runtime_status,
)
from ads_autopilot.paths import RuntimePaths

CONTRACT = ROOT / "config/codex-compatibility.json"


def emit(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Owner-pinned Codex Evergreen runtime manager")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    probe = sub.add_parser("probe")
    probe.add_argument("--binary")
    candidate = sub.add_parser("candidate")
    candidate.add_argument("--binary", required=True)
    promote = sub.add_parser("promote")
    promote.add_argument("runtime_id")
    sub.add_parser("rollback")
    adopt = sub.add_parser("adopt-current")
    adopt.add_argument("--binary")
    ns = parser.parse_args()
    paths = RuntimePaths.resolve(ROOT)
    paths.ensure_directories()
    try:
        if ns.command == "status":
            emit(runtime_status(paths))
            return 0
        if ns.command == "probe":
            binary = ns.binary or resolve_active_binary(paths)
            report = probe_codex(binary, CONTRACT)
            emit(report)
            return 0 if report.get("compatible") else 2
        if ns.command == "candidate":
            record = register_candidate(paths, ns.binary, CONTRACT)
            emit(record)
            return 0 if record.get("compatible") else 2
        if ns.command == "promote":
            emit(promote_candidate(paths, ns.runtime_id, CONTRACT))
            return 0
        if ns.command == "rollback":
            emit(rollback_runtime(paths, CONTRACT))
            return 0
        if ns.command == "adopt-current":
            binary = ns.binary or shutil.which("codex")
            if not binary:
                raise CodexRuntimeError("Codex CLI not found on PATH")
            record = register_candidate(paths, binary, CONTRACT)
            if not record.get("compatible"):
                emit(record)
                return 2
            emit(promote_candidate(paths, record["id"], CONTRACT))
            return 0
        raise CodexRuntimeError("unknown command")
    except CodexRuntimeError as exc:
        emit({"ok": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
