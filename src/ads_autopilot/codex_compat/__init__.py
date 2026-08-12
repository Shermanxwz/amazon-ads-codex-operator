"""Capability-gated Codex runtime selection and Evergreen upgrade support."""

from .contract import ContractError, contract_digest, load_contract
from .probe import probe_codex
from .registry import (
    CodexRuntimeError,
    active_identity,
    load_registry,
    promote_candidate,
    register_candidate,
    resolve_active_binary,
    rollback_runtime,
    runtime_status,
)

__all__ = [
    "ContractError",
    "CodexRuntimeError",
    "active_identity",
    "contract_digest",
    "load_contract",
    "load_registry",
    "probe_codex",
    "promote_candidate",
    "register_candidate",
    "resolve_active_binary",
    "rollback_runtime",
    "runtime_status",
]
