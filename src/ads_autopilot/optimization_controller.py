from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
from typing import Any

from .codex_runner import run_codex
from .controller import Controller
from .optimization_memory import OptimizationMemory

UTC = timezone.utc


class OptimizationController(Controller):
    """Sealed Controller with a read-only observation/learning plane attached.

    The added plane is deliberately not an authority layer. It can enrich or
    degrade decision evidence, but it cannot shrink the business discretion
    granted by Owner Control.
    """

    def __init__(self, root: Path, owner_home: str | Path | None = None):
        super().__init__(root, owner_home)
        economics_path = os.environ.get("ADS_ECONOMICS_FILE")
        self.optimization = OptimizationMemory(
            self.store,
            economics_path=economics_path or (self.paths.owner_home / "economics.json"),
        )

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
            counts = self.optimization.ingest_plan(observation_id, {"learning_snapshot": value.get("learning_snapshot") or {}})
            return {"status": "recorded", "observation_id": observation_id, "summary": str(value.get("summary") or ""), "ingested": counts}
        except Exception as exc:
            self.store.event("warning", "optimization.observer_failed", None, {"observation_id": observation_id, "cycle_kind": kind, "error_type": type(exc).__name__, "error": str(exc)})
            return {"status": "degraded", "observation_id": observation_id, "error_type": type(exc).__name__, "error": str(exc)}

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
            result["optimization_learning"] = {"status": "recorded", "ingested": learning.get("ingested", {}), "outcomes_recorded": learning["outcomes_recorded"]}
        except Exception as exc:
            try:
                self.store.event("warning", "optimization.learning_ingest_failed", cycle_id, {"error_type": type(exc).__name__, "error": str(exc)})
            finally:
                result["optimization_learning"] = {"status": "degraded", "error_type": type(exc).__name__, "error": str(exc)}
        return result
