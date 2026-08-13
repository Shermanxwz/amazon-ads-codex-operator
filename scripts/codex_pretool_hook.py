#!/usr/bin/env python3
"""Frozen, self-contained Codex PreToolUse policy hook.

Bootstrap copies this file into the Owner-controlled runtime tree. Production
hooks execute that frozen copy, never the mutable Git checkout.

The Executor grant is a capability ticket, not a reusable approval. An exact
Amazon MCP call is allowed only after this hook has:

1. verified the grant-only HMAC signature and expiry;
2. re-read Owner mode/revisions at the final tool boundary; and
3. atomically consumed the grant before returning ``allow``.

The model never receives Owner DB or signing-key contents. The hook receives
only a derived Executor-grant key; it does not receive the Owner master key used
for audit history and normal sealed-action signatures.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

UTC = timezone.utc


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def output(decision: str, reason: str | None = None) -> int:
    body: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
        }
    }
    if reason:
        body["hookSpecificOutput"]["permissionDecisionReason"] = reason
    print(json.dumps(body, separators=(",", ":")))
    return 0


def deny(reason: str) -> int:
    return output("deny", reason)


def allow() -> int:
    return output("allow")


def bare_mcp(name: str) -> str | None:
    prefix = "mcp__amazon_ads__"
    return name[len(prefix) :] if name.startswith(prefix) else None


def _owner_home(codex_home: Path) -> Path:
    resolved = codex_home.resolve()
    if resolved.name != "codex-home":
        raise ValueError("unexpected CODEX_HOME layout")
    return resolved.parent


def verify_grant(grant_path: Path, codex_home: Path) -> tuple[dict[str, Any], Path]:
    owner_home = _owner_home(codex_home)
    grant_root = (owner_home / "grants").resolve()
    grant_file = grant_path.resolve()
    if grant_file.parent != grant_root:
        raise ValueError("grant outside Owner grants directory")

    value = json.loads(grant_file.read_text())
    if not isinstance(value, dict):
        raise ValueError("grant must be a JSON object")
    signature = str(value.pop("signature"))
    if int(value.get("version") or 0) != 2:
        raise ValueError("unsupported grant version")

    action_hash = str(value.get("action_hash") or "")
    if not action_hash or grant_file.name != f"{action_hash}.json":
        raise ValueError("grant filename/action hash mismatch")

    key = (owner_home / "secrets/executor_grant_signing_key").read_bytes().strip()
    if len(key) < 32:
        raise ValueError("executor grant key is invalid")
    expected = hmac.new(key, canonical_json(value).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("invalid grant signature")

    expires = datetime.fromisoformat(str(value["expires_at"]).replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires.astimezone(UTC) <= datetime.now(UTC):
        raise ValueError("grant expired")
    return value, owner_home


def verify_live_owner_authority(owner_home: Path, grant: dict[str, Any]) -> None:
    """Re-check Owner authority immediately before the Amazon MCP call."""
    db = owner_home / "owner.db"
    uri = f"file:{db.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=2) as conn:
        conn.row_factory = sqlite3.Row
        control = conn.execute(
            "SELECT mode, emergency_stop FROM control_state WHERE id=1"
        ).fetchone()
        revisions = {
            str(row["kind"]): int(row["revision"])
            for row in conn.execute(
                "SELECT kind, revision FROM owner_documents WHERE kind IN ('policy','operator')"
            ).fetchall()
        }

    if not control:
        raise ValueError("Owner control state missing")
    if bool(control["emergency_stop"]):
        raise ValueError("Owner emergency stop is active")
    if str(control["mode"]).lower() != "autopilot":
        raise ValueError("Owner mode is not autopilot")
    if revisions.get("policy") != int(grant.get("policy_revision") or -1):
        raise ValueError("Owner policy revision changed")
    if revisions.get("operator") != int(grant.get("operator_revision") or -1):
        raise ValueError("Owner operator revision changed")


def consume_grant(grant_file: Path, grant: dict[str, Any], event: dict[str, Any]) -> Path:
    """Atomically claim a grant once before allowing the side effect."""
    marker = Path(str(grant_file) + ".consumed")
    record = {
        "version": 1,
        "action_hash": str(grant.get("action_hash") or ""),
        "tool_name": str(grant.get("tool_name") or ""),
        "consumed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "session_id": str(event.get("session_id") or ""),
        "turn_id": str(event.get("turn_id") or ""),
    }
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("grant already consumed") from exc

    try:
        payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)

    try:
        grant_file.unlink()
    except FileNotFoundError as exc:
        raise ValueError("grant disappeared during atomic consumption") from exc
    return marker


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return deny("hook received invalid JSON")

    mode = os.environ.get("ADS_CODEX_HOOK_MODE", "read_only")
    tool = str(event.get("tool_name") or "")

    if mode != "executor":
        if tool in {"Bash", "apply_patch", "Edit", "Write"}:
            return deny(f"{mode} role cannot use local mutation tool {tool}")
        bare = bare_mcp(tool)
        if bare is not None:
            lower = bare.lower()
            mutation = (
                "create", "update", "delete", "archive", "pause", "enable",
                "resume", "mutate", "remove", "addnegative", "setbid", "setbudget",
            )
            if any(token in lower for token in mutation):
                return deny(f"{mode} role cannot call mutation-like Amazon MCP tool {bare}")
        return allow()

    grant_raw = os.environ.get("ADS_CODEX_EXEC_GRANT")
    home_raw = os.environ.get("CODEX_HOME")
    if not grant_raw or not home_raw:
        return deny("executor has no controller grant")

    grant_file = Path(grant_raw)
    try:
        value, owner_home = verify_grant(grant_file, Path(home_raw))
    except Exception as exc:
        return deny(f"executor grant cannot be validated: {type(exc).__name__}")

    bare = bare_mcp(tool)
    if bare is None:
        return deny("executor may only call amazon_ads MCP")
    if bare != str(value.get("tool_name") or ""):
        return deny("MCP tool name differs from sealed grant")
    if canonical_json(event.get("tool_input")) != canonical_json(value.get("arguments")):
        return deny("MCP arguments differ from sealed grant")

    try:
        verify_live_owner_authority(owner_home, value)
    except Exception as exc:
        return deny(f"Owner authority changed before execution: {type(exc).__name__}")

    try:
        consume_grant(grant_file.resolve(), value, event)
    except Exception as exc:
        return deny(f"executor grant cannot be consumed: {type(exc).__name__}")
    return allow()


if __name__ == "__main__":
    raise SystemExit(main())
