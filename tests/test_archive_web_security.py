import json
from pathlib import Path

import pytest

from ads_autopilot.owner_store import OwnerStore
from ads_autopilot.security import SessionStore, hash_password

ROOT = Path(__file__).resolve().parents[1]


def test_password_rotation_primitive_can_revoke_every_session():
    sessions = SessionStore(ttl_seconds=3600, max_sessions=8)
    first, _ = sessions.create()
    second, _ = sessions.create()
    assert sessions.validate(first) is not None
    assert sessions.validate(second) is not None
    sessions.revoke_all()
    assert sessions.validate(first) is None
    assert sessions.validate(second) is None


def test_execution_safety_mechanics_are_not_owner_editable(tmp_path: Path):
    store = OwnerStore(tmp_path / "owner.db", b"k" * 32)
    policy = json.loads((ROOT / "config/autonomy-policy.json").read_text())
    operator = json.loads((ROOT / "config/operator.example.json").read_text())
    store.bootstrap(policy, operator, hash_password("correct horse battery staple"))
    for path in (
        "scope.require_independent_verification",
        "scope.require_prewrite_read",
        "scope.require_verified_activation",
    ):
        with pytest.raises(ValueError, match="not owner-editable"):
            store.update_policy({path: False})
    snapshot = store.snapshot()
    assert snapshot["policy"]["scope"]["require_independent_verification"] is True
    assert snapshot["policy"]["scope"]["require_prewrite_read"] is True
    assert snapshot["policy"]["scope"]["require_verified_activation"] is True
