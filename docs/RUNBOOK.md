# Operations runbook

## Normal startup
1. `python3 scripts/bootstrap.py`
2. `./scripts/configure_amazon_mcp.sh`
3. `python3 scripts/run_web.py`
4. Configure Owner account/profile/timezone/ceiling while mode remains Observe.
5. `python3 scripts/preflight.py`
6. `python3 scripts/archive_check.py`
7. Run daily dry-run and inspect Owner run artifacts.
8. Complete staged live acceptance before choosing Autopilot.

## Emergency stop
Preferred: Owner Web → **紧急停止全部写操作**.

Fallback:
```bash
python3 scripts/ownerctl.py emergency-stop
```

Do not clear Emergency Stop merely to make a failed timer green. Investigate the last run and any uncertain reservations first. `emergency-clear` deliberately returns mode to Observe.

## Unknown/partial write
1. Keep system Paused.
2. Inspect `execution-summary.json` in the corresponding Owner run directory.
3. Confirm the affected entity directly from Amazon.
4. Do not manually release/alter SQLite reservation rows.
5. Resolve platform state and only then return to Observe for another validation cycle.

## Owner policy rollback
Use the Web revision section or the revision restore API. Restore creates a *new* revision and audit entry, preserving history, and forces mode to Observe.

## Git/code upgrade
1. Emergency stop or Pause.
2. Pull/review the new code.
3. Run tests and `archive_check.py`.
4. Run `bootstrap.py` again to deploy the newly vetted frozen PreToolUse hook into Owner Home.
5. Run `preflight.py` and Observe dry-run.
6. Only then re-enable Autopilot.
