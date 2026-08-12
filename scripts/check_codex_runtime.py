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

from ads_autopilot.codex_compat import probe_codex, resolve_active_binary
from ads_autopilot.paths import RuntimePaths


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a Codex CLI against the archive-certified capability contract")
    parser.add_argument("--binary", help="Codex binary to probe; defaults to Owner ACTIVE runtime, then PATH")
    parser.add_argument("--json", action="store_true", help="Emit one machine-readable JSON report")
    ns = parser.parse_args()
    paths = RuntimePaths.resolve(ROOT)
    binary = ns.binary or resolve_active_binary(paths)
    if binary == "codex" and not shutil.which("codex"):
        report = {"compatible": False, "binary": "codex", "checks": [{"name": "binary-executable", "ok": False, "required": True, "detail": "Codex CLI not found"}]}
    else:
        report = probe_codex(binary, ROOT / "config/codex-compatibility.json")
    if ns.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"Codex runtime: {report.get('version_text') or 'unknown'}")
        print(f"Binary:        {report.get('binary') or binary}")
        print(f"SHA-256:       {report.get('binary_sha256') or 'unknown'}")
        for item in report.get("checks", []):
            print(("[OK]   " if item.get("ok") else "[FAIL] ") + str(item.get("name")) + " — " + str(item.get("detail") or ""))
        passed = sum(bool(item.get("ok")) for item in report.get("checks", []))
        print(f"\n{passed}/{len(report.get('checks', []))} Codex runtime compatibility checks passed")
    return 0 if report.get("compatible") else 2


if __name__ == "__main__":
    raise SystemExit(main())
