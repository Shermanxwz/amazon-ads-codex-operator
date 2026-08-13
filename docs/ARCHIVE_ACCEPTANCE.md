# Archive / production acceptance gates

A source release may be **archive-sealed** while a specific Amazon account deployment remains **live-acceptance pending**. v0.5.x preserves broad AI autonomy inside the Owner envelope; acceptance proves execution, runtime and recovery machinery rather than adding routine human approval.

## A. Source/archive gate

Required before automatic sealing:

- all Python compiles and the complete test suite passes on supported Python CI;
- JSON configs/schemas, Codex plugin manifest and repo marketplace parse;
- package/runtime/plugin release versions agree and matching release notes exist;
- Owner Web assets are packaged in the wheel;
- repository tree contains no runtime Owner/auth files or known credential/token patterns;
- project MCP base config keeps writes gated until sealed Executor release;
- one-use grants, exact MCP tool/arguments, final Owner re-check, fresh pre-write state guard and crash reconciliation remain covered;
- deployed production hook is behavior-tested directly;
- backup/restore preserves SQLite/audit integrity **and** the content-addressed ACTIVE/PREVIOUS Codex runtime identities while clearing stale OAuth/grant/runtime side state;
- Codex Evergreen contract, registry, candidate promotion/rollback and ACTIVE runner binding tests pass;
- production runner records ACTIVE runtime identity/fingerprint evidence;
- Amazon Postman reference remains pinned to an immutable certified upstream commit;
- shell scripts and rendered systemd units validate;
- repo-scoped Codex plugin/skills and single-main-branch/release workflows are present;
- a fresh Ubuntu 24.04 `virtual-full-stack` job passes bootstrap → preflight → Observe → sealed live path → frozen hook → verification → ambiguous/restart recovery → Emergency Stop/process-lock drills inside an isolated Python virtual environment;
- `archive_check.py` exits 0 on the exact main SHA.

`sealed-release` is allowed to create the version tag only after the whole `archive-gate` workflow succeeds for the exact current main SHA, including every Python matrix job and `virtual-full-stack`.

## B. Ubuntu host gate

Required before any live mutation:

- Owner Home/signing key permissions are private;
- frozen hook hash matches the vetted source;
- dedicated `CODEX_HOME` has hooks enabled and Amazon Ads MCP configured;
- `python3 scripts/codex_runtime.py status` shows an Owner-private ACTIVE slot with valid SHA-256 integrity;
- `scripts/check_codex_runtime.py` and `preflight.py` accept the ACTIVE runtime;
- changing/updating PATH Codex does not change ACTIVE identity;
- a compatible candidate can be registered, promoted and rolled back while Owner policy remains unchanged;
- Owner audit chain/runtime SQLite integrity pass;
- backup and restore drill restores ACTIVE/PREVIOUS runtime identity and returns Owner mode to Observe without carrying stale OAuth or grant state;
- reboot recovery leaves timers/Web healthy and does not replay consumed actions.

## C. Codex update acceptance drill

For a new Codex candidate on a production host:

1. Capture ACTIVE identity with `python3 scripts/codex_runtime.py status`.
2. Install/update system Codex and confirm ACTIVE identity is unchanged.
3. Register the new binary as candidate and inspect the capability probe.
4. Do not promote if any required stable command/flag or strict-config check fails.
5. If compatible, promote deliberately; run preflight, Observe/dry-run and Amazon MCP read checks.
6. Run at least one controlled cycle with independent verification.
7. Exercise `python3 scripts/codex_runtime.py rollback` once during initial host certification and confirm the previous runtime becomes ACTIVE again.
8. Re-promote only after the rollback drill proves recovery works.

## D. Real Amazon account staged acceptance

Not reproducible in credential-free CI, including the virtual Amazon harness:

1. **Observe:** verify Profile/account/marketplace/currency binding, reporting coverage and authenticated live MCP schemas.
2. **Dry-run:** inspect representative plans and exact MCP tool/argument contracts while AI retains normal planning freedom.
3. **Fresh-state drill:** externally change a harmless test entity between planning/release and confirm stale intent is blocked/replanned.
4. **Micro-live:** low ceiling, one reversible bid/budget mutation; confirm one-use grant, outcome parsing and independent verification.
5. **Ambiguous transport drill:** induce/simulate client-side failure after tool boundary and prove no blind replay.
6. **Restart drill:** interrupt around Executor execution; startup reconciliation must prove state or pause with uncertain reservation.
7. **Create lifecycle:** CODEX-prefixed PAUSED campaign, verify lineage, enable only in a later authorized cycle.
8. **Emergency Stop:** trigger while Executor prepares work; any not-yet-submitted next mutation must be denied at final hook boundary.
9. **Contract drift:** record authenticated live MCP tool/schema set used by the accepted host.
10. Run several clean autonomous cycles and inspect the first complete attribution window before materially widening Owner monetary authority.

## E. Release identity

A source release is sealed only when:

- final `main` SHA passes the complete archive-gate, including full virtual-stack acceptance;
- package/runtime/plugin/changelog/release notes identify the same version;
- immutable tag points exactly at that green main SHA;
- GitHub Release artifacts and `RELEASE_IDENTITY.json` identify the same SHA;
- SHA-256 manifest covers wheel, source archive and release identity;
- certified Amazon contract commit and Codex compatibility contract are inside the tagged tree;
- repository branch list contains only `main`.

Only after section D is complete should that **specific Ubuntu + Amazon account deployment** be described as production-accepted.
