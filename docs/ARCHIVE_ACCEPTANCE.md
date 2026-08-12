# Archive / production acceptance gates

A source release may be **archive-ready** while a specific Amazon account deployment is still **live-acceptance pending**. Do not collapse these two states.

The v0.4 goal is high-autonomy engineering: AI remains free to act inside the Owner envelope. Acceptance proves that the execution machinery cannot duplicate, replay, outrun Owner changes or silently drift—not that a human approves routine actions.

## A. Source/archive gate

Required before tagging/releasing source:

- all Python compiles;
- complete test suite passes;
- supported Python CI matrix passes;
- JSON configs/schemas parse;
- Web static assets are packaged in the wheel;
- package/runtime release versions agree;
- no runtime Owner files or known credential/token patterns are present in source;
- project MCP base config keeps writes gated until the sealed Executor release;
- atomic Executor uses one enabled MCP tool + a signed exact-input grant;
- the actual production hook is behavior-tested, not a duplicate implementation;
- a grant can be consumed exactly once and replay is denied;
- the final hook boundary re-checks Owner mode, Emergency Stop and policy/operator revisions;
- existing-entity mutation path contains a fresh pre-write state guard;
- crash/restart path reconciles consumed/ambiguous actions from fresh Amazon state instead of blind replay;
- Owner revision/audit/emergency-stop tests pass;
- consistent backup/restore round-trip verifies SQLite integrity and signed Owner audit history;
- Codex runtime compatibility contract covers the required non-interactive structured-execution capabilities;
- Amazon Postman contract reference is pinned to an immutable certified upstream commit;
- shell scripts pass syntax validation;
- systemd calendars and rendered service/timer units validate cleanly;
- Codex machine-readable JSONL event logging is enabled for forensic evidence;
- `archive_check.py` exits 0.

## B. Host deployment gate

Required on the Ubuntu host:

- Owner Home permissions and signing key are private;
- frozen hook source hash matches the vetted project hook;
- dedicated `CODEX_HOME` has hooks enabled and Amazon Ads MCP configured;
- `scripts/check_codex_runtime.py` / `preflight.py` accept the installed Codex capabilities;
- Owner audit chain and runtime SQLite integrity pass;
- repository is mounted/read as code, not used for runtime secrets;
- Web remains loopback-only or is fronted by an explicitly secured TLS proxy;
- a real `scripts/backup_owner.py` backup completes and its manifest is retained privately;
- a restore drill to a separate temporary Owner Home passes checksum, SQLite and audit-chain validation;
- reboot recovery leaves timers/Web healthy and does not replay any previously consumed action;
- a deliberately interrupted test action demonstrates the distinction between an unconsumed grant (safe cancel) and consumed/ambiguous grant (fresh reconciliation, never blind retry).

## C. Real Amazon account staged acceptance

Not reproducible in a credential-free build sandbox and therefore must be completed after OAuth:

1. **Observe only:** verify Profile/account/marketplace/currency binding, read/report coverage and live MCP schemas.
2. **Dry-run:** inspect representative plans and exact MCP tool/argument contracts while AI retains normal planning freedom.
3. **Fresh-state drill:** change a harmless test entity externally between planning and release and confirm the stale sealed action is blocked/replanned rather than written over the new state.
4. **Micro-live:** use a deliberately low daily ceiling for one reversible bid/budget mutation; confirm one-use grant consumption, result parsing and independent verification.
5. **Ambiguous transport drill:** after the Amazon tool boundary, induce/simulate a client-side failure where practical; confirm the controller independently re-reads Amazon and does not blindly replay.
6. **Restart drill:** interrupt a controlled cycle around Executor execution and confirm startup reconciliation either proves the intended state or pauses with an uncertain reservation.
7. **Create lifecycle:** create one CODEX-prefixed PAUSED campaign, verify lineage, then enable in a separate cycle; confirm it cannot enable before verification.
8. **Emergency-stop test:** trigger Emergency Stop while a controlled Executor is still preparing work and confirm a not-yet-submitted subsequent mutation is denied at the final hook boundary.
9. **Contract drift check:** record the authenticated live MCP tool/schema set used by the accepted deployment and verify no critical unexpected drift.
10. Run several clean autonomous cycles and review the first complete attribution window before materially widening the Owner monetary envelope.

## D. Release identity

Before calling a source release sealed:

- final `main` commit passes the archive workflow;
- package version, runtime version, changelog and archive status identify the same release;
- immutable Git tag points exactly at that CI-passing commit;
- GitHub Release identifies the same tag/commit and states clearly that source sealing does not itself certify a credentialed Amazon deployment;
- the certified Amazon contract commit and Codex compatibility contract are included in that tagged tree;
- release notes record any remaining live-acceptance items rather than converting them into unsupported claims.

Only after section C is complete should that **specific Ubuntu + Amazon account deployment** be described as production-accepted. Sections A, B and D can establish a reproducible archive-grade source/host package without weakening the AI's in-envelope autonomy.
