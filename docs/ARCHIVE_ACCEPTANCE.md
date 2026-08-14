# Archive / production acceptance gates

A source release may be **archive-sealed** while a specific Amazon account deployment remains **live-acceptance pending**. v0.7.x preserves broad AI business autonomy inside the Owner envelope while treating Planner/Verifier declarations as untrusted inputs: mutation identity, monetary exposure, fresh-state comparison and final acceptance are deterministic control-plane facts.

## A. Source/archive gate

Required before automatic sealing:

- all Python compiles and the complete test suite pass on the explicitly certified Python 3.11/3.12 matrix;
- JSON configs/schemas, Codex plugin manifest and repo marketplace parse;
- package/runtime/plugin release versions agree and matching release notes exist;
- PEP 517/build/test tooling and pytest transitive dependencies are exactly version-pinned;
- GitHub Actions dependencies are pinned by exact commit SHA;
- Owner Web assets are packaged in the wheel;
- current repository tree and complete Git history contain no forbidden runtime Owner/auth/key/database filenames or known credential/token patterns;
- project MCP base config keeps writes gated until sealed Executor release;
- exact MCP tool/arguments/entity binding, non-empty existing-entity before-state, intended after-state, one-use grants, final Owner re-check and fresh pre-write state remain covered;
- spend expansion is determined from mutation semantics and fresh account evidence; a model-provided `spend_delta=0` cannot remove the Owner monetary reservation;
- hourly bid limits, campaign daily creation limits and historical runtime accounting are behavior-tested;
- budget day boundaries follow the Owner account timezone and expired never-executed reservations are reclaimable without releasing ambiguous writes;
- post-write `VERIFIED` requires both fresh read evidence and deterministic sealed-after subset comparison; verifier model text alone is insufficient;
- configured post-write verification grace is exercised, and persisted verification uncertainty is restart-reconciled without replay or automatic unpause;
- deployed production Hook is behavior-tested directly;
- the Owner-owned master-key file is the canonical production signing identity and the Hook receives only the domain-separated Executor-grant key;
- backup/restore preserves SQLite/audit integrity and content-addressed ACTIVE/PREVIOUS Codex runtime identities while clearing stale OAuth/grant/runtime side state;
- Codex Evergreen contract, registry, candidate promotion/rollback and ACTIVE runner binding tests pass;
- compatibility-sensitive changes trigger an actual current-official-Codex Ubuntu job, including repo-native marketplace/plugin installation;
- production runner records ACTIVE runtime identity/fingerprint evidence;
- Amazon contract reference remains pinned to an immutable certified upstream commit;
- shell scripts and rendered systemd units validate;
- production cycle overlap serializes instead of silently dropping timer work; runtime scheduling switches are independently enforced;
- production user-systemd installation requires linger and reflects Owner timer-enable switches;
- Owner policy/operator boolean and numeric fields are strictly typed;
- repo-scoped Codex plugin/skills, main-only release hygiene, release, drift and release-integrity workflows are present;
- a fresh Ubuntu 24.04 Python-3.12 `virtual-full-stack` job passes all ten credential-free production scenarios listed below;
- the virtual job double-builds the wheel using commit-derived `SOURCE_DATE_EPOCH` and requires byte identity;
- `archive_check.py` exits 0 on the exact release checkout.

`sealed-release` may create a version tag only after the whole `archive-gate` workflow succeeds for the exact current main SHA, including every Python matrix job and `virtual-full-stack`.

## B. Ten-scenario credential-free virtual production acceptance

The mandatory `virtual-full-stack` consists of the control-plane harness plus the production-surface harness:

1. **Fresh bootstrap + preflight:** initialize Owner state, grant key, frozen Hook and Owner-pinned ACTIVE virtual Codex; capability/preflight must pass.
2. **Observe no-write:** Planner may reason/seal while external virtual Amazon state remains unchanged.
3. **Sealed live happy path:** Planner → deterministic semantic policy → Controller-derived spend reservation → fresh pre-write state → one-use grant → exact frozen PreToolUse Hook → one mutation → independent Verifier → deterministic final comparison → verified state.
4. **Evergreen promote/rollback:** compatible candidate promotion changes ACTIVE; rollback restores the exact prior content-addressed runtime.
5. **Disaster recovery:** backup/restore preserves audit/DB plus ACTIVE runtime identity and removes stale OAuth/auth/grant state; restored Owner mode is Observe.
6. **Ambiguous after-write transport:** external state proves the intended mutation happened; action verifies without replay.
7. **Crash after grant consumption before write:** consumed evidence is retained, mutation is not replayed, Owner auto-pauses and restart reconciliation persists uncertainty.
8. **Emergency Stop + overlap lock:** a second direct/manual cycle cannot execute concurrently; Emergency Stop triggered while Executor waits at the final Hook boundary denies the not-yet-submitted write.
9. **Production Owner Web entrypoint:** start the real `scripts/run_web.py` on loopback; verify static UI/security headers/readiness, unauthenticated denial, password login, CSRF rejection/enforcement, policy revision, revision restore, Autopilot transition and Emergency Stop.
10. **Production systemd install/render path:** run the real `scripts/install_systemd.sh` inside an isolated HOME with `ADS_SYSTEMD_RENDER_ONLY=1`; all five user units must be rendered with no unresolved placeholders, correct project/Owner paths, schedule controls and pass `systemd-analyze verify` when available. Render-only exits before `systemctl` or linger mutation.

These scenarios intentionally substitute only the external Amazon/Codex network boundary and host service activation. They do not substitute the Controller, Owner DB, runtime DB, policy engine, budget ledger, runtime registry, frozen Hook, grant consumption, verifier, recovery code, Owner Web server or systemd rendering logic.

## C. Ubuntu host gate

Required before any live mutation:

- Owner Home/signing key permissions are private;
- frozen Hook hash matches the vetted source;
- dedicated `CODEX_HOME` has hooks enabled and Amazon Ads MCP configured;
- repo-native `amazon-ads-operator` plugin is installed/enabled in that dedicated `CODEX_HOME`;
- `python3 scripts/codex_runtime.py status` shows an Owner-private ACTIVE slot with valid SHA-256 integrity;
- `scripts/check_codex_runtime.py` and `preflight.py` accept the ACTIVE runtime;
- changing/updating PATH Codex does not change ACTIVE identity;
- a compatible candidate can be registered, promoted and rolled back while Owner policy remains unchanged;
- Owner audit chain/runtime SQLite integrity pass;
- backup and restore drill restores ACTIVE/PREVIOUS runtime identity and returns Owner mode to Observe without carrying stale OAuth or grant state;
- actual user-systemd installation succeeds, linger is enabled, Owner Web/timers are healthy after logout/reboot, disabled schedule families do not execute, and timer collisions serialize;
- consumed actions are not replayed.

## D. Codex update acceptance drill

For a new Codex candidate on a production host:

1. Capture ACTIVE identity with `python3 scripts/codex_runtime.py status`.
2. Install/update system Codex and confirm ACTIVE identity is unchanged.
3. Register the new binary as candidate and inspect the capability probe.
4. Do not promote if any required stable command/config behavior or strict-config check fails.
5. Confirm repo-native marketplace/plugin installation against the candidate.
6. If compatible, promote deliberately; run preflight, Observe/dry-run and Amazon MCP read checks.
7. Run at least one controlled cycle with deterministic independent verification.
8. Exercise `python3 scripts/codex_runtime.py rollback` once during initial host certification and confirm the previous runtime becomes ACTIVE again.
9. Re-promote only after rollback proves recovery works.

## E. Real Amazon account staged acceptance

Not reproducible in credential-free CI, including the virtual Amazon harness:

1. **Observe:** verify Profile/account/marketplace/currency binding, reporting coverage, OAuth and authenticated live MCP schemas.
2. **Dry-run:** inspect representative plans and exact live MCP tool/argument contracts while AI retains normal planning freedom.
3. **Fresh-state drill:** externally change a harmless test entity between planning/release and confirm stale intent is blocked/replanned.
4. **Monetary-boundary drill:** deliberately make Planner-reported `spend_delta` unhelpful in a controlled fixture and confirm Controller-derived reservation still protects the Owner ceiling.
5. **Micro-live:** low ceiling, one reversible bid/budget mutation; confirm one-use grant, outcome parsing, deterministic final comparison and independent verification.
6. **Ambiguous transport drill:** induce/simulate client-side failure after tool boundary and prove no blind replay.
7. **Restart drill:** interrupt around Executor execution; startup reconciliation must prove state or pause with uncertain reservation.
8. **Create lifecycle:** CODEX-prefixed PAUSED campaign, verify lineage, enable only in a later authorized cycle.
9. **Emergency Stop:** trigger while Executor prepares work; any not-yet-submitted next mutation must be denied at final Hook boundary.
10. **Contract drift:** record authenticated live MCP tool/schema set used by the accepted host.
11. **Scheduling/reboot:** prove configured schedule switches, local timezone, user linger and overlapping timer serialization on the actual VPS.
12. Run several clean autonomous cycles and inspect the first complete attribution window before materially widening Owner monetary authority.

## F. Release identity / provenance

A source release is sealed only when:

- final `main` SHA passes the complete archive gate, including virtual acceptance, history privacy checks and compatibility-sensitive current-Codex gates;
- package/runtime/plugin/changelog/release notes identify the same version;
- the version tag points exactly at that green main SHA and the release workflow refuses to reuse that version for another SHA;
- release wheel and source archive each pass a two-build byte-identity check before publication;
- GitHub Release artifacts and `RELEASE_IDENTITY.json` identify the same SHA and reproducibility epoch;
- SHA-256 manifest covers wheel, source archive and release identity;
- v0.5.2+ checksummed subjects receive GitHub Artifact Attestations / Sigstore provenance;
- scheduled release-integrity verification re-downloads assets, validates checksums, checks `RELEASE_IDENTITY.commit == tag SHA`, and verifies applicable attestations;
- certified Amazon contract commit, Codex compatibility contract and archive-tooling hash are inside the tagged/release identity chain;
- temporary hardening branches are removed after merge so the sealed release target returns to `main`-only hygiene.

Repository-level branch protection/rulesets are an account setting outside the source tree. Their absence must not be described as cryptographic immutability; source controls provide exact identity, tamper evidence, provenance and continuous verification.

Only after section E is complete should that **specific Ubuntu + Amazon account deployment** be described as production-accepted.
