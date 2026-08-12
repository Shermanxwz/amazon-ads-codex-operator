# Changelog

## 0.3.0 — Owner Control / sealed execution

- Added Owner Web as the highest operational authority layer with authenticated mode, scope, monetary limits, emergency stop, immutable revisions, and rollback-to-Observe.
- Moved Owner policy, runtime DB, signing key, production Codex home, grants, workspaces, and run evidence outside the Git checkout.
- Added HMAC-signed Owner audit chain and immutable Policy/Operator revision history.
- Converted live execution to one mutation at a time with authority re-check before every release and immediate independent verification.
- Added short-lived one-action Executor grants, exact MCP `enabled_tools`, and a frozen `PreToolUse` hook that rejects any tool or argument mismatch.
- Added deterministic `action_type ↔ tool_name ↔ entity ↔ arguments ↔ after-state` contract validation and Owner profile/account/ASIN scope enforcement.
- Added daily spend reservation, ambiguous-write retention, cross-cycle cooldowns, campaign creation/budget envelopes, recovery breaker, and two-phase PAUSED campaign activation.
- Added forensic Codex JSONL event-stream retention.
- Added hardened systemd units, local `ownerctl` emergency controls, archive checks, and staged production-acceptance documentation.
- Production-certified autonomous ad-product scope remains Sponsored Products only in this release.
