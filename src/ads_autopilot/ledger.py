from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from .state import Store, now_iso

UTC=timezone.utc
class BudgetError(ValueError): pass

# Ambiguous/unknown writes remain charged against the owner envelope until they
# are independently reconciled. This is intentionally conservative.
COUNTABLE={'reserved','pending','unknown','uncertain','executed','verified','verification_failed'}

class BudgetLedger:
    def __init__(self,store:Store,policy:dict[str,Any]): self.store=store; self.policy=policy
    def day_key(self,at:datetime|None=None)->str: return (at or datetime.now(UTC)).date().isoformat()
    def reserved_total(self,day_key:str|None=None)->float:
        day_key=day_key or self.day_key(); marks=','.join('?' for _ in COUNTABLE)
        with self.store.connection() as c:
            row=c.execute(f"SELECT COALESCE(SUM(amount),0) total FROM reservations WHERE day_key=? AND status IN ({marks})",(day_key,*sorted(COUNTABLE))).fetchone()
            return float(row['total'] or 0)
    def reserve(self,action_hash:str,amount:float,observed_spend:float)->None:
        if amount<=0: return
        ceiling=self.policy['money'].get('owner_daily_spend_ceiling')
        if ceiling is None: raise BudgetError('owner_daily_spend_ceiling must be configured before autonomous spend increases')
        buffer=float(self.policy['money'].get('platform_buffer_pct') or 0)/100.0
        effective=float(ceiling)*(1.0-buffer)
        day=self.day_key(); expires=(datetime.now(UTC)+timedelta(seconds=int(self.policy['money']['reservation_hold_seconds']))).isoformat()
        marks=','.join('?' for _ in COUNTABLE)
        with self.store.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            existing=c.execute("SELECT status,amount FROM reservations WHERE action_hash=?",(action_hash,)).fetchone()
            if existing:
                if existing['status'] in COUNTABLE: return
                raise BudgetError(f'action already has non-countable reservation status {existing["status"]}')
            row=c.execute(f"SELECT COALESCE(SUM(amount),0) total FROM reservations WHERE day_key=? AND status IN ({marks})",(day,*sorted(COUNTABLE))).fetchone()
            reserved=float(row['total'] or 0); current=max(0,float(observed_spend))+reserved
            if current+amount>effective: raise BudgetError(f'daily spend envelope exceeded: {current+amount:.2f} > {effective:.2f}')
            c.execute("INSERT INTO reservations(day_key,action_hash,amount,status,expires_at,created_at) VALUES(?,?,?,?,?,?)",(day,action_hash,float(amount),'reserved',expires,now_iso()))
    def mark(self,action_hash:str,status:str)->None:
        with self.store.connection() as c: c.execute("UPDATE reservations SET status=? WHERE action_hash=?",(status,action_hash))
    def release(self,action_hash:str,reason:str='cancelled')->None:
        with self.store.connection() as c: c.execute("UPDATE reservations SET status=? WHERE action_hash=? AND status='reserved'",(reason,action_hash))
