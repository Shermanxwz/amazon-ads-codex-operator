from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_learning_snapshot_is_a_required_planner_contract():
    schema = json.loads((ROOT / "schemas/plan.schema.json").read_text())
    assert "learning_snapshot" in schema["required"]
    learning = schema["properties"]["learning_snapshot"]
    assert learning["properties"]["entities"]["maxItems"] >= 1000
    assert set(learning["required"]) == {"observed_at", "entities", "economics", "portfolio_candidates", "experiments"}


def test_strategy_prompt_is_profit_portfolio_and_sp_native():
    prompt = (ROOT / "prompts/observe_plan.md").read_text().lower()
    for token in (
        "incremental contribution profit",
        "opportunity cost",
        "search-term mining",
        "rest of search",
        "amazon business",
        "search term impression share",
        "audience bid boosting",
        "sponsored products video",
        "amazon marketing stream",
        "experiments and causal learning",
        "exploration capital",
    ):
        assert token in prompt
    assert "do not hoard authorized budget" in prompt


def test_production_cycle_uses_optimization_controller_without_new_approval_gate():
    run_cycle = (ROOT / "scripts/run_cycle.py").read_text()
    controller = (ROOT / "src/ads_autopilot/optimization_controller.py").read_text()
    assert "OptimizationController(ROOT).run" in run_cycle
    assert "optimization_observer" in controller
    assert "retains normal Owner-granted autonomy" in controller
    assert "human approval" not in controller.lower()


def test_owner_economics_format_is_explicit_and_optional():
    doc = json.loads((ROOT / "config/economics.example.json").read_text())
    assert doc["version"] == 1
    asin = next(iter(doc["asins"].values()))
    assert "contribution_margin_pct" in asin
    assert "return_rate_pct" in asin
    assert "inventory_units" in asin
