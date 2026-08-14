from __future__ import annotations

from typing import Any

from .models import Action
from .policy import (
    PolicyDecision,
    PolicyEngine,
    PolicyError,
    _action_intent,
    _argument_intent_reasons,
    _blocked_argument_signal,
    _norm,
)

DIRECT_ROOT_BLOCKS = ("billing", "payment", "account_admin", "accountadmin", "credentials", "credential", "oauth", "user_management", "usermanagement", "delete_account", "deleteaccount", "close_account", "closeaccount")
MUTATION_TOKENS = ("create", "add", "update", "set", "manage", "mutate", "pause", "enable", "resume", "remove", "delete", "archive")


class DirectPolicyEngine(PolicyEngine):
    """Root safety envelope for an authenticated, Owner-armed direct command."""

    def evaluate_action(self, a: Action, *, context: dict[str, Any] | None = None, store=None, timezone_name: str = "UTC") -> PolicyDecision:
        context = dict(context or {}); reasons: list[str] = []; data = self.data
        if data.get("recovery", {}).get("kill_switch"):
            reasons.append("kill switch enabled")
        if not a.action_id.strip():
            reasons.append("missing action_id")
        if not a.action_type.strip():
            reasons.append("missing action_type")
        if not a.entity_type.strip():
            reasons.append("missing entity_type")
        if not a.entity_id.strip():
            reasons.append("missing entity_id")
        if not isinstance(a.arguments, dict) or not a.arguments:
            reasons.append("direct mutation arguments must be a non-empty object")
        if not a.after:
            reasons.append("direct mutation requires non-empty sealed after-state")

        tool = str(a.tool_name or "").strip()
        if not tool:
            reasons.append("missing exact MCP tool_name")
        elif tool.startswith("mcp__"):
            reasons.append("tool_name must be the bare amazon_ads MCP tool name")
        else:
            tool_norm = _norm(tool); action_norm = _norm(a.action_type)
            if not any(token in tool_norm for token in MUTATION_TOKENS):
                reasons.append("direct command is not bound to a mutation-capable Amazon MCP tool")
            create = _action_intent(a)["create"]
            create_action = action_norm.startswith("create")
            create_verb = any(token in tool_norm for token in ("create", "add"))
            if create_action and not create_verb:
                reasons.append("direct create action is not bound to a create/add MCP tool")
            if not create_action and create_verb:
                reasons.append("direct non-create action cannot use a create/add MCP tool")
            aliases = {"adgroup": ("adgroup", "adgroups"), "campaign": ("campaign", "campaigns"), "keyword": ("keyword", "keywords"), "target": ("target", "targets"), "ad": ("ad", "ads", "productad", "productads")}
            entity_norm = _norm(a.entity_type); options = aliases.get(entity_norm, (entity_norm,)) if entity_norm else ()
            if not options:
                reasons.append("direct MCP tool cannot be bound without entity_type")
            elif not any(option in tool_norm for option in options):
                reasons.append("direct MCP tool family does not match action entity_type")

        if str(a.ad_product).upper() != "SPONSORED_PRODUCTS":
            reasons.append("Owner Direct Override is limited to Sponsored Products")
        allowed = {str(x).upper() for x in data.get("scope", {}).get("allowed_ad_products", [])}
        if "SPONSORED_PRODUCTS" not in allowed:
            reasons.append("Sponsored Products is outside standing Owner product scope")
        lowered = _norm(a.action_type); tool_lower = _norm(tool); entity_lower = _norm(a.entity_type)
        if entity_lower in {"account", "profile", "billing", "credential", "credentials", "user"}:
            reasons.append("direct command cannot mutate Owner/account administration entities")
        for blocked in DIRECT_ROOT_BLOCKS:
            normalized = _norm(blocked)
            if normalized in lowered or normalized in tool_lower or normalized in entity_lower or _blocked_argument_signal(a.arguments, blocked):
                reasons.append(f"root safety block: {blocked}")
        scope_context = dict(context); scope_context["_owner_managed_asins"] = []
        reasons.extend(_argument_intent_reasons(a, scope_context))

        is_create = _action_intent(a)["create"]
        if not is_create:
            if not a.prewrite_observed_at:
                reasons.append("direct mutation requires a fresh prewrite observation timestamp")
            if not a.before:
                reasons.append("direct mutation requires fresh before-state for TOCTOU protection")
            elif a.prewrite_observed_at:
                try:
                    age = self._timestamp_age(a.prewrite_observed_at)
                    if age > float(data.get("scope", {}).get("prewrite_read_max_age_seconds", 300)):
                        reasons.append("direct mutation prewrite observation is too old")
                    if age < -60:
                        reasons.append("direct mutation prewrite observation is in the future")
                except Exception:
                    reasons.append("invalid direct mutation prewrite observation timestamp")
        if not a.evidence_refs:
            reasons.append("direct mutation has no evidence refs")
        return PolicyDecision(not reasons, reasons, 0.0)

    def evaluate_plan(self, actions: list[Action], *, context: dict[str, Any] | None = None, store=None, timezone_name: str = "UTC", cycle_id: str | None = None) -> list[PolicyDecision]:
        if len({a.action_id for a in actions}) != len(actions):
            raise PolicyError("duplicate action_id")
        ids = {a.action_id for a in actions}
        for action in actions:
            missing = set(action.dependencies) - ids
            if missing:
                raise PolicyError(f"{action.action_id} dependencies missing: {sorted(missing)}")
        return [self.evaluate_action(action, context=context, store=store, timezone_name=timezone_name) for action in actions]
