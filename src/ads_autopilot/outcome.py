from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Any

FAIL={'error','failed','failure','cancelled','canceled','rejected','invalid','timeout'}
SUCCESS={'success','succeeded','completed','complete','ok','accepted','done','verified'}
PENDING={'pending','in_progress','in-progress','processing','queued','submitted'}
@dataclass(frozen=True)
class Outcome:
    status:str
    summary:str

def _payload(value:Any)->tuple[Any,bool]:
    if isinstance(value,(dict,list)): return value,True
    if isinstance(value,str):
        try: return json.loads(value),True
        except Exception: return value,False
    return value,False

def _raw(value:Any)->Outcome:
    payload,structured=_payload(value)
    if not structured: return Outcome('unknown','raw tool result is unstructured')
    if isinstance(payload,list):
        statuses=[_raw(x).status if isinstance(x,dict) else 'unknown' for x in payload]
        if 'failure' in statuses and any(x=='success' for x in statuses): return Outcome('partial','raw list contains success and failure')
        if 'failure' in statuses: return Outcome('failure','raw list contains failure')
        if 'pending' in statuses: return Outcome('pending','raw list contains pending item')
        if statuses and all(x=='success' for x in statuses): return Outcome('success','raw list explicitly successful')
        return Outcome('unknown','raw list is not fully classified')
    if not isinstance(payload,dict): return Outcome('unknown','raw result is not an object')
    s=str(payload.get('status') or payload.get('state') or '').lower().strip()
    if s in FAIL: return Outcome('failure',f'raw result status {s}')
    if s in PENDING: return Outcome('pending',f'raw result status {s}')
    if s in SUCCESS and not payload.get('error') and not payload.get('errors'): return Outcome('success',f'raw result status {s}')
    success=payload.get('success'); error=payload.get('error'); errors=payload.get('errors')
    successes=payload.get('successes')
    if isinstance(success,list): successes=success
    if isinstance(error,list): errors=error
    ec=len(errors) if isinstance(errors,(list,dict)) else (1 if error else 0)
    sc=len(successes) if isinstance(successes,(list,dict)) else (1 if success is True else 0)
    if ec and sc: return Outcome('partial',f'raw bulk result has {sc} success and {ec} error')
    if ec or success is False: return Outcome('failure','raw result contains explicit failure')
    if sc or success is True: return Outcome('success','raw result contains explicit success')
    # IDs can prove a resource exists/was returned, but not that a mutation was accepted/applied.
    return Outcome('unknown','raw result has no explicit write success/failure signal')

def parse_outcome(receipt_item:Any)->Outcome:
    if not isinstance(receipt_item,dict): return Outcome('unknown','receipt is not a structured object')
    declared=str(receipt_item.get('status') or '').lower().strip()
    if declared in FAIL: return Outcome('failure',f'executor declared {declared}')
    if declared=='partial': return Outcome('partial','executor declared partial')
    if declared in PENDING: return Outcome('pending',f'executor declared {declared}')
    raw=_raw(receipt_item.get('result'))
    if raw.status in {'failure','partial','pending'}: return raw
    if declared in SUCCESS:
        if raw.status=='success': return Outcome('success','executor and raw MCP result explicitly indicate success')
        return Outcome('unknown','executor claimed success but raw MCP result does not explicitly prove write success')
    if raw.status=='success': return raw
    return Outcome('unknown','no explicit write outcome')
