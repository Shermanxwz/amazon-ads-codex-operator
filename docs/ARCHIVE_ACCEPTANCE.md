# Archive / production acceptance gates

A source release may be **archive-ready** while a specific Amazon account deployment is still **live-acceptance pending**. Do not collapse these two states.

## A. Source/archive gate
Required before tagging/releasing source:
- all Python compiles;
- complete test suite passes;
- JSON configs/schemas parse;
- Web static assets are packaged in the wheel;
- no runtime Owner files or known credential/token patterns are present in source;
- project MCP base config keeps writes gated;
- atomic Executor uses one enabled tool + signed exact-input hook grant;
- Owner revision/audit/emergency-stop tests pass;
- shell scripts pass syntax validation;
- systemd calendars and rendered service/timer units validate cleanly;
- Codex machine-readable JSONL event logging is enabled for forensic evidence;
- `archive_check.py` exits 0.

## B. Host deployment gate
Required on the Ubuntu host:
- Owner Home permissions and signing key are private;
- frozen hook source hash matches the vetted project hook;
- dedicated `CODEX_HOME` has hooks enabled and Amazon Ads MCP configured;
- Owner audit chain and runtime SQLite integrity pass;
- repository is mounted/read as code, not used for runtime secrets;
- Web remains loopback-only or is fronted by an explicitly secured TLS proxy.

## C. Real Amazon account staged acceptance
Not reproducible in a credential-free build sandbox and therefore must be completed after OAuth:
1. **Observe only:** verify report/read coverage and Profile/account binding.
2. **Dry-run:** manually review several representative plans and exact MCP tool contracts.
3. **Micro-live:** deliberately low daily ceiling, one reversible bid/budget mutation; confirm tool-result parsing and independent verification.
4. **Create lifecycle:** create one CODEX-prefixed PAUSED campaign, verify lineage, then enable in a separate cycle; confirm it cannot enable before verification.
5. **Emergency-stop test:** trigger stop during a controlled cycle and confirm no subsequent action is released.
6. **Ambiguous-failure drill:** simulate/induce a non-success response in a test account where possible and confirm the reservation remains uncertain and system pauses.
7. Gradually raise standing monetary authority only after several clean cycles.

Only after C is complete should that specific deployment be described as production-accepted.
