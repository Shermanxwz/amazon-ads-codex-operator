from pathlib import Path
import json
import pytest
from ads_autopilot.owner_store import OwnerStore
from ads_autopilot.security import hash_password, verify_password
ROOT=Path(__file__).resolve().parents[1]
def defaults(): return json.loads((ROOT/'config/autonomy-policy.json').read_text()), json.loads((ROOT/'config/operator.example.json').read_text())
def test_owner_policy_is_versioned_audited_and_narrow(tmp_path:Path):
    p,o=defaults(); s=OwnerStore(tmp_path/'owner.db',b'k'*32); s.bootstrap(p,o,hash_password('correct horse battery staple'))
    before=s.snapshot(); assert before['mode']=='observe'; assert s.verify_audit_chain()['ok']
    after=s.update_policy({'money.owner_daily_spend_ceiling':500,'autonomy.allow_campaign_creation':False}); assert after['policy_revision']==before['policy_revision']+1; assert after['policy']['money']['owner_daily_spend_ceiling']==500; assert after['policy']['autonomy']['allow_campaign_creation'] is False; assert s.verify_audit_chain()['ok']
    with pytest.raises(ValueError): s.update_policy({'permanent_blocks':[]})
    with pytest.raises(ValueError): s.update_policy({'autonomy.allow_irreversible_cleanup':True})
def test_system_can_only_reduce_authority(tmp_path:Path):
    p,o=defaults(); s=OwnerStore(tmp_path/'owner.db',b'k'*32); s.bootstrap(p,o,hash_password('correct horse battery staple')); s.update_policy({'money.owner_daily_spend_ceiling':500}); s.update_operator({'advertiser_account_id':'A1','profile_ids':['P1']}); s.set_mode('autopilot'); assert s.snapshot()['mode']=='autopilot'; s.system_pause('test'); assert s.snapshot()['mode']=='paused'; s.emergency_stop()
    with pytest.raises(ValueError): s.set_mode('autopilot')
    s.clear_emergency_stop(); assert s.snapshot()['mode']=='observe' and not s.snapshot()['emergency_stop']
def test_password_hash_scrypt():
    h=hash_password('correct horse battery staple'); assert verify_password('correct horse battery staple',h); assert not verify_password('wrong password here',h)
def test_autopilot_requires_owner_readiness_and_revision_restore(tmp_path):
    p,o=defaults(); store=OwnerStore(tmp_path/'owner.db',b'k'*32); store.bootstrap(p,o,hash_password('correct horse battery staple'))
    try: store.set_mode('autopilot')
    except ValueError as e: assert 'readiness' in str(e)
    else: raise AssertionError('autopilot must fail closed before owner monetary/account setup')
    store.update_policy({'money.owner_daily_spend_ceiling':250}); store.update_operator({'advertiser_account_id':'A1','profile_ids':['P1']}); assert store.set_mode('autopilot')['mode']=='autopilot'; before=store.snapshot()['policy_revision']; store.update_policy({'money.max_single_campaign_budget':99}); restored=store.restore_revision('policy',before); assert restored['mode']=='observe'; assert restored['policy']['money']['max_single_campaign_budget'] != 99; assert store.verify_audit_chain()['ok']
