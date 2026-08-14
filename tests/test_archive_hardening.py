from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from ads_autopilot.codex_runner import _enforce_verification
from ads_autopilot.ledger import BudgetLedger
from ads_autopilot.models import Action
from ads_autopilot.owner_store import OwnerStore
from ads_autopilot.policy import PolicyEngine
from ads_autopilot.security import hash_password
from ads_autopilot.state import Store

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def policy() -> PolicyEngine:
    data = json.loads((ROOT / "config/autonomy-policy.json").read_text())
    data["money"]["owner_daily_spend_ceiling"] = 1000.0
    data["scope"]["cooldown_hours"] = 0
    return PolicyEngine(data)


def bid_action(**updates) -> Action:
    base = dict(
        action_id="a1",
        action_type="update_keyword",
        tool_name="updateKeywords",
        ad_product="SPONSORED_PRODUCTS",
        entity_type="keyword",
        entity_id="K1",
        arguments={"keywordId": "K1", "bid": 1.2},
        before={"bid": 1.0},
        after={"bid": 1.2},
        spend_delta=0.0,
        confidence=0.95,
        evidence_refs=("amazon:keyword:K1",),
        dependencies=(),
        reversible=True,
        rollback={"bid": 1.0},
        prewrite_observed_at=datetime.now(UTC).isoformat(),
    )
    base.update(updates)
    return Action(**base)


def context() -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "today_spend": 10.0,
        "today_spend_observed_at": now,
        "today_spend_evidence_ref": "amazon:today-spend",
        "active_campaign_budget_total": 100.0,
        "observed_asins": [],
        "_owner_profile_ids": ["P1"],
        "_owner_advertiser_account_id": "A1",
        "_owner_managed_asins": [],
    }


def test_empty_before_cannot_skip_existing_entity_guard():
    decision = policy().evaluate_action(bid_action(before={}), context=context())
    assert not decision.allowed
    assert any("before-state" in reason for reason in decision.reasons)


def test_generic_action_name_does_not_hide_bid_semantics():
    decision = policy().evaluate_action(bid_action(action_type="update_keyword"), context=context())
    assert decision.allowed, decision.reasons
    bad = policy().evaluate_action(
        bid_action(action_type="update_keyword", after={"bid": 50.0}, arguments={"keywordId": "K1", "bid": 50.0}),
        context=context(),
    )
    assert not bad.allowed
    assert any("bid change" in reason or "bid outside" in reason for reason in bad.reasons)


def test_model_zero_spend_delta_cannot_remove_plan_reservation(tmp_path: Path):
    store = Store(tmp_path / "runtime.db")
    store.create_cycle("c1", "daily")
    decisions = policy().evaluate_plan(
        [bid_action(spend_delta=0.0)],
        context=context(),
        store=store,
        timezone_name="UTC",
        cycle_id="c1",
    )
    assert decisions[0].allowed, decisions[0].reasons
    # Worst-case Sponsored Ads overdelivery is 2x average daily budgets:
    # 2*100 active budget - 10 already observed = 190 remaining exposure.
    assert decisions[0].spend_reservation >= 190.0


def test_exact_budget_increase_reserves_twice_delta_for_high_traffic_day(tmp_path: Path):
    store = Store(tmp_path / "runtime.db")
    store.create_cycle("budget-cycle", "daily")
    action = bid_action(
        action_type="update_budget",
        tool_name="updateCampaigns",
        entity_type="campaign",
        entity_id="C1",
        arguments={"campaignId": "C1", "budget": 120.0},
        before={"budget": 100.0},
        after={"budget": 120.0},
        spend_delta=0.0,
    )
    decisions = policy().evaluate_plan(
        [action], context=context(), store=store, timezone_name="UTC", cycle_id="budget-cycle"
    )
    assert decisions[0].allowed, decisions[0].reasons
    assert decisions[0].spend_reservation == 40.0


def test_create_paused_campaign_does_not_require_state_change_authority():
    engine = policy()
    engine.data["autonomy"]["allow_state_changes"] = False
    action = bid_action(
        action_type="create_campaign",
        tool_name="createCampaigns",
        entity_type="campaign",
        entity_id="new",
        arguments={"name": "CODEX-new", "state": "PAUSED", "budget": 25.0},
        before={},
        after={"name": "CODEX-new", "state": "PAUSED", "budget": 25.0},
        spend_delta=0.0,
    )
    decision = engine.evaluate_action(action, context=context())
    assert decision.allowed, decision.reasons


def test_hourly_bid_cap_is_actually_enforced(tmp_path: Path):
    store = Store(tmp_path / "runtime.db")
    store.create_cycle("hourly-cycle", "hourly")
    decisions = policy().evaluate_plan(
        [bid_action()],
        context=context(),
        store=store,
        timezone_name="UTC",
        cycle_id="hourly-cycle",
    )
    assert not decisions[0].allowed
    assert any("bid change exceeds" in reason for reason in decisions[0].reasons)


def test_verifier_cannot_claim_verified_over_deterministic_mismatch():
    payload = {
        "cycle_id": "c",
        "sealed_actions": [{"action_hash": "h", "after": {"bid": 1.2}}],
        "execution_receipt": {},
    }
    raw = {
        "cycle_id": "c",
        "results": [
            {
                "action_hash": "h",
                "status": "verified",
                "observed": {"bid": 2.0},
                "differences": [],
            }
        ],
    }
    value, verified = _enforce_verification(
        "verifier", "VERIFY\n\nINPUT_JSON:\n" + json.dumps(payload), raw
    )
    assert not verified
    assert value["results"][0]["status"] == "mismatch"
    assert any("bid" in diff for diff in value["results"][0]["differences"])


def _minimal_owner_db(path: Path, timezone_name: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE owner_documents(kind TEXT PRIMARY KEY, body_json TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO owner_documents(kind,body_json) VALUES('operator',?)",
            (json.dumps({"timezone": timezone_name}),),
        )


def test_ledger_uses_owner_timezone_and_expires_never_executed_hold(tmp_path: Path):
    _minimal_owner_db(tmp_path / "owner.db", "Asia/Singapore")
    store = Store(tmp_path / "runtime.db")
    data = json.loads((ROOT / "config/autonomy-policy.json").read_text())
    data["money"]["owner_daily_spend_ceiling"] = 100.0
    ledger = BudgetLedger(store, data)
    boundary = datetime(2026, 8, 13, 16, 30, tzinfo=UTC)
    assert ledger.day_key(boundary) == "2026-08-14"
    ledger.reserve("orphan", 10.0, 0.0)
    with store.connection() as conn:
        conn.execute(
            "UPDATE reservations SET expires_at=? WHERE action_hash='orphan'",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),),
        )
    assert ledger.reserved_total() == 0.0
    with store.connection() as conn:
        status = conn.execute(
            "SELECT status FROM reservations WHERE action_hash='orphan'"
        ).fetchone()["status"]
    assert status == "expired"


def test_dashboard_reservation_day_uses_owner_timezone(tmp_path: Path):
    _minimal_owner_db(tmp_path / "owner.db", "America/Los_Angeles")
    store = Store(tmp_path / "runtime.db")
    expected = datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
    assert store.reservation_summary()["day_key"] == expected


def test_historical_campaign_creation_is_counted_by_semantics_not_only_label(tmp_path: Path):
    store = Store(tmp_path / "runtime.db")
    store.create_cycle("c", "daily")
    store.add_action(
        "c",
        {
            "action_hash": "h",
            "action_id": "legacy",
            "action_type": "create_structure",
            "tool_name": "createCampaigns",
            "entity_type": "campaign",
            "entity_id": "new",
            "arguments": {"budget": 25, "state": "PAUSED", "name": "CODEX-legacy"},
            "after": {"budget": 25, "state": "PAUSED"},
            "signature": "s",
        },
    )
    count, budget = store.campaign_creates_today("UTC")
    assert count == 1
    assert budget == 25.0


def test_owner_boolean_and_numeric_fields_are_strictly_typed(tmp_path: Path):
    store = OwnerStore(tmp_path / "strict-owner.db", b"k" * 32)
    owner_policy = json.loads((ROOT / "config/autonomy-policy.json").read_text())
    operator = json.loads((ROOT / "config/operator.example.json").read_text())
    store.bootstrap(owner_policy, operator, hash_password("correct horse battery staple"))
    with pytest.raises(ValueError, match="hourly_pacing must be boolean"):
        store.update_operator({"scheduling.hourly_pacing": "false"})
    with pytest.raises(ValueError, match="max_actions_per_cycle must be an integer"):
        store.update_policy({"scope.max_actions_per_cycle": True})
