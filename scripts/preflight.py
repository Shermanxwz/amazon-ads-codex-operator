#!/usr/bin/env python3
from pathlib import Path
import json, shutil, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
checks=[]
def add(ok,msg): checks.append((ok,msg)); print(('[OK] ' if ok else '[FAIL] ')+msg)
add(shutil.which('codex') is not None,'Codex CLI installed')
add((ROOT/'config/operator.local.json').exists(),'operator.local.json present')
add((ROOT/'config/autonomy-policy.local.json').exists(),'autonomy-policy.local.json present')
add((ROOT/'.secrets/operator_signing_key').exists(),'controller signing key present')
if (ROOT/'config/autonomy-policy.local.json').exists():
    p=json.loads((ROOT/'config/autonomy-policy.local.json').read_text()); add(p['money'].get('owner_daily_spend_ceiling') is not None,'owner_daily_spend_ceiling configured')
if shutil.which('codex'):
    cp=subprocess.run(['codex','mcp','list'],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    add(cp.returncode==0 and 'amazon_ads' in cp.stdout,'amazon_ads MCP configured')
sys.exit(0 if all(x for x,_ in checks) else 2)
