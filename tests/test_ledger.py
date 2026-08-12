from pathlib import Path
from ads_autopilot.state import Store
from ads_autopilot.ledger import BudgetLedger,BudgetError

def test_reservation_enforces_ceiling(tmp_path:Path):
    p={'money':{'owner_daily_spend_ceiling':100,'platform_buffer_pct':10,'reservation_hold_seconds':60}}
    l=BudgetLedger(Store(tmp_path/'x.db'),p); l.reserve('a',20,60)
    assert l.reserved_total()==20
    try: l.reserve('b',20,60)
    except BudgetError: pass
    else: raise AssertionError('should block')

def test_unknown_write_keeps_reservation_counted(tmp_path:Path):
    p={'money':{'owner_daily_spend_ceiling':100,'platform_buffer_pct':0,'reservation_hold_seconds':60}}
    l=BudgetLedger(Store(tmp_path/'x.db'),p); l.reserve('a',20,10); l.mark('a','uncertain')
    assert l.reserved_total()==20
