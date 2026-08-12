# Changelog

## 0.4.0 — Archive hardening / crash-safe sealed execution

- Preserved full-managed AI autonomy inside the Owner-defined scope and monetary envelope; no per-action human approval workflow was introduced.
- Upgraded Executor grants to deterministic v2 one-use capability tickets. The production `PreToolUse` hook atomically consumes a grant with an `O_EXCL` replay barrier before returning `allow`.
- Added final-boundary Owner authority checks: Autopilot mode, Emergency Stop, Policy revision and Operator revision are re-read immediately before the Amazon mutation is authorized.
- Added fresh pre-write Amazon state validation for existing-entity mutations. If live state no longer matches the sealed `before` state, the action is cancelled and the next cycle replans from reality.
- Added crash/restart reconciliation. Unconsumed grants are safely cancelled; consumed/ambiguous actions are independently re-read from Amazon and are never blindly replayed.
- Made independent Amazon state the final source of truth when an Executor transport/receipt is ambiguous.
- Removed the duplicate package-level hook implementation; tests now exercise the exact production hook script deployed by bootstrap.
- Added a Codex runtime capability contract and host preflight check for the non-interactive structured execution features on which production depends.
- Pinned the certified Amazon Ads Postman reference to an immutable upstream commit and added scheduled upstream drift detection.
- Added checksum-manifested SQLite-safe Owner/runtime backup and verified restore tooling. Restored hosts return to Observe until OAuth and live state are re-bound.
- Expanded the archive gate to verify v0.4 versions, one-use grant semantics, crash recovery presence, fresh-state guard, production hook uniqueness, Codex compatibility contract and Amazon contract pin.
- Production-certified autonomous ad-product scope remains Sponsored Products; live-account acceptance is still required per `docs/ARCHIVE_ACCEPTANCE.md` for each deployment.

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
