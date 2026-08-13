# Changelog

## 0.5.2 — Reproducibility / provenance maintenance seal

- Made the Owner-owned signing-key file the canonical production signing identity; ambient environment variables can no longer override it.
- Bounded certified Python support to 3.11/3.12 and moved Ubuntu 24.04 full-stack/release certification to Python 3.12.
- Upgraded GitHub Actions to current Node-24-era checkout/setup-python releases while retaining exact commit-SHA pinning.
- Fully pinned archive/test/build tooling, including pytest transitive dependencies, in `config/archive-tooling.txt` and pinned the PEP 517 setuptools backend.
- Added complete Git-history privacy scanning for forbidden runtime/auth filenames and credential/token patterns.
- Added deterministic `SOURCE_DATE_EPOCH` plus byte-for-byte double-build checks for wheels and release source archives.
- Added release-tooling identity to `RELEASE_IDENTITY.json`.
- Added exact-SHA GitHub/Sigstore artifact provenance attestations for release subjects.
- Added scheduled release-integrity verification for checksums, tag/identity binding and v0.5.2+ attestations.
- Ignored local virtual-acceptance build artifacts so certification runs keep the checkout clean.

## 0.5.1 — Final acceptance / disaster-recovery seal

- Domain-separated Executor grant signing from the Owner master key; the frozen hook receives only the derived grant-verification secret.
- Added a fresh Ubuntu 24.04 full virtual production acceptance covering bootstrap/preflight, Observe, sealed execution, real frozen Hook, verification, upgrade/rollback, ambiguous-write recovery, restart, Emergency Stop and process locking.
- Upgraded backup manifests to v2 and preserved content-addressed ACTIVE/PREVIOUS/candidate Codex runtime slots plus registry with SHA-256 verification and path rebinding on restore.
- Hardened restore to clear stale OAuth/auth, grants, disposable workspaces, run artifacts, old runtime slots/registry, lock files and SQLite sidecars.
- Made archive release-version consistency dynamic across package, runtime, plugin and release notes.

## 0.5.0 — Codex Evergreen / native integration

- Decoupled production execution from Linux PATH and introduced Owner-pinned ACTIVE Codex runtime identities with candidate probe, atomic promotion and rollback.
- Added daily latest-Codex compatibility CI and repo-native Amazon Ads Operator plugin/skills.
- Added automatic green-main release sealing and single-main-branch enforcement.
- Preserved broad AI decision freedom inside Owner scope and monetary limits.

## 0.4.0 — Archive hardening / crash-safe sealed execution

- Added one-use grant replay protection, final-boundary Owner checks, fresh pre-write state validation, crash/restart reconciliation, direct production-hook tests, immutable Amazon contract pinning and verified backup/restore.

## 0.3.0 — Owner Control / sealed execution

- Added Owner Web/DB authority, signed audit history, exact one-action execution, budget reservations, cooldowns, recovery breaker and PAUSED-first campaign creation lifecycle.
