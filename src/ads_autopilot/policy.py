from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any
from .canonical import digest
from .models import Action
from .state import Store

UTC=timezone.utc
HARD_PERMANENT_BLOCKS=('billing','payment','account_admin','credentials','user_management','permanent_delete','delete_account','close_account')

class PolicyError(ValueError): pass

@dataclass
class PolicyDecision:
    allowed: bool
    reasons: list[str]
    spend_reservation: float=0.0

class PolicyEngine:
    def __init__(self, data:dict[str,Any]): self.data=data
    @classmethod
    def load(cls,path:str|Path): return cls(json.loads(Path(path).read_text()))
    @classmethod
    def from_dict(cls,data:dict[str,Any]): return cls(json.loads(json.dumps(data)))
    @property
    def hash(self): return digest(self.data)
    def _pct_change(self,before:Any,after:Any)->float:
        try: b=float(before); a=float(after)
        except (TypeError,ValueError): raise PolicyError('numeric before/after value required')
        if b<=0: raise PolicyError('before value must be > 0')
        return abs((a-b)/b*100.0)
    def _timestamp_age(self,value:str)->float:
        ts=datetime.fromisoformat(value.replace('Z','+00:00'))
        if ts.tzinfo is None: ts=ts.replace(tzinfo=UTC)
        return (datetime.now(UTC)-ts.astimezone(UTC)).total_seconds()
    def evaluate_action(self,a:Action,*,context:dict[str,Any]|None=None,store:Store|None=None,timezone_name:str='UTC')->PolicyDecision:
        r=[]; d=self.data; context=context or {}
        if d['recovery'].get('kill_switch'): r.append('kill switch enabled')
        if not a.action_id: r.append('missing action_id')
        if not a.action_type: r.append('missing action_type')
        if not a.tool_name: r.append('missing exact MCP tool_name')
        if a.ad_product not in d['scope']['allowed_ad_products']: r.append(f'ad product {a.ad_product} outside standing scope')
        r.extend(_tool_contract_reasons(a)); r.extend(_argument_intent_reasons(a, context))
        lowered=a.action_type.lower(); tool_lower=a.tool_name.lower(); entity_lower=a.entity_type.lower()
        for blocked in set(HARD_PERMANENT_BLOCKS) | {str(x).lower() for x in d.get('permanent_blocks',[])}:
            if blocked in lowered or blocked in tool_lower or blocked in entity_lower or _blocked_argument_signal(a.arguments,blocked): r.append(f'permanent block: {blocked}')
        if any(token in lowered for token in ('delete','archive','remove_account','close_account')) and not d['autonomy'].get('allow_irreversible_cleanup',False): r.append('destructive/irreversible operation blocked')
        if not a.reversible and not d['autonomy'].get('allow_irreversible_cleanup',False): r.append('irreversible action blocked')
        if lowered.startswith('create_campaign'):
            if not d['autonomy'].get('allow_campaign_creation'): r.append('campaign creation disabled')
            desired=str(a.arguments.get('state') or a.arguments.get('status') or a.after.get('state') or '').upper()
            if d['scope'].get('require_paused_campaign_create') and desired not in {'PAUSED','PAUSE'}: r.append('new campaign must be created PAUSED')
            prefix=str(d['scope'].get('autonomous_campaign_name_prefix') or ''); name=str(a.arguments.get('name') or a.arguments.get('campaignName') or a.after.get('name') or '')
            if prefix and not name.startswith(prefix): r.append(f'autonomous campaign name must start with {prefix}')
            budget=_number(a.arguments.get('budget',a.arguments.get('dailyBudget',a.after.get('budget',0))))
            if budget>d['money']['max_single_campaign_budget']: r.append('new campaign budget exceeds single-campaign cap')
        if lowered.startswith('create_ad_group') and not d['autonomy'].get('allow_ad_group_creation'): r.append('ad group creation disabled')
        if lowered.startswith('create_ad'):
            if not d['autonomy'].get('allow_ad_creation'): r.append('ad creation disabled')
            if d['scope'].get('require_observed_asin_for_product_ad_create'):
                asin=_find_first(a.arguments,('asin','advertisedAsin','advertised_asin','advertisedProductAsin')); observed={str(x).upper() for x in (context.get('observed_asins') or [])}
                if not asin: r.append('product-ad creation requires an advertised ASIN')
                elif str(asin).upper() not in observed: r.append('product-ad ASIN is not present in current-cycle Amazon observations')
                managed={str(x).upper() for x in (context.get('_owner_managed_asins') or [])}
                if asin and managed and str(asin).upper() not in managed: r.append('product-ad ASIN is outside Owner managed-ASIN scope')
        if ('keyword' in lowered and lowered.startswith('create')) and not d['autonomy'].get('allow_keyword_creation'): r.append('keyword creation disabled')
        if ('target' in lowered and lowered.startswith('create')) and not d['autonomy'].get('allow_target_creation'): r.append('target creation disabled')
        if 'negative' in lowered and not d['autonomy'].get('allow_negative_targeting'): r.append('negative targeting disabled')
        if any(x in lowered for x in ('pause','enable','resume','state')) and not d['autonomy'].get('allow_state_changes'): r.append('state changes disabled')
        if store and _is_enable_campaign(a):
            managed=store.managed_entity('campaign',a.entity_id)
            if managed and managed.get('activation_status')!='verified': r.append('controller-created campaign is not independently verified for activation')
            prefix=str(d['scope'].get('autonomous_campaign_name_prefix') or ''); before_name=str(a.before.get('name') or a.arguments.get('name') or '')
            if prefix and before_name.startswith(prefix) and not managed: r.append('autonomous campaign cannot be enabled without controller verification lineage')
        field=str(a.arguments.get('field') or '').lower()
        if 'bid' in lowered or field=='bid':
            if not d['autonomy'].get('allow_bid_changes'): r.append('bid changes disabled')
            before=a.before.get('bid'); after=a.after.get('bid')
            try:
                if before is not None and after is not None:
                    pct=self._pct_change(before,after); cap=d['bidding']['max_bid_increase_pct_per_action'] if float(after)>float(before) else d['bidding'].get('max_bid_decrease_pct_per_action',d['bidding']['max_bid_increase_pct_per_action'])
                    if pct>cap: r.append('bid change exceeds per-action cap')
                if after is not None and not (d['bidding']['min_bid']<=float(after)<=d['bidding']['max_bid']): r.append('bid outside min/max')
            except (PolicyError,ValueError,TypeError) as e: r.append(str(e))
        if 'budget' in lowered or field=='budget':
            before=a.before.get('budget'); after=a.after.get('budget')
            if before is not None and after is not None:
                try:
                    increasing=float(after)>float(before)
                    if increasing and not d['autonomy'].get('allow_budget_increases'): r.append('budget increases disabled')
                    if float(after)<float(before) and not d['autonomy'].get('allow_budget_decreases'): r.append('budget decreases disabled')
                    cap=d['money']['max_budget_increase_pct_per_action'] if increasing else d['money'].get('max_budget_decrease_pct_per_action',d['money']['max_budget_increase_pct_per_action'])
                    if self._pct_change(before,after)>cap: r.append('budget change exceeds per-action cap')
                except (PolicyError,ValueError,TypeError) as e: r.append(str(e))
        if 'placement' in lowered or field in {'placement','placement_pct'}:
            if not d['autonomy'].get('allow_placement_changes'): r.append('placement changes disabled')
            b=a.before.get('placement_pct'); n=a.after.get('placement_pct')
            try:
                if b is not None and n is not None and abs(float(n)-float(b))>d['placement']['max_change_points_per_action']: r.append('placement change exceeds cap')
                if n is not None and not (float(d['placement']['min_multiplier_pct'])<=float(n)<=float(d['placement']['max_multiplier_pct'])): r.append('placement multiplier outside min/max')
            except (ValueError,TypeError): r.append('invalid placement value')
        if a.spend_delta<0: r.append('spend_delta cannot be negative')
        if a.spend_delta>0 and a.confidence<d['bidding']['min_confidence_scale']: r.append('insufficient confidence for spend increase')
        if a.spend_delta==0 and ('decrease' in lowered or 'pause' in lowered) and a.confidence<d['bidding']['min_confidence_reduce']: r.append('insufficient confidence for reduction')
        if d['scope'].get('require_prewrite_read') and not a.prewrite_observed_at: r.append('missing prewrite observation timestamp')
        elif a.prewrite_observed_at:
            try:
                age=self._timestamp_age(a.prewrite_observed_at)
                if age>d['scope']['prewrite_read_max_age_seconds']: r.append('prewrite observation too old')
                if age < -60: r.append('prewrite observation timestamp is in the future')
            except Exception: r.append('invalid prewrite observation timestamp')
        if not a.evidence_refs: r.append('action has no evidence refs')
        if store and a.entity_id and not lowered.startswith('create_'):
            hours=float(d['scope'].get('cooldown_hours') or 0)
            if hours>0:
                since=(datetime.now(UTC)-timedelta(hours=hours)).isoformat(); recent=store.recent_same_entity_action(a.entity_type,a.entity_id,_action_family(a),since)
                if recent: r.append(f'entity/action-family is inside {hours:g}h cooldown')
        return PolicyDecision(not r,r,max(0.0,a.spend_delta))
    def evaluate_plan(self,actions:list[Action],*,context:dict[str,Any]|None=None,store:Store|None=None,timezone_name:str='UTC',cycle_id:str|None=None)->list[PolicyDecision]:
        context=context or {}; d=self.data
        if len(actions)>d['scope']['max_actions_per_cycle']: raise PolicyError('plan exceeds max_actions_per_cycle')
        if len({a.action_id for a in actions})!=len(actions): raise PolicyError('duplicate action_id')
        ids={a.action_id for a in actions}
        for a in actions:
            missing=set(a.dependencies)-ids
            if missing: raise PolicyError(f'{a.action_id} dependencies missing: {sorted(missing)}')
        if store and store.consecutive_exceptions(exclude_cycle_id=cycle_id)>=int(d['recovery'].get('max_consecutive_failures') or 0)>0: raise PolicyError('automatic recovery breaker open after consecutive exception cycles')
        if any(a.spend_delta>0 for a in actions):
            ref=str(context.get('today_spend_evidence_ref') or '').strip(); observed=str(context.get('today_spend_observed_at') or '').strip()
            if not ref: raise PolicyError('spend-increasing plan lacks today_spend_evidence_ref')
            if not observed: raise PolicyError('spend-increasing plan lacks today_spend_observed_at')
            try:
                age=self._timestamp_age(observed)
                if age>float(d['money'].get('spend_evidence_max_age_seconds',1800)): raise PolicyError('today spend evidence is too old')
                if age < -60: raise PolicyError('today spend evidence timestamp is in the future')
            except PolicyError: raise
            except Exception as exc: raise PolicyError('invalid today_spend_observed_at') from exc
        creates=[a for a in actions if a.action_type.lower().startswith('create_campaign')]
        if store and creates:
            prior_count,prior_budget=store.campaign_creates_today(timezone_name)
            if prior_count+len(creates)>int(d['scope']['max_campaign_creates_per_day']): raise PolicyError('daily campaign creation limit exceeded')
            proposed=sum(_campaign_budget(a) for a in creates)
            if prior_budget+proposed>float(d['money']['max_new_campaign_budget_per_day']): raise PolicyError('daily new-campaign budget envelope exceeded')
        positive_budget_delta=0.0
        for a in actions:
            if a.action_type.lower().startswith('create_campaign'): continue
            if 'budget' in a.action_type.lower() or str(a.arguments.get('field') or '').lower()=='budget':
                try: positive_budget_delta+=max(0.0,float(a.after.get('budget'))-float(a.before.get('budget')))
                except (TypeError,ValueError): pass
        if positive_budget_delta>0:
            base=_number(context.get('active_campaign_budget_total'))
            if base<=0: raise PolicyError('budget-increase plan lacks active_campaign_budget_total evidence')
            if positive_budget_delta/base*100.0>float(d['money']['max_profile_budget_increase_pct_per_cycle']): raise PolicyError('profile budget increase exceeds per-cycle cap')
        return [self.evaluate_action(a,context=context,store=store,timezone_name=timezone_name) for a in actions]

def _norm(value:Any)->str: return ''.join(ch for ch in str(value).lower() if ch.isalnum())
def _scalar_values(value:Any)->list[str]:
    if isinstance(value,(list,tuple,set)):
        out=[]
        for x in value: out.extend(_scalar_values(x))
        return out
    if isinstance(value,dict): return []
    return [str(value)] if value not in (None,'') else []
def _find_values(value:Any,keys:tuple[str,...])->list[Any]:
    wanted={_norm(k) for k in keys}; found=[]; stack=[value]
    while stack:
        item=stack.pop()
        if isinstance(item,dict):
            for k,v in item.items():
                if _norm(k) in wanted:
                    if isinstance(v,list): found.extend(v)
                    else: found.append(v)
                if isinstance(v,(dict,list)): stack.append(v)
        elif isinstance(item,list): stack.extend(item)
    return found
def _numeric_values(value:Any,keys:tuple[str,...])->list[float]:
    out=[]
    for raw in _find_values(value,keys):
        if isinstance(raw,dict): continue
        try: out.append(float(raw))
        except (TypeError,ValueError): pass
    return out
def _same_number(a:Any,b:Any)->bool:
    try: return abs(float(a)-float(b)) <= max(1e-9,abs(float(b))*1e-9)
    except (TypeError,ValueError): return False
def _tool_contract_reasons(a:Action)->list[str]:
    r=[]; tool=str(a.tool_name or '')
    if tool.startswith('mcp__'): return ['tool_name must be the bare amazon_ads MCP tool name']
    lower=_norm(tool); action=_norm(a.action_type); entity=_norm(a.entity_type)
    if not lower: return ['missing exact MCP tool_name']
    if any(x in lower for x in ('delete','archive','permanentdelete','closeaccount')): r.append('MCP tool is destructive and outside autonomous contract')
    create=action.startswith('create'); create_verb=any(x in lower for x in ('create','add')); write_verb=any(x in lower for x in ('create','add','update','set','manage','mutate','pause','enable','resume','remove'))
    if create and not create_verb: r.append('create action is not bound to a create/add MCP tool')
    if not create and create_verb: r.append('non-create action cannot use a create/add MCP tool')
    if not write_verb: r.append('action is not bound to a mutation-capable MCP tool name')
    aliases={'adgroup':('adgroup','adgroups'),'campaign':('campaign','campaigns'),'keyword':('keyword','keywords'),'target':('target','targets'),'ad':('ad','ads','productad','productads')}; options=aliases.get(entity,(entity,)) if entity else ()
    if options and not any(x in lower for x in options): r.append('MCP tool family does not match action entity_type')
    if 'negative' in action and 'negative' not in lower: r.append('negative action requires a negative-targeting MCP tool')
    return r
def _argument_intent_reasons(a:Action,context:dict[str,Any])->list[str]:
    r=[]; action=a.action_type.lower(); field=str(a.arguments.get('field') or '').lower(); owner_profiles={str(x) for x in context.get('_owner_profile_ids',[]) if str(x)}
    seen_profiles=set(sum((_scalar_values(v) for v in _find_values(a.arguments,('profileId','profile_id','profileIds','profile_ids'))),[]))
    if seen_profiles and not seen_profiles.issubset(owner_profiles): r.append('MCP arguments reference a profile outside Owner scope')
    owner_account=str(context.get('_owner_advertiser_account_id') or ''); seen_accounts=set(sum((_scalar_values(v) for v in _find_values(a.arguments,('accountId','account_id','advertiserAccountId','advertiser_account_id'))),[]))
    if seen_accounts and (not owner_account or seen_accounts!={owner_account}): r.append('MCP arguments reference an account outside Owner scope')
    managed={str(x).upper() for x in context.get('_owner_managed_asins',[]) if str(x)}; seen_asins={x.upper() for v in _find_values(a.arguments,('asin','asins','advertisedAsin','advertised_asin','advertisedProductAsin')) for x in _scalar_values(v)}
    if managed and seen_asins and not seen_asins.issubset(managed): r.append('MCP arguments contain ASIN outside Owner managed-ASIN scope')
    if a.entity_id and not action.startswith('create_'):
        id_keys={'campaign':('campaignId','campaign_id','campaignIds','campaign_ids'),'ad_group':('adGroupId','ad_group_id','adGroupIds','ad_group_ids'),'adgroup':('adGroupId','ad_group_id','adGroupIds','ad_group_ids'),'keyword':('keywordId','keyword_id','keywordIds','keyword_ids'),'target':('targetId','target_id','targetIds','target_ids'),'ad':('adId','ad_id','adIds','ad_ids','productAdId','product_ad_id')}.get(a.entity_type.lower(),())
        ids={x for v in _find_values(a.arguments,id_keys) for x in _scalar_values(v)} if id_keys else set()
        if ids and ids!={str(a.entity_id)}: r.append('MCP arguments do not target exactly the declared entity_id')
    if 'bid' in action or field=='bid':
        expected=a.after.get('bid'); vals=_numeric_values(a.arguments,('bid','newBid','bidAmount'))
        if expected is not None and (not vals or any(not _same_number(x,expected) for x in vals)): r.append('MCP bid arguments do not equal sealed after.bid')
    if 'budget' in action or field=='budget' or action.startswith('create_campaign'):
        expected=a.after.get('budget'); vals=_numeric_values(a.arguments,('budget','dailyBudget','budgetAmount'))
        if expected is not None and (not vals or any(not _same_number(x,expected) for x in vals)): r.append('MCP budget arguments do not equal sealed after.budget')
    if any(x in action for x in ('pause','enable','resume','state')):
        expected=str(a.after.get('state') or '').upper(); vals=[x.upper() for v in _find_values(a.arguments,('state','status')) for x in _scalar_values(v)]
        if expected and (not vals or any(x!=expected for x in vals)): r.append('MCP state arguments do not equal sealed after.state')
    if 'placement' in action or field in {'placement','placement_pct'}:
        expected=a.after.get('placement_pct'); vals=_numeric_values(a.arguments,('percentage','adjustmentPercent','adjustment_percentage','placementPercentage','placement_pct'))
        if expected is not None and (not vals or any(not _same_number(x,expected) for x in vals)): r.append('MCP placement arguments do not equal sealed after.placement_pct')
    return r
def _blocked_argument_signal(value:Any,blocked:str)->bool:
    control_keys={'operation','action','resource','resourcetype','entitytype','endpoint','path','scope','permission'}; stack=[value]
    while stack:
        item=stack.pop()
        if isinstance(item,dict):
            for key,val in item.items():
                norm=''.join(ch for ch in str(key).lower() if ch.isalnum() or ch=='_')
                if blocked in norm: return True
                if norm.replace('_','') in control_keys and blocked in str(val).lower(): return True
                if isinstance(val,(dict,list)): stack.append(val)
        elif isinstance(item,list): stack.extend(item)
    return False
def _number(value:Any)->float:
    try: return max(0.0,float(value or 0))
    except (TypeError,ValueError): return 0.0
def _campaign_budget(a:Action)->float: return _number(a.arguments.get('budget',a.arguments.get('dailyBudget',a.after.get('budget',0))))
def _find_first(value:Any,keys:tuple[str,...])->Any:
    wanted={''.join(ch for ch in k.lower() if ch.isalnum()) for k in keys}; stack=[value]
    while stack:
        item=stack.pop()
        if isinstance(item,dict):
            for k,v in item.items():
                if ''.join(ch for ch in str(k).lower() if ch.isalnum()) in wanted and v not in (None,''): return v
                if isinstance(v,(dict,list)): stack.append(v)
        elif isinstance(item,list): stack.extend(item)
    return None
def _is_enable_campaign(a:Action)->bool:
    action=a.action_type.lower()
    if a.entity_type.lower()!='campaign': return False
    if any(x in action for x in ('enable','resume')): return True
    if 'state' in action:
        desired=str(_find_first(a.arguments,('state','status')) or a.after.get('state') or '').upper(); return desired=='ENABLED'
    return False
def _action_family(a:Action)->str:
    action=a.action_type.lower(); field=str(a.arguments.get('field') or '').lower()
    if 'budget' in action or field=='budget': return 'budget'
    if 'bid' in action or field=='bid': return 'bid'
    if 'placement' in action or field in {'placement','placement_pct'}: return 'placement'
    if 'negative' in action: return 'negative'
    if action.startswith('create_'): return 'create'
    if any(x in action for x in ('pause','enable','resume','state')): return 'state'
    return action or 'other'
