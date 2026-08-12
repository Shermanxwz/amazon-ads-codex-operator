from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from typing import Any

from .paths import RuntimePaths

class CodexError(RuntimeError): pass
_ENV_ALLOW={"PATH","LANG","LANGUAGE","LC_ALL","LC_CTYPE","TERM","COLORTERM","SSL_CERT_FILE","SSL_CERT_DIR","HTTP_PROXY","HTTPS_PROXY","NO_PROXY","http_proxy","https_proxy","no_proxy"}

def sanitized_env(paths:RuntimePaths,workspace:Path,*,role:str="read_only",grant_path:Path|None=None)->dict[str,str]:
    env={k:v for k,v in os.environ.items() if k in _ENV_ALLOW or k.startswith("LC_")}
    fake_home=workspace/"home"; fake_home.mkdir(parents=True,exist_ok=True,mode=0o700)
    env["HOME"]=str(fake_home); env["CODEX_HOME"]=str(paths.codex_home); env["PYTHONUNBUFFERED"]="1"
    env["ADS_CODEX_HOOK_MODE"]="executor" if role=="executor" else "read_only"
    if grant_path is not None: env["ADS_CODEX_EXEC_GRANT"]=str(grant_path)
    return env

def prepare_workspace(paths:RuntimePaths,role:str)->Path:
    paths.ensure_directories(); workspace=paths.workspace_root/f"{role}-{uuid.uuid4().hex}"; workspace.mkdir(parents=True,mode=0o700)
    constitution=paths.project_root/"AGENTS.md"
    if constitution.exists(): shutil.copy2(constitution,workspace/"AGENTS.md")
    (workspace/"WORKSPACE_NOTICE.txt").write_text("Disposable Codex workspace. Owner policy, signing keys, OAuth config, and runtime DB live outside this directory.\n")
    return workspace

def build_command(*,paths:RuntimePaths,workspace:Path,schema:Path,output:Path,model:str|None=None,allowed_mcp_tools:list[str]|None=None)->list[str]:
    cmd=["codex","exec","--cd",str(workspace),"--skip-git-repo-check","--sandbox","read-only","--ask-for-approval","never","--strict-config","--dangerously-bypass-hook-trust","--ephemeral","--json","--output-schema",str(schema),"--output-last-message",str(output)]
    approval="approve" if workspace.name.startswith("executor-") else "writes"
    cmd.extend(["--config",f'mcp_servers.amazon_ads.default_tools_approval_mode="{approval}"'])
    if allowed_mcp_tools is not None:
        encoded=json.dumps([str(x) for x in allowed_mcp_tools],separators=(",",":")); cmd.extend(["--config",f"mcp_servers.amazon_ads.enabled_tools={encoded}"])
    if model: cmd.extend(["--model",model])
    cmd.append("-"); return cmd

def run_codex(*,paths:RuntimePaths,role:str,prompt:str,schema:Path,output:Path,timeout:int=1800,model:str|None=None,keep_workspace:bool=False,grant_path:Path|None=None,allowed_mcp_tools:list[str]|None=None)->dict[str,Any]:
    workspace=prepare_workspace(paths,role); output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    cmd=build_command(paths=paths,workspace=workspace,schema=schema,output=output,model=model,allowed_mcp_tools=allowed_mcp_tools)
    try:
        proc=subprocess.run(cmd,input=prompt,text=True,cwd=workspace,env=sanitized_env(paths,workspace,role=role,grant_path=grant_path),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
        event_log=output.with_name(output.name+".events.jsonl"); event_log.write_text(proc.stdout or ""); os.chmod(event_log,0o600)
        if proc.stderr:
            stderr_log=output.with_name(output.name+".stderr.log"); stderr_log.write_text(proc.stderr); os.chmod(stderr_log,0o600)
        if proc.returncode!=0: raise CodexError(f"codex exec failed ({proc.returncode}): {proc.stderr[-4000:]}")
        if not output.exists(): raise CodexError("codex did not write structured output")
        try: return json.loads(output.read_text())
        except Exception as exc: raise CodexError(f"invalid structured output: {exc}") from exc
    finally:
        if not keep_workspace: shutil.rmtree(workspace,ignore_errors=True)
