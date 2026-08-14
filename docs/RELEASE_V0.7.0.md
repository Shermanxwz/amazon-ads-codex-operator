# v0.7.0 — Deterministic Owner-Boundary Hardening

v0.7.0 closes the remaining source-level gaps between the autonomous Planner and the Owner-controlled execution boundary. It is a hardening release: AI retains broad Sponsored Products business discretion, while mutation identity, monetary exposure and final verification are no longer trusted merely because one model call declared them.

## Sealed invariants

- Existing-entity writes require non-empty fresh `before` state and a non-empty sealed `after` state.
- MCP tool family, mutation semantics, target entity IDs and changed bid/budget/placement/state values are cross-checked against exact MCP arguments.
- Sponsored Products scope is checked both at the action declaration and whenever ad-product arguments are present.
- Planner-reported `today_spend`, `active_campaign_budget_total` and `observed_asins` are independently re-read from Amazon by a separate read-only state-verifier pass and must match deterministically before a normal autonomous plan with mutations can proceed.
- Plan-level spend reservation is derived deterministically. A Planner-provided `spend_delta=0` cannot remove Owner monetary protection.
- Sponsored Ads exposure uses the worldwide conservative high-traffic-day bound of **2× average daily budgets** (100% overdelivery), rather than assuming the campaign daily-budget number is a rigid same-day cap.
- Unknown bid/placement/state/targeting expansion is conservatively bounded by worst-case active-budget headroom; known budget increases reserve twice their exact positive delta.
- Required `PAUSED` state on campaign creation is creation semantics and does not incorrectly consume the separate standing state-change authority.
- Hourly bid changes honor `bidding.hourly_max_bid_change_pct`.
- The spend ledger uses the Owner account timezone and reclaims only expired grants that never crossed execution; ambiguous/possibly executed writes remain charged for the local day.
- Post-write verifier output is deterministically compared with the sealed `after` state. Model text cannot promote a mismatch to VERIFIED.
- `recovery.verification_grace_seconds` is an actual retry window for normal post-write verification; persisted uncertainty is later re-read without replay and without automatic unpause.
- Overlapping production hourly/daily/weekly/direct processes serialize through the Linux lock without an arbitrary production wait timeout; manual invocations retain a bounded wait for operator feedback.
- Owner scheduling booleans are honored at the runtime entrypoint and systemd installer.
- Production user-systemd installation requires verified linger so services survive logout and start after boot.
- Codex Evergreen uses the current `approval_policy="never"` config override and no longer false-fails by assuming a global approval flag must appear in `codex exec --help`.
- Compatibility-sensitive changes run against the current official Codex on Ubuntu, including real repo-local marketplace/plugin install and `plugin list` verification.
- Dedicated production `CODEX_HOME` setup installs and verifies the repo-native `amazon-ads-operator` plugin from the local marketplace.
- Owner policy/operator booleans and numeric fields are strictly typed; invalid string/bool substitutions fail closed.

## Claim boundary

The source/archive can be sealed only after the complete credential-free archive and virtual-production gates pass on the exact release SHA. A particular Ubuntu host and Amazon Ads advertiser/profile remain separately live-acceptance pending until OAuth, current MCP schemas, profile/account/currency binding, fresh-read behavior, controlled micro-live mutation, restart/ambiguity drills and actual reboot/systemd behavior are proven on that deployment.
