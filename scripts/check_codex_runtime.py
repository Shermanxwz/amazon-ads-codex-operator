#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/codex-compatibility.json"


def main() -> int:
    checks: list[tuple[bool, str]] = []

    def add(ok: bool, message: str) -> None:
        checks.append((bool(ok), message))
        print(("[OK]   " if ok else "[FAIL] ") + message)

    try:
        contract = json.loads(CONTRACT.read_text())
    except Exception as exc:
        print(f"[FAIL] compatibility contract cannot be parsed: {exc}")
        return 2

    codex = shutil.which("codex")
    add(codex is not None, "Codex CLI installed")
    if not codex:
        return 2

    version = subprocess.run(
        [codex, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    version_text = (version.stdout or "").strip()
    add(version.returncode == 0 and bool(version_text), f"Codex version: {version_text or 'unknown'}")

    help_run = subprocess.run(
        [codex, "exec", "--help"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    help_text = help_run.stdout or ""
    add(help_run.returncode == 0, "codex exec --help succeeds")
    for flag in contract.get("required_exec_flags", []):
        add(str(flag) in help_text, f"Codex exec capability present: {flag}")

    codex_home_raw = os.environ.get("CODEX_HOME")
    if codex_home_raw:
        codex_home = Path(codex_home_raw).expanduser().resolve()
        for name in contract.get("required_runtime_files", []):
            add((codex_home / str(name)).exists(), f"CODEX_HOME runtime file exists: {name}")
        config_path = codex_home / "config.toml"
        config_text = config_path.read_text() if config_path.exists() else ""
        for fragment in contract.get("required_config_fragments", []):
            add(str(fragment) in config_text, f"CODEX_HOME config contract: {fragment}")
    else:
        print("[INFO] CODEX_HOME is not set; CLI capability check only")

    passed = sum(ok for ok, _ in checks)
    print(f"\n{passed}/{len(checks)} Codex runtime compatibility checks passed")
    return 0 if all(ok for ok, _ in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
