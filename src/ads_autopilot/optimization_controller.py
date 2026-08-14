from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
from typing import Any

from . import controller as controller_module
from .codex_runner import run_codex
from .controller import Controller
from .optimization_memory import OptimizationMemory
from .policy import PolicyEngine, PolicyError

UTC = timezone.utc


class OptimizationController(Controller):
    """Sealed Controller with read-only optimization intelligence attached."""

    def __init__(self, root: Path, owner_home: str | Path | None = None):
        super().__init__(root, owner_home)
        economics_path = os.environ.get("ADS_ECONOMICS_FILE")
        self.optimization = OptimizationMemory(
            self.store,
            economics_path=economics_path or (self.paths.owner_home / "economics.json"),
        )

    def _recover_incomplete_actions(self, snapshot: dict[str, Any]) -> None:
        # Never replay uncertain writes. A later process may only re-read Amazon
        # and repair evidence; an existing Owner/system PAUSED mode stays PAUSED.
        with self.store.connection() as conn:
            conn.execute(
                "UPDATE actions SET status='unknown' "
                "WHERE status IN ('verification_failed','recovery_uncertain')"
            )
        super()._recover_incomplete_actions(snapshot)

    def _verify_planner_context(
        self,
        *,
        cycle_id: str,
        run_dir: Path,
        context: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> None:
        expected = {
            "today_spend": context.get("today_spend"),
            "active_campaign_budget_total": context.get("active_campaign_budget_total"),
            "observed_asins": sorted(
                {str(value).upper() for value in (context.get("observed_asins") or [])}
            ),
        }
        if expected["today_spend"] is None or expected["active_campaign_budget_total"] is None:
            raise PolicyError("planner critical Amazon spend context is incomplete")
        operator = snapshot["operator"]
        action_hash = f"planner-context:{cycle_id}"
        payload = {
            "cycle_id": cycle_id,
            "action_hash": action_hash,
            "operator_scope": {
                "advertiser_account_id": operator.get("advertiser_account_id"),
                "profile_ids": list(operator.get("profile_ids") or []),
                "timezone": operator.get("timezone"),
                "ad_products": list(operator.get("scope", {}).get("ad_products") or []),
                "managed_asins": list(operator.get("scope", {}).get("managed_asins") or []),
            },
            "expected_state": expected,
            "planner_evidence": {
                "today_spend_observed_at": context.get("today_spend_observed_at"),
                "today_spend_evidence_ref": context.get("today_spend_evidence_ref"),
            },
        }
        value = run_codex(
            paths=self.paths,
            role="state_verifier",
            prompt=self._prompt("spend_context_check.md", payload),
            schema=self.root / "schemas/verification.schema.json",
            output=run_dir / "planner-context-verification.json",
            timeout=self.timeout,
            model=self.model,
        )
        results = value.get("results") if isinstance(value, dict) else None
        item = results[0] if isinstance(results, list) and len(results) == 1 else None
        if not isinstance(item, dict) or str(item.get("action_hash") or "") != action_hash:
            raise PolicyError("independent planner-context verifier returned invalid identity")
        if str(item.get("status") or "") != "verified":
            raise PolicyError(
                "independent Amazon spend/scope context does not match Planner context: "
                + "; ".join(str(x) for x in (item.get("differences") or [item.get("status") or "unknown"]))
            )

    def _run(
        self,
        cycle_id: str,
        run_dir: Path,
        kind: str,
        dry_run: bool,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        direct = snapshot.get("direct_override") or {}
        if direct.get("armed") and direct.get("command_active"):
            # OwnerOverrideOptimizationController installs DirectPolicyEngine for
            # this call. Direct authority deliberately bypasses routine money caps.
            return super()._run(cycle_id, run_dir, kind, dry_run, snapshot)

        outer = self
        baseline_engine = controller_module.PolicyEngine

        class ContextVerifiedPolicyEngine(PolicyEngine):
            def evaluate_plan(self, actions, *, context=None, store=None, timezone_name="UTC", cycle_id=None):
                critical_context = dict(context or {})
                if actions:
                    outer._verify_planner_context(
                        cycle_id=str(cycle_id or ""),
                        run_dir=run_dir,
                        context=critical_context,
                        snapshot=snapshot,
                    )
                return super().evaluate_plan(
                    actions,
                    context=critical_context,
                    store=store,
                    timezone_name=timezone_name,
                    cycle_id=cycle_id,
                )

        controller_module.PolicyEngine = ContextVerifiedPolicyEngine
        try:
            return super()._run(cycle_id, run_dir, kind, dry_run, snapshot)
        finally:
            controller_module.PolicyEngine = baseline_engine

    def _recent_state(self) -> dict[str, Any]:
        state = super()._recent_state()
        try:
            state["optimization_intelligence"] = self.optimization.planner_context(self.owner.snapshot())
        except Exception as exc:
            state["optimization_intelligence"] = {
                "version": 1,
                "status": "degraded",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "interpretation": "Optimization memory unavailable; Planner retains normal Owner-granted autonomy and must rely on fresh Amazon evidence.",
            }
        return state

    def _collect_read_only_observation(self, kind: str) -> dict[str, Any]:
        observation_id = f"obs-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
        try:
            snapshot = self.owner.snapshot()
            if snapshot["mode"] == "paused" or snapshot["emergency_stop"]:
                return {"status": "skipped", "reason": "owner control paused"}
            root = self.paths.run_root / "_optimization-observations"
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            output = root / f"{observation_id}.json"
            payload = {
                "observation_id": observation_id,
                "cycle_kind": kind,
                "operator": snapshot["operator"],
                "historical_intelligence": self.optimization.planner_context(snapshot),
            }
            value = run_codex(
                paths=self.paths,
                role="optimization_observer",
                prompt=self._prompt("observe_learning.md", payload),
                schema=self.root / "schemas/learning.schema.json",
                output=output,
                timeout=self.timeout,
                model=self.model,
            )
            counts = self.optimization.ingest_plan(
                observation_id, {"learning_snapshot": value.get("learning_snapshot") or {}}
            )
            return {
                "status": "recorded",
                "observation_id": observation_id,
                "summary": str(value.get("summary") or ""),
                "ingested": counts,
            }
        except Exception as exc:
            self.store.event(
                "warning",
                "optimization.observer_failed",
                None,
                {
                    "observation_id": observation_id,
                    "cycle_kind": kind,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            return {
                "status": "degraded",
                "observation_id": observation_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    def run(self, kind: str = "daily", dry_run: bool = False) -> dict[str, Any]:
        observer = self._collect_read_only_observation(kind)
        result = super().run(kind, dry_run)
        result["optimization_observer"] = observer
        cycle_id = str(result.get("cycle_id") or "")
        if not cycle_id:
            return result
        learning: dict[str, Any] = {}
        try:
            plan_path = self.paths.run_root / cycle_id / "plan.json"
            if plan_path.exists():
                plan = json.loads(plan_path.read_text())
                learning["ingested"] = self.optimization.ingest_plan(cycle_id, plan)
            learning["outcomes_recorded"] = self.optimization.capture_action_outcomes(cycle_id)
            learning["report"] = self.optimization.report(self.owner.snapshot())
            report_path = self.paths.run_root / cycle_id / "optimization-learning.json"
            report_path.write_text(json.dumps(learning, indent=2, ensure_ascii=False))
            result["optimization_learning"] = {
                "status": "recorded",
                "ingested": learning.get("ingested", {}),
                "outcomes_recorded": learning["outcomes_recorded"],
            }
        except Exception as exc:
            try:
                self.store.event(
                    "warning",
                    "optimization.learning_ingest_failed",
                    cycle_id,
                    {"error_type": type(exc).__name__, "error": str(exc)},
                )
            finally:
                result["optimization_learning"] = {
                    "status": "degraded",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
        return result
