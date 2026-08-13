# v0.5.1 archive status

Status policy: **GREEN MAIN + FULL VIRTUAL STACK AUTO-SEALS / REAL-ACCOUNT LIVE ACCEPTANCE REMAINS HOST-SPECIFIC**

v0.5.1 makes the source seal depend on both static/unit evidence and a complete credential-free production-path simulation. The exact `main` SHA must pass `archive-gate` on Ubuntu 24.04 for Python 3.11 and 3.12 **and** the independent `virtual-full-stack` job. Only then may `sealed-release` create the version tag at that same SHA and publish wheel/source artifacts, `RELEASE_IDENTITY.json` and SHA-256 checksums.

## Signing-key separation seal

The Owner/action master signing key and the hook-visible Executor-grant key are now domain-separated. Bootstrap derives the grant-only key, preflight verifies it, the controller signs v2 grants through the derived domain, and the frozen hook reads only that derived secret. Owner audit/action signing remains on the master key.

## Full virtual-stack seal

The virtual acceptance uses a self-contained fake Codex executable and persistent virtual Amazon state, but runs the real production Controller, RuntimePaths, OwnerStore, SQLite ledger/state, Codex Evergreen registry, frozen PreToolUse hook, grant files, runner isolation, verification and recovery logic. It covers:

- fresh bootstrap, capability probe, ACTIVE snapshot and preflight;
- Observe planning/sealing with zero external mutation;
- Autopilot planner → policy → fresh prewrite → one-use grant → frozen hook → mutation → independent verifier;
- candidate promotion and rollback;
- backup/restore of Owner state plus ACTIVE/PREVIOUS Codex runtime identity;
- transport failure after a successful write, reconciled from fresh external state with no replay;
- crash after grant consumption but before a write, retained as uncertain and never blindly replayed;
- restart reconciliation and automatic pause;
- Emergency Stop applied while Executor waits immediately before the hook boundary;
- rejection of a concurrent overlapping cycle by the Linux `flock` single-instance lock.

## Disaster-recovery seal

Backup manifest v2 includes Owner/runtime SQLite, signing key, production Codex config/hook and the content-addressed Codex runtime registry/slots needed to restore ACTIVE and PREVIOUS identities. Restore verifies hashes, rewrites runtime slot paths to the target Owner Home, clears stale OAuth/auth state, grants, prior runtime slots, disposable workspaces, run artifacts, lock files and SQLite sidecars, validates SQLite/audit/runtime integrity, and always returns Owner mode to Observe.

## Codex Evergreen / native integration seal

Production still selects an Owner-pinned ACTIVE Codex runtime instead of following PATH; fingerprints are checked before use and recorded per invocation. New Codex versions remain candidates until capability-probed and explicitly promoted, with PREVIOUS retained for rollback. The repo continues to expose the native `amazon-ads-operator` plugin/skills without creating another privileged Amazon mutation path.

## Repository and authority seal

The GitHub repository policy remains one branch: `main`. v0.5.1 does **not** reduce AI business autonomy: Codex remains free to optimize inside Owner-defined Sponsored Products scope and monetary limits; hardening constrains authorization mechanics, runtime replacement and recovery rather than routine business choices.

## Claim boundary

The virtual Amazon boundary is intentionally credential-free. It proves deterministic control-plane mechanics but cannot certify Amazon OAuth, a particular advertiser/profile, the current authenticated live MCP schema, Amazon-side timing/429 behavior or a real-money mutation. Those host/account-specific checks remain mandatory per `docs/ARCHIVE_ACCEPTANCE.md` before a specific Ubuntu host + Amazon account is called production-accepted.
