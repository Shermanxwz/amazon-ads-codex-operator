from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json, os, sqlite3
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

UTC=timezone.utc

def now_iso()->str: return datetime.now(UTC).isoformat()
def _norm(value:Any)->str: return ''.join(ch for ch in str(value).lower() if ch.isalnum())

def _day_bounds(timezone_name:str)->tuple[str,str]:
    tz=ZoneInfo(timezone_name)
    local_now=datetime.now(tz)
    start_local=local_now.replace(hour=0,minute=0,second=0,microsecond=0)
    end_local=start_local+timedelta(days=1)
    return start_local.astimezone(UTC).isoformat(), end_local.astimezone(UTC).isoformat()

def _is_campaign_create_payload(payload:dict[str,Any])->bool:
    if _norm(payload.get('entity_type'))!='campaign': return False
    action=_norm(payload.get('action_type')); tool=_norm(payload.get('tool_name'))
    return action.startswith('createcampaign') or ('campaign' in tool and any(token in tool for token in ('create','add')))

class Store:
    def __init__(self, path: str|Path):
        self.path=Path(path); self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700); self._init()
        try: self.path.chmod(0o600)
        except OSError: pass
    @contextmanager
    def connection(self)->Iterator[sqlite3.Connection]:
        conn=sqlite3.connect(self.path, timeout=30); conn.row_factory=sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA foreign_keys=ON")
            yield conn; conn.commit()
        except Exception:
            conn.rollback(); raise
        finally: conn.close()
    def _init(self):
        with self.connection() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS cycles(id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, plan_hash TEXT, policy_hash TEXT, started_at TEXT NOT NULL, finished_at TEXT, summary_json TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS actions(action_hash TEXT PRIMARY KEY, cycle_id TEXT NOT NULL, action_id TEXT NOT NULL, action_type TEXT NOT NULL, payload_json TEXT NOT NULL, signature TEXT NOT NULL, status TEXT NOT NULL, spend_delta REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL, FOREIGN KEY(cycle_id) REFERENCES cycles(id));
            CREATE INDEX IF NOT EXISTS idx_actions_cycle ON actions(cycle_id,created_at);
            CREATE INDEX IF NOT EXISTS idx_actions_type_time ON actions(action_type,created_at);
            CREATE TABLE IF NOT EXISTS reservations(id INTEGER PRIMARY KEY AUTOINCREMENT, day_key TEXT NOT NULL, action_hash TEXT NOT NULL UNIQUE, amount REAL NOT NULL, status TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_reservations_day ON reservations(day_key,status);
            CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY AUTOINCREMENT, action_hash TEXT NOT NULL, status TEXT NOT NULL, tool_name TEXT, result_json TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS verifications(id INTEGER PRIMARY KEY AUTOINCREMENT, action_hash TEXT NOT NULL, status TEXT NOT NULL, observed_json TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_verifications_action ON verifications(action_hash,created_at DESC);
            CREATE TABLE IF NOT EXISTS managed_entities(entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, source_action_hash TEXT NOT NULL, activation_status TEXT NOT NULL, created_at TEXT NOT NULL, verified_at TEXT, PRIMARY KEY(entity_type,entity_id));
            CREATE INDEX IF NOT EXISTS idx_managed_entities_source ON managed_entities(source_action_hash);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, level TEXT NOT NULL, event_type TEXT NOT NULL, cycle_id TEXT, data_json TEXT NOT NULL, created_at TEXT NOT NULL);
            """)
    def _owner_timezone(self)->str:
        owner_db=self.path.with_name('owner.db')
        if not owner_db.exists(): return 'UTC'
        try:
            with sqlite3.connect(owner_db,timeout=2) as conn:
                row=conn.execute("SELECT body_json FROM owner_documents WHERE kind='operator'").fetchone()
            value=json.loads(row[0] or '{}') if row else {}
            timezone_name=str(value.get('timezone') or 'UTC'); ZoneInfo(timezone_name); return timezone_name
        except Exception: return 'UTC'
    def create_cycle(self, cycle_id:str, kind:str):
        with self.connection() as c: c.execute("INSERT INTO cycles(id,kind,status,started_at) VALUES(?,?,?,?)",(cycle_id,kind,"planning",now_iso()))
    def finish_cycle(self, cycle_id:str,status:str,summary:dict[str,Any]):
        with self.connection() as c: c.execute("UPDATE cycles SET status=?,finished_at=?,summary_json=? WHERE id=?",(status,now_iso(),json.dumps(summary),cycle_id))
    def set_plan(self,cycle_id:str,plan_hash:str,policy_hash:str):
        with self.connection() as c: c.execute("UPDATE cycles SET plan_hash=?,policy_hash=?,status='released' WHERE id=?",(plan_hash,policy_hash,cycle_id))
    def add_action(self,cycle_id:str,row:dict[str,Any]):
        with self.connection() as c: c.execute("INSERT INTO actions(action_hash,cycle_id,action_id,action_type,payload_json,signature,status,spend_delta,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(row['action_hash'],cycle_id,row['action_id'],row['action_type'],json.dumps(row,sort_keys=True),row['signature'],'released',float(row.get('spend_delta') or 0),now_iso()))
    def set_action_status(self,action_hash:str,status:str):
        with self.connection() as c: c.execute("UPDATE actions SET status=? WHERE action_hash=?",(status,action_hash))
    def action(self,action_hash:str)->dict[str,Any]|None:
        with self.connection() as c:
            row=c.execute("SELECT * FROM actions WHERE action_hash=?",(action_hash,)).fetchone()
            if not row: return None
            out=dict(row); out['payload']=json.loads(out.pop('payload_json') or '{}'); return out
    def add_receipt(self,action_hash:str,status:str,result:dict[str,Any]):
        with self.connection() as c: c.execute("INSERT INTO receipts(action_hash,status,tool_name,result_json,created_at) VALUES(?,?,?,?,?)",(action_hash,status,str(result.get('tool_name') or ''),json.dumps(result),now_iso()))
    def add_verification(self,action_hash:str,status:str,observed:dict[str,Any]):
        with self.connection() as c: c.execute("INSERT INTO verifications(action_hash,status,observed_json,created_at) VALUES(?,?,?,?)",(action_hash,status,json.dumps(observed),now_iso()))
    def register_managed_entity(self,entity_type:str,entity_id:str,source_action_hash:str,status:str)->None:
        entity_type=str(entity_type or '').lower().strip(); entity_id=str(entity_id or '').strip()
        if not entity_type or not entity_id: return
        verified_at=now_iso() if status=='verified' else None
        with self.connection() as c:
            c.execute("INSERT INTO managed_entities(entity_type,entity_id,source_action_hash,activation_status,created_at,verified_at) VALUES(?,?,?,?,?,?) ON CONFLICT(entity_type,entity_id) DO UPDATE SET source_action_hash=excluded.source_action_hash,activation_status=excluded.activation_status,verified_at=COALESCE(excluded.verified_at,managed_entities.verified_at)",(entity_type,entity_id,source_action_hash,status,now_iso(),verified_at))
    def managed_entity(self,entity_type:str,entity_id:str)->dict[str,Any]|None:
        with self.connection() as c:
            row=c.execute("SELECT * FROM managed_entities WHERE entity_type=? AND entity_id=?",(str(entity_type).lower(),str(entity_id))).fetchone()
            return dict(row) if row else None
    def event(self,level:str,event_type:str,cycle_id:str|None,data:dict[str,Any]):
        with self.connection() as c: c.execute("INSERT INTO events(level,event_type,cycle_id,data_json,created_at) VALUES(?,?,?,?,?)",(level,event_type,cycle_id,json.dumps(data),now_iso()))
    def consecutive_exceptions(self,exclude_cycle_id:str|None=None,limit:int=20)->int:
        with self.connection() as c:
            rows=c.execute("SELECT id,status FROM cycles WHERE finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT ?",(limit,)).fetchall()
        count=0
        for row in rows:
            if exclude_cycle_id and row['id']==exclude_cycle_id: continue
            if row['status']=='exception': count+=1
            else: break
        return count
    def campaign_creates_today(self,timezone_name:str)->tuple[int,float]:
        start,end=_day_bounds(timezone_name)
        with self.connection() as c:
            rows=c.execute("SELECT payload_json,status FROM actions WHERE created_at>=? AND created_at<?",(start,end)).fetchall()
        count=0; budget=0.0
        for row in rows:
            if row['status'] in {'rejected','cancelled','dry_run'}: continue
            try: payload=json.loads(row['payload_json'] or '{}')
            except Exception: continue
            if not _is_campaign_create_payload(payload): continue
            args=payload.get('arguments') or {}; after=payload.get('after') or {}
            value=args.get('budget',args.get('dailyBudget',after.get('budget',0)))
            try: amount=max(0.0,float(value or 0))
            except (TypeError,ValueError): amount=0.0
            count+=1; budget+=amount
        return count,budget
    def recent_same_entity_action(self,entity_type:str,entity_id:str,action_family:str,since_iso:str)->dict[str,Any]|None:
        with self.connection() as c:
            rows=c.execute("SELECT * FROM actions WHERE created_at>=? ORDER BY created_at DESC LIMIT 500",(since_iso,)).fetchall()
        for row in rows:
            try: payload=json.loads(row['payload_json'] or '{}')
            except Exception: continue
            if str(payload.get('entity_type') or '').lower()!=str(entity_type or '').lower(): continue
            if str(payload.get('entity_id') or '')!=str(entity_id or ''): continue
            family=_action_family(str(payload.get('action_type') or ''),payload.get('arguments') or {})
            if family==action_family and row['status'] not in {'rejected','cancelled','dry_run'}:
                out=dict(row); out['payload']=payload; return out
        return None
    def list_cycles(self,limit:int=50)->list[dict[str,Any]]:
        with self.connection() as c:
            rows=c.execute("SELECT * FROM cycles ORDER BY started_at DESC LIMIT ?",(max(1,min(1000,int(limit))),)).fetchall()
        out=[]
        for r in rows:
            d=dict(r)
            try: d['summary']=json.loads(d.pop('summary_json') or '{}')
            except Exception: d['summary']={}
            out.append(d)
        return out
    def list_actions(self,limit:int=200)->list[dict[str,Any]]:
        with self.connection() as c:
            rows=c.execute("SELECT a.*,v.status verification_status,v.created_at verification_at FROM actions a LEFT JOIN verifications v ON v.id=(SELECT id FROM verifications vv WHERE vv.action_hash=a.action_hash ORDER BY vv.id DESC LIMIT 1) ORDER BY a.created_at DESC LIMIT ?",(max(1,min(2000,int(limit))),)).fetchall()
        out=[]
        for r in rows:
            d=dict(r)
            try: d['payload']=json.loads(d.pop('payload_json') or '{}')
            except Exception: d['payload']={}
            out.append(d)
        return out
    def list_events(self,limit:int=200)->list[dict[str,Any]]:
        with self.connection() as c:
            rows=c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?",(max(1,min(2000,int(limit))),)).fetchall()
        out=[]
        for r in rows:
            d=dict(r)
            try: d['data']=json.loads(d.pop('data_json') or '{}')
            except Exception: d['data']={}
            out.append(d)
        return out
    def reservation_summary(self,day_key:str|None=None)->dict[str,Any]:
        day_key=day_key or datetime.now(ZoneInfo(self._owner_timezone())).date().isoformat()
        with self.connection() as c:
            rows=c.execute("SELECT status,COUNT(*) count,COALESCE(SUM(amount),0) amount FROM reservations WHERE day_key=? GROUP BY status",(day_key,)).fetchall()
        return {'day_key':day_key,'by_status':{str(r['status']):{'count':int(r['count']),'amount':float(r['amount'] or 0)} for r in rows}}
    def integrity_check(self)->dict[str,Any]:
        with self.connection() as c:
            result=str(c.execute("PRAGMA integrity_check").fetchone()[0]); fk=[tuple(r) for r in c.execute("PRAGMA foreign_key_check").fetchall()]
        return {'ok':result.lower()=='ok' and not fk,'integrity':result,'foreign_key_errors':len(fk)}
    def dashboard(self)->dict[str,Any]:
        return {'integrity':self.integrity_check(),'cycles':self.list_cycles(12),'actions':self.list_actions(40),'events':self.list_events(40),'reservations':self.reservation_summary(),'state_summary':self.recent_state_summary(5,20)}
    def recent_state_summary(self,cycle_limit:int=10,action_limit:int=50)->dict[str,Any]:
        with self.connection() as c:
            cycles=[dict(r) for r in c.execute("SELECT kind,status,started_at,finished_at,summary_json FROM cycles ORDER BY started_at DESC LIMIT ?",(cycle_limit,)).fetchall()]
            rows=c.execute("SELECT a.action_hash,a.action_type,a.status,a.payload_json,a.created_at,v.status verification_status,v.observed_json,v.created_at verification_at FROM actions a LEFT JOIN verifications v ON v.id=(SELECT id FROM verifications vv WHERE vv.action_hash=a.action_hash ORDER BY vv.id DESC LIMIT 1) ORDER BY a.created_at DESC LIMIT ?",(action_limit,)).fetchall()
            managed=[dict(r) for r in c.execute("SELECT * FROM managed_entities ORDER BY created_at DESC LIMIT 100").fetchall()]
        actions=[]
        for r in rows:
            d=dict(r)
            try: d['payload']=json.loads(d.pop('payload_json') or '{}')
            except Exception: d['payload']={}
            try: d['observed']=json.loads(d.pop('observed_json') or '{}') if d.get('observed_json') else {}
            except Exception: d['observed']={}
            d.pop('observed_json',None); actions.append(d)
        return {'recent_cycles':cycles,'recent_actions':actions,'managed_entities':managed}

def _action_family(action_type:str,args:dict[str,Any])->str:
    action=str(action_type or '').lower(); field=str(args.get('field') or '').lower()
    if 'budget' in action or field=='budget' or any(k in args for k in ('budget','dailyBudget','budgetAmount')): return 'budget'
    if 'bid' in action or field=='bid' or any(k in args for k in ('bid','newBid','bidAmount')): return 'bid'
    if 'placement' in action or field in {'placement','placement_pct'}: return 'placement'
    if 'negative' in action: return 'negative'
    if action.startswith('create_'): return 'create'
    if any(x in action for x in ('pause','enable','resume','state')) or any(k in args for k in ('state','status')): return 'state'
    return action or 'other'
