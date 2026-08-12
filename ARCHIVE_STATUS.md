# v0.5.0 archive status

Status policy: **GREEN MAIN AUTO-SEALS / REAL-ACCOUNT LIVE ACCEPTANCE REMAINS HOST-SPECIFIC**

v0.5.0 is designed so source sealing is mechanical rather than a prose claim. The exact `main` SHA must pass `archive-gate` on Ubuntu 24.04 for Python 3.11 and 3.12. Only then does `sealed-release` create `v0.5.0` at that same SHA and publish wheel/source artifacts, `RELEASE_IDENTITY.json` and SHA-256 checksums. If the version tag already points elsewhere, a changed `main` cannot be silently resealed under the same version.

## Codex Evergreen seal

- Production Controller selects an Owner-pinned ACTIVE Codex runtime instead of following PATH.
- ACTIVE binary fingerprint is checked before use and recorded with each Codex invocation.
- New Codex versions are registered as content-addressed candidates and capability-probed before promotion.
- Promotion and rollback are atomic registry transitions; previous ACTIVE remains rollback target.
- Bootstrap only adopts PATH Codex when no ACTIVE exists, so later system updates cannot silently replace production.
- Amazon MCP OAuth/configuration commands use ACTIVE Codex.
- Daily Ubuntu CI installs the current official Codex and probes the same contract for early compatibility drift.
- Stable Codex execution/MCP/plugin surfaces are dependencies; explicitly experimental surfaces are not.

## Native integration seal

The repo includes an official-shape `.codex-plugin/plugin.json`, four focused skills, and a repo marketplace at `.agents/plugins/marketplace.json`. This makes Codex the native operator UX without creating a parallel privileged Amazon mutation path.

## Repository seal

The repository policy is one branch: `main`. `single-main-branch` deletes non-main branches after main pushes and verifies only main remains.

## Authority status

v0.5.0 does **not** reduce AI business autonomy. Codex remains free to optimize inside Owner-defined Sponsored Products scope and monetary limits. Evergreen hardening controls runtime replacement, replay, stale state, crash recovery and release identity—not routine business choices.

## Claim boundary

Credential-free GitHub CI cannot certify a real Amazon Ads deployment. OAuth, live MCP tool/schema binding, fresh-state race drill, micro-live reversible writes, crash/restart reconciliation against real Amazon state, PAUSED-create/verify/enable lifecycle, Emergency Stop timing and ambiguous-failure behavior remain required per `docs/ARCHIVE_ACCEPTANCE.md` before a specific Ubuntu host + Amazon account is called production-accepted.
