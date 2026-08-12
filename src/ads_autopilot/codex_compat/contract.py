from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ContractError(RuntimeError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load_contract(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text())
    except Exception as exc:
        raise ContractError(f"cannot parse Codex compatibility contract {source}: {exc}") from exc
    validate_contract(value)
    return value


def validate_contract(value: dict[str, Any]) -> None:
    if not isinstance(value, dict):
        raise ContractError("Codex compatibility contract must be an object")
    if int(value.get("version") or 0) < 2:
        raise ContractError("Codex compatibility contract version must be >= 2")
    if value.get("strategy") != "capability-gated-evergreen":
        raise ContractError("Codex compatibility strategy must be capability-gated-evergreen")
    commands = value.get("required_commands")
    if not isinstance(commands, list) or not commands:
        raise ContractError("required_commands must be a non-empty list")
    names: set[str] = set()
    for item in commands:
        if not isinstance(item, dict):
            raise ContractError("each required command must be an object")
        name = str(item.get("name") or "").strip()
        argv = item.get("argv")
        if not name or name in names:
            raise ContractError(f"invalid/duplicate required command name: {name!r}")
        names.add(name)
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            raise ContractError(f"required command {name} must have argv")
        tokens = item.get("required_tokens") or []
        if not isinstance(tokens, list) or not all(isinstance(x, str) and x for x in tokens):
            raise ContractError(f"required command {name} has invalid required_tokens")
    required = {"exec", "mcp", "plugin", "features", "sandbox"}
    missing = sorted(required - names)
    if missing:
        raise ContractError(f"Codex compatibility contract missing required stable commands: {missing}")


def contract_digest(path: str | Path) -> str:
    value = load_contract(path)
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()
