#!/usr/bin/env python3
"""Frozen, self-contained Codex PreToolUse policy hook.

Bootstrap copies this file into the Owner-controlled runtime tree. Production
hooks execute that copy, never the mutable Git checkout.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, hmac, json, os
from pathlib import Path
import sys
from typing import Any
UTC=timezone.utc

def canonical_json(value:Any)->str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)

def output(decision:str,reason:str|None=None)->int:
    body={"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":decision}}
    if reason: body["hookSpecificOutput"]["permissionDecisionReason"]=reason
    print(json.dumps(body,separators=(",",":"))); return 0

def deny(reason:str)->int: return output("deny",reason)
def allow()->int: return output("allow")

def bare_mcp(name:str)->str|None:
    prefix="mcp__amazon_ads__"
    return name[len(prefix):] if name.startswith(prefix) else None

def verify_grant(grant_path:Path,codex_home:Path)->dict[str,Any]:
    owner_home=codex_home.resolve().parent
    grant_file=grant_path.resolve()
    if owner_home not in grant_file.parents: raise ValueError("grant outside Owner home")
    value=json.loads(grant_file.read_text())
    signature=str(value.pop("signature"))
    key=(owner_home/"secrets/operator_signing_key").read_bytes().strip()
    expected=hmac.new(key,canonical_json(value).encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature): raise ValueError("invalid grant signature")
    expires=datetime.fromisoformat(str(value["expires_at"]).replace("Z","+00:00"))
    if expires.tzinfo is None: expires=expires.replace(tzinfo=UTC)
    if expires.astimezone(UTC)<=datetime.now(UTC): raise ValueError("grant expired")
    return value

def main()->int:
    try: event=json.load(sys.stdin)
    except Exception: return deny("hook received invalid JSON")
    mode=os.environ.get("ADS_CODEX_HOOK_MODE","read_only")
    tool=str(event.get("tool_name") or "")
    if mode!="executor":
        if tool in {"Bash","apply_patch","Edit","Write"}: return deny(f"{mode} role cannot use local mutation tool {tool}")
        bare=bare_mcp(tool)
        if bare is not None:
            lower=bare.lower()
            mutation=("create","update","delete","archive","pause","enable","resume","mutate","remove","addnegative","setbid","setbudget")
            if any(x in lower for x in mutation): return deny(f"{mode} role cannot call mutation-like Amazon MCP tool {bare}")
        return allow()
    grant=os.environ.get("ADS_CODEX_EXEC_GRANT"); home=os.environ.get("CODEX_HOME")
    if not grant or not home: return deny("executor has no controller grant")
    try: value=verify_grant(Path(grant),Path(home))
    except Exception as exc: return deny(f"executor grant cannot be validated: {type(exc).__name__}")
    bare=bare_mcp(tool)
    if bare is None: return deny("executor may only call amazon_ads MCP")
    if bare!=str(value.get("tool_name") or ""): return deny("MCP tool name differs from sealed grant")
    if canonical_json(event.get("tool_input"))!=canonical_json(value.get("arguments")): return deny("MCP arguments differ from sealed grant")
    return allow()
if __name__=="__main__": raise SystemExit(main())
