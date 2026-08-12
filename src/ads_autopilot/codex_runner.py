from __future__ import annotations
import json, os, subprocess
from pathlib import Path
from typing import Any

class CodexError(RuntimeError): pass

def sanitized_env()->dict[str,str]:
    env=dict(os.environ)
    for key in list(env):
        if key in {'ADS_OPERATOR_SIGNING_KEY'} or key.startswith('AMAZON_ADS_CLIENT_') or key.endswith('_REFRESH_TOKEN'):
            env.pop(key,None)
    return env

def run_codex(*,root:Path,prompt:str,schema:Path,output:Path,timeout:int=1800)->dict[str,Any]:
    cmd=['codex','exec','--sandbox','workspace-write','--ephemeral','--output-schema',str(schema),'-o',str(output),'-']
    proc=subprocess.run(cmd,input=prompt,text=True,cwd=root,env=sanitized_env(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if proc.returncode!=0: raise CodexError(f'codex exec failed ({proc.returncode}): {proc.stderr[-4000:]}')
    if not output.exists(): raise CodexError('codex did not write structured output')
    try: return json.loads(output.read_text())
    except Exception as e: raise CodexError(f'invalid structured output: {e}') from e
