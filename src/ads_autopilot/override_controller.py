from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from . import controller as controller_module
from .canonical import canonical_json
from .controller import _fsync_directory
from .direct_policy import DirectPolicyEngine
from .optimization_controller import OptimizationController
from .owner_override import OwnerOverrideStore

UTC = timezone.utc
DIRECT_PLANNER_CONSTITUTION = r"""

## OWNER DIRECT OVERRIDE — HIGHEST BUSINESS PRIORITY FOR THIS CYCLE

`policy.owner_direct_override.active` means the authenticated Owner explicitly armed a time-bounded direct-command window and then issued the natural-language `instruction` in that object. Treat that instruction as the highest-priority business directive for this cycle.

For this direct cycle you have the entire executable Sponsored Products advertising surface inside the configured advertiser/profile boundary. Normal autonomy toggles, monetary caps, bid/placement caps, cooldowns, campaign naming, managed-ASIN filters, PAUSED-first creation rules, routine confidence thresholds and the routine recovery breaker are not business restrictions for this command. You may create, update, enable, pause, archive/delete advertising entities, change bids/budgets/placements/targeting, restructure campaigns, or otherwise use the authenticated Sponsored Products MCP mutation surface when the Owner instruction requires it.

This is not permission to improvise unrelated work. Execute the Owner's instruction faithfully and no broader. If the requested end state is already satisfied, return zero actions rather than repeating it. For a multi-step instruction, use explicit dependencies and verify each intended state.

The following invariants remain absolute even in Owner Direct Override: stay inside configured advertiser/profile scope and Sponsored Products; never touch billing, payment, credentials/OAuth, users, account administration or account deletion; use only exact live Amazon MCP tool names/arguments; perform fresh reads for existing entities; preserve before/after state and evidence; never bypass the sealed one-use Executor; and accept independent verification as the final source of truth. Emergency Stop always wins.

The Owner's direct command is temporary authority, not a new autonomous default. Do not reinterpret ordinary optimization objectives as additional direct commands.
"""


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class OwnerOverrideOptimizationController(OptimizationController):
    """OptimizationController with Owner-armed direct-command capability."""

    def __init__(self, root: Path, owner_home: str | Path | None = None):
        super().__init__(root, owner_home)
        self.owner = OwnerOverrideStore(self.paths.owner_db, self.sealer.key)

    def run(self, kind: str = "daily", dry_run: bool = False) -> dict[str, Any]:
        state = self.owner.direct_override_state()
        if kind == "direct":
            if not (state.get("armed") and state.get("command_active")):
                return {"status": "blocked", "reason": "direct cycle requires an Owner-armed window and a bound Owner instruction", "direct_override": state}
        elif state.get("armed") and (state.get("return_mode") != "autopilot" or state.get("command_active")):
            return {"status": "paused", "reason": "scheduled autonomous cycle suppressed while Owner Direct Override reserves authority for direct commands", "direct_override": state}
        return super().run(kind, dry_run)

    def _prompt(self, name: str, payload: dict[str, Any]) -> str:
        direct = payload.get("policy", {}).get("owner_direct_override", {}) if isinstance(payload, dict) else {}
        if name == "observe_plan.md" and direct.get("active"):
            base = (self.root / f"prompts/{name}").read_text() + DIRECT_PLANNER_CONSTITUTION
            return base + "\n\nINPUT_JSON:\n" + canonical_json(payload)
        return super()._prompt(name, payload)

    def _run(self, cycle_id: str, run_dir: Path, kind: str, dry_run: bool, snapshot: dict[str, Any]) -> dict[str, Any]:
        direct = snapshot.get("direct_override") or {}
        if not (direct.get("armed") and direct.get("command_active")):
            return super()._run(cycle_id, run_dir, kind, dry_run, snapshot)
        original = controller_module.PolicyEngine
        controller_module.PolicyEngine = DirectPolicyEngine
        try:
            return super()._run(cycle_id, run_dir, kind, dry_run, snapshot)
        finally:
            controller_module.PolicyEngine = original

    def _write_executor_grant(self, sealed_row: dict[str, Any]) -> Path:
        path = super()._write_executor_grant(sealed_row)
        state = self.owner.direct_override_state()
        expires_at = state.get("expires_at") if state.get("command_active") else None
        if not expires_at:
            return path
        body = json.loads(path.read_text()); grant_expiry = _utc(str(body["expires_at"])); override_expiry = _utc(str(expires_at))
        if grant_expiry <= override_expiry:
            return path
        body.pop("signature", None); body["expires_at"] = override_expiry.isoformat().replace("+00:00", "Z"); body["signature"] = self.sealer.sign(body)
        tmp = path.with_name(f".{path.name}.override-{os.getpid()}")
        try:
            with tmp.open("x") as handle:
                json.dump(body, handle, sort_keys=True, separators=(",", ":")); handle.flush(); os.fsync(handle.fileno())
            tmp.chmod(0o600); os.replace(tmp, path); _fsync_directory(self.paths.grant_root)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        return path
