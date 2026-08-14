from datetime import datetime, timezone
import json
from pathlib import Path
from ads_autopilot.models import Action
from ads_autopilot.policy import PolicyEngine, PolicyError
from ads_autopilot.state import Store

ROOT=Path(__file__).resolve().parents[1]
NOW=lambda: datetime.now(timezone.utc).isoformat()

def engine(): return PolicyEngine(json.loads((ROOT/'config/autonomy-policy.json').read_text()))

def action(**kw):
    base=dict(action_id='a1',action_type='update_bid',tool_name='updateKeywords',ad_product='SPONSORED_PRODUCTS',entity_type='keyword',entity_id='k1',arguments={'keywordId':'k1','field':'bid','bid':1.1},before={'bid':1.0},after={'bid':1.1},spend_delta=0,confidence=.9,evidence_refs=('live:keyword:k1',),dependencies=(),reversible=True,rollback={'bid':1.0},prewrite_observed_at=NOW(),rationale='test')
    base.update(kw); return Action(**base)

def context(**kw):
    base=dict(today_spend=10.0,today_spend_observed_at=NOW(),today_spend_evidence_ref='live:spend',active_campaign_budget_total=100.0,observed_asins=['B000TEST01'])
    base.update(kw); return base

def test_spend_increase_requires_fresh_spend_evidence(tmp_path:Path):
    a=action(spend_delta=5)
    try: engine().evaluate_plan([a],context={'today_spend':10},store=Store(tmp_path/'s.db'))
    except PolicyError as exc: assert 'spend' in str(exc)
    else: raise AssertionError('must require fresh spend evidence')

def test_product_ad_create_requires_observed_asin():
    a=action(action_type='create_ad',tool_name='createProductAds',entity_type='ad',entity_id='new',arguments={'advertisedAsin':'B000BAD999'},before={},after={'asin':'B000BAD999'},spend_delta=0)
    d=engine().evaluate_action(a,context=context()); assert not d.allowed and any('ASIN' in x for x in d.reasons)
    b=action(action_type='create_ad',tool_name='createProductAds',entity_type='ad',entity_id='new2',arguments={'advertisedAsin':'B000TEST01'},before={},after={'asin':'B000TEST01'},spend_delta=0)
    assert engine().evaluate_action(b,context=context()).allowed

def test_cooldown_is_cross_cycle(tmp_path:Path):
    store=Store(tmp_path/'s.db'); store.create_cycle('c0','daily')
    row={'action_hash':'h1','action_id':'old','action_type':'update_bid','entity_type':'keyword','entity_id':'k1','arguments':{'keywordId':'k1','field':'bid','bid':1.1},'before':{'bid':1},'after':{'bid':1.1},'spend_delta':0,'signature':'s'}
    store.add_action('c0',row)
    d=engine().evaluate_action(action(),context=context(),store=store); assert not d.allowed and any('cooldown' in x for x in d.reasons)

def test_pending_controller_campaign_cannot_activate(tmp_path:Path):
    store=Store(tmp_path/'s.db'); store.register_managed_entity('campaign','123','createhash','pending_verification')
    a=action(action_type='enable_campaign',tool_name='updateCampaigns',entity_type='campaign',entity_id='123',arguments={'campaignId':'123','state':'ENABLED'},before={'state':'PAUSED','name':'CODEX-test'},after={'state':'ENABLED'},spend_delta=0)
    d=engine().evaluate_action(a,context=context(),store=store); assert not d.allowed and any('not independently verified' in x for x in d.reasons)
    store.register_managed_entity('campaign','123','createhash','verified')
    d=engine().evaluate_action(a,context=context(),store=store); assert d.allowed

def test_profile_budget_expansion_cap(tmp_path:Path):
    a=action(action_type='update_budget',tool_name='updateCampaigns',entity_type='campaign',entity_id='c1',arguments={'campaignId':'c1','field':'budget','budget':140},before={'budget':100},after={'budget':140},spend_delta=20)
    try: engine().evaluate_plan([a],context=context(active_campaign_budget_total=100),store=Store(tmp_path/'s.db'))
    except PolicyError as exc: assert 'profile budget increase' in str(exc)
    else: raise AssertionError('40% aggregate increase should exceed default 35% cap')

def test_daily_campaign_create_count_and_budget(tmp_path:Path):
    store=Store(tmp_path/'s.db'); store.create_cycle('c0','daily')
    for i in range(10):
        row={'action_hash':f'h{i}','action_id':f'a{i}','action_type':'create_campaign','entity_type':'campaign','entity_id':f'new{i}','arguments':{'name':f'CODEX-{i}','state':'PAUSED','budget':10},'before':{},'after':{'budget':10,'state':'PAUSED','name':f'CODEX-{i}'},'spend_delta':10,'signature':'s'}
        store.add_action('c0',row)
    new=action(action_type='create_campaign',tool_name='createCampaigns',entity_type='campaign',entity_id='newx',arguments={'name':'CODEX-x','state':'PAUSED','budget':10},before={},after={'budget':10,'state':'PAUSED','name':'CODEX-x'},spend_delta=10)
    try: engine().evaluate_plan([new],context=context(),store=store)
    except PolicyError as exc: assert 'creation limit' in str(exc)
    else: raise AssertionError('daily create limit should block')

def test_mcp_arguments_cannot_escape_owner_profile_scope():
    a=action(arguments={'keywordId':'k1','profileId':'999','field':'bid','bid':1.1})
    d=engine().evaluate_action(a,context=context(_owner_profile_ids=['123']))
    assert not d.allowed and any('profile outside Owner scope' in x for x in d.reasons)

def test_mcp_arguments_cannot_escape_managed_asin_scope():
    a=action(action_type='create_ad', tool_name='createProductAds', entity_type='ad', entity_id='new3', arguments={'advertisedAsin':'B000OUTSIDE'}, before={}, after={'asin':'B000OUTSIDE'}, spend_delta=0)
    d=engine().evaluate_action(a,context=context(observed_asins=['B000OUTSIDE'],_owner_managed_asins=['B000TEST01']))
    assert not d.allowed and any('managed-ASIN' in x for x in d.reasons)

def test_declared_bid_cannot_differ_from_actual_mcp_arguments():
    a=action(arguments={'keywordId':'k1','field':'bid','bid':9.0},before={'bid':1.0},after={'bid':1.1})
    d=engine().evaluate_action(a,context=context())
    assert not d.allowed and any('sealed after.bid' in x for x in d.reasons)
