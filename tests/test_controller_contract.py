from ads_autopilot.controller import _one_receipt, _state_differences


def test_atomic_receipt_requires_exact_tool_name():
    receipt = {
        "cycle_id": "c",
        "results": [
            {
                "action_hash": "h",
                "status": "success",
                "tool_name": "wrong",
                "result": {},
                "error": None,
            }
        ],
    }
    _, problem = _one_receipt(receipt, "c", "h", "updateCampaigns")
    assert problem and "tool" in problem


def test_fresh_state_comparison_is_expected_subset():
    expected = {"bid": 1.1, "state": "ENABLED"}
    observed = {
        "bid": "1.10",
        "state": "ENABLED",
        "campaignId": "123",
        "name": "CODEX-test",
    }
    assert _state_differences(expected, observed) == []


def test_fresh_state_comparison_detects_missing_or_changed_values():
    expected = {"budget": 20.0, "state": "PAUSED"}
    observed = {"budget": 25.0}
    differences = _state_differences(expected, observed)
    assert any("budget" in item and "25" in item for item in differences)
    assert any("state" in item and "missing" in item for item in differences)


def test_fresh_state_list_comparison_is_order_independent():
    expected = {"targets": [{"id": "1"}, {"id": "2"}]}
    observed = {"targets": [{"id": "2"}, {"id": "1"}]}
    assert _state_differences(expected, observed) == []
