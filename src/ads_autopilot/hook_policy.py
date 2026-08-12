from __future__ import annotations
from datetime import datetime,timezone
import json,os,sys
from pathlib import Path
from .canonical import canonical_json
from .sealing import Sealer
UTC=timezone.utc

def deny(reason:str)->int:
    print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":reason}})); return 0
def allow()->int:
    print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}})); return 0
def _bare_mcp_name(canonical:str)->str|None:
    prefix="mcp__amazon_ads__"; return canonical[len(prefix):] if canonical.startswith(prefix) else None

def main()->int:
    try: event=json.load(sys.stdin)
    except Exception: return deny("hook received invalid JSON")
    mode=os.environ.get("ADS_CODEX_HOOK_MODE","read_only"); tool_name=str(event.get("tool_name") or "")
    if mode!="executor":
        if tool_name in {"apply_patch","Edit","Write"} or tool_name=="Bash": return deny(f"{mode} role cannot use local mutation tool {tool_name}")
        bare=_bare_mcp_name(tool_name)
        if bare is not None:
            lower=bare.lower(); mutation_verbs=("create","update","delete","archive","pause","enable","resume","mutate","remove","addnegative","setbid","setbudget")
            if any(v in lower for v in mutation_verbs): return deny(f"{mode} role cannot call mutation-like Amazon MCP tool {bare}")
        return allow()
    grant_path=os.environ.get("ADS_CODEX_EXEC_GRANT"); codex_home=os.environ.get("CODEX_HOME")
    if not grant_path or not codex_home: return deny("executor has no controller grant")
    try:
        grant_file=Path(grant_path).resolve(); owner_home=Path(codex_home).resolve().parent
        if owner_home not in grant_file.parents: return deny("executor grant is outside trusted owner home")
        grant=json.loads(grant_file.read_text()); sig=str(grant.pop("signature")); sealer=Sealer.from_path(owner_home/"secrets"/"operator_signing_key")
        if not sealer.verify(grant,sig): return deny("executor grant signature invalid")
        expires=datetime.fromisoformat(str(grant["expires_at"]).replace("Z","+00:00"));
        if expires.tzinfo is None: expires=expires.replace(tzinfo=UTC)
        if expires.astimezone(UTC)<=datetime.now(UTC): return deny("executor grant expired")
    except Exception as exc: return deny(f"executor grant cannot be validated: {type(exc).__name__}")
    bare=_bare_mcp_name(tool_name)
    if bare is None: return deny(f"executor may only call the granted amazon_ads MCP tool, not {tool_name}")
    if bare!=str(grant.get("tool_name") or ""): return deny("MCP tool name differs from sealed grant")
    if canonical_json(event.get("tool_input"))!=canonical_json(grant.get("arguments")): return deny("MCP arguments differ from sealed grant")
    return allow()
if __name__=="__main__": raise SystemExit(main())
