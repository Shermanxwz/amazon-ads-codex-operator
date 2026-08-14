from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from .canonical import digest
from .models import Action
from .state import Store

UTC = timezone.utc
# Amazon's current sponsored-ads policy can allow up to 100% above the
# average daily budget on a high-traffic day. The Owner boundary therefore
# uses the worldwide worst-case 2x factor rather than assuming a 1x/1.25x cap.
SP_DAILY_BUDGET_OVERDELIVERY_FACTOR = 2.0
HARD_PERMANENT_BLOCKS = (
    "billing", "payment", "account_admin", "credentials", "user_management",
    "permanent_delete", "delete_account", "close_account",
)
_MUTATION_TOKENS = (
    "create", "add", "update", "set", "manage", "mutate", "pause", "enable",
    "resume", "remove",
)
_ENTITY_IDS = {
    "campaign": ("campaignId", "campaign_id", "campaignIds", "campaign_ids"),
    "ad_group": ("adGroupId", "ad_group_id", "adGroupIds", "ad_group_ids"),
    "adgroup": ("adGroupId", "ad_group_id", "adGroupIds", "ad_group_ids"),
    "keyword": ("keywordId", "keyword_id", "keywordIds", "keyword_ids"),
    "target": ("targetId", "target_id", "targetIds", "target_ids"),
    "ad": ("adId", "ad_id", "adIds", "ad_ids", "productAdId", "product_ad_id"),
}


class PolicyError(ValueError):
    pass


@dataclass
class PolicyDecision:
    allowed: bool
    reasons: list[str]
    spend_reservation: float = 0.0


class PolicyEngine:
    def __init__(self, data: dict[str, Any]):
        self.data = data

    @classmethod
    def load(cls, path: str | Path):
        return cls(json.loads(Path(path).read_text()))

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        return cls(json.loads(json.dumps(data)))

    @property
    def hash(self):
        return digest(self.data)

    def _pct_change(self, before: Any, after: Any) -> float:
        try:
            left, right = float(before), float(after)
        except (TypeError, ValueError) as exc:
            raise PolicyError("numeric before/after value required") from exc
        if left <= 0:
            raise PolicyError("before value must be > 0")
        return abs((right - left) / left * 100.0)

    def _timestamp_age(self, value: str) -> float:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return (datetime.now(UTC) - parsed.astimezone(UTC)).total_seconds()

    def evaluate_action(
        self,
        a: Action,
        *,
        context: dict[str, Any] | None = None,
        store: Store | None = None,
        timezone_name: str = "UTC",
    ) -> PolicyDecision:
        reasons: list[str] = []
        data = self.data
        context = dict(context or {})
        intent = _action_intent(a)
        create = intent["create"]
        entity = _norm(a.entity_type)

        if data["recovery"].get("kill_switch"):
            reasons.append("kill switch enabled")
        if not a.action_id.strip():
            reasons.append("missing action_id")
        if not a.action_type.strip():
            reasons.append("missing action_type")
        if not a.tool_name.strip():
            reasons.append("missing exact MCP tool_name")
        if not a.entity_type.strip():
            reasons.append("missing entity_type")
        if not a.entity_id.strip():
            reasons.append("missing entity_id")
        if not isinstance(a.arguments, dict) or not a.arguments:
            reasons.append("mutation arguments must be a non-empty object")
        if str(a.ad_product).upper() != "SPONSORED_PRODUCTS":
            reasons.append("this release is certified only for Sponsored Products")
        if str(a.ad_product).upper() not in {
            str(value).upper() for value in data["scope"]["allowed_ad_products"]
        }:
            reasons.append(f"ad product {a.ad_product} outside standing scope")

        reasons.extend(_tool_contract_reasons(a))
        reasons.extend(_argument_intent_reasons(a, context))

        lowered = a.action_type.lower()
        tool_lower = a.tool_name.lower()
        entity_lower = a.entity_type.lower()
        for blocked in set(HARD_PERMANENT_BLOCKS) | {
            str(value).lower() for value in data.get("permanent_blocks", [])
        }:
            if (
                blocked in lowered
                or blocked in tool_lower
                or blocked in entity_lower
                or _blocked_argument_signal(a.arguments, blocked)
            ):
                reasons.append(f"permanent block: {blocked}")
        if any(token in lowered for token in ("delete", "archive", "remove_account", "close_account")):
            reasons.append("destructive/irreversible operation blocked")
        if not a.reversible:
            reasons.append("irreversible action blocked")

        # Model-declared state is evidence, not authority. Existing entities
        # must carry a fresh before-state; every mutation must seal its intent.
        if not create and not a.before:
            reasons.append("existing-entity mutation requires non-empty fresh before-state")
        if not a.after:
            reasons.append("mutation requires non-empty sealed after-state")

        if create:
            creation_flags = {
                "campaign": "allow_campaign_creation",
                "adgroup": "allow_ad_group_creation",
                "ad": "allow_ad_creation",
                "keyword": "allow_keyword_creation",
                "target": "allow_target_creation",
            }
            flag = creation_flags.get(entity)
            if flag and not data["autonomy"].get(flag):
                reasons.append(flag.removeprefix("allow_").replace("_", " ") + " disabled")
        if intent["negative"] and not data["autonomy"].get("allow_negative_targeting"):
            reasons.append("negative targeting disabled")
        # A required PAUSED state on creation is part of creation semantics,
        # not a separate standing state-change authority.
        if intent["state"] and not create and not data["autonomy"].get("allow_state_changes"):
            reasons.append("state changes disabled")

        if create and entity == "campaign":
            desired = str(
                _find_first(a.arguments, ("state", "status"))
                or a.after.get("state")
                or ""
            ).upper()
            if data["scope"].get("require_paused_campaign_create") and desired not in {"PAUSED", "PAUSE"}:
                reasons.append("new campaign must be created PAUSED")
            prefix = str(data["scope"].get("autonomous_campaign_name_prefix") or "")
            name = str(
                _find_first(a.arguments, ("name", "campaignName"))
                or a.after.get("name")
                or ""
            )
            if prefix and not name.startswith(prefix):
                reasons.append(f"autonomous campaign name must start with {prefix}")
            budget = _campaign_budget(a)
            if budget > float(data["money"]["max_single_campaign_budget"]):
                reasons.append("new campaign budget exceeds single-campaign cap")

        if create and entity == "ad" and data["scope"].get("require_observed_asin_for_product_ad_create"):
            asin = _find_first(
                a.arguments,
                ("asin", "advertisedAsin", "advertised_asin", "advertisedProductAsin"),
            )
            observed = {str(value).upper() for value in context.get("observed_asins", [])}
            managed = {str(value).upper() for value in context.get("_owner_managed_asins", [])}
            if not asin:
                reasons.append("product-ad creation requires an advertised ASIN")
            elif str(asin).upper() not in observed:
                reasons.append("product-ad ASIN is not present in current-cycle Amazon observations")
            if asin and managed and str(asin).upper() not in managed:
                reasons.append("product-ad ASIN is outside Owner managed-ASIN scope")

        if store and _is_enable_campaign(a):
            managed = store.managed_entity("campaign", a.entity_id)
            if managed and managed.get("activation_status") != "verified":
                reasons.append("controller-created campaign is not independently verified for activation")
            prefix = str(data["scope"].get("autonomous_campaign_name_prefix") or "")
            before_name = str(
                a.before.get("name")
                or _find_first(a.arguments, ("name", "campaignName"))
                or ""
            )
            if prefix and before_name.startswith(prefix) and not managed:
                reasons.append("autonomous campaign cannot be enabled without controller verification lineage")

        if intent["bid"]:
            if not data["autonomy"].get("allow_bid_changes"):
                reasons.append("bid changes disabled")
            before, after = a.before.get("bid"), a.after.get("bid")
            if before is None and not create:
                reasons.append("bid mutation requires before.bid")
            if after is None:
                reasons.append("bid mutation requires after.bid")
            if before is not None and after is not None:
                try:
                    increasing = float(after) > float(before)
                    cap = float(
                        data["bidding"]["max_bid_increase_pct_per_action"]
                        if increasing
                        else data["bidding"].get(
                            "max_bid_decrease_pct_per_action",
                            data["bidding"]["max_bid_increase_pct_per_action"],
                        )
                    )
                    if context.get("_cycle_kind") == "hourly":
                        cap = min(
                            cap,
                            float(data["bidding"].get("hourly_max_bid_change_pct", cap)),
                        )
                    if self._pct_change(before, after) > cap:
                        reasons.append("bid change exceeds per-action cap")
                    if not (
                        float(data["bidding"]["min_bid"])
                        <= float(after)
                        <= float(data["bidding"]["max_bid"])
                    ):
                        reasons.append("bid outside min/max")
                except (PolicyError, ValueError, TypeError) as exc:
                    reasons.append(str(exc))

        if intent["budget"]:
            before, after = a.before.get("budget"), a.after.get("budget")
            if before is None and not create:
                reasons.append("budget mutation requires before.budget")
            if after is None:
                reasons.append("budget mutation requires after.budget")
            if before is not None and after is not None:
                try:
                    increasing = float(after) > float(before)
                    if increasing and not data["autonomy"].get("allow_budget_increases"):
                        reasons.append("budget increases disabled")
                    if float(after) < float(before) and not data["autonomy"].get("allow_budget_decreases"):
                        reasons.append("budget decreases disabled")
                    cap = float(
                        data["money"]["max_budget_increase_pct_per_action"]
                        if increasing
                        else data["money"].get(
                            "max_budget_decrease_pct_per_action",
                            data["money"]["max_budget_increase_pct_per_action"],
                        )
                    )
                    if self._pct_change(before, after) > cap:
                        reasons.append("budget change exceeds per-action cap")
                except (PolicyError, ValueError, TypeError) as exc:
                    reasons.append(str(exc))

        if intent["placement"]:
            if not data["autonomy"].get("allow_placement_changes"):
                reasons.append("placement changes disabled")
            before = a.before.get("placement_pct")
            after = a.after.get("placement_pct")
            if before is None and not create:
                reasons.append("placement mutation requires before.placement_pct")
            if after is None:
                reasons.append("placement mutation requires after.placement_pct")
            if before is not None and after is not None:
                try:
                    if abs(float(after) - float(before)) > float(data["placement"]["max_change_points_per_action"]):
                        reasons.append("placement change exceeds cap")
                    if not (
                        float(data["placement"]["min_multiplier_pct"])
                        <= float(after)
                        <= float(data["placement"]["max_multiplier_pct"])
                    ):
                        reasons.append("placement multiplier outside min/max")
                except (ValueError, TypeError):
                    reasons.append("invalid placement value")

        if intent["state"] and not a.after.get("state"):
            reasons.append("state mutation requires after.state")
        if a.spend_delta < 0:
            reasons.append("spend_delta cannot be negative")
        if _spend_expanding(a) and a.confidence < float(data["bidding"]["min_confidence_scale"]):
            reasons.append("insufficient confidence for spend increase")
        if (
            not create
            and not _spend_expanding(a)
            and (intent["bid"] or intent["budget"] or intent["state"])
            and a.confidence < float(data["bidding"]["min_confidence_reduce"])
        ):
            reasons.append("insufficient confidence for reduction")

        if not create and data["scope"].get("require_prewrite_read"):
            if not a.prewrite_observed_at:
                reasons.append("missing prewrite observation timestamp")
            else:
                try:
                    age = self._timestamp_age(a.prewrite_observed_at)
                    if age > float(data["scope"]["prewrite_read_max_age_seconds"]):
                        reasons.append("prewrite observation too old")
                    if age < -60:
                        reasons.append("prewrite observation timestamp is in the future")
                except Exception:
                    reasons.append("invalid prewrite observation timestamp")
        if not a.evidence_refs:
            reasons.append("action has no evidence refs")

        if store and not create:
            hours = float(data["scope"].get("cooldown_hours") or 0)
            if hours > 0:
                since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
                if store.recent_same_entity_action(
                    a.entity_type, a.entity_id, _action_family(a), since
                ):
                    reasons.append(f"entity/action-family is inside {hours:g}h cooldown")

        return PolicyDecision(not reasons, reasons, 0.0)

    def evaluate_plan(
        self,
        actions: list[Action],
        *,
        context: dict[str, Any] | None = None,
        store: Store | None = None,
        timezone_name: str = "UTC",
        cycle_id: str | None = None,
    ) -> list[PolicyDecision]:
        context = dict(context or {})
        data = self.data
        if len(actions) > int(data["scope"]["max_actions_per_cycle"]):
            raise PolicyError("plan exceeds max_actions_per_cycle")
        if len({action.action_id for action in actions}) != len(actions):
            raise PolicyError("duplicate action_id")
        ids = {action.action_id for action in actions}
        for action in actions:
            missing = set(action.dependencies) - ids
            if missing:
                raise PolicyError(f"{action.action_id} dependencies missing: {sorted(missing)}")

        if (
            store
            and store.consecutive_exceptions(exclude_cycle_id=cycle_id)
            >= int(data["recovery"].get("max_consecutive_failures") or 0)
            > 0
        ):
            raise PolicyError("automatic recovery breaker open after consecutive exception cycles")

        cycle_kind = ""
        if store and cycle_id:
            with store.connection() as conn:
                row = conn.execute("SELECT kind FROM cycles WHERE id=?", (cycle_id,)).fetchone()
            cycle_kind = str(row["kind"] or "") if row else ""
        context["_cycle_kind"] = cycle_kind

        decisions = [
            self.evaluate_action(
                action,
                context=context,
                store=store,
                timezone_name=timezone_name,
            )
            for action in actions
        ]

        campaign_creates = [
            action
            for action in actions
            if _action_intent(action)["create"] and _norm(action.entity_type) == "campaign"
        ]
        if store and campaign_creates:
            prior_count, prior_budget = store.campaign_creates_today(timezone_name)
            if prior_count + len(campaign_creates) > int(data["scope"]["max_campaign_creates_per_day"]):
                raise PolicyError("daily campaign creation limit exceeded")
            proposed = sum(_campaign_budget(action) for action in campaign_creates)
            if prior_budget + proposed > float(data["money"]["max_new_campaign_budget_per_day"]):
                raise PolicyError("daily new-campaign budget envelope exceeded")

        positive_budget_delta = sum(_positive_budget_delta(action) for action in actions)
        if positive_budget_delta > 0:
            active_budget_total = _number(context.get("active_campaign_budget_total"))
            if active_budget_total <= 0:
                raise PolicyError("budget-increase plan lacks active_campaign_budget_total evidence")
            if (
                positive_budget_delta / active_budget_total * 100.0
                > float(data["money"]["max_profile_budget_increase_pct_per_cycle"])
            ):
                raise PolicyError("profile budget increase exceeds per-cycle cap")

        expanding_indexes = [
            index for index, action in enumerate(actions) if _spend_expanding(action)
        ]
        if expanding_indexes:
            evidence_ref = str(context.get("today_spend_evidence_ref") or "").strip()
            observed_at = str(context.get("today_spend_observed_at") or "").strip()
            if not evidence_ref:
                raise PolicyError("spend-increasing plan lacks today_spend_evidence_ref")
            if not observed_at:
                raise PolicyError("spend-increasing plan lacks today_spend_observed_at")
            try:
                age = self._timestamp_age(observed_at)
                if age > float(data["money"].get("spend_evidence_max_age_seconds", 1800)):
                    raise PolicyError("today spend evidence is too old")
                if age < -60:
                    raise PolicyError("today spend evidence timestamp is in the future")
            except PolicyError:
                raise
            except Exception as exc:
                raise PolicyError("invalid today_spend_observed_at") from exc

            observed_spend = _number(context.get("today_spend"))
            active_budget_total = _number(context.get("active_campaign_budget_total"))
            unknown_expansion = any(
                _unknown_spend_expansion(actions[index]) for index in expanding_indexes
            )
            # Exact campaign-budget increases can enlarge a high-traffic-day cap
            # by up to 2x the budget delta. Bid/placement/enable/targeting changes
            # can unlock existing campaign headroom, so conservatively reserve
            # the worst current sponsored-ads day cap less already observed spend.
            deterministic_exposure = (
                positive_budget_delta * SP_DAILY_BUDGET_OVERDELIVERY_FACTOR
            )
            if unknown_expansion:
                if active_budget_total <= 0:
                    raise PolicyError(
                        "cannot deterministically bound spend expansion without active_campaign_budget_total"
                    )
                deterministic_exposure += max(
                    0.0,
                    active_budget_total * SP_DAILY_BUDGET_OVERDELIVERY_FACTOR
                    - observed_spend,
                )
            model_claim = sum(max(0.0, float(action.spend_delta)) for action in actions)
            reservation = max(deterministic_exposure, model_claim)
            if reservation > 0:
                decisions[expanding_indexes[0]].spend_reservation = reservation

        return decisions


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _scalar_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(_scalar_values(item))
        return out
    if isinstance(value, dict):
        return []
    return [str(value)] if value not in (None, "") else []


def _find_values(value: Any, keys: tuple[str, ...]) -> list[Any]:
    wanted = {_norm(key) for key in keys}
    found: list[Any] = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, nested in item.items():
                if _norm(key) in wanted:
                    if isinstance(nested, list):
                        found.extend(nested)
                    else:
                        found.append(nested)
                if isinstance(nested, (dict, list)):
                    stack.append(nested)
        elif isinstance(item, list):
            stack.extend(item)
    return found


def _find_first(value: Any, keys: tuple[str, ...]) -> Any:
    for item in _find_values(value, keys):
        if item not in (None, "") and not isinstance(item, (dict, list)):
            return item
    return None


def _numeric_values(value: Any, keys: tuple[str, ...]) -> list[float]:
    out: list[float] = []
    for raw in _find_values(value, keys):
        if isinstance(raw, dict):
            continue
        try:
            out.append(float(raw))
        except (TypeError, ValueError):
            pass
    return out


def _same_number(left: Any, right: Any) -> bool:
    try:
        a, b = float(left), float(right)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(1e-9, abs(a) * 1e-9, abs(b) * 1e-9)


def _action_intent(a: Action) -> dict[str, bool]:
    action = _norm(a.action_type)
    tool = _norm(a.tool_name)
    field = _norm(a.arguments.get("field") or "")
    return {
        "create": action.startswith("create") or any(token in tool for token in ("create", "add")),
        "bid": "bid" in action or field == "bid" or bool(_find_values(a.arguments, ("bid", "newBid", "bidAmount"))),
        "budget": "budget" in action or field == "budget" or bool(_find_values(a.arguments, ("budget", "dailyBudget", "budgetAmount"))),
        "placement": "placement" in action or field in {"placement", "placementpct"} or bool(_find_values(a.arguments, ("percentage", "adjustmentPercent", "adjustment_percentage", "placementPercentage", "placement_pct"))),
        "state": any(token in action for token in ("pause", "enable", "resume", "state")) or bool(_find_values(a.arguments, ("state", "status"))),
        "negative": "negative" in action or "negative" in tool,
    }


def _tool_contract_reasons(a: Action) -> list[str]:
    reasons: list[str] = []
    tool = str(a.tool_name or "")
    if tool.startswith("mcp__"):
        return ["tool_name must be the bare amazon_ads MCP tool name"]
    lower, action, entity = _norm(tool), _norm(a.action_type), _norm(a.entity_type)
    if not lower:
        return ["missing exact MCP tool_name"]
    if any(token in lower for token in ("delete", "archive", "permanentdelete", "closeaccount")):
        reasons.append("MCP tool is destructive and outside autonomous contract")
    create_action = action.startswith("create")
    create_tool = any(token in lower for token in ("create", "add"))
    if create_action and not create_tool:
        reasons.append("create action is not bound to a create/add MCP tool")
    if not create_action and create_tool:
        reasons.append("non-create action cannot use a create/add MCP tool")
    if not any(token in lower for token in _MUTATION_TOKENS):
        reasons.append("action is not bound to a mutation-capable MCP tool name")
    aliases = {
        "adgroup": ("adgroup", "adgroups"),
        "campaign": ("campaign", "campaigns"),
        "keyword": ("keyword", "keywords"),
        "target": ("target", "targets"),
        "ad": ("ad", "ads", "productad", "productads"),
    }
    options = aliases.get(entity, (entity,)) if entity else ()
    if not options:
        reasons.append("MCP tool cannot be bound without entity_type")
    elif not any(option in lower for option in options):
        reasons.append("MCP tool family does not match action entity_type")
    if "negative" in action and "negative" not in lower:
        reasons.append("negative action requires a negative-targeting MCP tool")
    return reasons


def _argument_intent_reasons(a: Action, context: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    intent = _action_intent(a)
    owner_profiles = {str(value) for value in context.get("_owner_profile_ids", []) if str(value)}
    seen_profiles = {
        item
        for value in _find_values(a.arguments, ("profileId", "profile_id", "profileIds", "profile_ids"))
        for item in _scalar_values(value)
    }
    if seen_profiles and not seen_profiles.issubset(owner_profiles):
        reasons.append("MCP arguments reference a profile outside Owner scope")

    owner_account = str(context.get("_owner_advertiser_account_id") or "")
    seen_accounts = {
        item
        for value in _find_values(a.arguments, ("accountId", "account_id", "advertiserAccountId", "advertiser_account_id"))
        for item in _scalar_values(value)
    }
    if seen_accounts and (not owner_account or seen_accounts != {owner_account}):
        reasons.append("MCP arguments reference an account outside Owner scope")

    seen_products = {
        item.upper()
        for value in _find_values(a.arguments, ("adProduct", "ad_product", "adProducts", "ad_products"))
        for item in _scalar_values(value)
    }
    if seen_products and seen_products != {"SPONSORED_PRODUCTS"}:
        reasons.append("MCP arguments reference an ad product outside Sponsored Products")

    managed = {str(value).upper() for value in context.get("_owner_managed_asins", []) if str(value)}
    seen_asins = {
        item.upper()
        for value in _find_values(a.arguments, ("asin", "asins", "advertisedAsin", "advertised_asin", "advertisedProductAsin"))
        for item in _scalar_values(value)
    }
    if managed and seen_asins and not seen_asins.issubset(managed):
        reasons.append("MCP arguments contain ASIN outside Owner managed-ASIN scope")

    if not intent["create"] and a.entity_type:
        keys = _ENTITY_IDS.get(a.entity_type.lower(), ())
        ids = {
            item for value in _find_values(a.arguments, keys) for item in _scalar_values(value)
        } if keys else set()
        if keys and not ids:
            reasons.append("MCP arguments do not contain the declared entity_id")
        elif ids and ids != {str(a.entity_id)}:
            reasons.append("MCP arguments do not target exactly the declared entity_id")

    if intent["bid"]:
        expected = a.after.get("bid")
        values = _numeric_values(a.arguments, ("bid", "newBid", "bidAmount"))
        if expected is None or not values or any(not _same_number(value, expected) for value in values):
            reasons.append("MCP bid arguments do not equal sealed after.bid")
    if intent["budget"]:
        expected = a.after.get("budget")
        values = _numeric_values(a.arguments, ("budget", "dailyBudget", "budgetAmount"))
        if expected is None or not values or any(not _same_number(value, expected) for value in values):
            reasons.append("MCP budget arguments do not equal sealed after.budget")
    if intent["state"]:
        expected = str(a.after.get("state") or "").upper()
        values = [
            item.upper()
            for value in _find_values(a.arguments, ("state", "status"))
            for item in _scalar_values(value)
        ]
        if not expected or not values or any(value != expected for value in values):
            reasons.append("MCP state arguments do not equal sealed after.state")
    if intent["placement"]:
        expected = a.after.get("placement_pct")
        values = _numeric_values(
            a.arguments,
            ("percentage", "adjustmentPercent", "adjustment_percentage", "placementPercentage", "placement_pct"),
        )
        if expected is None or not values or any(not _same_number(value, expected) for value in values):
            reasons.append("MCP placement arguments do not equal sealed after.placement_pct")
    return reasons


def _blocked_argument_signal(value: Any, blocked: str) -> bool:
    control_keys = {
        "operation", "action", "resource", "resourcetype", "entitytype",
        "endpoint", "path", "scope", "permission",
    }
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, nested in item.items():
                norm = "".join(
                    char for char in str(key).lower() if char.isalnum() or char == "_"
                )
                if blocked in norm:
                    return True
                if norm.replace("_", "") in control_keys and blocked in str(nested).lower():
                    return True
                if isinstance(nested, (dict, list)):
                    stack.append(nested)
        elif isinstance(item, list):
            stack.extend(item)
    return False


def _number(value: Any) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _campaign_budget(a: Action) -> float:
    return _number(
        _find_first(a.arguments, ("budget", "dailyBudget", "budgetAmount"))
        or a.after.get("budget")
    )


def _positive_budget_delta(a: Action) -> float:
    intent = _action_intent(a)
    if not intent["budget"] or intent["create"]:
        return 0.0
    try:
        return max(0.0, float(a.after["budget"]) - float(a.before["budget"]))
    except (KeyError, TypeError, ValueError):
        return 0.0


def _is_enable_campaign(a: Action) -> bool:
    if _norm(a.entity_type) != "campaign":
        return False
    desired = str(
        a.after.get("state")
        or _find_first(a.arguments, ("state", "status"))
        or ""
    ).upper()
    return not _action_intent(a)["create"] and _action_intent(a)["state"] and desired == "ENABLED"


def _spend_expanding(a: Action) -> bool:
    intent = _action_intent(a)
    if intent["negative"]:
        return False
    if intent["budget"] and not intent["create"]:
        try:
            return float(a.after.get("budget")) > float(a.before.get("budget"))
        except (TypeError, ValueError):
            return True
    if intent["bid"] and not intent["create"]:
        try:
            return float(a.after.get("bid")) > float(a.before.get("bid"))
        except (TypeError, ValueError):
            return True
    if intent["placement"] and not intent["create"]:
        try:
            return float(a.after.get("placement_pct")) > float(a.before.get("placement_pct"))
        except (TypeError, ValueError):
            return True
    if intent["state"] and not intent["create"]:
        desired = str(a.after.get("state") or "").upper()
        return desired in {"ENABLED", "ENABLE", "ACTIVE", "RESUMED", "RESUME"}
    if intent["create"]:
        if _norm(a.entity_type) == "campaign":
            desired = str(
                a.after.get("state")
                or _find_first(a.arguments, ("state", "status"))
                or ""
            ).upper()
            return desired not in {"PAUSED", "PAUSE"}
        # Ad-group/target/keyword/product-ad creation may unlock delivery inside
        # an already active campaign and is therefore conservatively expanding.
        return True
    return False


def _unknown_spend_expansion(a: Action) -> bool:
    intent = _action_intent(a)
    return _spend_expanding(a) and not (intent["budget"] and not intent["create"])


def _action_family(a: Action) -> str:
    intent = _action_intent(a)
    if intent["budget"]:
        return "budget"
    if intent["bid"]:
        return "bid"
    if intent["placement"]:
        return "placement"
    if intent["negative"]:
        return "negative"
    if intent["create"]:
        return "create"
    if intent["state"]:
        return "state"
    return _norm(a.action_type) or "other"
