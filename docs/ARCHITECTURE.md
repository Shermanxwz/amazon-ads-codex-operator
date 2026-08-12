# Architecture

## Design objective

The system intentionally maximizes **AI freedom inside an Owner-defined envelope**. Codex may choose optimization strategy and routine Sponsored Products mutations without per-action human approval. Deterministic code owns the monetary ceiling, permanent blocks, scope, replay barrier and state-transition integrity.

## Trust domains

### Owner domain — highest authority

`owner.db`, signing key, frozen hook, production `CODEX_HOME`, mode and monetary envelope live under `ADS_OWNER_HOME`, outside the Git checkout and outside model-writable workspaces. Owner changes are validated server-side, versioned and entered into an HMAC-signed hash-chain audit log.

### Runtime controller domain

Python loads an immutable Owner snapshot for a cycle, performs deterministic policy checks, reserves spend capacity and seals actions. It may auto-pause after uncertainty, but it cannot clear Emergency Stop or elevate itself to Autopilot.

### Model domain

Each Planner/Executor/Verifier invocation receives a disposable directory. Shell sandbox policy is `read-only`. The environment excludes controller/Amazon secrets. Planner and Verifier remain read roles; the Executor receives only the single Amazon MCP tool associated with the sealed action.

### Atomic mutation domain

A live action is not released as a batch. For each action:

1. re-check the Owner authority token;
2. require verified dependencies;
3. for an existing entity, perform a fresh read and deterministically compare live state with the sealed `before` state;
4. mint a signed v2 grant containing the exact action hash, MCP tool, arguments and Owner policy/operator revisions;
5. start an Executor with only that MCP tool in `enabled_tools`;
6. immediately before the Amazon call, the frozen `PreToolUse` hook re-reads Owner mode/Emergency Stop/revisions, validates the exact canonical tool input, then atomically consumes the grant with an `O_EXCL` marker;
7. parse the Amazon result conservatively;
8. immediately run an independent read-only Verifier;
9. only then permit the next action.

The one-use marker is an execution-boundary journal. A second attempt with the same action grant cannot pass the hook.

## Crash/restart state machine

The runtime distinguishes **authorization evidence** from a transport receipt:

```text
released
   │
   ├─ grant never consumed ─────────────► cancelled / safe to replan
   │
   ▼
executing
   │
   ├─ consumed marker exists
   │       │
   │       ├─ process/host survives ────► receipt + independent verification
   │       │
   │       └─ process/host crashes ─────► restart reconciliation
   │                                      │
   │                                      ├─ Amazon state == sealed after
   │                                      │      └─ verified; never replay
   │                                      └─ cannot prove exact intended state
   │                                             └─ uncertain + Paused
   ▼
verified
```

A consumed grant is never treated as permission to retry. Fresh Amazon state is the final evidence used to distinguish a successfully applied write from an ambiguous failure.

## Stale-state / TOCTOU control

The Planner is free to choose the action. The controller prevents the action from being applied against an entity that changed after planning. Existing-entity writes receive a fresh state read immediately before release; the sealed `before` state must be an exact subset of the fresh observed state. A mismatch does not permanently reject the strategy—it cancels the stale action so a later cycle can reason from current reality.

## Monetary concurrency

Spend-increasing actions reserve the Owner daily envelope in SQLite before Amazon is called. Reservation acquisition uses a write transaction. Pending/unknown outcomes continue consuming capacity, preventing a later cycle from treating ambiguous exposure as free budget.

`scripts/run_cycle.py` also uses a Linux `flock` single-instance lock, so hourly/daily/weekly systemd invocations cannot concurrently run against the same Owner Home.

## Two-phase creation

A new autonomous Campaign must be created PAUSED and under the configured namespace. The created entity is registered as pending verification. Only independent verification marks it eligible for later enablement.

## Runtime compatibility

`config/codex-compatibility.json` describes the Codex execution capabilities required by this architecture. `scripts/check_codex_runtime.py` validates the installed CLI and production `CODEX_HOME`; `preflight.py` fails closed when required non-interactive/structured execution capabilities disappear.

This is a capability contract rather than blind trust in a version string.

## External contract reproducibility

Amazon MCP is the runtime transport. As an independent reference, `vendor/amazon-postman/CERTIFIED_UPSTREAM.json` pins the exact Amazon public Postman commit certified for the release. The sync script fetches only that commit. A scheduled CI drift job reports upstream changes without silently changing the certified contract.

## Disaster recovery

`scripts/backup_owner.py` uses SQLite's backup API for consistent `owner.db` and `runtime.db` snapshots and records SHA-256, size and mode in a manifest. It also backs up the controller signing key and deterministic production config/hook files. OAuth/auth stores are intentionally excluded.

`scripts/restore_owner.py` verifies every manifest hash, SQLite integrity, runtime foreign keys and the signed Owner audit chain before accepting a restore. A recovered host returns to Observe until OAuth and live Amazon state are re-established.

## Git checkout role

The repository is deployable code, not runtime state. Production systemd units mount it read-only. Real account identifiers, Owner policies, OAuth material, signing keys, run logs and database files must not be committed.
