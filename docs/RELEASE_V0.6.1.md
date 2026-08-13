# Amazon Ads Codex Operator v0.6.1

**Owner Direct Override seal.**

v0.6.1 adds an explicit Owner-armed capability window for exceptional Sponsored Products operations without weakening the normal full-managed Autopilot architecture.

## New Owner capability

The authenticated Control Plane now exposes four Owner Direct Override durations: 30 minutes, 1 hour, 2 hours and permanent-until-cleared. The AI cannot arm or extend this authority itself.

Once armed, the Owner can give Codex a natural-language special operation. Codex routes that instruction through a `direct` cycle, where routine autonomous restrictions are lifted for the bound instruction: autonomy toggles, normal money/bid/placement caps, campaign-creation quotas, cooldowns, naming/PAUSED-first rules, managed-ASIN filters, routine confidence thresholds and routine irreversible-ad restrictions.

## Authority and revocation design

The window itself is only a capability. Full direct policy is injected only while an explicit direct instruction is active, so background hourly/daily/weekly optimization does not silently inherit unrestricted authority.

Every arm, direct-command start, direct-command finish, clear, expiry and authority-changing event advances the Owner policy revision. That immediately invalidates previously issued one-use Executor grants at the frozen PreToolUse boundary. Timed direct grants are also capped to the window expiry.

Timed windows return to the prior mode. Permanent authorization remains until the Owner selects another mode, clears the override or triggers Emergency Stop.

## Invariants retained

Owner Direct Override never bypasses Owner authentication, configured advertiser/profile identity, Sponsored Products scope, Emergency Stop, exact sealed MCP arguments, fresh pre-write state, one-use grants, independent verification, crash ambiguity handling or the signed audit chain. Billing/payment, credentials/OAuth, user management, account administration and account deletion remain outside the capability.

## Operator surfaces

- Owner Web: duration selector, live countdown/status and clear control.
- Codex/operator: `python3 scripts/run_cycle.py direct --instruction "..."` consumes an already armed window; it cannot create one.
- Owner CLI status exposes `direct_override`; selecting a normal mode clears any active override.
- `docs/OWNER_DIRECT_OVERRIDE.md` defines the capability and trust boundary.

The normal Sponsored Products optimization/learning architecture from v0.6.0 is unchanged.
