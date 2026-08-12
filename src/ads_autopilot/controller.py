from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
from typing import Any

from .canonical import canonical_json, digest
from .codex_runner import run_codex
from .ledger import BudgetLedger
from .models import Action
from .outcome import parse_outcome
from .owner_store import OwnerStore
from .paths import RuntimePaths
from .policy import PolicyEngine, PolicyError
from .sealing import Sealer
from .state import Store

UTC = timezone.utc


class AuthorityChanged(RuntimeError):
    pass


class Controller:
    def __init__(self, root: Path, owner_home: str | Path | None = None):
        self.root = Path(root).resolve()
        self.paths = RuntimePaths.resolve(self.root, owner_home)
        self.paths.ensure_directories()
        self.sealer = Sealer.from_path(self.paths.signing_key)
        self.owner = OwnerStore(self.paths.owner_db, self.sealer.key)
        self.store = Store(os.environ.get("ADS_STATE_DB", self.paths.runtime_db))
        self.timeout = int(os.environ.get("ADS_CODEX_TIMEOUT_SECONDS", "1800"))
        self.model = os.environ.get("ADS_CODEX_MODEL") or None

    def _prompt(self, name: str, payload: dict[str, Any]) -> str:
        return (
            (self.root / f"prompts/{name}").read_text()
            + "\n\nINPUT_JSON:\n"
            + canonical_json(payload)
        )

    def _authority_token(self, snapshot: dict[str, Any]) -> tuple[Any, ...]:
        return (
            snapshot["mode"],
            snapshot["emergency_stop"],
            snapshot["policy_revision"],
            snapshot["policy_hash"],
            snapshot["operator_revision"],
            snapshot["operator_hash"],
        )

    def _assert_authority(
        self, baseline: dict[str, Any], *, require_autopilot: bool
    ) -> dict[str, Any]:
        current = self.owner.snapshot()
        if self._authority_token(current) != self._authority_token(baseline):
            raise AuthorityChanged(
                "owner authority changed during cycle; remaining mutations cancelled"
            )
        if current["emergency_stop"]:
            raise AuthorityChanged("owner emergency stop is active")
        if require_autopilot and current["mode"] != "autopilot":
            raise AuthorityChanged(
                f"owner mode is {current['mode']}, not autopilot"
            )
        return current

    def _validate_scope_alignment(self, snapshot: dict[str, Any]) -> None:
        op = {
            str(x).upper()
            for x in snapshot["operator"].get("scope", {}).get("ad_products", [])
        }
        pol = {
            str(x).upper()
            for x in snapshot["policy"].get("scope", {}).get("allowed_ad_products", [])
        }
        if not op:
            raise RuntimeError("operator scope has no ad products")
        if not op.issubset(pol):
            raise RuntimeError(
                f"operator ad products exceed owner policy scope: {sorted(op-pol)}"
            )
        profiles = [
            x
            for x in snapshot["operator"].get("profile_ids", [])
            if str(x).strip() and str(x) != "REPLACE_ME"
        ]
        if not profiles:
            raise RuntimeError("no real Amazon Ads profile_id configured in Owner Control")

    def run(self, kind: str = "daily", dry_run: bool = False) -> dict[str, Any]:
        snapshot = self.owner.snapshot()

        # Reconcile any action that survived a process/host crash before a new
        # plan is allowed to run. This is read-only against Amazon and does not
        # reduce the model's standing business authority.
        self._recover_incomplete_actions(snapshot)
        snapshot = self.owner.snapshot()

        cycle_id = (
            f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
        )
        run_dir = self.paths.run_root / cycle_id
        run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.store.create_cycle(cycle_id, kind)
        (run_dir / "owner-authority.json").write_text(
            json.dumps(
                {
                    "mode": snapshot["mode"],
                    "emergency_stop": snapshot["emergency_stop"],
                    "policy_revision": snapshot["policy_revision"],
                    "policy_hash": snapshot["policy_hash"],
                    "operator_revision": snapshot["operator_revision"],
                    "operator_hash": snapshot["operator_hash"],
                },
                indent=2,
            )
        )
        try:
            if snapshot["mode"] == "paused" or snapshot["emergency_stop"]:
                summary = {
                    "reason": "owner control paused",
                    "emergency_stop": snapshot["emergency_stop"],
                }
                self.store.finish_cycle(cycle_id, "paused", summary)
                return {"cycle_id": cycle_id, "status": "paused", **summary}
            self._validate_scope_alignment(snapshot)
            return self._run(cycle_id, run_dir, kind, dry_run, snapshot)
        except Exception as exc:
            data = {"error_type": type(exc).__name__, "error": str(exc)}
            (run_dir / "exception.json").write_text(json.dumps(data, indent=2))
            self.store.event("error", "cycle.exception", cycle_id, data)
            self.store.finish_cycle(cycle_id, "exception", data)
            return {"cycle_id": cycle_id, "status": "exception", **data}

    def _run(
        self,
        cycle_id: str,
        run_dir: Path,
        kind: str,
        dry_run: bool,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        policy = PolicyEngine.from_dict(snapshot["policy"])
        operator = snapshot["operator"]
        ledger = BudgetLedger(self.store, policy.data)
        planning_input = {
            "cycle_id": cycle_id,
            "cycle_kind": kind,
            "operator": operator,
            "policy": policy.data,
            "owner_mode": snapshot["mode"],
            "state_summary": self._recent_state(),
        }
        plan = run_codex(
            paths=self.paths,
            role="planner",
            prompt=self._prompt("observe_plan.md", planning_input),
            schema=self.root / "schemas/plan.schema.json",
            output=run_dir / "plan.json",
            timeout=self.timeout,
            model=self.model,
        )
        self._assert_authority(snapshot, require_autopilot=False)
        plan_hash = digest(plan)
        context = dict(plan.get("context") or {})
        context["_owner_profile_ids"] = [
            str(x) for x in operator.get("profile_ids", [])
        ]
        context["_owner_advertiser_account_id"] = str(
            operator.get("advertiser_account_id") or ""
        )
        context["_owner_managed_asins"] = [
            str(x).upper()
            for x in operator.get("scope", {}).get("managed_asins", [])
        ]
        context["_owner_ad_products"] = [
            str(x).upper()
            for x in operator.get("scope", {}).get("ad_products", [])
        ]
        actions = [Action.from_dict(x) for x in plan.get("actions", [])]
        timezone_name = str(operator.get("timezone") or "UTC")
        try:
            decisions = policy.evaluate_plan(
                actions,
                context=context,
                store=self.store,
                timezone_name=timezone_name,
                cycle_id=cycle_id,
            )
        except PolicyError as exc:
            rejected = [{"plan": str(exc)}]
            (run_dir / "policy-rejections.json").write_text(
                json.dumps(rejected, indent=2)
            )
            self.store.finish_cycle(cycle_id, "blocked", {"rejected": rejected})
            return {"cycle_id": cycle_id, "status": "blocked", "rejected": rejected}

        rejected = [
            {"action_id": action.action_id, "reasons": decision.reasons}
            for action, decision in zip(actions, decisions)
            if not decision.allowed
        ]
        if rejected:
            (run_dir / "policy-rejections.json").write_text(
                json.dumps(rejected, indent=2)
            )
            self.store.finish_cycle(cycle_id, "blocked", {"rejected": rejected})
            return {"cycle_id": cycle_id, "status": "blocked", "rejected": rejected}
        if not actions:
            self.store.finish_cycle(
                cycle_id,
                "completed",
                {"planned_actions": 0, "reason": "planner proposed no mutation"},
            )
            return {"cycle_id": cycle_id, "status": "completed", "planned_actions": 0}

        ordered = _topological_actions(actions)
        by_action_id = {
            action.action_id: (action, decision)
            for action, decision in zip(actions, decisions)
        }
        effective_dry_run = dry_run or snapshot["mode"] == "observe"
        sealed: list[dict[str, Any]] = []
        reserved: list[str] = []
        observed_spend = float(context.get("today_spend") or 0)
        try:
            for action in ordered:
                decision = by_action_id[action.action_id][1]
                base = {
                    "cycle_id": cycle_id,
                    "action_id": action.action_id,
                    "action_type": action.action_type,
                    "tool_name": action.tool_name,
                    "ad_product": action.ad_product,
                    "entity_type": action.entity_type,
                    "entity_id": action.entity_id,
                    "arguments": action.arguments,
                    "before": action.before,
                    "after": action.after,
                    "spend_delta": action.spend_delta,
                    "confidence": action.confidence,
                    "evidence_refs": list(action.evidence_refs),
                    "dependencies": list(action.dependencies),
                    "reversible": action.reversible,
                    "rollback": action.rollback,
                    "prewrite_observed_at": action.prewrite_observed_at,
                    "rationale": action.rationale,
                }
                row = self.sealer.seal_action(
                    base,
                    policy_hash=snapshot["policy_hash"],
                    plan_hash=plan_hash,
                    operator_hash=snapshot["operator_hash"],
                    policy_revision=snapshot["policy_revision"],
                    operator_revision=snapshot["operator_revision"],
                )
                if not effective_dry_run and decision.spend_reservation > 0:
                    ledger.reserve(
                        row["action_hash"],
                        decision.spend_reservation,
                        observed_spend,
                    )
                    reserved.append(row["action_hash"])
                self.store.add_action(cycle_id, row)
                if effective_dry_run:
                    self.store.set_action_status(row["action_hash"], "dry_run")
                sealed.append(row)
        except Exception:
            for action_hash in reserved:
                ledger.release(action_hash, "cancelled")
            raise

        bundle = {
            "version": 4,
            "cycle_id": cycle_id,
            "cycle_kind": kind,
            "plan_hash": plan_hash,
            "policy_hash": snapshot["policy_hash"],
            "policy_revision": snapshot["policy_revision"],
            "operator_hash": snapshot["operator_hash"],
            "operator_revision": snapshot["operator_revision"],
            "actions": sealed,
        }
        (run_dir / "sealed-actions.json").write_text(json.dumps(bundle, indent=2))
        self.store.set_plan(cycle_id, plan_hash, snapshot["policy_hash"])
        if effective_dry_run:
            status = (
                "observed"
                if snapshot["mode"] == "observe" and not dry_run
                else "dry_run"
            )
            self.store.finish_cycle(
                cycle_id,
                status,
                {"actions": len(sealed), "owner_mode": snapshot["mode"]},
            )
            return {"cycle_id": cycle_id, "status": status, "actions": len(sealed)}

        sealed_by_id = {row["action_id"]: row for row in sealed}
        action_status: dict[str, str] = {}
        issues: list[dict[str, Any]] = []
        receipts: list[dict[str, Any]] = []
        verifications: list[dict[str, Any]] = []

        for index, action in enumerate(ordered):
            sealed_row = sealed_by_id[action.action_id]
            action_hash = sealed_row["action_hash"]
            try:
                self._assert_authority(snapshot, require_autopilot=True)
            except AuthorityChanged as exc:
                issues.append(
                    {
                        "action_hash": action_hash,
                        "phase": "authority",
                        "reason": str(exc),
                    }
                )
                self._cancel_remaining(
                    ordered[index:],
                    sealed_by_id,
                    ledger,
                    action_status,
                    "authority_changed",
                )
                break

            bad_dependencies = [
                dep for dep in action.dependencies if action_status.get(dep) != "verified"
            ]
            if bad_dependencies:
                self.store.set_action_status(action_hash, "dependency_blocked")
                ledger.release(action_hash, "dependency_blocked")
                action_status[action.action_id] = "dependency_blocked"
                issues.append(
                    {
                        "action_hash": action_hash,
                        "phase": "dependency",
                        "reason": f"dependencies not verified: {bad_dependencies}",
                    }
                )
                continue

            # Final fresh read before an existing entity is changed. This is a
            # stale-state/TOCTOU guard, not an AI policy restriction: if Amazon
            # moved since planning, the next cycle simply replans from reality.
            if not action.action_type.lower().startswith("create_") and sealed_row.get(
                "before"
            ):
                pre_ok, pre_item, pre_diffs = self._check_live_state(
                    cycle_id=cycle_id,
                    run_dir=run_dir,
                    sealed_row=sealed_row,
                    expected_state=dict(sealed_row.get("before") or {}),
                    label=f"prewrite-{index:03d}-{action.action_id}",
                )
                if not pre_ok:
                    self.store.set_action_status(action_hash, "stale_prewrite")
                    ledger.release(action_hash, "stale_prewrite")
                    action_status[action.action_id] = "stale_prewrite"
                    issues.append(
                        {
                            "action_hash": action_hash,
                            "phase": "prewrite",
                            "reason": "fresh Amazon state no longer matches sealed before-state",
                            "differences": pre_diffs,
                            "observed": pre_item.get("observed", {}) if pre_item else {},
                        }
                    )
                    self._cancel_remaining(
                        ordered[index + 1 :],
                        sealed_by_id,
                        ledger,
                        action_status,
                        "prewrite_state_changed",
                    )
                    break

            execution_input = {
                "cycle_id": cycle_id,
                "owner_authority": {
                    "policy_revision": snapshot["policy_revision"],
                    "policy_hash": snapshot["policy_hash"],
                    "operator_revision": snapshot["operator_revision"],
                    "operator_hash": snapshot["operator_hash"],
                },
                "actions": [sealed_row],
            }
            grant_path = self._write_executor_grant(sealed_row)
            self.store.set_action_status(action_hash, "executing")

            try:
                receipt = run_codex(
                    paths=self.paths,
                    role="executor",
                    prompt=self._prompt("execute_sealed.md", execution_input),
                    schema=self.root / "schemas/receipt.schema.json",
                    output=run_dir / f"receipt-{index:03d}-{action.action_id}.json",
                    timeout=self.timeout,
                    model=self.model,
                    grant_path=grant_path,
                    allowed_mcp_tools=[action.tool_name],
                )
            except Exception as exc:
                grant_state = self._grant_state(action_hash)
                if grant_state == "issued":
                    # The one-use PreToolUse boundary was never crossed, so no
                    # Amazon write was authorized. Cancel safely and replan.
                    self.store.set_action_status(action_hash, "cancelled")
                    ledger.release(action_hash, "executor_not_invoked")
                    action_status[action.action_id] = "cancelled"
                    self._cleanup_grant(action_hash)
                    issues.append(
                        {
                            "action_hash": action_hash,
                            "phase": "executor",
                            "reason": f"executor failed before grant consumption: {type(exc).__name__}",
                        }
                    )
                    self._cancel_remaining(
                        ordered[index + 1 :],
                        sealed_by_id,
                        ledger,
                        action_status,
                        "executor_not_invoked",
                    )
                    break

                # The tool boundary was crossed (or evidence is missing), so
                # never replay. Re-read Amazon and accept the intended end state
                # if independently verified; otherwise pause for ambiguity.
                ok, recovered, differences = self._check_live_state(
                    cycle_id=cycle_id,
                    run_dir=run_dir,
                    sealed_row=sealed_row,
                    expected_state=dict(sealed_row.get("after") or {}),
                    label=f"executor-reconcile-{index:03d}-{action.action_id}",
                )
                if ok and recovered is not None:
                    recovered_record = dict(recovered)
                    recovered_record["recovered_after_executor_error"] = True
                    self.store.add_verification(
                        action_hash, "verified", recovered_record
                    )
                    self.store.set_action_status(action_hash, "verified")
                    ledger.mark(action_hash, "verified")
                    action_status[action.action_id] = "verified"
                    verifications.append(recovered_record)
                    issues.append(
                        {
                            "action_hash": action_hash,
                            "phase": "executor_recovered",
                            "reason": f"executor transport failed ({type(exc).__name__}) but fresh Amazon state proves intent applied",
                        }
                    )
                    self._cleanup_grant(action_hash)
                    continue

                self.store.set_action_status(action_hash, "unknown")
                ledger.mark(action_hash, "uncertain")
                action_status[action.action_id] = "unknown"
                issues.append(
                    {
                        "action_hash": action_hash,
                        "phase": "executor_unknown",
                        "reason": f"executor failed after possible grant consumption: {type(exc).__name__}",
                        "differences": differences,
                    }
                )
                if policy.data.get("recovery", {}).get(
                    "pause_on_unknown_write_outcome", True
                ):
                    self.owner.system_pause(
                        f"ambiguous executor outcome at {action_hash}"
                    )
                self._cancel_remaining(
                    ordered[index + 1 :],
                    sealed_by_id,
                    ledger,
                    action_status,
                    "previous_action_unknown",
                )
                # Keep consumed marker for forensic/recovery evidence.
                break

            grant_state = self._grant_state(action_hash)
            item, problem = _one_receipt(
                receipt, cycle_id, action_hash, action.tool_name
            )
            if grant_state != "consumed":
                problem = problem or "executor returned without consuming one-use grant"

            if problem:
                outcome_status, outcome_summary = "unknown", problem
                item = item or {
                    "action_hash": action_hash,
                    "status": "unknown",
                    "tool_name": "",
                    "result": {},
                    "error": problem,
                }
            else:
                outcome = parse_outcome(item)
                outcome_status, outcome_summary = outcome.status, outcome.summary

            receipts.append(item)
            self.store.add_receipt(action_hash, outcome_status, item)
            self.store.set_action_status(action_hash, outcome_status)
            ledger.mark(
                action_hash,
                "executed" if outcome_status == "success" else "uncertain",
            )
            if action.action_type.lower().startswith("create_"):
                entity_id = _extract_entity_id(item.get("result"), action.entity_type)
                if entity_id:
                    self.store.register_managed_entity(
                        action.entity_type,
                        entity_id,
                        action_hash,
                        "pending_verification",
                    )

            try:
                self._assert_authority(snapshot, require_autopilot=True)
            except AuthorityChanged as exc:
                issues.append(
                    {
                        "action_hash": action_hash,
                        "phase": "authority_after_write",
                        "reason": str(exc),
                    }
                )

            verification_input = {
                "cycle_id": cycle_id,
                "sealed_actions": [sealed_row],
                "execution_receipt": {"cycle_id": cycle_id, "results": [item]},
            }
            verification = run_codex(
                paths=self.paths,
                role="verifier",
                prompt=self._prompt("verify.md", verification_input),
                schema=self.root / "schemas/verification.schema.json",
                output=run_dir / f"verification-{index:03d}-{action.action_id}.json",
                timeout=self.timeout,
                model=self.model,
            )
            vitem, vproblem = _one_verification(
                verification, cycle_id, action_hash
            )
            if vproblem:
                vitem = vitem or {
                    "action_hash": action_hash,
                    "status": "unknown",
                    "observed": {},
                    "differences": [vproblem],
                }
            verifications.append(vitem)
            vstatus = str(vitem.get("status") or "unknown")
            self.store.add_verification(action_hash, vstatus, vitem)

            # Fresh independent state is the final source of truth. A transport
            # response may be ambiguous even when Amazon has durably applied the
            # exact intended state; verified state must not be replayed.
            if vstatus == "verified":
                self.store.set_action_status(action_hash, "verified")
                ledger.mark(action_hash, "verified")
                action_status[action.action_id] = "verified"
                if outcome_status != "success":
                    self.store.event(
                        "warning",
                        "action.verified_after_ambiguous_receipt",
                        cycle_id,
                        {
                            "action_hash": action_hash,
                            "outcome": outcome_status,
                            "summary": outcome_summary,
                        },
                    )
                if action.action_type.lower().startswith("create_"):
                    entity_id = _extract_entity_id(
                        vitem.get("observed"), action.entity_type
                    ) or _extract_entity_id(item.get("result"), action.entity_type)
                    if entity_id:
                        self.store.register_managed_entity(
                            action.entity_type,
                            entity_id,
                            action_hash,
                            "verified",
                        )
                self._cleanup_grant(action_hash)
            else:
                self.store.set_action_status(action_hash, "verification_failed")
                ledger.mark(action_hash, "uncertain")
                action_status[action.action_id] = "verification_failed"
                issues.append(
                    {
                        "action_hash": action_hash,
                        "phase": "verification",
                        "outcome": outcome_status,
                        "outcome_summary": outcome_summary,
                        "verification": vstatus,
                        "differences": vitem.get("differences") or [],
                    }
                )
                if policy.data.get("recovery", {}).get(
                    "pause_on_unknown_write_outcome", True
                ):
                    self.owner.system_pause(
                        f"write/verification uncertainty at {action_hash}"
                    )
                self._cleanup_grant(action_hash)
                self._cancel_remaining(
                    ordered[index + 1 :],
                    sealed_by_id,
                    ledger,
                    action_status,
                    "previous_action_not_verified",
                )
                break

        (run_dir / "execution-summary.json").write_text(
            json.dumps(
                {
                    "receipts": receipts,
                    "verifications": verifications,
                    "issues": issues,
                },
                indent=2,
            )
        )
        all_verified = all(
            action_status.get(action.action_id) == "verified" for action in ordered
        )
        if all_verified:
            status = "completed"
        elif issues and all(issue.get("phase") == "prewrite" for issue in issues):
            status = "blocked"
        else:
            status = "exception"
        summary = {
            "planned_actions": len(sealed),
            "verified_actions": sum(
                1 for value in action_status.values() if value == "verified"
            ),
            "issues": issues,
        }
        self.store.finish_cycle(cycle_id, status, summary)
        return {"cycle_id": cycle_id, "status": status, **summary}

    def _write_executor_grant(self, sealed_row: dict[str, Any]) -> Path:
        tool_name = str(sealed_row.get("tool_name") or "").strip()
        if not tool_name or tool_name.startswith("mcp__"):
            raise RuntimeError(
                "sealed action must carry the exact bare Amazon MCP tool_name"
            )
        action_hash = str(sealed_row["action_hash"])
        path = self.paths.grant_root / f"{action_hash}.json"
        consumed = Path(str(path) + ".consumed")
        if path.exists() or consumed.exists():
            raise RuntimeError(
                f"one-use grant evidence already exists for action {action_hash}; recovery required"
            )
        expires = datetime.now(UTC) + timedelta(
            seconds=min(max(self.timeout + 60, 300), 3600)
        )
        grant = {
            "version": 2,
            "action_hash": action_hash,
            "tool_name": tool_name,
            "arguments": sealed_row.get("arguments") or {},
            "policy_revision": int(sealed_row["policy_revision"]),
            "policy_hash": str(sealed_row["policy_hash"]),
            "operator_revision": int(sealed_row["operator_revision"]),
            "operator_hash": str(sealed_row["operator_hash"]),
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
        }
        grant["signature"] = self.sealer.sign(grant)
        with path.open("x") as handle:
            json.dump(grant, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o600)
        _fsync_directory(self.paths.grant_root)
        return path

    def _grant_paths(self, action_hash: str) -> tuple[Path, Path]:
        issued = self.paths.grant_root / f"{action_hash}.json"
        return issued, Path(str(issued) + ".consumed")

    def _grant_state(self, action_hash: str) -> str:
        issued, consumed = self._grant_paths(action_hash)
        if consumed.exists():
            return "consumed"
        if issued.exists():
            return "issued"
        return "missing"

    def _cleanup_grant(self, action_hash: str) -> None:
        for path in self._grant_paths(action_hash):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        _fsync_directory(self.paths.grant_root)

    def _check_live_state(
        self,
        *,
        cycle_id: str,
        run_dir: Path,
        sealed_row: dict[str, Any],
        expected_state: dict[str, Any],
        label: str,
    ) -> tuple[bool, dict[str, Any] | None, list[str]]:
        if not expected_state:
            return False, None, ["expected state is empty"]
        payload = {
            "cycle_id": cycle_id,
            "action_hash": str(sealed_row["action_hash"]),
            "action": sealed_row,
            "expected_state": expected_state,
            "comparison": "expected_state must be an exact subset of fresh observed state",
        }
        try:
            value = run_codex(
                paths=self.paths,
                role="state_verifier",
                prompt=self._prompt("state_check.md", payload),
                schema=self.root / "schemas/verification.schema.json",
                output=run_dir / f"{label}.json",
                timeout=self.timeout,
                model=self.model,
            )
        except Exception as exc:
            return False, None, [f"fresh-state read failed: {type(exc).__name__}: {exc}"]

        item, problem = _one_verification(
            value, cycle_id, str(sealed_row["action_hash"])
        )
        if problem:
            return False, item, [problem]
        assert item is not None
        observed = item.get("observed") or {}
        deterministic = _state_differences(expected_state, observed)
        model_differences = [str(x) for x in (item.get("differences") or [])]
        ok = str(item.get("status") or "") == "verified" and not deterministic
        differences = list(dict.fromkeys(model_differences + deterministic))
        if not ok and not differences:
            differences = [f"state verifier returned {item.get('status') or 'unknown'}"]
        return ok, item, differences

    def _recover_incomplete_actions(self, snapshot: dict[str, Any]) -> None:
        with self.store.connection() as conn:
            rows = conn.execute(
                "SELECT action_hash,status,payload_json FROM actions "
                "WHERE status IN ('released','executing','success','unknown') "
                "ORDER BY created_at ASC"
            ).fetchall()
        if not rows:
            return

        recovery_id = (
            f"recovery-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(3)}"
        )
        recovery_dir = self.paths.run_root / recovery_id
        recovery_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        report: list[dict[str, Any]] = []

        for row in rows:
            action_hash = str(row["action_hash"])
            status = str(row["status"])
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            grant_state = self._grant_state(action_hash)

            # A released action was never marked executing. Likewise an
            # executing action whose original grant still exists never crossed
            # the one-use PreToolUse consume barrier. Both are safe to cancel.
            if status == "released" or (
                status == "executing" and grant_state == "issued"
            ):
                self.store.set_action_status(action_hash, "cancelled")
                self._set_reservation_status(
                    action_hash, "recovered_not_executed", only_reserved=True
                )
                self._cleanup_grant(action_hash)
                report.append(
                    {
                        "action_hash": action_hash,
                        "from": status,
                        "result": "cancelled_not_executed",
                        "grant_state": grant_state,
                    }
                )
                continue

            expected = dict(payload.get("after") or {})
            ok, item, differences = self._check_live_state(
                cycle_id=str(payload.get("cycle_id") or recovery_id),
                run_dir=recovery_dir,
                sealed_row=payload,
                expected_state=expected,
                label=f"reconcile-{action_hash}",
            )
            if ok and item is not None:
                recovered = dict(item)
                recovered["recovered_after_restart"] = True
                self.store.add_verification(action_hash, "verified", recovered)
                self.store.set_action_status(action_hash, "verified")
                self._set_reservation_status(action_hash, "verified")
                if str(payload.get("action_type") or "").lower().startswith(
                    "create_"
                ):
                    entity_id = _extract_entity_id(
                        recovered.get("observed"), str(payload.get("entity_type") or "")
                    )
                    if entity_id:
                        self.store.register_managed_entity(
                            str(payload.get("entity_type") or ""),
                            entity_id,
                            action_hash,
                            "verified",
                        )
                self._cleanup_grant(action_hash)
                report.append(
                    {
                        "action_hash": action_hash,
                        "from": status,
                        "result": "verified_from_fresh_amazon_state",
                        "grant_state": grant_state,
                    }
                )
                continue

            self.store.set_action_status(action_hash, "recovery_uncertain")
            self._set_reservation_status(action_hash, "uncertain")
            report.append(
                {
                    "action_hash": action_hash,
                    "from": status,
                    "result": "uncertain_paused",
                    "grant_state": grant_state,
                    "differences": differences,
                }
            )
            self.owner.system_pause(
                f"restart reconciliation could not prove action {action_hash}"
            )
            # Keep consumed evidence when outcome remains ambiguous.

        (recovery_dir / "recovery-summary.json").write_text(
            json.dumps(report, indent=2)
        )
        self.store.event(
            "warning",
            "runtime.recovery",
            None,
            {"recovery_id": recovery_id, "actions": report},
        )

    def _set_reservation_status(
        self, action_hash: str, status: str, *, only_reserved: bool = False
    ) -> None:
        with self.store.connection() as conn:
            if only_reserved:
                conn.execute(
                    "UPDATE reservations SET status=? WHERE action_hash=? AND status='reserved'",
                    (status, action_hash),
                )
            else:
                conn.execute(
                    "UPDATE reservations SET status=? WHERE action_hash=?",
                    (status, action_hash),
                )

    def _cancel_remaining(
        self,
        actions: list[Action],
        sealed_by_id: dict[str, dict[str, Any]],
        ledger: BudgetLedger,
        action_status: dict[str, str],
        reason: str,
    ) -> None:
        for action in actions:
            if action.action_id in action_status:
                continue
            row = sealed_by_id[action.action_id]
            self.store.set_action_status(row["action_hash"], "cancelled")
            ledger.release(row["action_hash"], reason)
            self._cleanup_grant(row["action_hash"])
            action_status[action.action_id] = "cancelled"

    def _recent_state(self) -> dict[str, Any]:
        return self.store.recent_state_summary()


def _topological_actions(actions: list[Action]) -> list[Action]:
    by_id = {action.action_id: action for action in actions}
    pending = {action.action_id: set(action.dependencies) for action in actions}
    ordered: list[Action] = []
    while pending:
        ready = [
            action.action_id
            for action in actions
            if action.action_id in pending and not pending[action.action_id]
        ]
        if not ready:
            raise PolicyError("action dependency graph contains a cycle")
        for action_id in ready:
            ordered.append(by_id[action_id])
            pending.pop(action_id)
            for dependencies in pending.values():
                dependencies.discard(action_id)
    return ordered


def _one_receipt(
    receipt: Any,
    cycle_id: str,
    action_hash: str,
    expected_tool_name: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(receipt, dict) or str(receipt.get("cycle_id") or "") != cycle_id:
        return None, "executor returned wrong/missing cycle_id"
    results = receipt.get("results")
    if not isinstance(results, list) or len(results) != 1:
        return None, "executor must return exactly one result for an atomic release"
    item = results[0] if isinstance(results[0], dict) else None
    if not item or str(item.get("action_hash") or "") != action_hash:
        return item, "executor returned wrong/missing action_hash"
    if str(item.get("tool_name") or "") != expected_tool_name:
        return item, "executor reported a tool different from the sealed MCP tool_name"
    return item, None


def _one_verification(
    value: Any, cycle_id: str, action_hash: str
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(value, dict) or str(value.get("cycle_id") or "") != cycle_id:
        return None, "verifier returned wrong/missing cycle_id"
    results = value.get("results")
    if not isinstance(results, list) or len(results) != 1:
        return None, "verifier must return exactly one result for an atomic verification"
    item = results[0] if isinstance(results[0], dict) else None
    if not item or str(item.get("action_hash") or "") != action_hash:
        return item, "verifier returned wrong/missing action_hash"
    return item, None


def _state_differences(
    expected: Any, observed: Any, path: str = "state"
) -> list[str]:
    differences: list[str] = []
    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            return [f"{path}: expected object, observed {type(observed).__name__}"]
        for key, expected_value in expected.items():
            child = f"{path}.{key}"
            if key not in observed:
                differences.append(f"{child}: missing from fresh observation")
                continue
            differences.extend(
                _state_differences(expected_value, observed[key], child)
            )
        return differences

    if isinstance(expected, list):
        if not isinstance(observed, list):
            return [f"{path}: expected list, observed {type(observed).__name__}"]
        expected_items = sorted(canonical_json(item) for item in expected)
        observed_items = sorted(canonical_json(item) for item in observed)
        if expected_items != observed_items:
            differences.append(f"{path}: list changed")
        return differences

    if _scalar_equal(expected, observed):
        return differences
    differences.append(f"{path}: expected {expected!r}, observed {observed!r}")
    return differences


def _scalar_equal(expected: Any, observed: Any) -> bool:
    if isinstance(expected, bool) or isinstance(observed, bool):
        return expected is observed
    if expected == observed:
        return True
    try:
        left = float(expected)
        right = float(observed)
    except (TypeError, ValueError):
        return False
    return abs(left - right) <= max(1e-9, abs(left) * 1e-9, abs(right) * 1e-9)


def _extract_entity_id(value: Any, entity_type: str) -> str | None:
    candidates = {
        "campaign": ("campaignId", "campaign_id"),
        "ad_group": ("adGroupId", "ad_group_id"),
        "adgroup": ("adGroupId", "ad_group_id"),
        "ad": ("adId", "ad_id"),
        "keyword": ("keywordId", "keyword_id"),
        "target": ("targetId", "target_id"),
    }.get(str(entity_type).lower(), ("id",))
    wanted = {
        "".join(ch for ch in candidate.lower() if ch.isalnum())
        for candidate in candidates
    }
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, nested in item.items():
                normalized = "".join(
                    ch for ch in str(key).lower() if ch.isalnum()
                )
                if normalized in wanted and nested not in (None, ""):
                    return str(nested)
                if isinstance(nested, (dict, list)):
                    stack.append(nested)
        elif isinstance(item, list):
            stack.extend(item)
    return None


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
