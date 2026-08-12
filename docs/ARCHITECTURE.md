# Architecture

## Trust domains

### Owner domain — highest authority
`owner.db`, signing key, frozen hook, production `CODEX_HOME`, mode and monetary envelope live under `ADS_OWNER_HOME`, outside the Git checkout and outside model-writable workspaces. Owner changes are validated server-side, versioned and entered into an HMAC-signed hash-chain audit log.

### Runtime controller domain
Python loads an immutable Owner snapshot for a cycle, performs deterministic policy checks, reserves spend capacity and seals actions. It may reduce authority by auto-pausing after uncertainty, but it cannot clear Emergency Stop or elevate itself to Autopilot.

### Model domain
Each Planner/Executor/Verifier invocation receives a disposable directory. Shell sandbox policy is `read-only`. The environment excludes controller/Amazon secrets. Planner and Verifier use the MCP server's `writes` approval mode plus no human approval path; the local hook also blocks common mutation-like MCP names as defense in depth.

### Atomic mutation domain
A live action is not released as a batch. For each action:
1. re-check the Owner authority token;
2. require verified dependencies;
3. mint a short-lived HMAC-signed grant containing one exact MCP bare tool name + arguments;
4. start an Executor with only that MCP tool in `enabled_tools`;
5. PreToolUse compares canonical tool input to the signed grant before the supported MCP tool call executes;
6. parse the Amazon result conservatively;
7. immediately run an independent read-only Verifier;
8. only then permit the next action.

This makes a mid-cycle Owner pause effective before the next mutation and limits the maximum in-flight release to one mutation.

## Monetary concurrency
Spend-increasing actions reserve the Owner daily envelope in SQLite before Amazon is called. Pending/unknown outcomes continue consuming capacity, preventing a later cycle from treating ambiguous exposure as free budget.

## Two-phase creation
A new autonomous Campaign must be created PAUSED and under the configured namespace. The created entity is registered as pending verification. Only independent verification marks it eligible for later enablement.

## Git checkout role
The repository is deployable code, not runtime state. Production systemd units mount it read-only. Real account identifiers, Owner policies, OAuth material, signing keys, run logs and database files must not be committed.
