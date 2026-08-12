from __future__ import annotations
from datetime import datetime, timezone
import json, os, secrets
from pathlib import Path
from typing import Any
from .canonical import digest,canonical_json
from .codex_runner import run_codex
from .ledger import BudgetLedger, BudgetError
from .models import Action
from .outcome import parse_outcome
from .policy import PolicyEngine,PolicyError
from .sealing import Sealer
from .state import Store

UTC=timezone.utc
class Controller:
    def __init__(self,root:Path):
        self.root=root
        op_path=root/'config/operator.local.json'
        if not op_path.exists(): raise RuntimeError('config/operator.local.json missing')
        pol_path=root/'config/autonomy-policy.local.json'
        if not pol_path.exists(): pol_path=root/'config/autonomy-policy.json'
        self.operator=json.loads(op_path.read_text()); self.policy=PolicyEngine.load(pol_path)
        self.store=Store(os.environ.get('ADS_STATE_DB',root/'state/operator.db'))
        self.sealer=Sealer.from_runtime(root); self.ledger=BudgetLedger(self.store,self.policy.data)
        self.timeout=int(os.environ.get('ADS_CODEX_TIMEOUT_SECONDS','1800'))
    def _prompt(self,name:str,payload:dict[str,Any])->str:
        return (self.root/f'prompts/{name}').read_text()+"\n\nINPUT_JSON:\n"+canonical_json(payload)
    def run(self,kind:str='daily',dry_run:bool=False)->dict[str,Any]:
        cycle_id=f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
        run_dir=self.root/f'state/runs/{cycle_id}'; run_dir.mkdir(parents=True,exist_ok=False)
        self.store.create_cycle(cycle_id,kind)
        try:
            return self._run(cycle_id,run_dir,kind,dry_run)
        except Exception as exc:
            data={'error_type':type(exc).__name__,'error':str(exc)}
            (run_dir/'exception.json').write_text(json.dumps(data,indent=2))
            self.store.event('error','cycle.exception',cycle_id,data)
            self.store.finish_cycle(cycle_id,'exception',data)
            return {'cycle_id':cycle_id,'status':'exception',**data}
    def _run(self,cycle_id:str,run_dir:Path,kind:str,dry_run:bool)->dict[str,Any]:
        planning_input={'cycle_id':cycle_id,'cycle_kind':kind,'operator':self.operator,'policy':self.policy.data,'state_summary':self._recent_state()}
        plan=run_codex(root=self.root,prompt=self._prompt('observe_plan.md',planning_input),schema=self.root/'schemas/plan.schema.json',output=run_dir/'plan.json',timeout=self.timeout)
        plan_hash=digest(plan); operator_hash=digest(self.operator); context=dict(plan.get('context') or {})
        actions=[Action.from_dict(x) for x in plan.get('actions',[])]
        timezone_name=str(self.operator.get('timezone') or 'UTC')
        try:
            decisions=self.policy.evaluate_plan(actions,context=context,store=self.store,timezone_name=timezone_name,cycle_id=cycle_id)
        except PolicyError as exc:
            rejected=[{'plan':str(exc)}]; (run_dir/'policy-rejections.json').write_text(json.dumps(rejected,indent=2)); self.store.finish_cycle(cycle_id,'blocked',{'rejected':rejected}); return {'cycle_id':cycle_id,'status':'blocked','rejected':rejected}
        rejected=[{'action_id':a.action_id,'reasons':d.reasons} for a,d in zip(actions,decisions) if not d.allowed]
        if rejected:
            (run_dir/'policy-rejections.json').write_text(json.dumps(rejected,indent=2)); self.store.finish_cycle(cycle_id,'blocked',{'rejected':rejected}); return {'cycle_id':cycle_id,'status':'blocked','rejected':rejected}
        if not actions:
            self.store.finish_cycle(cycle_id,'completed',{'planned_actions':0,'reason':'planner proposed no mutation'}); return {'cycle_id':cycle_id,'status':'completed','planned_actions':0}

        sealed=[]; reserved=[]; observed_spend=float(context.get('today_spend') or 0)
        try:
            for a,d in zip(actions,decisions):
                base={
                  'cycle_id':cycle_id,'action_id':a.action_id,'action_type':a.action_type,'ad_product':a.ad_product,
                  'entity_type':a.entity_type,'entity_id':a.entity_id,'arguments':a.arguments,'before':a.before,'after':a.after,
                  'spend_delta':a.spend_delta,'confidence':a.confidence,'evidence_refs':list(a.evidence_refs),'dependencies':list(a.dependencies),
                  'reversible':a.reversible,'rollback':a.rollback,'prewrite_observed_at':a.prewrite_observed_at,'rationale':a.rationale
                }
                row=self.sealer.seal_action(base,policy_hash=self.policy.hash,plan_hash=plan_hash,operator_hash=operator_hash)
                if not dry_run and d.spend_reservation>0:
                    self.ledger.reserve(row['action_hash'],d.spend_reservation,observed_spend); reserved.append(row['action_hash'])
                self.store.add_action(cycle_id,row)
                if dry_run: self.store.set_action_status(row['action_hash'],'dry_run')
                sealed.append(row)
        except (BudgetError,Exception):
            for h in reserved: self.ledger.release(h,'cancelled')
            raise
        bundle={'version':2,'cycle_id':cycle_id,'cycle_kind':kind,'plan_hash':plan_hash,'policy_hash':self.policy.hash,'operator_hash':operator_hash,'actions':sealed}
        (run_dir/'sealed-actions.json').write_text(json.dumps(bundle,indent=2))
        self.store.set_plan(cycle_id,plan_hash,self.policy.hash)
        if dry_run:
            self.store.finish_cycle(cycle_id,'dry_run',{'actions':len(sealed)}); return {'cycle_id':cycle_id,'status':'dry_run','actions':len(sealed)}

        receipt=run_codex(root=self.root,prompt=self._prompt('execute_sealed.md',bundle),schema=self.root/'schemas/receipt.schema.json',output=run_dir/'receipt.json',timeout=self.timeout)
        by_hash={x['action_hash']:x for x in sealed}; seen=set(); execution_bad=[]
        for item in receipt.get('results',[]):
            h=str(item.get('action_hash') or '')
            if h in seen: execution_bad.append({'action_hash':h,'reason':'duplicate receipt'}); continue
            seen.add(h)
            if h not in by_hash: execution_bad.append({'action_hash':h,'reason':'unreleased action hash'}); continue
            sealed_row=dict(by_hash[h]); sig=sealed_row.pop('signature')
            if not self.sealer.verify(sealed_row,sig): execution_bad.append({'action_hash':h,'reason':'signature verification failed'}); self.ledger.mark(h,'uncertain'); continue
            outcome=parse_outcome(item); self.store.add_receipt(h,outcome.status,item); self.store.set_action_status(h,outcome.status)
            ledger_status='executed' if outcome.status=='success' else ('pending' if outcome.status=='pending' else 'uncertain')
            self.ledger.mark(h,ledger_status)
            action=by_hash[h]
            if str(action.get('action_type') or '').lower().startswith('create_'):
                entity_type=str(action.get('entity_type') or '').lower(); entity_id=_extract_entity_id(item.get('result'),entity_type)
                if entity_id: self.store.register_managed_entity(entity_type,entity_id,h,'pending_verification')
            if outcome.status!='success': execution_bad.append({'action_hash':h,'reason':outcome.summary})
        for h in set(by_hash)-seen:
            self.store.set_action_status(h,'unknown'); self.ledger.mark(h,'uncertain'); execution_bad.append({'action_hash':h,'reason':'executor omitted released action from receipt'})

        verification_input={'cycle_id':cycle_id,'sealed_actions':sealed,'execution_receipt':receipt}
        verification=run_codex(root=self.root,prompt=self._prompt('verify.md',verification_input),schema=self.root/'schemas/verification.schema.json',output=run_dir/'verification.json',timeout=self.timeout)
        failed=[]; verified_seen=set()
        for v in verification.get('results',[]):
            h=str(v.get('action_hash') or ''); status=str(v.get('status') or 'unknown'); verified_seen.add(h)
            if h in by_hash:
                self.store.add_verification(h,status,v); self.store.set_action_status(h,'verified' if status=='verified' else 'verification_failed')
                self.ledger.mark(h,'verified' if status=='verified' else 'uncertain')
                action=by_hash[h]
                if status=='verified' and str(action.get('action_type') or '').lower().startswith('create_'):
                    entity_type=str(action.get('entity_type') or '').lower(); entity_id=_extract_entity_id(v.get('observed'),entity_type) or _extract_entity_id((next((x for x in receipt.get('results',[]) if x.get('action_hash')==h),{}) or {}).get('result'),entity_type)
                    if entity_id: self.store.register_managed_entity(entity_type,entity_id,h,'verified')
            else:
                failed.append({'action_hash':h,'status':'unknown','differences':['verification references unreleased action']}); continue
            if status!='verified': failed.append(v)
        for h in set(by_hash)-verified_seen:
            self.store.set_action_status(h,'verification_failed'); self.ledger.mark(h,'uncertain'); failed.append({'action_hash':h,'status':'unknown','differences':['verifier omitted released action']})
        status='completed' if not execution_bad and not failed else 'exception'
        summary={'planned_actions':len(sealed),'execution_issues':execution_bad,'verification_issues':failed}
        self.store.finish_cycle(cycle_id,status,summary); return {'cycle_id':cycle_id,'status':status,**summary}
    def _recent_state(self)->dict[str,Any]:
        return self.store.recent_state_summary()

def _extract_entity_id(value:Any,entity_type:str)->str|None:
    candidates={
      'campaign':('campaignId','campaign_id'), 'ad_group':('adGroupId','ad_group_id'), 'adgroup':('adGroupId','ad_group_id'),
      'ad':('adId','ad_id'), 'keyword':('keywordId','keyword_id'), 'target':('targetId','target_id')
    }.get(str(entity_type).lower(),('id',))
    wanted={''.join(ch for ch in x.lower() if ch.isalnum()) for x in candidates}
    stack=[value]
    while stack:
        item=stack.pop()
        if isinstance(item,dict):
            for k,v in item.items():
                key=''.join(ch for ch in str(k).lower() if ch.isalnum())
                if key in wanted and v not in (None,''): return str(v)
                if isinstance(v,(dict,list)): stack.append(v)
        elif isinstance(item,list): stack.extend(item)
    return None
