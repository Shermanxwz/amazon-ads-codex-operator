from ads_autopilot.controller import _one_receipt

def test_atomic_receipt_requires_exact_tool_name():
    receipt={'cycle_id':'c','results':[{'action_hash':'h','status':'success','tool_name':'wrong','result':{},'error':None}]}
    _,problem=_one_receipt(receipt,'c','h','updateCampaigns')
    assert problem and 'tool' in problem
