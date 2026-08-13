# Owner Direct Override

Owner Direct Override is a deliberately explicit **temporary delegation capability** for special Sponsored Products operations that should not be forced through the normal autonomous optimization envelope.

It exists for cases where the Owner would otherwise need to open the Amazon console and perform an exceptional operation manually. The Owner arms a time window in the authenticated Control Plane, then gives Codex a natural-language instruction. Codex executes that instruction through the same sealed Controller/Executor/Verifier path used by normal automation.

## Authorization windows

The Control Plane exposes four choices:

- 30 minutes;
- 1 hour;
- 2 hours;
- permanent, until the Owner explicitly selects another mode, clears the override, or triggers Emergency Stop.

A timed window automatically returns to the mode that was active before it was armed. If that previous Autopilot configuration is no longer valid when the window ends, the system returns to Observe instead of silently restoring an invalid authority state.

The AI cannot arm or extend the window itself. This is intentional: a model may consume an Owner-granted capability, but it must not manufacture that capability.

## Direct-command flow

```text
Authenticated Owner Web
        |
        | arm 30m / 1h / 2h / permanent
        v
Owner Direct Override capability window
        |
        | Owner speaks/types a special instruction to Codex
        v
python3 scripts/run_cycle.py direct --instruction "..."
        |
        | bind exact instruction to a new Owner policy revision
        v
Direct Sponsored Products Planner
        |
        | full advertising-operation authority for this instruction
        v
fresh pre-write state -> sealed one-use Executor -> Amazon MCP
        |
        v
independent verification -> audit/outcome learning
        |
        `-> direct command closes; window remains armed until expiry/clear
```

Each direct command increments the Owner policy revision before execution and again when the command closes. Arming, clearing, expiration, mode changes and Emergency Stop also invalidate the capability. This makes any previously issued Executor grant stale at the frozen PreToolUse boundary.

Executor grant expiry is additionally capped to the authorization-window expiry, closing the narrow race where a grant could otherwise outlive a 30-minute/1-hour/2-hour window by a few seconds.

## What "full permissions" means

For the currently certified project scope, it means **all executable Sponsored Products advertising operations inside the configured advertiser/profile boundary that are necessary to carry out the Owner's direct instruction**.

The direct policy can bypass routine autonomous restrictions including:

- normal autonomy toggle matrix;
- Owner daily automation budget envelope and spend reservations;
- per-action bid/budget caps;
- placement caps;
- campaign creation quotas;
- cooldowns;
- autonomous campaign naming prefix;
- PAUSED-first autonomous creation rule;
- managed-ASIN filter;
- routine confidence thresholds;
- routine recovery breaker;
- routine irreversible-ad-operation prohibition.

That allows special operations such as large budget changes, large bid/placement changes, cross-ASIN restructuring, immediate enable/pause/archive work, bulk creation or cleanup, and other exceptional Sponsored Products mutations when the Owner explicitly asks for them.

## Invariants that never disappear

Owner Direct Override does **not** dismantle the trust boundary. The following remain mandatory:

- authenticated Owner activation;
- configured advertiser/profile scope;
- Sponsored Products product scope;
- Emergency Stop dominance;
- exact live Amazon MCP tool name and arguments;
- fresh pre-write state for existing entities;
- sealed one-action execution;
- one-use Executor grants;
- grant expiry;
- independent post-write verification;
- no blind replay after ambiguous writes;
- signed Owner audit chain;
- no billing/payment mutation;
- no credentials/OAuth mutation;
- no user management;
- no account administration or account deletion.

Those are not advertising strategy limits. They are the identity, integrity and recovery substrate that makes temporary full advertising authority auditable and revocable.

## Interaction with normal Autopilot

Arming a window does not turn normal scheduled optimization into unrestricted root automation.

- If the previous mode was Autopilot, hourly/daily/weekly cycles continue under the normal Owner policy while the direct window is idle.
- If the previous mode was Observe or Paused, scheduled autonomous cycles are suppressed while the direct window is armed; only explicit `direct` cycles can write.
- Full direct policy is injected only while one direct instruction is actively bound to a `direct` cycle.
- When the command finishes, normal policy is restored immediately even if the authorization window remains open for another Owner instruction.

This distinction keeps the Owner's intent precise: **open capability window** does not mean **let every background optimizer ignore all limits**.

## Operational use

1. Open Owner Control Plane.
2. Select `放开 30 分钟`, `放开 1 小时`, `放开 2 小时`, or `永久放开`.
3. Give Codex the special Sponsored Products instruction in natural language.
4. Codex checks `python3 scripts/ownerctl.py status` and confirms `direct_override.armed=true`.
5. Codex routes the instruction through `python3 scripts/run_cycle.py direct --instruction <instruction>`.
6. Review the normal action/verification/audit surfaces if desired.
7. For permanent authorization, explicitly select another Control Plane mode when finished.

Emergency Stop can be used at any time and immediately revokes the window as well as normal writes.
