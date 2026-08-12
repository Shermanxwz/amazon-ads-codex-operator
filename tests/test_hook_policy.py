from __future__ import annotations
from datetime import datetime, timedelta, timezone
import io, json, os
from pathlib import Path
from unittest.mock import patch
from ads_autopilot.hook_policy import main
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.sealing import Sealer, bootstrap_key

UTC=timezone.utc

def invoke(event, env):
    out=io.StringIO()
    with patch.dict(os.environ,env,clear=False), patch('sys.stdin',io.StringIO(json.dumps(event))), patch('sys.stdout',out): rc=main()
    return rc,json.loads(out.getvalue())

def setup_grant(tmp_path:Path, *, tool='updateCampaigns', args=None, expired=False, tamper=False):
    project=tmp_path/'project'; project.mkdir(parents=True); paths=RuntimePaths.resolve(project,tmp_path/'owner'); paths.ensure_directories(); bootstrap_key(paths.signing_key)
    sealer=Sealer.from_path(paths.signing_key)
    body={'version':1,'action_hash':'abc','tool_name':tool,'arguments':args or {'campaignId':'1','budget':10},'expires_at':(datetime.now(UTC)+(timedelta(seconds=-1) if expired else timedelta(minutes=5))).isoformat().replace('+00:00','Z')}
    sig=sealer.sign(body); body['signature']=sig
    if tamper: body['arguments']['budget']=999
    grant=paths.grant_root/'g.json'; grant.write_text(json.dumps(body)); grant.chmod(0o600)
    return paths,grant

def decision(obj): return obj['hookSpecificOutput']['permissionDecision']

def test_executor_allows_exact_granted_mcp_call(tmp_path):
    paths,grant=setup_grant(tmp_path)
    _,out=invoke({'tool_name':'mcp__amazon_ads__updateCampaigns','tool_input':{'campaignId':'1','budget':10}}, {'ADS_CODEX_HOOK_MODE':'executor','ADS_CODEX_EXEC_GRANT':str(grant),'CODEX_HOME':str(paths.codex_home)})
    assert decision(out)=='allow'

def test_executor_denies_argument_or_tool_change(tmp_path):
    paths,grant=setup_grant(tmp_path); env={'ADS_CODEX_HOOK_MODE':'executor','ADS_CODEX_EXEC_GRANT':str(grant),'CODEX_HOME':str(paths.codex_home)}
    _,out=invoke({'tool_name':'mcp__amazon_ads__updateCampaigns','tool_input':{'campaignId':'1','budget':11}},env); assert decision(out)=='deny'
    _,out=invoke({'tool_name':'mcp__amazon_ads__deleteCampaigns','tool_input':{'campaignId':'1','budget':10}},env); assert decision(out)=='deny'

def test_executor_denies_expired_or_tampered_grant(tmp_path):
    for expired,tamper in [(True,False),(False,True)]:
        paths,grant=setup_grant(tmp_path/('e' if expired else 't'),expired=expired,tamper=tamper); env={'ADS_CODEX_HOOK_MODE':'executor','ADS_CODEX_EXEC_GRANT':str(grant),'CODEX_HOME':str(paths.codex_home)}
        _,out=invoke({'tool_name':'mcp__amazon_ads__updateCampaigns','tool_input':{'campaignId':'1','budget':10}},env); assert decision(out)=='deny'

def test_read_only_role_denies_common_mutation_mcp():
    _,out=invoke({'tool_name':'mcp__amazon_ads__createCampaigns','tool_input':{}},{'ADS_CODEX_HOOK_MODE':'read_only'}); assert decision(out)=='deny'
    _,out=invoke({'tool_name':'mcp__amazon_ads__getCampaigns','tool_input':{}},{'ADS_CODEX_HOOK_MODE':'read_only'}); assert decision(out)=='allow'
