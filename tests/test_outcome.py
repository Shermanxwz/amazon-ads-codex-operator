from ads_autopilot.outcome import parse_outcome

def test_executor_success_without_raw_proof_is_unknown():
    o=parse_outcome({'status':'success','result':{'campaignId':'123'}}); assert o.status=='unknown'

def test_raw_explicit_success_allows_success():
    o=parse_outcome({'status':'success','result':{'status':'SUCCESS','campaignId':'123'}}); assert o.status=='success'

def test_raw_failure_overrides_executor_success():
    o=parse_outcome({'status':'success','result':{'status':'FAILED','error':'no'}}); assert o.status=='failure'
