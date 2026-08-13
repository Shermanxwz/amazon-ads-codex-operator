#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPCookieProcessor, Request

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
PASSWORD = "VirtualAcceptancePass-2026!"


class SurfaceAcceptanceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SurfaceAcceptanceError(message)


def load_virtual_acceptance():
    path = ROOT / "scripts/virtual_acceptance.py"
    spec = importlib.util.spec_from_file_location("virtual_acceptance_base", path)
    if not spec or not spec.loader:
        raise SurfaceAcceptanceError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def json_call(opener, base: str, path: str, method: str = "GET", body: dict[str, Any] | None = None, csrf: str | None = None) -> dict[str, Any]:
    headers: dict[str, str] = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if csrf:
        headers["X-CSRF-Token"] = csrf
    with opener.open(Request(base + path, data=data, headers=headers, method=method), timeout=5) as response:
        value = json.loads(response.read())
    require(isinstance(value, dict), f"non-object JSON response from {path}")
    return value


def expect_http(opener, base: str, path: str, code: int, method: str = "GET", body: dict[str, Any] | None = None) -> None:
    try:
        json_call(opener, base, path, method, body)
    except HTTPError as exc:
        require(exc.code == code, f"{path} returned HTTP {exc.code}, expected {code}")
        return
    raise SurfaceAcceptanceError(f"{path} unexpectedly succeeded; expected HTTP {code}")


def wait_ready(opener, base: str, process: subprocess.Popen[str]) -> None:
    deadline = time.time() + 15
    last = ""
    while time.time() < deadline:
        if process.poll() is not None:
            stdout = process.stdout.read() if process.stdout else ""
            raise SurfaceAcceptanceError(f"Owner Web exited before readiness: {stdout[-2000:]}")
        try:
            ready = json_call(opener, base, "/health/ready")
            if ready.get("ok") is True:
                return
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
            last = str(exc)
        time.sleep(0.05)
    raise SurfaceAcceptanceError(f"Owner Web readiness timeout: {last}")


def run_owner_web(paths, env: dict[str, str]) -> None:
    port = free_port()
    web_env = dict(env)
    web_env["ADS_WEB_HOST"] = "127.0.0.1"
    web_env["ADS_WEB_PORT"] = str(port)
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts/run_web.py")],
        cwd=ROOT,
        env=web_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    try:
        wait_ready(opener, base, process)
        with opener.open(base + "/", timeout=5) as response:
            html = response.read()
            require(response.status == 200 and len(html) > 100, "Owner Web static entrypoint failed")
            require(str(response.headers.get("X-Frame-Options") or "") == "DENY", "Owner Web security headers missing")

        expect_http(opener, base, "/api/dashboard", 401)
        login = json_call(opener, base, "/api/login", "POST", {"password": PASSWORD})
        csrf = str(login.get("csrf") or "")
        require(login.get("ok") is True and len(csrf) >= 20, "Owner Web login/CSRF issuance failed")

        dashboard = json_call(opener, base, "/api/dashboard")
        owner_view = dashboard.get("owner") or {}
        require(owner_view.get("mode") == "observe", "Owner Web did not expose Observe state")
        baseline_revision = int(owner_view.get("policy_revision") or 0)
        require(baseline_revision > 0, "Owner Web did not expose a baseline policy revision")
        expect_http(opener, base, "/api/policy", 403, "PUT", {"patch": {"money.owner_daily_spend_ceiling": 125.0}})

        changed = json_call(opener, base, "/api/policy", "PUT", {"patch": {"money.owner_daily_spend_ceiling": 125.0}}, csrf)
        require(abs(float((changed.get("policy") or {}).get("money", {}).get("owner_daily_spend_ceiling", 0)) - 125.0) < 1e-9, "Owner Web policy update did not persist")
        revisions = json_call(opener, base, "/api/revisions?kind=policy&limit=20").get("revisions") or []
        require(any(int(row.get("revision") or 0) == baseline_revision for row in revisions), "Owner Web baseline policy revision disappeared")
        restored = json_call(opener, base, "/api/revisions/restore", "POST", {"kind": "policy", "revision": baseline_revision}, csrf)
        require(restored.get("mode") == "observe", "Owner Web revision restore did not return to Observe")

        mode = json_call(opener, base, "/api/mode", "PUT", {"mode": "autopilot"}, csrf)
        require(mode.get("mode") == "autopilot", "Owner Web could not enter Autopilot after readiness")
        stopped = json_call(opener, base, "/api/emergency-stop", "POST", {}, csrf)
        require(stopped.get("emergency_stop") is True and stopped.get("mode") == "paused", "Owner Web Emergency Stop failed")
        ready = json_call(opener, base, "/health/ready")
        require(ready.get("ok") is True, "Owner Web readiness failed after audited mutations")
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def run_systemd_render(paths, env: dict[str, str], base: Path) -> None:
    render_home = base / "systemd-render-home"
    render_home.mkdir(parents=True, exist_ok=True)
    render_env = dict(env)
    render_env["HOME"] = str(render_home)
    render_env["ADS_OWNER_HOME"] = str(paths.owner_home)
    render_env["ADS_SYSTEMD_RENDER_ONLY"] = "1"
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts/install_systemd.sh")],
        cwd=ROOT,
        env=render_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=30,
    )
    require(proc.returncode == 0, f"systemd production installer render failed: {proc.stdout}")
    require("Rendered systemd user units only" in proc.stdout, "systemd render-only guard was not exercised")
    unit_dir = render_home / ".config/systemd/user"
    names = (
        "amazon-ads-codex@.service",
        "amazon-ads-owner-web.service",
        "amazon-ads-codex-hourly.timer",
        "amazon-ads-codex-daily.timer",
        "amazon-ads-codex-weekly.timer",
    )
    units = [unit_dir / name for name in names]
    require(all(path.is_file() for path in units), "systemd installer did not render all production units")
    combined = "\n".join(path.read_text() for path in units)
    require(not any(token in combined for token in ("@ROOT@", "@OWNER_HOME@", "@TIMEZONE@", "@DAILY_HOUR@", "@WEEKLY_DAY@", "@WEEKLY_HOUR@")), "systemd installer left template placeholders")
    require(str(ROOT) in combined and str(paths.owner_home) in combined, "systemd installer rendered wrong project/Owner paths")
    if shutil.which("systemd-analyze"):
        verify = subprocess.run(
            ["systemd-analyze", "verify", *[str(path) for path in units]],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=30,
        )
        require(verify.returncode == 0, f"rendered production systemd units failed verify: {verify.stdout}")


def run_acceptance(report_path: Path | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {"version": 1, "started_at": datetime.now(UTC).isoformat(), "checks": []}
    virtual = load_virtual_acceptance()
    with tempfile.TemporaryDirectory(prefix="amazon-ads-surface-acceptance-") as temp:
        base = Path(temp)
        paths, env, _ = virtual.bootstrap_host(base, "surface")
        run_owner_web(paths, env)
        report["checks"].append("owner-web-production-entrypoint")
        run_systemd_render(paths, env, base)
        report["checks"].append("systemd-render-install")
        report["owner_homes_exercised"] = 1
        report["checks_passed"] = len(report["checks"])
        report["finished_at"] = datetime.now(UTC).isoformat()
        report["status"] = "passed"
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Credential-free Owner Web + systemd production-surface acceptance")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = run_acceptance(args.report)
    except Exception as exc:
        failure = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}
        if args.report:
            args.report.write_text(json.dumps(failure, indent=2, sort_keys=True))
        print(json.dumps(failure, indent=2, sort_keys=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
