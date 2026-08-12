from __future__ import annotations
from datetime import datetime,timedelta,timezone
import json,os,secrets
from pathlib import Path
from typing import Any
from .canonical import canonical_json,digest
from .codex_runner import run_codex
from .ledger import BudgetLedger
from .models import Action
from .outcome import parse_outcome
from .owner_store import OwnerStore
from .paths import RuntimePaths
from .policy import PolicyEngine,PolicyError
from .sealing import Sealer
from .state import Store
UTC=timezone.utc
class AuthorityChanged(RuntimeError):pass
class Controller:
    def __init__(self,root:Path,owner_home:str|Path|None=None):
        self.root=Path(root).resolve(); self.paths=RuntimePaths.resolve(self.root,owner_home); self.paths.ensure_directories(); self.sealer=Sealer.from_path(self.paths.signing_key); self.owner=OwnerStore(self.paths.owner_db,self.sealer.key); self.store=Store(os.environ.get('ADS_STATE_DB',self.paths.runtime_db)); self.timeout=int(os.environ.get('ADS_CODEX_TIMEOUT_SECONDS','1800')); self.model=os.environ.get('ADS_CODEX_MODEL') or None
    def _prompt(self,name:str,payload:dict[str,Any])->str:return (self.root/f'prompts/{name}').read_text()+'\n\nINPUT_JSON:\n'+canonical_json(payload)
    def _authority_token(self,snapshot:dict[str,Any])->tuple[Any,...]:return (snapshot['mode'],snapshot['emergency_stop'],snapshot['policy_revision'],snapshot['policy_hash'],snapshot['operator_revision'],snapshot['operator_hash'])
    def _assert_authority(self,baseline:dict[str,Any],*,require_autopilot:bool)->dict[str,Any]:
        current=self.owner.snapshot()
        if self._authority_token(current)!=self._authority_token(baseline):raise AuthorityChanged('owner authority changed during cycle; remaining mutations cancelled')
        if current['emergency_stop']:raise AuthorityChanged('owner emergency stop is active')
        if require_autopilot and current['mode']!='autopilot':raise AuthorityChanged(f"owner mode is {current['mode']}, not autopilot")
        return current
    def _validate_scope_alignment(self,snapshot:dict[str,Any])->None:
        op={str(x).upper() for x in snapshot['operator'].get('scope',{}).get('ad_products',[])}; pol={str(x).upper() for x in snapshot['policy'].get('scope',{}).get('allowed_ad_products',[])}
        if not op:raise RuntimeError('operator scope has no ad products')
        if not op.issubset(pol):raise RuntimeError(f'operator ad products exceed owner policy scope: {sorted(op-pol)}')
        profiles=[x for x in snapshot['operator'].get('profile_ids',[]) if str(x).strip() and str(x)!='REPLACE_ME']
        if not profiles:raise RuntimeError('no real Amazon Ads profile_id configured in Owner Control')
    def run(self,kind:str='daily',dry_run:bool=False)->dict[str,Any]:
        snapshot=self.owner.snapshot(); cycle_id=f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"; run_dir=self.paths.run_root/cycle_id; run_dir.mkdir(parents=True,exist_ok=False,mode=0o700); self.store.create_cycle(cycle_id,kind)
        (run_dir/'owner-authority.json').write_text(json.dumps({'mode':snapshot['mode'],'emergency_stop':snapshot['emergency_stop'],'policy_revision':snapshot['policy_revision'],'policy_hash':snapshot['policy_hash'],'operator_revision':snapshot['operator_revision'],'operator_hash':snapshot['operator_hash']},indent=2))
        try:
            if snapshot['mode']=='paused' or snapshot['emergency_stop']:
                summary={'reason':'owner control paused','emergency_stop':snapshot['emergency_stop']}; self.store.finish_cycle(cycle_id,'paused',summary); return {'cycle_id':cycle_id,'status':'paused',**summary}
            self._validate_scope_alignment(snapshot); return self._run(cycle_id,run_dir,kind,dry_run,snapshot)
        except Exception as exc:
            data={'error_type':type(exc).__name__,'error':str(exc)}; (run_dir/'exception.json').write_text(json.dumps(data,indent=2)); self.store.event('error','cycle.exception',cycle_id,data); self.store.finish_cycle(cycle_id,'exception',data); return {'cycle_id':cycle_id,'status':'exception',**data}
    def _run(self,cycle_id:str,run_dir:Path,kind:str,dry_run:bool,snapshot:dict[str,Any])->dict[str,Any]:
        policy=PolicyEngine.from_dict(snapshot['policy']); operator=snapshot['operator']; ledger=BudgetLedger(self.store,policy.data)
        planning_input={'cycle_id':cycle_id,'cycle_kind':kind,'operator':operator,'policy':policy.data,'owner_mode':snapshot['mode'],'state_summary':self._recent_state()}
        plan=run_codex(paths=self.paths,role='planner',prompt=self._prompt('observe_plan.md',planning_input),schema=self.root/'schemas/plan.schema.json',output=run_dir/'plan.json',timeout=self.timeout,model=self.model)
        self._assert_authority(snapshot,require_autopilot=False); plan_hash=digest(plan); context=dict(plan.get('context') or {})
        context['_owner_profile_ids']=[str(x) for x in operator.get('profile_ids',[])]; context['_owner_advertiser_account_id']=str(operator.get('advertiser_account_id') or ''); context['_owner_managed_asins']=[str(x).upper() for x in operator.get('scope',{}).get('managed_asins',[])]; context['_owner_ad_products']=[str(x).upper() for x in operator.get('scope',{}).get('ad_products',[])]
        actions=[Action.from_dict(x) for x in plan.get('actions',[])]; timezone_name=str(operator.get('timezone') or 'UTC')
        try:decisions=policy.evaluate_plan(actions,context=context,store=self.store,timezone_name=timezone_name,cycle_id=cycle_id)
        except PolicyError as exc:
            rejected=[{'plan':str(exc)}]; (run_dir/'policy-rejections.json').write_text(json.dumps(rejected,indent=2)); self.store.finish_cycle(cycle_id,'blocked',{'rejected':rejected}); return {'cycle_id':cycle_id,'status':'blocked','rejected':rejected}
        rejected=[{'action_id':a.action_id,'reasons':d.reasons} for a,d in zip(actions,decisions) if not d.allowed]
        if rejected:(run_dir/'policy-rejections.json').write_text(json.dumps(rejected,indent=2)); self.store.finish_cycle(cycle_id,'blocked',{'rejected':rejected}); return {'cycle_id':cycle_id,'status':'blocked','rejected':rejected}
        if not actions:self.store.finish_cycle(cycle_id,'completed',{'planned_actions':0,'reason':'planner proposed no mutation'}); return {'cycle_id':cycle_id,'status':'completed','planned_actions':0}
        ordered=_topological_actions(actions); by_action_id={a.action_id:(a,d) for a,d in zip(actions,decisions)}; effective_dry_run=dry_run or snapshot['mode']=='observe'; sealed=[]; reserved=[]; observed_spend=float(context.get('today_spend') or 0)
        try:
            for a in ordered:
                d=by_action_id[a.action_id][1]; base={'cycle_id':cycle_id,'action_id':a.action_id,'action_type':a.action_type,'tool_name':a.tool_name,'ad_product':a.ad_product,'entity_type':a.entity_type,'entity_id':a.entity_id,'arguments':a.arguments,'before':a.before,'after':a.after,'spend_delta':a.spend_delta,'confidence':a.confidence,'evidence_refs':list(a.evidence_refs),'dependencies':list(a.dependencies),'reversible':a.reversible,'rollback':a.rollback,'prewrite_observed_at':a.prewrite_observed_at,'rationale':a.rationale}
                row=self.sealer.seal_action(base,policy_hash=snapshot['policy_hash'],plan_hash=plan_hash,operator_hash=snapshot['operator_hash'],policy_revision=snapshot['policy_revision'],operator_revision=snapshot['operator_revision'])
                if not effective_dry_run and d.spend_reservation>0:ledger.reserve(row['action_hash'],d.spend_reservation,observed_spend); reserved.append(row['action_hash'])
                self.store.add_action(cycle_id,row)
                if effective_dry_run:self.store.set_action_status(row['action_hash'],'dry_run')
                sealed.append(row)
        except Exception:
            for h in reserved:ledger.release(h,'cancelled')
            raise
        bundle={'version':3,'cycle_id':cycle_id,'cycle_kind':kind,'plan_hash':plan_hash,'policy_hash':snapshot['policy_hash'],'policy_revision':snapshot['policy_revision'],'operator_hash':snapshot['operator_hash'],'operator_revision':snapshot['operator_revision'],'actions':sealed}; (run_dir/'sealed-actions.json').write_text(json.dumps(bundle,indent=2)); self.store.set_plan(cycle_id,plan_hash,snapshot['policy_hash'])
        if effective_dry_run:
            status='observed' if snapshot['mode']=='observe' and not dry_run else 'dry_run'; self.store.finish_cycle(cycle_id,status,{'actions':len(sealed),'owner_mode':snapshot['mode']}); return {'cycle_id':cycle_id,'status':status,'actions':len(sealed)}
        sealed_by_id={x['action_id']:x for x in sealed}; action_status={}; issues=[]; receipts=[]; verifications=[]
        for index,action in enumerate(ordered):
            sealed_row=sealed_by_id[action.action_id]; action_hash=sealed_row['action_hash']
            try:self._assert_authority(snapshot,require_autopilot=True)
            except AuthorityChanged as exc:issues.append({'action_hash':action_hash,'phase':'authority','reason':str(exc)}); self._cancel_remaining(ordered[index:],sealed_by_id,ledger,action_status,'authority_changed'); break
            bad_dependencies=[dep for dep in action.dependencies if action_status.get(dep)!='verified']
            if bad_dependencies:self.store.set_action_status(action_hash,'dependency_blocked'); ledger.release(action_hash,'dependency_blocked'); action_status[action.action_id]='dependency_blocked'; issues.append({'action_hash':action_hash,'phase':'dependency','reason':f'dependencies not verified: {bad_dependencies}'}); continue
            execution_input={'cycle_id':cycle_id,'owner_authority':{'policy_revision':snapshot['policy_revision'],'policy_hash':snapshot['policy_hash'],'operator_revision':snapshot['operator_revision'],'operator_hash':snapshot['operator_hash']},'actions':[sealed_row]}; grant_path=self._write_executor_grant(sealed_row)
            try:receipt=run_codex(paths=self.paths,role='executor',prompt=self._prompt('execute_sealed.md',execution_input),schema=self.root/'schemas/receipt.schema.json',output=run_dir/f'receipt-{index:03d}-{action.action_id}.json',timeout=self.timeout,model=self.model,grant_path=grant_path,allowed_mcp_tools=[action.tool_name])
            finally:
                try:grant_path.unlink(missing_ok=True)
                except OSError:pass
            item,problem=_one_receipt(receipt,cycle_id,action_hash,action.tool_name)
            if problem:outcome_status,outcome_summary='unknown',problem; item=item or {'action_hash':action_hash,'status':'unknown','tool_name':'','result':{},'error':problem}
            else:outcome=parse_outcome(item); outcome_status,outcome_summary=outcome.status,outcome.summary
            receipts.append(item); self.store.add_receipt(action_hash,outcome_status,item); self.store.set_action_status(action_hash,outcome_status); ledger.mark(action_hash,'executed' if outcome_status=='success' else 'uncertain')
            if action.action_type.lower().startswith('create_'):
                entity_id=_extract_entity_id(item.get('result'),action.entity_type)
                if entity_id:self.store.register_managed_entity(action.entity_type,entity_id,action_hash,'pending_verification')
            try:self._assert_authority(snapshot,require_autopilot=True)
            except AuthorityChanged as exc:issues.append({'action_hash':action_hash,'phase':'authority_after_write','reason':str(exc)})
            verification_input={'cycle_id':cycle_id,'sealed_actions':[sealed_row],'execution_receipt':{'cycle_id':cycle_id,'results':[item]}}
            verification=run_codex(paths=self.paths,role='verifier',prompt=self._prompt('verify.md',verification_input),schema=self.root/'schemas/verification.schema.json',output=run_dir/f'verification-{index:03d}-{action.action_id}.json',timeout=self.timeout,model=self.model)
            vitem,vproblem=_one_verification(verification,cycle_id,action_hash)
            if vproblem:vitem=vitem or {'action_hash':action_hash,'status':'unknown','observed':{},'differences':[vproblem]}
            verifications.append(vitem); vstatus=str(vitem.get('status') or 'unknown'); self.store.add_verification(action_hash,vstatus,vitem)
            if vstatus=='verified' and outcome_status=='success':
                self.store.set_action_status(action_hash,'verified'); ledger.mark(action_hash,'verified'); action_status[action.action_id]='verified'
                if action.action_type.lower().startswith('create_'):
                    entity_id=_extract_entity_id(vitem.get('observed'),action.entity_type) or _extract_entity_id(item.get('result'),action.entity_type)
                    if entity_id:self.store.register_managed_entity(action.entity_type,entity_id,action_hash,'verified')
            else:
                self.store.set_action_status(action_hash,'verification_failed'); ledger.mark(action_hash,'uncertain'); action_status[action.action_id]='verification_failed'; issues.append({'action_hash':action_hash,'phase':'verification','outcome':outcome_status,'outcome_summary':outcome_summary,'verification':vstatus,'differences':vitem.get('differences') or []})
                if policy.data.get('recovery',{}).get('pause_on_unknown_write_outcome',True):self.owner.system_pause(f'write/verification uncertainty at {action_hash}')
                self._cancel_remaining(ordered[index+1:],sealed_by_id,ledger,action_status,'previous_action_not_verified'); break
        (run_dir/'execution-summary.json').write_text(json.dumps({'receipts':receipts,'verifications':verifications,'issues':issues},indent=2)); status='completed' if not issues and all(action_status.get(a.action_id)=='verified' for a in ordered) else 'exception'; summary={'planned_actions':len(sealed),'verified_actions':sum(1 for x in action_status.values() if x=='verified'),'issues':issues}; self.store.finish_cycle(cycle_id,status,summary); return {'cycle_id':cycle_id,'status':status,**summary}
    def _write_executor_grant(self,sealed_row:dict[str,Any])->Path:
        tool_name=str(sealed_row.get('tool_name') or '').strip()
        if not tool_name or tool_name.startswith('mcp__'):raise RuntimeError('sealed action must carry the exact bare Amazon MCP tool_name')
        expires=datetime.now(UTC)+timedelta(seconds=min(max(self.timeout+60,300),3600)); grant={'version':1,'action_hash':str(sealed_row['action_hash']),'tool_name':tool_name,'arguments':sealed_row.get('arguments') or {},'expires_at':expires.isoformat().replace('+00:00','Z')}; grant['signature']=self.sealer.sign(grant); path=self.paths.grant_root/f"{grant['action_hash']}-{secrets.token_hex(8)}.json"; path.write_text(json.dumps(grant,separators=(',',':'))); path.chmod(0o600); return path
    def _cancel_remaining(self,actions:list[Action],sealed_by_id:dict[str,dict[str,Any]],ledger:BudgetLedger,action_status:dict[str,str],reason:str)->None:
        for action in actions:
            if action.action_id in action_status:continue
            row=sealed_by_id[action.action_id]; self.store.set_action_status(row['action_hash'],'cancelled'); ledger.release(row['action_hash'],reason); action_status[action.action_id]='cancelled'
    def _recent_state(self)->dict[str,Any]:return self.store.recent_state_summary()
def _topological_actions(actions:list[Action])->list[Action]:
    by_id={a.action_id:a for a in actions}; pending={a.action_id:set(a.dependencies) for a in actions}; ordered=[]
    while pending:
        ready=[a.action_id for a in actions if a.action_id in pending and not pending[a.action_id]]
        if not ready:raise PolicyError('action dependency graph contains a cycle')
        for action_id in ready:
            ordered.append(by_id[action_id]); pending.pop(action_id)
            for deps in pending.values():deps.discard(action_id)
    return ordered
def _one_receipt(receipt:Any,cycle_id:str,action_hash:str,expected_tool_name:str)->tuple[dict[str,Any]|None,str|None]:
    if not isinstance(receipt,dict) or str(receipt.get('cycle_id') or '')!=cycle_id:return None,'executor returned wrong/missing cycle_id'
    results=receipt.get('results')
    if not isinstance(results,list) or len(results)!=1:return None,'executor must return exactly one result for an atomic release'
    item=results[0] if isinstance(results[0],dict) else None
    if not item or str(item.get('action_hash') or '')!=action_hash:return item,'executor returned wrong/missing action_hash'
    if str(item.get('tool_name') or '')!=expected_tool_name:return item,'executor reported a tool different from the sealed MCP tool_name'
    return item,None
def _one_verification(value:Any,cycle_id:str,action_hash:str)->tuple[dict[str,Any]|None,str|None]:
    if not isinstance(value,dict) or str(value.get('cycle_id') or '')!=cycle_id:return None,'verifier returned wrong/missing cycle_id'
    results=value.get('results')
    if not isinstance(results,list) or len(results)!=1:return None,'verifier must return exactly one result for an atomic verification'
    item=results[0] if isinstance(results[0],dict) else None
    if not item or str(item.get('action_hash') or '')!=action_hash:return item,'verifier returned wrong/missing action_hash'
    return item,None
def _extract_entity_id(value:Any,entity_type:str)->str|None:
    candidates={'campaign':('campaignId','campaign_id'),'ad_group':('adGroupId','ad_group_id'),'adgroup':('adGroupId','ad_group_id'),'ad':('adId','ad_id'),'keyword':('keywordId','keyword_id'),'target':('targetId','target_id')}.get(str(entity_type).lower(),('id',)); wanted={''.join(ch for ch in x.lower() if ch.isalnum()) for x in candidates}; stack=[value]
    while stack:
        item=stack.pop()
        if isinstance(item,dict):
            for k,v in item.items():
                key=''.join(ch for ch in str(k).lower() if ch.isalnum())
                if key in wanted and v not in (None,''):return str(v)
                if isinstance(v,(dict,list)):stack.append(v)
        elif isinstance(item,list):stack.extend(item)
    return None
