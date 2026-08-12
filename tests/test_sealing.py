from ads_autopilot.sealing import Sealer

def test_seal_exact_payload_binding():
    s=Sealer(b'secret'); row=s.seal_action({'action_id':'a','arguments':{'bid':1.2}},policy_hash='p',plan_hash='x',operator_hash='o')
    sig=row.pop('signature'); assert s.verify(row,sig)
    row['arguments']['bid']=1.3; assert not s.verify(row,sig)
