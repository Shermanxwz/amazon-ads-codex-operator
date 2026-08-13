# Changelog

## 0.6.0 — Sponsored Products optimization-intelligence seal

- Added a dedicated read-only Sponsored Products research pass before each autonomous cycle so fresh normalized performance evidence is persisted before strategy selection.
- Added `OptimizationMemory` with durable performance facts, ASIN economics, portfolio alternatives, experiments and verified action outcomes in the runtime database.
- Added empirical-Bayesian CVR shrinkage, evidence confidence, attribution-tail risk, short-vs-long trend detection, intraday pattern summaries, impression-share headroom and marginal profit-per-click/ad-dollar signals.
- Upgraded the Planner from campaign-level ACOS tuning to account/ASIN portfolio allocation based on expected incremental contribution profit, opportunity cost and exploration value.
- Added first-class reasoning for search-term harvesting/isolation, target lifecycle, placement economics, Amazon Business/off-Amazon evidence, SIS, audience boosts, Amazon Marketing Stream, rule-based bidding/budget rules and Sponsored Products video when exposed by the authenticated Amazon surface.
- Added an optional Owner economics feed at `$ADS_OWNER_HOME/economics.json` (or `ADS_ECONOMICS_FILE`) with `break_even_acos_pct` as a useful fallback margin proxy.
- Made `learning_snapshot` a required Planner output even on zero-mutation cycles, preserving observations, foregone portfolio candidates and explicit causal experiments for future cycles.
- Added `OptimizationController` without adding an approval tier or reducing the AI's Owner-granted business authority; optimization telemetry degrades independently from the sealed write control plane.
- Added optimization architecture/unit contracts and a CLI optimization report.

## 0.5.3 — Production-surface full-stack acceptance seal

- Extended fresh Ubuntu 24.04 Python-3.12 full-stack certification from eight internal execution/recovery scenarios to ten end-to-end production scenarios.
- Added a real `scripts/run_web.py` loopback HTTP drill covering static UI, readiness, authentication, CSRF denial/enforcement, Owner policy revision, revision restore, Autopilot transition and Emergency Stop.
- Added an explicit `ADS_SYSTEMD_RENDER_ONLY=1` certification mode to `install_systemd.sh`; it runs the exact production unit-rendering path inside an isolated HOME without touching the validation host's user services.
- Added full-stack verification of rendered systemd units, resolved project/Owner paths and `systemd-analyze verify`.
- Added executable tests that make both production-surface drills mandatory in the archive workflow.
- Updated `make virtual-acceptance` to run both the control-plane and production-surface harnesses.

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
