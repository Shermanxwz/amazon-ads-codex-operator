from datetime import datetime,timezone
import json
from pathlib import Path
from ads_autopilot.models import Action
from ads_autopilot.policy import PolicyEngine
ROOT=Path(__file__).resolve().parents[1]
def action(**kw):
    base=dict(action_id='a1',action_type='update_bid',tool_name='updateKeywords',ad_product='SPONSORED_PRODUCTS',entity_type='keyword',entity_id='1',arguments={'keywordId':'1','field':'bid','bid':1.2},before={'bid':1.0},after={'bid':1.2},spend_delta=2,confidence=.9,evidence_refs=('e1',),dependencies=(),reversible=True,rollback={'bid':1.0},prewrite_observed_at=datetime.now(timezone.utc).isoformat()); base.update(kw); return Action(**base)
def policy(): return PolicyEngine(json.loads((ROOT/'config/autonomy-policy.json').read_text()))
def test_bid_allowed(): assert policy().evaluate_action(action()).allowed
def test_large_bid_blocked():
    d=policy().evaluate_action(action(after={'bid':2.0})); assert not d.allowed and any('bid change' in x for x in d.reasons)
def test_permanent_delete_blocked():
    d=policy().evaluate_action(action(action_type='permanent_delete_campaign',reversible=False,spend_delta=0)); assert not d.allowed
def test_campaign_create_requires_paused():
    a=action(action_type='create_campaign',tool_name='createCampaigns',entity_type='campaign',entity_id='new',arguments={'state':'ENABLED','budget':50,'name':'CODEX-test'},before={},after={'state':'ENABLED','budget':50,'name':'CODEX-test'},spend_delta=50); d=policy().evaluate_action(a); assert not d.allowed and any('PAUSED' in x for x in d.reasons)
def test_confused_deputy_tool_name_is_blocked():
    a=action(tool_name='createCampaigns',action_type='update_bid',entity_type='keyword',entity_id='1',arguments={'keywordId':'1','bid':1.2}); d=policy().evaluate_action(a); assert not d.allowed and any('MCP tool' in x or 'create' in x for x in d.reasons)
def test_arguments_cannot_exceed_declared_after_value():
    a=action(tool_name='updateKeywords',arguments={'keywordId':'1','bid':10.0},after={'bid':1.2}); d=policy().evaluate_action(a); assert not d.allowed and any('after.bid' in x for x in d.reasons)
def test_arguments_cannot_target_multiple_entities():
    a=action(tool_name='updateKeywords',arguments={'keywordIds':['1','2'],'bid':1.2}); d=policy().evaluate_action(a); assert not d.allowed and any('entity_id' in x for x in d.reasons)
