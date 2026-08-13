#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ads_autopilot.codex_compat import (
    active_identity,
    promote_candidate,
    register_candidate,
    rollback_runtime,
)
from ads_autopilot.owner_store import OwnerStore
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.sealing import Sealer
from ads_autopilot.state import Store

UTC = timezone.utc


class AcceptanceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    if not spec or not spec.loader:
        raise AcceptanceError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_fake_codex(path: Path, version: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fixture = ROOT / "tests/fixtures/virtual_codex.py"
    text = fixture.read_text().replace("__VIRTUAL_CODEX_VERSION__", version)
    path.write_text(text)
    path.chmod(0o755)
    return path


def command(env: dict[str, str], *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=timeout,
    )


def parsed_cycle(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    require(proc.stdout.strip().startswith("{"), f"cycle did not return JSON: {proc.stdout[-1000:]}")
    return json.loads(proc.stdout)


def bootstrap_host(base: Path, name: str, *, version: str = "1.0") -> tuple[RuntimePaths, dict[str, str], Path]:
    owner_home = base / name
    fake = write_fake_codex(base / f"{name}-bin" / "codex", version)
    env = os.environ.copy()
    env["ADS_OWNER_HOME"] = str(owner_home)
    env["ADS_CONTROL_PASSWORD"] = "VirtualAcceptancePass-2026!"
    env["PATH"] = str(fake.parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = str(ROOT / "src")
    boot = command(env, str(ROOT / "scripts/bootstrap.py"))
    require(boot.returncode == 0, f"bootstrap failed: {boot.stdout}")
    paths = RuntimePaths.resolve(ROOT, owner_home)
    sealer = Sealer.from_path(paths.signing_key)
    owner = OwnerStore(paths.owner_db, sealer.key)
    owner.update_policy({"money.owner_daily_spend_ceiling": 100.0}, actor="virtual-acceptance")
    owner.update_operator(
        {
            "advertiser_account_id": "VIRTUAL-ADVERTISER",
            "profile_ids": ["VIRTUAL-PROFILE"],
            "scope.managed_asins": ["B000VIRTUAL"],
            "timezone": "UTC",
        },
        actor="virtual-acceptance",
    )
    (paths.codex_home / "virtual-amazon-state.json").write_text(json.dumps({"bid": 1.0}))
    (paths.codex_home / "virtual-control.json").write_text(json.dumps({"mode": "normal"}))
    return paths, env, fake


def owner_for(paths: RuntimePaths) -> OwnerStore:
    return OwnerStore(paths.owner_db, Sealer.from_path(paths.signing_key).key)


def run_acceptance(report_path: Path | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {"version": 1, "started_at": datetime.now(UTC).isoformat(), "checks": []}
    with tempfile.TemporaryDirectory(prefix="amazon-ads-virtual-acceptance-") as temp:
        base = Path(temp)

        # 1. Fresh host bootstrap + capability-pinned ACTIVE runtime + preflight.
        paths, env, fake_v1 = bootstrap_host(base, "happy")
        active = active_identity(paths)
        require(bool(active and active.get("integrity_ok")), "bootstrap did not create an intact ACTIVE Codex runtime")
        pre = command(env, str(ROOT / "scripts/preflight.py"))
        require(pre.returncode == 0, f"preflight failed: {pre.stdout}")
        report["checks"].append("fresh-bootstrap-preflight")

        # 2. Observe cycle must plan/seal without touching external state.
        observe = parsed_cycle(command(env, str(ROOT / "scripts/run_cycle.py"), "daily"))
        require(observe["status"] == "observed", f"observe cycle status={observe}")
        require(json.loads((paths.codex_home / "virtual-amazon-state.json").read_text())["bid"] == 1.0, "Observe mutated virtual Amazon state")
        report["checks"].append("observe-no-write")

        # 3. Full live path: planner -> policy -> prewrite -> grant -> real frozen hook -> mutation -> verifier.
        owner = owner_for(paths)
        owner.set_mode("autopilot", actor="virtual-acceptance")
        live = parsed_cycle(command(env, str(ROOT / "scripts/run_cycle.py"), "daily"))
        require(live["status"] == "completed" and live.get("verified_actions") == 1, f"live cycle failed: {live}")
        require(abs(float(json.loads((paths.codex_home / "virtual-amazon-state.json").read_text())["bid"]) - 1.1) < 1e-9, "live mutation not applied exactly once")
        actions = Store(paths.runtime_db).list_actions(10)
        require(any(row["status"] == "verified" for row in actions), "no verified action persisted")
        require(not list(paths.grant_root.glob("*.json")) and not list(paths.grant_root.glob("*.consumed")), "verified grant evidence was not cleaned")
        runtime_logs = list(paths.run_root.rglob("*.runtime.json"))
        require(runtime_logs and all(json.loads(p.read_text())["selection"] == "owner-pinned-active" for p in runtime_logs), "runtime evidence did not bind Owner ACTIVE Codex")
        report["checks"].append("sealed-live-happy-path")

        # 4. Evergreen candidate promotion and exact rollback target.
        fake_v2 = write_fake_codex(base / "happy-v2-bin" / "codex", "2.0")
        contract = ROOT / "config/codex-compatibility.json"
        candidate = register_candidate(paths, fake_v2, contract)
        require(candidate.get("compatible") is True, "v2 compatible candidate rejected")
        promote_candidate(paths, str(candidate["id"]), contract)
        require(active_identity(paths)["version_text"] == "codex-cli 2.0", "candidate promotion did not become ACTIVE")
        restored = rollback_runtime(paths, contract)
        require(restored["version_text"] == "codex-cli 1.0", "rollback did not restore previous ACTIVE")
        report["checks"].append("evergreen-promote-rollback")

        # 5. Disaster recovery must preserve DB/audit plus ACTIVE/PREVIOUS runtime identity and clear stale auth/grants.
        backup_mod = load_script("backup_owner.py")
        restore_mod = load_script("restore_owner.py")
        backup = backup_mod.create_backup(paths, base / "backups")
        restored_home = base / "restored-owner"
        (restored_home / "codex-home").mkdir(parents=True, exist_ok=True)
        (restored_home / "codex-home/auth.json").write_text("stale-oauth")
        (restored_home / "grants").mkdir(parents=True, exist_ok=True)
        (restored_home / "grants/stale.json").write_text("stale-grant")
        restored_paths = RuntimePaths.resolve(ROOT, restored_home)
        restore_mod.restore_backup(backup, restored_paths)
        require(not (restored_home / "codex-home/auth.json").exists(), "restore retained stale OAuth/auth state")
        require(not (restored_home / "grants/stale.json").exists(), "restore retained stale grant state")
        restored_owner = owner_for(restored_paths)
        require(restored_owner.verify_audit_chain().get("ok") is True, "restored Owner audit chain invalid")
        require(restored_owner.snapshot()["mode"] == "observe", "restored host did not return to Observe")
        restored_active = active_identity(restored_paths)
        require(bool(restored_active and restored_active.get("integrity_ok")), "restored ACTIVE Codex runtime missing")
        require(restored_active["version_text"] == "codex-cli 1.0", "restored ACTIVE runtime identity changed")
        report["checks"].append("backup-restore-active-runtime")

        # 6. Transport crash after the Amazon write: fresh state proves intent, no replay, action becomes verified.
        crash_paths, crash_env, _ = bootstrap_host(base, "after-write")
        crash_owner = owner_for(crash_paths)
        crash_owner.set_mode("autopilot", actor="virtual-acceptance")
        (crash_paths.codex_home / "virtual-control.json").write_text(json.dumps({"mode":"crash_after_write"}))
        recovered = parsed_cycle(command(crash_env, str(ROOT / "scripts/run_cycle.py"), "daily"))
        require(recovered["status"] == "completed" and recovered.get("verified_actions") == 1, f"after-write recovery failed: {recovered}")
        require(abs(float(json.loads((crash_paths.codex_home / "virtual-amazon-state.json").read_text())["bid"]) - 1.1) < 1e-9, "after-write state was not retained")
        report["checks"].append("ambiguous-after-write-reconciled")

        # 7. Crash after grant consumption but before write: never replay, retain ambiguity evidence, auto-pause, restart reconciles fail-closed.
        amb_paths, amb_env, _ = bootstrap_host(base, "after-consume")
        amb_owner = owner_for(amb_paths)
        amb_owner.set_mode("autopilot", actor="virtual-acceptance")
        (amb_paths.codex_home / "virtual-control.json").write_text(json.dumps({"mode":"crash_after_consume_before_write"}))
        ambiguous = parsed_cycle(command(amb_env, str(ROOT / "scripts/run_cycle.py"), "daily"))
        require(ambiguous["status"] == "exception", f"consume-before-write did not fail closed: {ambiguous}")
        require(owner_for(amb_paths).snapshot()["mode"] == "paused", "ambiguous write did not auto-pause")
        require(float(json.loads((amb_paths.codex_home / "virtual-amazon-state.json").read_text())["bid"]) == 1.0, "ambiguous path mutated external state")
        require(bool(list(amb_paths.grant_root.glob("*.consumed"))), "ambiguous path lost consumed evidence")
        restart = parsed_cycle(command(amb_env, str(ROOT / "scripts/run_cycle.py"), "daily"))
        require(restart["status"] == "paused", f"restart did not remain fail-closed: {restart}")
        require(any(row["status"] == "recovery_uncertain" for row in Store(amb_paths.runtime_db).list_actions(10)), "restart reconciliation did not persist recovery_uncertain")
        report["checks"].append("consume-before-write-never-replayed")

        # 8. Final-boundary Emergency Stop and process lock while an Executor is waiting to call the hook.
        stop_paths, stop_env, _ = bootstrap_host(base, "emergency")
        stop_owner = owner_for(stop_paths)
        stop_owner.set_mode("autopilot", actor="virtual-acceptance")
        (stop_paths.codex_home / "virtual-control.json").write_text(json.dumps({"mode":"pause_before_hook"}))
        first = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts/run_cycle.py"), "daily"], cwd=ROOT, env=stop_env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        ready = stop_paths.codex_home / "virtual-executor-ready"
        deadline = time.time() + 20
        while not ready.exists() and time.time() < deadline:
            time.sleep(0.05)
        require(ready.exists(), "executor never reached final hook boundary")
        second = command(stop_env, str(ROOT / "scripts/run_cycle.py"), "hourly", "--dry-run", timeout=10)
        require(second.returncode == 3 and "another Amazon Ads Codex cycle is already running" in second.stdout, "single-instance lock did not reject overlapping cycle")
        stop_owner.emergency_stop(actor="virtual-acceptance")
        (stop_paths.codex_home / "virtual-continue").write_text("continue")
        stdout, _ = first.communicate(timeout=30)
        require(first.returncode == 3, f"emergency-boundary cycle unexpectedly succeeded: {stdout}")
        stopped = json.loads(stdout)
        require(stopped["status"] == "exception", f"emergency result not fail-closed: {stopped}")
        require(float(json.loads((stop_paths.codex_home / "virtual-amazon-state.json").read_text())["bid"]) == 1.0, "Emergency Stop allowed a not-yet-submitted mutation")
        require(not list(stop_paths.grant_root.glob("*.consumed")), "denied emergency action consumed the grant")
        report["checks"].append("emergency-final-boundary-and-flock")

        report["owner_homes_exercised"] = 4
        report["checks_passed"] = len(report["checks"])
        report["finished_at"] = datetime.now(UTC).isoformat()
        report["status"] = "passed"

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Credential-free full-stack virtual production acceptance")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = run_acceptance(args.report)
    except Exception as exc:
        failure = {"status":"failed","error_type":type(exc).__name__,"error":str(exc)}
        if args.report:
            args.report.write_text(json.dumps(failure, indent=2, sort_keys=True))
        print(json.dumps(failure, indent=2, sort_keys=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
