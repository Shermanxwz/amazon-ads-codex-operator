from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import secrets
from typing import Any

from .canonical import canonical_json, digest

_GRANT_KDF_CONTEXT = b"amazon-ads-codex/executor-grant/v2"


def _is_executor_grant(value: Any) -> bool:
    if not isinstance(value, dict) or int(value.get("version") or 0) != 2:
        return False
    required = {"action_hash", "tool_name", "arguments", "policy_revision", "operator_revision", "expires_at"}
    return required.issubset(value)


def executor_grant_signing_key(master_key: bytes) -> bytes:
    """Derive the hook-visible Executor grant key from the Owner master key."""
    if len(master_key) < 32:
        raise ValueError("master signing key must contain at least 32 bytes")
    return hmac.new(master_key, _GRANT_KDF_CONTEXT, hashlib.sha256).hexdigest().encode()


class Sealer:
    def __init__(self, key: bytes):
        if len(key) < 32:
            raise ValueError("signing key must contain at least 32 bytes")
        self.key = key

    @classmethod
    def from_path(cls, path: str | Path):
        # Production signing identity is the Owner-owned file, full stop. An
        # ambient environment variable must never be able to make runtime
        # signatures diverge from the key that backup/restore preserves.
        p = Path(path)
        if not p.exists():
            raise RuntimeError("signing key missing; run scripts/bootstrap.py")
        return cls(p.read_bytes().strip())

    @classmethod
    def from_runtime(cls, root: str | Path):
        return cls.from_path(Path(root) / ".secrets" / "operator_signing_key")

    def sign(self, value: Any) -> str:
        # v2 capability grants occupy a separate cryptographic domain. The
        # dispatch is deterministic and behavior-tested; all other values use
        # the Owner/action master domain.
        key = executor_grant_signing_key(self.key) if _is_executor_grant(value) else self.key
        return hmac.new(key, canonical_json(value).encode(), hashlib.sha256).hexdigest()

    def verify(self, value: Any, signature: str) -> bool:
        return hmac.compare_digest(self.sign(value), signature)

    def seal_action(self, base: dict[str, Any], *, policy_hash: str, plan_hash: str, operator_hash: str, policy_revision: int | None = None, operator_revision: int | None = None) -> dict[str, Any]:
        body = dict(base)
        body["policy_hash"] = policy_hash
        body["plan_hash"] = plan_hash
        body["operator_hash"] = operator_hash
        if policy_revision is not None:
            body["policy_revision"] = int(policy_revision)
        if operator_revision is not None:
            body["operator_revision"] = int(operator_revision)
        body["action_hash"] = digest(body)
        body["signature"] = self.sign(body)
        return body


def bootstrap_key(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not p.exists():
        p.write_text(secrets.token_urlsafe(64))
    os.chmod(p, 0o600)
    try:
        p.parent.chmod(0o700)
    except OSError:
        pass
    return p


def bootstrap_executor_grant_key(master_path: str | Path, derived_path: str | Path) -> Path:
    master = Sealer.from_path(master_path).key
    expected = executor_grant_signing_key(master)
    destination = Path(derived_path)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists():
        actual = destination.read_bytes().strip()
        if not hmac.compare_digest(actual, expected):
            raise RuntimeError("executor grant signing key does not match Owner master key")
    else:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, expected)
            os.fsync(fd)
        finally:
            os.close(fd)
    os.chmod(destination, 0o600)
    try:
        destination.parent.chmod(0o700)
    except OSError:
        pass
    return destination
