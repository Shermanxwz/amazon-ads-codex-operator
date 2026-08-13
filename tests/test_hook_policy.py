from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from ads_autopilot.canonical import canonical_json
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.sealing import Sealer, bootstrap_executor_grant_key, bootstrap_key

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "scripts/codex_pretool_hook.py"


def invoke(event: dict, env: dict[str, str]):
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, **env},
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def init_owner_db(
    paths: RuntimePaths,
    *, mode: str = "autopilot",
    emergency_stop: int = 0,
    policy_revision: int = 1,
    operator_revision: int = 1,
) -> None:
    with sqlite3.connect(paths.owner_db) as conn:
        conn.executescript(
            """
            CREATE TABLE control_state(
              id INTEGER PRIMARY KEY,
              mode TEXT NOT NULL,
              emergency_stop INTEGER NOT NULL
            );
            CREATE TABLE owner_documents(
              kind TEXT PRIMARY KEY,
              revision INTEGER NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO control_state(id,mode,emergency_stop) VALUES(1,?,?)",
            (mode, emergency_stop),
        )
        conn.executemany(
            "INSERT INTO owner_documents(kind,revision) VALUES(?,?)",
            [("policy", policy_revision), ("operator", operator_revision)],
        )


def setup_grant(
    tmp_path: Path,
    *,
    tool: str = "updateCampaigns",
    args: dict | None = None,
    expired: bool = False,
    tamper: bool = False,
):
    project = tmp_path / "project"
    project.mkdir(parents=True)
    paths = RuntimePaths.resolve(project, tmp_path / "owner")
    paths.ensure_directories()
    bootstrap_key(paths.signing_key)
    bootstrap_executor_grant_key(paths.signing_key, paths.grant_signing_key)
    init_owner_db(paths)
    sealer = Sealer.from_path(paths.signing_key)
    body = {
        "version": 2,
        "action_hash": "abc",
        "tool_name": tool,
        "arguments": args or {"campaignId": "1", "budget": 10},
        "policy_revision": 1,
        "policy_hash": "policy-hash",
        "operator_revision": 1,
        "operator_hash": "operator-hash",
        "expires_at": (
            datetime.now(UTC)
            + (timedelta(seconds=-1) if expired else timedelta(minutes=5))
        )
        .isoformat()
        .replace("+00:00", "Z"),
    }
    body["signature"] = sealer.sign(body)
    if tamper:
        body["arguments"]["budget"] = 999
    grant = paths.grant_root / "abc.json"
    grant.write_text(json.dumps(body))
    grant.chmod(0o600)
    return paths, grant


def env_for(paths: RuntimePaths, grant: Path) -> dict[str, str]:
    return {
        "ADS_CODEX_HOOK_MODE": "executor",
        "ADS_CODEX_EXEC_GRANT": str(grant),
        "CODEX_HOME": str(paths.codex_home),
    }


def decision(obj: dict) -> str:
    return obj["hookSpecificOutput"]["permissionDecision"]


def exact_event() -> dict:
    return {
        "session_id": "s1",
        "turn_id": "t1",
        "tool_name": "mcp__amazon_ads__updateCampaigns",
        "tool_input": {"campaignId": "1", "budget": 10},
    }


def test_executor_consumes_exact_grant_once(tmp_path: Path):
    paths, grant = setup_grant(tmp_path)
    out = invoke(exact_event(), env_for(paths, grant))
    assert decision(out) == "allow"
    assert not grant.exists()
    assert Path(str(grant) + ".consumed").exists()
    replay = invoke(exact_event(), env_for(paths, grant))
    assert decision(replay) == "deny"


def test_executor_denies_argument_or_tool_change(tmp_path: Path):
    paths, grant = setup_grant(tmp_path)
    env = env_for(paths, grant)
    out = invoke(
        {"tool_name": "mcp__amazon_ads__updateCampaigns", "tool_input": {"campaignId": "1", "budget": 11}},
        env,
    )
    assert decision(out) == "deny"
    assert grant.exists()
    out = invoke(
        {"tool_name": "mcp__amazon_ads__deleteCampaigns", "tool_input": {"campaignId": "1", "budget": 10}},
        env,
    )
    assert decision(out) == "deny"
    assert grant.exists()


def test_executor_denies_expired_or_tampered_grant(tmp_path: Path):
    for expired, tamper in [(True, False), (False, True)]:
        paths, grant = setup_grant(tmp_path / ("expired" if expired else "tampered"), expired=expired, tamper=tamper)
        out = invoke(exact_event(), env_for(paths, grant))
        assert decision(out) == "deny"
        assert grant.exists()


def test_hook_uses_grant_only_key_not_owner_master_key(tmp_path: Path):
    paths, grant = setup_grant(tmp_path)
    value = json.loads(grant.read_text())
    unsigned = dict(value)
    unsigned.pop("signature")
    master = paths.signing_key.read_bytes().strip()
    value["signature"] = hmac.new(master, canonical_json(unsigned).encode(), hashlib.sha256).hexdigest()
    grant.write_text(json.dumps(value))
    out = invoke(exact_event(), env_for(paths, grant))
    assert decision(out) == "deny"
    assert grant.exists()
    assert paths.grant_signing_key.read_bytes().strip() != master


def test_executor_rechecks_emergency_stop_at_tool_boundary(tmp_path: Path):
    paths, grant = setup_grant(tmp_path)
    with sqlite3.connect(paths.owner_db) as conn:
        conn.execute("UPDATE control_state SET emergency_stop=1 WHERE id=1")
    out = invoke(exact_event(), env_for(paths, grant))
    assert decision(out) == "deny"
    assert grant.exists()


def test_executor_rechecks_owner_revision_at_tool_boundary(tmp_path: Path):
    paths, grant = setup_grant(tmp_path)
    with sqlite3.connect(paths.owner_db) as conn:
        conn.execute("UPDATE owner_documents SET revision=2 WHERE kind='policy'")
    out = invoke(exact_event(), env_for(paths, grant))
    assert decision(out) == "deny"
    assert grant.exists()


def test_executor_requires_autopilot_at_tool_boundary(tmp_path: Path):
    paths, grant = setup_grant(tmp_path)
    with sqlite3.connect(paths.owner_db) as conn:
        conn.execute("UPDATE control_state SET mode='observe' WHERE id=1")
    out = invoke(exact_event(), env_for(paths, grant))
    assert decision(out) == "deny"
    assert grant.exists()


def test_read_only_role_denies_common_mutation_mcp():
    out = invoke(
        {"tool_name": "mcp__amazon_ads__createCampaigns", "tool_input": {}},
        {"ADS_CODEX_HOOK_MODE": "read_only"},
    )
    assert decision(out) == "deny"
    out = invoke(
        {"tool_name": "mcp__amazon_ads__getCampaigns", "tool_input": {}},
        {"ADS_CODEX_HOOK_MODE": "read_only"},
    )
    assert decision(out) == "allow"
