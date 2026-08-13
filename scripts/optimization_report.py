#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ads_autopilot.optimization_controller import OptimizationController


def main() -> int:
    p = argparse.ArgumentParser(description="Print the persistent Sponsored Products optimization/learning report")
    p.add_argument("--owner-home")
    args = p.parse_args()
    controller = OptimizationController(ROOT, args.owner_home)
    report = controller.optimization.report(controller.owner.snapshot())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
