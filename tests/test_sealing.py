import hashlib
import hmac

from ads_autopilot.canonical import canonical_json
from ads_autopilot.sealing import Sealer, executor_grant_signing_key


def test_seal_exact_payload_binding():
    s = Sealer(b"s" * 32)
    row = s.seal_action(
        {"action_id": "a", "arguments": {"bid": 1.2}},
        policy_hash="p",
        plan_hash="x",
        operator_hash="o",
    )
    sig = row.pop("signature")
    assert s.verify(row, sig)
    row["arguments"]["bid"] = 1.3
    assert not s.verify(row, sig)


def test_executor_grant_signature_is_domain_separated_from_action_key():
    master = b"m" * 32
    s = Sealer(master)
    grant = {
        "version": 2,
        "action_hash": "h",
        "tool_name": "updateKeywords",
        "arguments": {"bid": 1.1},
        "policy_revision": 1,
        "operator_revision": 1,
        "expires_at": "2099-01-01T00:00:00Z",
    }
    signature = s.sign(grant)
    master_signature = hmac.new(master, canonical_json(grant).encode(), hashlib.sha256).hexdigest()
    derived_signature = hmac.new(executor_grant_signing_key(master), canonical_json(grant).encode(), hashlib.sha256).hexdigest()
    assert signature == derived_signature
    assert signature != master_signature
