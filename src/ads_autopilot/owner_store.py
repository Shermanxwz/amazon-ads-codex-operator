from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib, hmac, json
from pathlib import Path
import sqlite3
from typing import Any, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .canonical import canonical_json, digest

UTC=timezone.utc
def now_iso()->str: return datetime.now(UTC).isoformat()
def _deep_get(value:dict[str,Any],path:str)->Any:
    current:Any=value
    for part in path.split('.'):
        if not isinstance(current,dict) or part not in current: raise KeyError(path)
        current=current[part]
    return current
def _deep_set(value:dict[str,Any],path:str,new_value:Any)->None:
    parts=path.split('.'); current=value
    for part in parts[:-1]:
        child=current.get(part)
        if not isinstance(child,dict): child={}; current[part]=child
        current=child
    current[parts[-1]]=new_value

POLICY_EDITABLE_PATHS={
'autonomy.allow_campaign_creation','autonomy.allow_ad_group_creation','autonomy.allow_ad_creation','autonomy.allow_keyword_creation','autonomy.allow_target_creation','autonomy.allow_negative_targeting','autonomy.allow_state_changes','autonomy.allow_budget_decreases','autonomy.allow_budget_increases','autonomy.allow_bid_changes','autonomy.allow_placement_changes','scope.allowed_ad_products','scope.max_actions_per_cycle','scope.max_campaign_creates_per_day','scope.require_observed_asin_for_product_ad_create','scope.require_paused_campaign_create','scope.require_independent_verification','scope.require_prewrite_read','scope.prewrite_read_max_age_seconds','scope.cooldown_hours','scope.autonomous_campaign_name_prefix','scope.require_verified_activation','money.owner_daily_spend_ceiling','money.max_new_campaign_budget_per_day','money.max_single_campaign_budget','money.max_budget_increase_pct_per_action','money.max_profile_budget_increase_pct_per_cycle','money.reservation_hold_seconds','money.platform_buffer_pct','money.max_budget_decrease_pct_per_action','money.spend_evidence_max_age_seconds','bidding.max_bid_increase_pct_per_action','bidding.max_bid_decrease_pct_per_action','bidding.hourly_max_bid_change_pct','bidding.min_bid','bidding.max_bid','bidding.min_confidence_scale','bidding.min_confidence_reduce','placement.max_change_points_per_action','placement.min_multiplier_pct','placement.max_multiplier_pct','recovery.max_consecutive_failures','recovery.verification_grace_seconds','recovery.pause_on_unknown_write_outcome'}
OPERATOR_EDITABLE_PATHS={'advertiser_account_id','profile_ids','marketplaces','timezone','currency','objectives.primary','objectives.target_acos_pct','objectives.target_roas','objectives.break_even_acos_pct','objectives.minimum_orders_for_scaling','objectives.economics_available','scope.ad_products','scope.managed_asins','scope.exclude_campaign_name_regex','scheduling.hourly_pacing','scheduling.daily_optimization','scheduling.weekly_strategy','scheduling.daily_hour_local','scheduling.weekly_day','scheduling.weekly_hour_local'}
PERMANENT_BLOCKS=['billing','payment','account_admin','credentials','user_management','permanent_delete']
ALLOWED_AD_PRODUCTS={'SPONSORED_PRODUCTS'}
POLICY_BOOLEAN_PATHS=(
'autonomy.allow_campaign_creation','autonomy.allow_ad_group_creation','autonomy.allow_ad_creation','autonomy.allow_keyword_creation','autonomy.allow_target_creation','autonomy.allow_negative_targeting','autonomy.allow_state_changes','autonomy.allow_budget_decreases','autonomy.allow_budget_increases','autonomy.allow_bid_changes','autonomy.allow_placement_changes','scope.require_observed_asin_for_product_ad_create','scope.require_paused_campaign_create','scope.require_independent_verification','scope.require_prewrite_read','scope.require_verified_activation','recovery.pause_on_unknown_write_outcome')
OPERATOR_BOOLEAN_PATHS=('objectives.economics_available','scheduling.hourly_pacing','scheduling.daily_optimization','scheduling.weekly_strategy')

def _require_boolean_paths(value:dict[str,Any],paths:tuple[str,...])->None:
    for path in paths:
        try: item=_deep_get(value,path)
        except KeyError: raise ValueError(f'{path} must be present and boolean')
        if type(item) is not bool: raise ValueError(f'{path} must be boolean')

class OwnerStore:
    def __init__(self,path:str|Path,audit_key:bytes):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700); self.audit_key=bytes(audit_key); self._init()
        try:self.path.chmod(0o600)
        except OSError:pass
    @contextmanager
    def connection(self)->Iterator[sqlite3.Connection]:
        conn=sqlite3.connect(self.path,timeout=30); conn.row_factory=sqlite3.Row
        try:
            conn.execute('PRAGMA journal_mode=WAL'); conn.execute('PRAGMA foreign_keys=ON'); conn.execute('PRAGMA synchronous=FULL'); yield conn; conn.commit()
        except Exception: conn.rollback(); raise
        finally: conn.close()
    def _init(self)->None:
        with self.connection() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS owner_documents(kind TEXT PRIMARY KEY,revision INTEGER NOT NULL,body_json TEXT NOT NULL,body_hash TEXT NOT NULL,updated_at TEXT NOT NULL,updated_by TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS owner_revisions(kind TEXT NOT NULL,revision INTEGER NOT NULL,body_json TEXT NOT NULL,body_hash TEXT NOT NULL,created_at TEXT NOT NULL,created_by TEXT NOT NULL,PRIMARY KEY(kind,revision));
            CREATE TABLE IF NOT EXISTS control_state(id INTEGER PRIMARY KEY CHECK(id=1),mode TEXT NOT NULL,emergency_stop INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,updated_by TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS secrets_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS owner_audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT NOT NULL,actor TEXT NOT NULL,payload_json TEXT NOT NULL,previous_hash TEXT NOT NULL,entry_hash TEXT NOT NULL UNIQUE,signature TEXT NOT NULL,created_at TEXT NOT NULL);
            """)
    def bootstrap(self,policy:dict[str,Any],operator:dict[str,Any],password_hash:str)->None:
        policy=self._sanitize_policy(policy); operator=self._sanitize_operator(operator)
        with self.connection() as c:
            existing=c.execute('SELECT COUNT(*) n FROM owner_documents').fetchone()['n']
            if not existing: self._put_document(c,'policy',policy,'bootstrap'); self._put_document(c,'operator',operator,'bootstrap')
            if not c.execute('SELECT 1 FROM control_state WHERE id=1').fetchone(): c.execute("INSERT INTO control_state(id,mode,emergency_stop,updated_at,updated_by) VALUES(1,'observe',0,?,?)",(now_iso(),'bootstrap'))
            if not c.execute("SELECT 1 FROM secrets_meta WHERE key='control_password_hash'").fetchone(): c.execute("INSERT INTO secrets_meta(key,value,updated_at) VALUES('control_password_hash',?,?)",(password_hash,now_iso()))
            self._append_audit(c,'owner.bootstrap','bootstrap',{'documents_created':not bool(existing)})
    def _put_document(self,c:sqlite3.Connection,kind:str,body:dict[str,Any],actor:str)->dict[str,Any]:
        row=c.execute('SELECT revision FROM owner_documents WHERE kind=?',(kind,)).fetchone(); revision=int(row['revision'] if row else 0)+1; body_json=canonical_json(body); body_hash=hashlib.sha256(body_json.encode()).hexdigest(); stamp=now_iso()
        c.execute('INSERT INTO owner_documents(kind,revision,body_json,body_hash,updated_at,updated_by) VALUES(?,?,?,?,?,?) ON CONFLICT(kind) DO UPDATE SET revision=excluded.revision,body_json=excluded.body_json,body_hash=excluded.body_hash,updated_at=excluded.updated_at,updated_by=excluded.updated_by',(kind,revision,body_json,body_hash,stamp,actor))
        c.execute('INSERT INTO owner_revisions(kind,revision,body_json,body_hash,created_at,created_by) VALUES(?,?,?,?,?,?)',(kind,revision,body_json,body_hash,stamp,actor)); return {'kind':kind,'revision':revision,'hash':body_hash}
    def _append_audit(self,c:sqlite3.Connection,event_type:str,actor:str,payload:dict[str,Any])->None:
        row=c.execute('SELECT entry_hash FROM owner_audit ORDER BY seq DESC LIMIT 1').fetchone(); previous=str(row['entry_hash'] if row else 'GENESIS'); stamp=now_iso(); payload_json=canonical_json(payload)
        material=canonical_json({'event_type':event_type,'actor':actor,'payload':json.loads(payload_json),'previous_hash':previous,'created_at':stamp}); entry_hash=hashlib.sha256(material.encode()).hexdigest(); signature=hmac.new(self.audit_key,entry_hash.encode(),hashlib.sha256).hexdigest()
        c.execute('INSERT INTO owner_audit(event_type,actor,payload_json,previous_hash,entry_hash,signature,created_at) VALUES(?,?,?,?,?,?,?)',(event_type,actor,payload_json,previous,entry_hash,signature,stamp))
    def _document(self,kind:str)->dict[str,Any]:
        with self.connection() as c: row=c.execute('SELECT * FROM owner_documents WHERE kind=?',(kind,)).fetchone()
        if not row: raise RuntimeError(f'owner document missing: {kind}; run bootstrap')
        return {'revision':int(row['revision']),'hash':str(row['body_hash']),'body':json.loads(row['body_json']),'updated_at':row['updated_at'],'updated_by':row['updated_by']}
    def snapshot(self)->dict[str,Any]:
        policy=self._document('policy'); operator=self._document('operator')
        with self.connection() as c: control=c.execute('SELECT * FROM control_state WHERE id=1').fetchone()
        if not control: raise RuntimeError('owner control state missing; run bootstrap')
        effective=deepcopy(policy['body']); effective.setdefault('recovery',{})['kill_switch']=bool(control['emergency_stop']); effective['permanent_blocks']=list(PERMANENT_BLOCKS); effective.setdefault('autonomy',{})['human_approval_required']=False; effective['autonomy']['mode']='full_managed'
        return {'mode':str(control['mode']),'emergency_stop':bool(control['emergency_stop']),'control_updated_at':str(control['updated_at']),'policy':effective,'policy_revision':policy['revision'],'policy_hash':digest(effective),'operator':operator['body'],'operator_revision':operator['revision'],'operator_hash':operator['hash']}
    def get_password_hash(self)->str:
        with self.connection() as c: row=c.execute("SELECT value FROM secrets_meta WHERE key='control_password_hash'").fetchone()
        if not row: raise RuntimeError('control password is not initialized')
        return str(row['value'])
    def update_password_hash(self,password_hash:str,actor:str='owner-web')->None:
        with self.connection() as c:
            c.execute("INSERT INTO secrets_meta(key,value,updated_at) VALUES('control_password_hash',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(password_hash,now_iso())); self._append_audit(c,'owner.password_changed',actor,{'changed':True})
    def set_mode(self,mode:str,actor:str='owner-web')->dict[str,Any]:
        mode=str(mode).lower().strip()
        if mode not in {'autopilot','observe','paused'}: raise ValueError('mode must be autopilot, observe, or paused')
        with self.connection() as c:
            old=c.execute('SELECT mode,emergency_stop FROM control_state WHERE id=1').fetchone()
            if not old: raise RuntimeError('owner control state missing')
            if bool(old['emergency_stop']) and mode=='autopilot': raise ValueError('clear emergency stop before enabling autopilot')
            if mode=='autopilot':
                policy=json.loads(c.execute("SELECT body_json FROM owner_documents WHERE kind='policy'").fetchone()['body_json']); operator=json.loads(c.execute("SELECT body_json FROM owner_documents WHERE kind='operator'").fetchone()['body_json']); blockers=_autopilot_blockers(policy,operator)
                if blockers: raise ValueError('autopilot readiness failed: '+'; '.join(blockers))
            c.execute('UPDATE control_state SET mode=?,updated_at=?,updated_by=? WHERE id=1',(mode,now_iso(),actor)); self._append_audit(c,'owner.mode_changed',actor,{'from':old['mode'],'to':mode})
        return self.snapshot()
    def system_pause(self,reason:str,actor:str='controller')->dict[str,Any]:
        with self.connection() as c:
            old=c.execute('SELECT mode,emergency_stop FROM control_state WHERE id=1').fetchone(); c.execute("UPDATE control_state SET mode='paused',updated_at=?,updated_by=? WHERE id=1",(now_iso(),actor)); self._append_audit(c,'system.auto_paused',actor,{'previous_mode':old['mode'] if old else None,'reason':str(reason)[:2000]})
        return self.snapshot()
    def emergency_stop(self,actor:str='owner-web')->dict[str,Any]:
        with self.connection() as c:
            old=c.execute('SELECT mode,emergency_stop FROM control_state WHERE id=1').fetchone(); c.execute("UPDATE control_state SET mode='paused',emergency_stop=1,updated_at=?,updated_by=? WHERE id=1",(now_iso(),actor)); self._append_audit(c,'owner.emergency_stop',actor,{'previous_mode':old['mode'] if old else None})
        return self.snapshot()
    def clear_emergency_stop(self,actor:str='owner-web')->dict[str,Any]:
        with self.connection() as c:
            old=c.execute('SELECT emergency_stop FROM control_state WHERE id=1').fetchone(); c.execute("UPDATE control_state SET emergency_stop=0,mode='observe',updated_at=?,updated_by=? WHERE id=1",(now_iso(),actor)); self._append_audit(c,'owner.emergency_stop_cleared',actor,{'was_set':bool(old and old['emergency_stop'])})
        return self.snapshot()
    def update_policy(self,patch:dict[str,Any],actor:str='owner-web')->dict[str,Any]:
        updated=deepcopy(self._document('policy')['body']); changed={}
        for path,value in patch.items():
            if path not in POLICY_EDITABLE_PATHS: raise ValueError(f'policy field is not owner-editable: {path}')
            _deep_set(updated,path,value); changed[path]=value
        updated=self._sanitize_policy(updated)
        with self.connection() as c:
            info=self._put_document(c,'policy',updated,actor); self._append_audit(c,'owner.policy_changed',actor,{'revision':info['revision'],'hash':info['hash'],'changed':changed})
        return self.snapshot()
    def update_operator(self,patch:dict[str,Any],actor:str='owner-web')->dict[str,Any]:
        updated=deepcopy(self._document('operator')['body']); changed={}
        for path,value in patch.items():
            if path not in OPERATOR_EDITABLE_PATHS: raise ValueError(f'operator field is not owner-editable: {path}')
            _deep_set(updated,path,value); changed[path]=value
        updated=self._sanitize_operator(updated)
        with self.connection() as c:
            info=self._put_document(c,'operator',updated,actor); self._append_audit(c,'owner.operator_changed',actor,{'revision':info['revision'],'hash':info['hash'],'changed':changed})
        return self.snapshot()
    def restore_revision(self,kind:str,revision:int,actor:str='owner-web')->dict[str,Any]:
        if kind not in {'policy','operator'}: raise ValueError('kind must be policy or operator')
        with self.connection() as c:
            row=c.execute('SELECT body_json,body_hash FROM owner_revisions WHERE kind=? AND revision=?',(kind,int(revision))).fetchone()
            if not row: raise ValueError(f'unknown {kind} revision: {revision}')
            body=json.loads(row['body_json'])
        body=self._sanitize_policy(body) if kind=='policy' else self._sanitize_operator(body)
        with self.connection() as c:
            info=self._put_document(c,kind,body,actor); self._append_audit(c,'owner.revision_restored',actor,{'kind':kind,'source_revision':int(revision),'new_revision':info['revision'],'hash':info['hash']})
        self.set_mode('observe',actor=actor); return self.snapshot()
    def audit(self,limit:int=200)->list[dict[str,Any]]:
        with self.connection() as c: rows=c.execute('SELECT * FROM owner_audit ORDER BY seq DESC LIMIT ?',(max(1,min(2000,int(limit))),)).fetchall()
        return [{**dict(r),'payload':json.loads(r['payload_json'])} for r in rows]
    def revisions(self,kind:str,limit:int=50)->list[dict[str,Any]]:
        if kind not in {'policy','operator'}: raise ValueError('kind must be policy or operator')
        with self.connection() as c: rows=c.execute('SELECT * FROM owner_revisions WHERE kind=? ORDER BY revision DESC LIMIT ?',(kind,max(1,min(500,int(limit))))).fetchall()
        return [{**dict(r),'body':json.loads(r['body_json'])} for r in rows]
    def verify_audit_chain(self)->dict[str,Any]:
        with self.connection() as c: rows=c.execute('SELECT * FROM owner_audit ORDER BY seq ASC').fetchall()
        previous='GENESIS'
        for row in rows:
            if row['previous_hash']!=previous: return {'ok':False,'seq':row['seq'],'reason':'previous hash mismatch'}
            material=canonical_json({'event_type':row['event_type'],'actor':row['actor'],'payload':json.loads(row['payload_json']),'previous_hash':row['previous_hash'],'created_at':row['created_at']}); entry_hash=hashlib.sha256(material.encode()).hexdigest()
            if not hmac.compare_digest(entry_hash,row['entry_hash']): return {'ok':False,'seq':row['seq'],'reason':'entry hash mismatch'}
            expected_sig=hmac.new(self.audit_key,entry_hash.encode(),hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected_sig,row['signature']): return {'ok':False,'seq':row['seq'],'reason':'signature mismatch'}
            previous=row['entry_hash']
        return {'ok':True,'entries':len(rows),'head':previous}
    @staticmethod
    def _sanitize_policy(policy:dict[str,Any])->dict[str,Any]:
        p=deepcopy(policy); p['permanent_blocks']=list(PERMANENT_BLOCKS); p.setdefault('autonomy',{})['human_approval_required']=False; p['autonomy']['allow_irreversible_cleanup']=False
        _require_boolean_paths(p,POLICY_BOOLEAN_PATHS)
        products=p.setdefault('scope',{}).get('allowed_ad_products') or []
        if not isinstance(products,list) or not products: raise ValueError('at least one allowed_ad_product is required')
        normalized=[str(x).upper() for x in products]; unknown=set(normalized)-ALLOWED_AD_PRODUCTS
        if unknown: raise ValueError(f'ad products are not production-certified in this release: {sorted(unknown)}')
        p['scope']['allowed_ad_products']=normalized; scope=p['scope']; money=p.setdefault('money',{}); bid=p.setdefault('bidding',{}); placement=p.setdefault('placement',{}); recovery=p.setdefault('recovery',{})
        _int_range(scope,'max_actions_per_cycle',1,500); _int_range(scope,'max_campaign_creates_per_day',0,100); _number_range(scope,'prewrite_read_max_age_seconds',30,3600); _number_range(scope,'cooldown_hours',0,8760)
        if money.get('owner_daily_spend_ceiling') is not None: _number_range(money,'owner_daily_spend_ceiling',0.01,1_000_000_000)
        _number_range(money,'max_new_campaign_budget_per_day',0.01,1_000_000_000); _number_range(money,'max_single_campaign_budget',0.01,1_000_000_000); _number_range(money,'max_budget_increase_pct_per_action',0,1000); _number_range(money,'max_budget_decrease_pct_per_action',0,100); _number_range(money,'max_profile_budget_increase_pct_per_cycle',0,1000); _number_range(money,'reservation_hold_seconds',60,86400); _number_range(money,'platform_buffer_pct',0,99.99); _number_range(money,'spend_evidence_max_age_seconds',60,86400)
        _number_range(bid,'max_bid_increase_pct_per_action',0,1000); _number_range(bid,'max_bid_decrease_pct_per_action',0,100); _number_range(bid,'hourly_max_bid_change_pct',0,100); _number_range(bid,'min_bid',0.01,1_000_000); _number_range(bid,'max_bid',0.01,1_000_000)
        if float(bid['max_bid'])<float(bid['min_bid']): raise ValueError('max_bid must be >= min_bid')
        _number_range(bid,'min_confidence_scale',0,1); _number_range(bid,'min_confidence_reduce',0,1); _number_range(placement,'max_change_points_per_action',0,900); _number_range(placement,'min_multiplier_pct',0,900); _number_range(placement,'max_multiplier_pct',0,900)
        if float(placement['max_multiplier_pct'])<float(placement['min_multiplier_pct']): raise ValueError('invalid placement range')
        _int_range(recovery,'max_consecutive_failures',1,100); _number_range(recovery,'verification_grace_seconds',0,3600); prefix=str(scope.get('autonomous_campaign_name_prefix') or '')
        if len(prefix)<3 or len(prefix)>32: raise ValueError('autonomous campaign prefix must be 3-32 characters')
        return p
    @staticmethod
    def _sanitize_operator(operator:dict[str,Any])->dict[str,Any]:
        o=deepcopy(operator); _require_boolean_paths(o,OPERATOR_BOOLEAN_PATHS)
        if not isinstance(o.get('profile_ids'),list): raise ValueError('profile_ids must be a list')
        if not isinstance(o.get('marketplaces'),list) or not o.get('marketplaces'): raise ValueError('at least one marketplace is required')
        o['profile_ids']=[str(x).strip() for x in o['profile_ids'] if str(x).strip()]
        if len(o['profile_ids'])>100: raise ValueError('too many profile_ids')
        o['marketplaces']=[str(x).strip().upper() for x in o['marketplaces'] if str(x).strip()]
        if any(len(x)>8 for x in o['marketplaces']): raise ValueError('invalid marketplace code')
        managed=o.setdefault('scope',{}).get('managed_asins') or []
        if not isinstance(managed,list): raise ValueError('managed_asins must be a list')
        o['scope']['managed_asins']=sorted({str(x).strip().upper() for x in managed if str(x).strip()})
        if len(o['scope']['managed_asins'])>10000: raise ValueError('too many managed ASINs')
        products=o['scope'].get('ad_products') or []
        if not isinstance(products,list) or not products: raise ValueError('operator ad_products must be a non-empty list')
        products=[str(x).upper() for x in products]; unknown=set(products)-ALLOWED_AD_PRODUCTS
        if unknown: raise ValueError(f'ad products are not production-certified in this release: {sorted(unknown)}')
        o['scope']['ad_products']=products; objectives=o.setdefault('objectives',{})
        for key in ('target_acos_pct','target_roas','break_even_acos_pct'): _number_range(objectives,key,0.0001,1_000_000)
        _int_range(objectives,'minimum_orders_for_scaling',1,1_000_000); scheduling=o.setdefault('scheduling',{}); _int_range(scheduling,'daily_hour_local',0,23); _int_range(scheduling,'weekly_hour_local',0,23); weekday=str(scheduling.get('weekly_day') or 'Sun').title()[:3]
        if weekday not in {'Mon','Tue','Wed','Thu','Fri','Sat','Sun'}: raise ValueError('weekly_day must be Mon-Sun')
        scheduling['weekly_day']=weekday; tz=str(o.get('timezone') or '').strip()
        try: ZoneInfo(tz)
        except (ZoneInfoNotFoundError,ValueError): raise ValueError('timezone must be a valid IANA timezone')
        currency=str(o.get('currency') or '').strip().upper()
        if len(currency)!=3 or not currency.isalpha(): raise ValueError('currency must be a 3-letter code')
        o['currency']=currency; return o

def _number_range(mapping:dict[str,Any],key:str,low:float,high:float)->None:
    raw=mapping.get(key)
    if isinstance(raw,bool): raise ValueError(f'{key} must be numeric, not boolean')
    try:value=float(raw)
    except (TypeError,ValueError):raise ValueError(f'{key} must be numeric')
    if not low<=value<=high:raise ValueError(f'{key} must be between {low} and {high}')
def _int_range(mapping:dict[str,Any],key:str,low:int,high:int)->None:
    try:
        raw=mapping.get(key)
        if isinstance(raw,bool): raise ValueError
        value=int(raw)
        if isinstance(raw,float) and raw!=value:raise ValueError
    except (TypeError,ValueError):raise ValueError(f'{key} must be an integer')
    if not low<=value<=high:raise ValueError(f'{key} must be between {low} and {high}')
    mapping[key]=value
def _autopilot_blockers(policy:dict[str,Any],operator:dict[str,Any])->list[str]:
    reasons=[]
    if policy.get('money',{}).get('owner_daily_spend_ceiling') is None:reasons.append('owner_daily_spend_ceiling is not set')
    profiles=[str(x).strip() for x in operator.get('profile_ids',[]) if str(x).strip() and str(x).strip()!='REPLACE_ME']
    if not profiles:reasons.append('no real profile_id configured')
    account=str(operator.get('advertiser_account_id') or '').strip()
    if not account or account=='REPLACE_ME':reasons.append('advertiser_account_id is not configured')
    op={str(x).upper() for x in operator.get('scope',{}).get('ad_products',[])}; allowed={str(x).upper() for x in policy.get('scope',{}).get('allowed_ad_products',[])}
    if not op or not op.issubset(allowed):reasons.append('operator ad products exceed owner policy')
    return reasons
