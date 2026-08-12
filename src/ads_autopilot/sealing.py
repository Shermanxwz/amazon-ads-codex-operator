from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import secrets
from typing import Any

from .canonical import canonical_json, digest


class Sealer:
    def __init__(self, key: bytes):
        if len(key) < 32:
            raise ValueError("signing key must contain at least 32 bytes")
        self.key = key

    @classmethod
    def from_path(cls, path: str | Path):
        env = os.environ.get("ADS_OPERATOR_SIGNING_KEY")
        if env:
            return cls(env.encode())
        p = Path(path)
        if not p.exists():
            raise RuntimeError("signing key missing; run scripts/bootstrap.py")
        return cls(p.read_bytes().strip())

    @classmethod
    def from_runtime(cls, root: str | Path):
        return cls.from_path(Path(root) / ".secrets" / "operator_signing_key")

    def sign(self, value: Any) -> str:
        return hmac.new(self.key, canonical_json(value).encode(), hashlib.sha256).hexdigest()

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
