#!/usr/bin/env python3
"""Credential-free Codex/Amazon boundary used only by virtual acceptance."""
from __future__ import annotations
from datetime import datetime, timezone
import json, os
from pathlib import Path
import subprocess, sys, time

VERSION = "__VIRTUAL_CODEX_VERSION__"
EXEC_HELP = "--strict-config --sandbox --ask-for-approval --dangerously-bypass-hook-trust --ephemeral --json --output-schema --output-last-message --config --model"

def arg(name): return sys.argv[sys.argv.index(name)+1]
def home(): return Path(os.environ["CODEX_HOME"])
def load(name, default=None):
    p=home()/name
    return json.loads(p.read_text()) if p.exists() else default

def save(name, value): (home()/name).write_text(json.dumps(value, sort_keys=True))
def amazon(): return load("virtual-amazon-state.json", {"bid":1.0})
def observed(): return {"keywordId":"k1", "bid":amazon()["bid"]}
def control(): return load("virtual-control.json", {"mode":"normal"})
def payload():
    text=sys.stdin.read(); marker="INPUT_JSON:\n"
    if marker not in text: raise RuntimeError("missing INPUT_JSON")
    return json.loads(text.split(marker,1)[1])
def output(value):
    p=Path(arg("--output-last-message")); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, sort_keys=True)); print(json.dumps({"type":"virtual-codex","version":VERSION}))
def differences(expected):
    got=observed(); diffs=[]
    for k,v in expected.items():
        if k not in got: diffs.append(f"{k} missing")
        elif isinstance(v,(int,float)) and isinstance(got[k],(int,float)):
            if abs(float(got[k])-float(v))>=1e-9: diffs.append(f"{k}: expected={v} observed={got[k]}")
        elif str(got[k]) != str(v): diffs.append(f"{k}: expected={v} observed={got[k]}")
    return got,diffs

def call_hook(action):
    hook=home().parent/"trusted-hooks"/"codex_pretool_hook.py"
    event={"session_id":"virtual","turn_id":"virtual","tool_name":"mcp__amazon_ads__"+action["tool_name"],"tool_input":action["arguments"]}
    p=subprocess.run([sys.executable,str(hook)],input=json.dumps(event),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=os.environ.copy(),check=False)
    if p.returncode: raise RuntimeError(p.stderr[-500:])
    return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]

def help_mode(cmd):
    if cmd=="exec": print(EXEC_HELP)
    elif cmd=="mcp": print("list login")
    elif cmd=="plugin" and len(sys.argv)>2 and sys.argv[2]=="marketplace": print("add list upgrade remove")
    elif cmd=="plugin": print("list marketplace")
    elif cmd=="features": print("list")
    else: print(cmd or "help")

def main():
    if len(sys.argv)>1 and sys.argv[1]=="--version": print("codex-cli "+VERSION); return 0
    cmd=sys.argv[1] if len(sys.argv)>1 else ""
    if "--help" in sys.argv: help_mode(cmd); return 0
    if cmd=="mcp" and len(sys.argv)>2 and sys.argv[2]=="list": print("amazon_ads enabled oauth"); return 0
    if cmd in {"plugin","features","sandbox","doctor","update","mcp"}: print(cmd); return 0
    if cmd!="exec": return 2
    workspace=Path(arg("--cd")); data=payload(); role=workspace.name.split("-",1)[0]
    now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    if role=="planner":
        if control().get("planner_sleep"): time.sleep(float(control()["planner_sleep"]))
        before=float(amazon()["bid"]); after=round(before+0.10,2)
        output({"context":{"today_spend":1.0,"today_spend_observed_at":now,"today_spend_evidence_ref":"virtual:spend","active_campaign_budget_total":10.0,"observed_asins":["B000VIRTUAL"]},"summary":"virtual acceptance bid update","learning_snapshot":{"observed_at":now,"entities":[],"economics":[],"portfolio_candidates":[],"experiments":[]},"actions":[{"action_id":"virtual-bid","action_type":"update_bid","tool_name":"updateKeywords","ad_product":"SPONSORED_PRODUCTS","entity_type":"keyword","entity_id":"k1","arguments":{"field":"bid","bid":after},"before":{"bid":before},"after":{"bid":after},"spend_delta":0.0,"confidence":0.95,"evidence_refs":["virtual:keyword:k1"],"dependencies":[],"reversible":True,"rollback":{"bid":before},"prewrite_observed_at":now,"rationale":"sealed full-stack acceptance"}]}); return 0
    if role=="optimization_observer":
        output({"summary":"virtual read-only optimization observation","learning_snapshot":{"observed_at":now,"entities":[],"economics":[],"portfolio_candidates":[],"experiments":[]}}); return 0
    if role in {"state_verifier","verifier"}:
        if role=="state_verifier": expected=data.get("expected_state") or {}; action_hash=data["action_hash"]
        else:
            a=data["sealed_actions"][0]; expected=a.get("after") or {}; action_hash=a["action_hash"]
        got,diffs=differences(expected)
        output({"cycle_id":data["cycle_id"],"results":[{"action_hash":action_hash,"status":"verified" if not diffs else "mismatch","observed":got,"differences":diffs}]}); return 0
    if role=="executor":
        action=data["actions"][0]; mode=str(control().get("mode") or "normal")
        if mode=="pause_before_hook":
            (home()/"virtual-executor-ready").write_text("ready"); deadline=time.time()+20
            while not (home()/"virtual-continue").exists() and time.time()<deadline: time.sleep(.05)
            if not (home()/"virtual-continue").exists(): return 74
        if call_hook(action)!="allow": print("hook denied virtual mutation",file=sys.stderr); return 73
        if mode=="crash_after_consume_before_write": return 71
        s=amazon(); s["bid"]=action["arguments"]["bid"]; save("virtual-amazon-state.json",s)
        if mode=="crash_after_write": return 72
        output({"cycle_id":data["cycle_id"],"results":[{"action_hash":action["action_hash"],"status":"success","tool_name":action["tool_name"],"result":observed(),"error":None}]}); return 0
    return 2

if __name__=="__main__": raise SystemExit(main())
