# Architecture

## Design objective

The system intentionally maximizes **AI freedom inside an Owner-defined envelope**. Codex may choose optimization strategy and routine Sponsored Products mutations without per-action human approval. Deterministic code owns the monetary ceiling, permanent blocks, scope, replay barrier, runtime identity and state-transition integrity.

## Trust domains

### Owner domain — highest authority

`owner.db`, the Owner/action master signing key, the derived Executor-grant key, frozen Hook, production `CODEX_HOME`, Owner-pinned Codex runtime registry/slots, mode and monetary envelope live under `ADS_OWNER_HOME`, outside the Git checkout and outside model-writable workspaces. Owner changes are validated server-side, versioned and entered into an HMAC-signed hash-chain audit log.

The master key signs Owner audit/action material. Executor v2 grants use a deterministic domain-separated key. The frozen Hook receives only the derived grant key and therefore cannot use its verification secret to forge Owner audit history or ordinary sealed-action signatures.

### Runtime controller domain

Python loads an immutable Owner snapshot for a cycle, performs deterministic policy checks, reserves spend capacity and seals actions. It may auto-pause after uncertainty, but it cannot clear Emergency Stop or elevate itself to Autopilot.

Production Codex execution resolves the Owner-pinned ACTIVE content-addressed runtime, verifies its SHA-256 fingerprint for every invocation and records runtime identity evidence beside the result. PATH updates only create candidates; they do not change production authority.

### Model domain

Each Planner/Executor/Verifier invocation receives a disposable directory. Shell sandbox policy is `read-only`. The environment excludes controller/Amazon secrets. Planner and Verifier remain read roles; the Executor receives only the single Amazon MCP tool associated with the sealed action.

### Atomic mutation domain

A live action is not released as a batch. For each action:

1. re-check the Owner authority token;
2. require verified dependencies;
3. for an existing entity, perform a fresh read and deterministically compare live state with the sealed `before` state;
4. mint a v2 grant containing the exact action hash, MCP tool, arguments and Owner policy/operator revisions, signed in the Executor-grant domain;
5. start an Executor with only that MCP tool in `enabled_tools`;
6. immediately before the Amazon call, the frozen `PreToolUse` Hook re-reads Owner mode/Emergency Stop/revisions, validates the exact canonical tool input, validates the grant with the derived key, then atomically consumes it with an `O_EXCL` marker;
7. parse the Amazon result conservatively;
8. immediately run an independent read-only Verifier;
9. only then permit the next action.

The one-use marker is an execution-boundary journal. A second attempt with the same action grant cannot pass the Hook.

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

## Runtime compatibility / Evergreen

`config/codex-compatibility.json` describes the stable Codex execution capabilities required by this architecture. New Codex installations are copied into Owner-private content-addressed candidate slots and probed there. Only an explicit atomic promotion can change ACTIVE; PREVIOUS is retained for rollback. `scripts/check_codex_runtime.py` and `preflight.py` fail closed when required non-interactive/structured execution capabilities disappear or the ACTIVE fingerprint changes.

This is a capability-and-content contract rather than blind trust in PATH or a version string.

## External contract reproducibility

Amazon MCP is the runtime transport. As an independent reference, `vendor/amazon-postman/CERTIFIED_UPSTREAM.json` pins the exact Amazon public Postman commit certified for the release. The sync script fetches only that commit. A scheduled CI drift job reports upstream changes without silently changing the certified contract.

## Full virtual-stack acceptance

The credential-free acceptance harness replaces only the outer Codex/Amazon network boundary with a self-contained fake Codex executable and persistent virtual Amazon state. It deliberately runs the real Controller, OwnerStore, RuntimePaths, SQLite stores/ledger, Evergreen registry, production runner, frozen Hook, one-use grants, verification, recovery and Linux process lock.

The fresh Ubuntu 24.04 CI job builds/installs the wheel in an isolated Python virtual environment and exercises bootstrap/preflight, Observe, the full sealed write path, candidate promotion/rollback, backup/restore, ambiguous failure after write, failure after grant consumption before write, restart reconciliation, Emergency Stop at the final Hook boundary and overlapping-cycle rejection.

This proves the control plane without credentials; authenticated Amazon semantics remain a separate live-acceptance domain.

## Disaster recovery

`scripts/backup_owner.py` uses SQLite's backup API for consistent `owner.db` and `runtime.db` snapshots and records SHA-256, size and mode in manifest v2. It also archives the Owner/action master key, domain-separated Executor-grant key, deterministic production config/frozen Hook, Codex runtime registry and every content-addressed slot referenced by ACTIVE, PREVIOUS or registered candidates. OAuth/auth stores are intentionally excluded.

`scripts/restore_owner.py` first scrubs stale non-archived surfaces on the target: OAuth/auth state, grants, disposable workspaces, run artifacts, old runtime registry/slots, lock files and SQLite sidecars. It then verifies every manifest hash, restores and path-rebinds runtime records to the new Owner Home, verifies runtime SHA-256 identities, SQLite integrity, runtime foreign keys and the signed Owner audit chain. A recovered host always returns to Observe until OAuth and live Amazon state are re-established.

## Git checkout role

The repository is deployable code, not runtime state. Production systemd units mount it read-only. Real account identifiers, Owner policies, OAuth material, signing keys, run logs and database files must not be committed.
