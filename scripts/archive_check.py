#!/usr/bin/env python3
from __future__ import annotations

import compileall
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks: list[tuple[bool, str]] = []


def add(ok: bool, msg: str) -> None:
    checks.append((bool(ok), msg))
    print(("[OK]   " if ok else "[FAIL] ") + msg)


def source_files():
    allowed = {".py", ".md", ".json", ".toml", ".sh", ".html", ".js", ".css", ".txt"}
    skip = {".git", ".pytest_cache", "__pycache__", ".venv", "vendor"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in path.parts for part in skip):
            continue
        if path.suffix not in allowed:
            continue
        yield path


def parse_json(path: Path) -> bool:
    try:
        json.loads(path.read_text())
        return True
    except Exception:
        return False


def main() -> int:
    add(
        compileall.compile_dir(ROOT / "src", quiet=1)
        and compileall.compile_dir(ROOT / "scripts", quiet=1),
        "Python source compiles",
    )

    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(tests.stdout.rstrip())
    add(tests.returncode == 0, "Test suite passes")

    json_files = [
        ROOT / "config/autonomy-policy.json",
        ROOT / "config/operator.example.json",
        ROOT / "config/codex-compatibility.json",
        ROOT / "vendor/amazon-postman/CERTIFIED_UPSTREAM.json",
        *sorted((ROOT / "schemas").glob("*.json")),
    ]
    for path in json_files:
        add(parse_json(path), f"JSON parses: {path.relative_to(ROOT)}")

    for name in ("index.html", "app.js", "style.css"):
        add(
            (ROOT / "src/ads_autopilot/static" / name).exists(),
            f"Owner Web asset present: {name}",
        )

    add(
        'version = "0.4.0"' in (ROOT / "pyproject.toml").read_text(),
        "Package version is v0.4.0",
    )
    add(
        '__version__ = "0.4.0"'
        in (ROOT / "src/ads_autopilot/__init__.py").read_text(),
        "Runtime package version is v0.4.0",
    )

    cfg = (ROOT / ".codex/config.toml").read_text()
    add(
        'default_tools_approval_mode = "writes"' in cfg,
        "Project MCP config is write-gated by default",
    )

    runner = (ROOT / "src/ads_autopilot/codex_runner.py").read_text()
    controller = (ROOT / "src/ads_autopilot/controller.py").read_text()
    add(
        "--sandbox" in runner and '"read-only"' in runner,
        "Codex shell sandbox is read-only",
    )
    add('"--json"' in runner, "Codex JSONL event-stream forensic logging enabled")
    add(
        "enabled_tools" in runner and "allowed_mcp_tools" in runner,
        "Atomic Executor constrains MCP enabled_tools",
    )
    add(
        '"--strict-config"' in runner
        and '"--dangerously-bypass-hook-trust"' in runner
        and '"--ephemeral"' in runner,
        "Codex exec uses strict automation/runtime contract flags",
    )

    add(
        '"version": 2' in controller
        and '_write_executor_grant' in controller
        and 'f"{action_hash}.json"' in controller,
        "Controller mints deterministic one-use v2 grants",
    )
    add(
        "_recover_incomplete_actions" in controller
        and "recovery_uncertain" in controller
        and "verified_from_fresh_amazon_state" in controller,
        "Controller has crash/restart reconciliation",
    )
    add(
        "_check_live_state" in controller
        and "stale_prewrite" in controller
        and (ROOT / "prompts/state_check.md").exists(),
        "Controller performs fresh pre-write state validation",
    )

    hook_path = ROOT / "scripts/codex_pretool_hook.py"
    add(hook_path.exists(), "Self-contained frozen production hook source exists")
    hook = hook_path.read_text() if hook_path.exists() else ""
    add(
        "read-only" in hook or "read_only" in hook,
        "Frozen hook retains read-only role mutation guard",
    )
    add(
        "verify_live_owner_authority" in hook
        and "Owner emergency stop is active" in hook
        and "Owner policy revision changed" in hook,
        "Frozen hook re-checks live Owner authority at execution boundary",
    )
    add(
        "O_EXCL" in hook
        and "grant already consumed" in hook
        and ".consumed" in hook,
        "Frozen hook atomically consumes each Executor grant once",
    )
    add(
        "executor may only call amazon_ads MCP" in hook
        and "MCP arguments differ from sealed grant" in hook,
        "Frozen hook fails closed to exact Executor MCP tool + arguments",
    )
    add(
        not (ROOT / "src/ads_autopilot/hook_policy.py").exists(),
        "No duplicate production-hook implementation can drift",
    )

    compatibility = json.loads((ROOT / "config/codex-compatibility.json").read_text())
    required_flags = set(compatibility.get("required_exec_flags") or [])
    add(
        {
            "--strict-config",
            "--dangerously-bypass-hook-trust",
            "--ephemeral",
            "--output-schema",
            "--json",
        }.issubset(required_flags),
        "Codex runtime compatibility contract covers critical automation features",
    )
    add(
        (ROOT / "scripts/check_codex_runtime.py").exists(),
        "Host Codex runtime capability checker exists",
    )

    amazon_cert = json.loads(
        (ROOT / "vendor/amazon-postman/CERTIFIED_UPSTREAM.json").read_text()
    )
    certified_commit = str(amazon_cert.get("commit") or "")
    add(
        bool(re.fullmatch(r"[0-9a-f]{40}", certified_commit)),
        "Amazon contract source is pinned to an immutable commit",
    )
    sync_script = (ROOT / "scripts/sync_amazon_postman.sh").read_text()
    add(
        "CERTIFIED_UPSTREAM.json" in sync_script
        and 'fetch --depth 1 origin "$PIN"' in sync_script,
        "Amazon contract sync consumes the certified commit pin",
    )

    web = (ROOT / "src/ads_autopilot/web_server.py").read_text()
    add(
        "ADS_WEB_HOST" in web and "127.0.0.1" in web,
        "Owner Web binds loopback by default",
    )
    add(
        "X-CSRF-Token" in web and "csrf_failed" in web,
        "Owner Web mutations require CSRF token",
    )
    add(
        "/api/emergency-stop" in web and "/api/revisions/restore" in web,
        "Owner Web exposes emergency stop and revision rollback",
    )

    sh_files = sorted((ROOT / "scripts").glob("*.sh"))
    for shell_file in sh_files:
        result = subprocess.run(
            ["bash", "-n", str(shell_file)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        add(result.returncode == 0, f"Shell syntax valid: {shell_file.name}")

    with tempfile.TemporaryDirectory() as wheel_dir:
        wheel = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                ".",
                "--no-deps",
                "--no-build-isolation",
                "-w",
                wheel_dir,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        wheels = list(Path(wheel_dir).glob("*.whl"))
        wheel_ok = wheel.returncode == 0 and len(wheels) == 1
        add(wheel_ok, "Offline wheel build succeeds with installed build toolchain")
        if wheel_ok:
            with zipfile.ZipFile(wheels[0]) as archive:
                names = set(archive.namelist())
            required = {
                "ads_autopilot/static/index.html",
                "ads_autopilot/static/app.js",
                "ads_autopilot/static/style.css",
            }
            add(required.issubset(names), "Wheel contains Owner Web static assets")

    forbidden_names = {"owner.db", "runtime.db", "operator_signing_key", "auth.json"}
    leaked = [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.name in forbidden_names
        and ".git" not in path.parts
    ]
    add(
        not leaked,
        "No runtime Owner/auth files in repository tree"
        + (f": {leaked}" if leaked else ""),
    )

    patterns = [
        (
            "Amazon OAuth client id",
            re.compile(r"amzn1\.application-oa2-client\.[A-Za-z0-9._-]{12,}"),
        ),
        ("Bearer token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{24,}")),
        (
            "PEM private key",
            re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        ),
        ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ]
    text = "\n".join(path.read_text(errors="ignore") for path in source_files())
    for label, pattern in patterns:
        add(not pattern.search(text), f"No {label} pattern in source")

    if shutil.which("systemd-analyze"):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            rendered_units: list[str] = []
            for source in sorted((ROOT / "systemd").glob("*")):
                if not source.is_file():
                    continue
                rendered = (
                    source.read_text()
                    .replace("@ROOT@", "/opt/amazon-ads-codex-operator")
                    .replace("@OWNER_HOME@", "/var/lib/amazon-ads-codex-owner")
                    .replace("@DAILY_HOUR@", "04")
                    .replace("@WEEKLY_DAY@", "Sun")
                    .replace("@WEEKLY_HOUR@", "05")
                    .replace("@TIMEZONE@", "UTC")
                )
                destination = temp / source.name
                destination.write_text(rendered)
                rendered_units.append(str(destination))
                if source.suffix == ".timer":
                    calendar = next(
                        (
                            line.split("=", 1)[1].strip()
                            for line in rendered.splitlines()
                            if line.startswith("OnCalendar=")
                        ),
                        None,
                    )
                    result = (
                        subprocess.run(
                            ["systemd-analyze", "calendar", calendar],
                            text=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            check=False,
                        )
                        if calendar
                        else None
                    )
                    add(
                        bool(result and result.returncode == 0),
                        f"Valid systemd calendar: {source.name}",
                    )
            verify = subprocess.run(
                ["systemd-analyze", "verify", *rendered_units],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            add(
                verify.returncode == 0,
                "Rendered systemd service/timer units verify cleanly",
            )
    else:
        print("[WARN] systemd-analyze unavailable; systemd validation skipped")

    passed = sum(ok for ok, _ in checks)
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if all(ok for ok, _ in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
