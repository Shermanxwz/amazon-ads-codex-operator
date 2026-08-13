from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ads_autopilot.optimization_memory import OptimizationMemory


class Store:
    def __init__(self, path: Path):
        self.path = path
        with self.connection() as c:
            c.executescript(
                """
                CREATE TABLE actions(action_hash TEXT PRIMARY KEY,cycle_id TEXT NOT NULL,action_id TEXT NOT NULL,action_type TEXT NOT NULL,payload_json TEXT NOT NULL,status TEXT NOT NULL,spend_delta REAL NOT NULL DEFAULT 0);
                CREATE TABLE verifications(id INTEGER PRIMARY KEY AUTOINCREMENT,action_hash TEXT NOT NULL,status TEXT NOT NULL,observed_json TEXT NOT NULL);
                """
            )

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()


def snapshot():
    return {
        "operator": {
            "objectives": {
                "primary": "contribution_profit",
                "break_even_acos_pct": 35.0,
            }
        }
    }


def test_learning_context_builds_bayesian_profit_signals(tmp_path):
    store = Store(tmp_path / "runtime.db")
    economics = tmp_path / "economics.json"
    economics.write_text(json.dumps({"version": 1, "asins": {"B0TEST": {"contribution_margin_pct": 50.0, "return_rate_pct": 0}}}))
    memory = OptimizationMemory(store, economics)
    plan = {
        "learning_snapshot": {
            "observed_at": "2026-08-13T07:00:00Z",
            "entities": [
                {
                    "profile_id": "p1", "entity_type": "keyword", "entity_id": "k-high", "campaign_id": "c1", "asin": "B0TEST", "query": "alpha", "window_label": "30d", "window_start": "2026-07-14", "window_end": "2026-08-12", "impressions": 5000, "clicks": 100, "spend": 100, "orders": 20, "sales": 800, "impression_share_pct": 25, "evidence_ref": "report:k-high"
                },
                {
                    "profile_id": "p1", "entity_type": "keyword", "entity_id": "k-low", "campaign_id": "c1", "asin": "B0TEST", "query": "beta", "window_label": "30d", "window_start": "2026-07-14", "window_end": "2026-08-12", "impressions": 400, "clicks": 4, "spend": 6, "orders": 1, "sales": 40, "impression_share_pct": 10, "evidence_ref": "report:k-low"
                },
            ],
            "economics": [],
            "portfolio_candidates": [],
            "experiments": [],
        }
    }
    counts = memory.ingest_plan("cycle-1", plan)
    assert counts["observations"] == 2
    context = memory.planner_context(snapshot())
    assert context["economics_mode"] == "owner_economics"
    by_id = {x["entity_id"]: x for x in context["entity_signals"]}
    assert by_id["k-high"]["posture"] == "scale"
    assert by_id["k-high"]["evidence_confidence"] > by_id["k-low"]["evidence_confidence"]
    assert by_id["k-high"]["expected_profit_per_ad_dollar"] > 0


def test_break_even_acos_proxy_keeps_optimizer_useful_without_economics(tmp_path):
    store = Store(tmp_path / "runtime.db")
    memory = OptimizationMemory(store)
    memory.ingest_plan("cycle-1", {"learning_snapshot": {"observed_at": "2026-08-13T07:00:00Z", "entities": [{"profile_id": "p1", "entity_type": "campaign", "entity_id": "c1", "window_label": "30d", "impressions": 1000, "clicks": 50, "spend": 100, "orders": 10, "sales": 500, "evidence_ref": "campaign-report"}], "economics": [], "portfolio_candidates": [], "experiments": []}})
    context = memory.planner_context(snapshot())
    assert context["economics_mode"] == "break_even_acos_proxy"
    assert context["entity_signals"][0]["margin_mode"] == "break_even_acos_proxy"
    assert context["entity_signals"][0]["expected_profit_per_ad_dollar"] > 0


def test_candidates_experiments_and_action_outcomes_are_persistent(tmp_path):
    store = Store(tmp_path / "runtime.db")
    memory = OptimizationMemory(store)
    plan = {
        "learning_snapshot": {
            "observed_at": "2026-08-13T07:00:00Z",
            "entities": [{"profile_id": "p1", "entity_type": "keyword", "entity_id": "k1", "window_label": "30d", "impressions": 1000, "clicks": 100, "spend": 100, "orders": 20, "sales": 500, "evidence_ref": "r1"}],
            "economics": [],
            "portfolio_candidates": [{"candidate_id": "scale-k1", "entity_type": "keyword", "entity_id": "k1", "hypothesis": "more profitable traffic available", "expected_incremental_spend": 20, "expected_incremental_sales": 80, "expected_incremental_profit": 8, "uncertainty": 0.2, "horizon_days": 7, "evidence_refs": ["r1"]}],
            "experiments": [{"experiment_id": "exp-k1", "hypothesis": "bid increase expands profitable volume", "action_ids": ["a1"], "entity_type": "keyword", "entity_id": "k1", "primary_metric": "roas", "expected_direction": "increase", "baseline_window_days": 14, "evaluation_days": 7, "evidence_refs": ["r1"]}],
        }
    }
    counts = memory.ingest_plan("cycle-1", plan)
    assert counts["candidates"] == 1
    assert counts["experiments"] == 1
    payload = {"entity_type": "keyword", "entity_id": "k1", "before": {"bid": 1}, "after": {"bid": 1.2}, "rationale": "test"}
    with store.connection() as c:
        c.execute("INSERT INTO actions VALUES(?,?,?,?,?,?,?)", ("h1", "cycle-1", "a1", "update_bid", json.dumps(payload), "verified", 2.0))
        c.execute("INSERT INTO verifications(action_hash,status,observed_json) VALUES(?,?,?)", ("h1", "verified", json.dumps({"bid": 1.2})))
    assert memory.capture_action_outcomes("cycle-1") == 1
    context = memory.planner_context(snapshot())
    assert context["learning_maturity"]["outcomes"] == 1
    assert context["learning_maturity"]["experiments"] == 1
    assert context["planner_portfolio_candidates"][0]["candidate_id"] == "scale-k1"


def test_ingest_is_idempotent_for_same_cycle_snapshot(tmp_path):
    store = Store(tmp_path / "runtime.db")
    memory = OptimizationMemory(store)
    plan = {"learning_snapshot": {"observed_at": "2026-08-13T07:00:00Z", "entities": [{"profile_id": "p1", "entity_type": "keyword", "entity_id": "k1", "window_label": "7d", "clicks": 10, "orders": 1, "spend": 5, "sales": 20, "evidence_ref": "r1"}], "economics": [], "portfolio_candidates": [], "experiments": []}}
    assert memory.ingest_plan("cycle-1", plan)["observations"] == 1
    assert memory.ingest_plan("cycle-1", plan)["observations"] == 0
    assert memory.ingest_plan("observer-2", plan)["observations"] == 0
    assert memory.planner_context(snapshot())["learning_maturity"]["observations"] == 1


def test_owner_cost_stack_derives_real_contribution_margin(tmp_path):
    store = Store(tmp_path / "runtime.db")
    economics = tmp_path / "economics.json"
    economics.write_text(json.dumps({"version": 1, "asins": {"B0COST": {"unit_cogs": 20.0, "amazon_fees": 10.0, "promo_cost_per_order": 5.0, "return_rate_pct": 0}}}))
    memory = OptimizationMemory(store, economics)
    memory.ingest_plan("cycle-1", {"learning_snapshot": {"observed_at": "2026-08-13T07:00:00Z", "entities": [{"profile_id": "p1", "entity_type": "advertised_product", "entity_id": "B0COST", "asin": "B0COST", "window_label": "30d", "impressions": 1000, "clicks": 100, "spend": 100, "orders": 10, "units": 10, "sales": 1000, "evidence_ref": "asin-report"}], "economics": [], "portfolio_candidates": [], "experiments": []}})
    signal = memory.planner_context(snapshot())["entity_signals"][0]
    assert signal["margin_mode"] == "owner_cost_stack"
    # $100 AOV - $20 COGS - $10 fees - $5 promo = $65 pre-ad contribution/order.
    assert signal["expected_profit_per_ad_dollar"] > 4.0


def test_query_routing_harvest_and_next_dollar_frontier(tmp_path):
    store = Store(tmp_path / "runtime.db")
    memory = OptimizationMemory(store)
    snapshot_rows = [
        {"profile_id":"p1","entity_type":"search_term","entity_id":"s1","campaign_id":"c-auto","query":"red widget","window_label":"30d","impressions":2000,"clicks":50,"spend":30,"orders":8,"sales":320,"evidence_ref":"s1"},
        {"profile_id":"p1","entity_type":"keyword","entity_id":"k-broad","campaign_id":"c-manual","query":"red widget","keyword_text":"red widgets","match_type":"BROAD","window_label":"30d","impressions":1000,"clicks":20,"spend":25,"orders":2,"sales":80,"evidence_ref":"k1"},
        {"profile_id":"p1","entity_type":"search_term","entity_id":"s-waste","campaign_id":"c-auto","query":"free widget","window_label":"30d","impressions":800,"clicks":20,"spend":22,"orders":0,"sales":0,"evidence_ref":"s2"},
    ]
    memory.ingest_plan("cycle-1", {"learning_snapshot":{"observed_at":"2026-08-13T07:00:00Z","entities":snapshot_rows,"economics":[],"portfolio_candidates":[],"experiments":[]}})
    context = memory.planner_context(snapshot())
    assert context["query_conflicts"][0]["query"] == "red widget"
    assert context["harvest_candidates"][0]["query"] == "red widget"
    assert context["waste_candidates"][0]["query"] == "free widget"
    assert context["next_dollar_frontier"]


def test_inventory_and_offer_readiness_are_economic_signals_not_authority_gates(tmp_path):
    store = Store(tmp_path / "runtime.db")
    economics = tmp_path / "economics.json"
    economics.write_text(json.dumps({"version":1,"asins":{"B0LOW":{"contribution_margin_pct":60,"inventory_units":2}}}))
    memory = OptimizationMemory(store, economics)
    memory.ingest_plan("cycle-1", {"learning_snapshot":{"observed_at":"2026-08-13T07:00:00Z","entities":[{"profile_id":"p1","entity_type":"advertised_product","entity_id":"B0LOW","asin":"B0LOW","window_label":"30d","impressions":2000,"clicks":100,"spend":100,"orders":30,"units":30,"sales":1000,"featured_offer_eligible":False,"in_stock":True,"evidence_ref":"asin"}],"economics":[],"portfolio_candidates":[],"experiments":[]}})
    signal = memory.planner_context(snapshot())["entity_signals"][0]
    assert signal["inventory_days_proxy"] < 7
    assert signal["retail_readiness_factor"] < 1
    assert signal["expected_profit_per_ad_dollar"] > 0
    # The model is advisory: no allowed/blocked/approval field exists in the signal.
    assert "allowed" not in signal and "approval" not in signal
