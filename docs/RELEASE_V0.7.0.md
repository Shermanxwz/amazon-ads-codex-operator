# v0.7.0 — Deterministic Owner-Boundary Hardening

v0.7.0 closes the remaining source-level gaps between the autonomous Planner and the Owner-controlled execution boundary. It is a hardening release: AI retains broad Sponsored Products business discretion, while mutation identity, monetary exposure and final verification are no longer trusted merely because the model declared them.

## Sealed invariants

- Existing-entity writes require non-empty fresh `before` state and a non-empty sealed `after` state.
- MCP tool family, mutation semantics, target entity IDs and changed bid/budget/placement/state values are cross-checked against exact MCP arguments.
- Sponsored Products scope is checked both at the action declaration and whenever ad-product arguments are present.
- Plan-level spend reservation is derived deterministically. A Planner-provided `spend_delta=0` cannot remove Owner monetary protection.
- Unknown bid/placement/state/targeting expansion is conservatively bounded by fresh active-budget headroom; known budget increases use their exact positive delta.
- Hourly bid changes honor `bidding.hourly_max_bid_change_pct`.
- The spend ledger uses the Owner account timezone and reclaims only expired grants that never crossed execution; ambiguous/possibly executed writes remain charged for the local day.
- Post-write verifier output is deterministically compared with the sealed `after` state. Model text cannot promote a mismatch to VERIFIED.
- `recovery.verification_grace_seconds` is now an actual retry window for normal post-write verification.
- Overlapping hourly/daily/weekly/direct processes serialize through the Linux lock instead of dropping a scheduled cycle on collision.
- Owner scheduling booleans are honored at the runtime entrypoint and systemd installer.
- Production user-systemd installation requires verified linger so services survive logout and start after boot.
- Codex Evergreen uses the current `approval_policy="never"` config override and no longer false-fails by assuming a global approval flag must appear in `codex exec --help`.
- Dedicated production `CODEX_HOME` setup installs and verifies the repo-native `amazon-ads-operator` plugin from the local marketplace.

## Claim boundary

The source/archive can be sealed only after the complete credential-free archive and virtual-production gates pass on the exact release SHA. A particular Ubuntu host and Amazon Ads advertiser/profile remain separately live-acceptance pending until OAuth, current MCP schemas, profile/account/currency binding, fresh-read behavior, controlled micro-live mutation, restart/ambiguity drills and systemd reboot behavior are proven on that deployment.
