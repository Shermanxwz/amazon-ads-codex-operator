from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from ads_autopilot.direct_policy import DirectPolicyEngine
from ads_autopilot.models import Action
from ads_autopilot.owner_override import OwnerOverrideStore
from ads_autopilot.policy import PolicyEngine
from ads_autopilot.security import hash_password

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def defaults():
    return (json.loads((ROOT / "config/autonomy-policy.json").read_text()), json.loads((ROOT / "config/operator.example.json").read_text()))


def ready_store(tmp_path: Path) -> OwnerOverrideStore:
    policy, operator = defaults(); store = OwnerOverrideStore(tmp_path / "owner.db", b"k" * 32)
    store.bootstrap(policy, operator, hash_password("correct horse battery staple")); store.update_operator({"advertiser_account_id": "A1", "profile_ids": ["P1"]}); return store


def direct_action(**updates) -> Action:
    base = dict(action_id="direct-1", action_type="archive_campaign", tool_name="updateCampaigns", ad_product="SPONSORED_PRODUCTS", entity_type="campaign", entity_id="C1", arguments={"campaignId": "C1", "state": "ARCHIVED"}, before={"state": "ENABLED"}, after={"state": "ARCHIVED"}, spend_delta=1000000, confidence=0.0, evidence_refs=("owner-direct:test",), dependencies=(), reversible=False, rollback={}, prewrite_observed_at=datetime.now(UTC).isoformat()); base.update(updates); return Action(**base)


def test_direct_window_arms_without_normal_money_ceiling_and_returns_to_prior_mode(tmp_path: Path):
    store = ready_store(tmp_path); before = store.snapshot(); assert before["mode"] == "observe"; assert before["policy"]["money"]["owner_daily_spend_ceiling"] is None
    armed = store.arm_direct_override("30m"); assert armed["mode"] == "autopilot"; assert armed["direct_override"]["armed"]; assert armed["direct_override"]["return_mode"] == "observe"; assert armed["direct_override"]["expires_at"]
    cleared = store.clear_direct_override(); assert not cleared["direct_override"]["armed"]; assert cleared["mode"] == "observe"; assert store.verify_audit_chain()["ok"]


def test_direct_command_gets_root_ad_policy_but_not_account_admin(tmp_path: Path):
    store = ready_store(tmp_path); store.arm_direct_override("1h"); command = store.begin_direct_command("Archive campaign C1 now, regardless of normal automation caps."); snapshot = store.snapshot(); direct = snapshot["policy"]["owner_direct_override"]
    assert direct["active"] and direct["generation"] == command["generation"]
    context = {"_owner_profile_ids": ["P1"], "_owner_advertiser_account_id": "A1", "_owner_managed_asins": ["B0LOCKED"]}
    normal = PolicyEngine.from_dict(snapshot["policy"]).evaluate_action(direct_action(), context=context); assert not normal.allowed
    decision = DirectPolicyEngine.from_dict(snapshot["policy"]).evaluate_action(direct_action(), context=context); assert decision.allowed, decision.reasons; assert decision.spend_reservation == 0
    blocked = DirectPolicyEngine.from_dict(snapshot["policy"]).evaluate_action(direct_action(action_type="delete_account", tool_name="deleteAccount", entity_type="account", entity_id="A1", arguments={"accountId": "A1"}, before={"status": "OPEN"}, after={"status": "DELETED"}), context=context); assert not blocked.allowed
    store.finish_direct_command(command["generation"]); assert "owner_direct_override" not in store.snapshot()["policy"]


def test_expiry_and_emergency_stop_revoke_direct_authority(tmp_path: Path):
    store = ready_store(tmp_path); store.arm_direct_override("2h")
    with store.connection() as c: c.execute("UPDATE owner_direct_override SET expires_at=? WHERE id=1", ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),))
    expired = store.snapshot(); assert not expired["direct_override"]["armed"]; assert expired["mode"] == "observe"
    permanent = store.arm_direct_override("permanent"); assert permanent["direct_override"]["permanent"]
    stopped = store.emergency_stop(); assert stopped["emergency_stop"]; assert stopped["mode"] == "paused"; assert not stopped["direct_override"]["armed"]


def test_mode_switch_clears_permanent_window_and_old_command_generation(tmp_path: Path):
    store = ready_store(tmp_path); store.arm_direct_override("permanent"); command = store.begin_direct_command("Set campaign C1 budget to whatever I specify."); old_revision = store.snapshot()["policy_revision"]
    changed = store.set_mode("observe"); assert changed["mode"] == "observe"; assert not changed["direct_override"]["armed"]; assert changed["policy_revision"] > old_revision
    finished = store.finish_direct_command(command["generation"]); assert not finished["armed"]


def test_model_cannot_start_direct_command_until_owner_arms_window(tmp_path: Path):
    store = ready_store(tmp_path)
    with pytest.raises(ValueError, match="not armed"): store.begin_direct_command("Do a special write")


def test_direct_executor_grant_never_outlives_authorization_window(tmp_path: Path):
    from ads_autopilot.override_controller import OwnerOverrideOptimizationController
    from ads_autopilot.paths import RuntimePaths
    from ads_autopilot.sealing import bootstrap_key, Sealer
    owner_home = tmp_path / "grant-owner"; paths = RuntimePaths.resolve(ROOT, owner_home); paths.ensure_directories(); bootstrap_key(paths.signing_key)
    policy, operator = defaults(); store = OwnerOverrideStore(paths.owner_db, Sealer.from_path(paths.signing_key).key); store.bootstrap(policy, operator, hash_password("correct horse battery staple")); store.update_operator({"advertiser_account_id": "A1", "profile_ids": ["P1"]}); store.arm_direct_override("30m"); command = store.begin_direct_command("Set campaign C1 budget to 500.")
    controller = OwnerOverrideOptimizationController(ROOT, owner_home); snapshot = controller.owner.snapshot()
    sealed = {"action_hash": "a" * 64, "tool_name": "updateCampaigns", "arguments": {"campaignId": "C1", "budget": 500}, "policy_revision": snapshot["policy_revision"], "policy_hash": snapshot["policy_hash"], "operator_revision": snapshot["operator_revision"], "operator_hash": snapshot["operator_hash"]}
    grant_path = controller._write_executor_grant(sealed); grant = json.loads(grant_path.read_text()); grant_expiry = datetime.fromisoformat(grant["expires_at"].replace("Z", "+00:00")); window_expiry = datetime.fromisoformat(snapshot["direct_override"]["expires_at"].replace("Z", "+00:00")); assert grant_expiry <= window_expiry
    store.finish_direct_command(command["generation"])
