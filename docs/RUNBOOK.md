# Operations runbook

## Normal startup

1. `python3 scripts/bootstrap.py`
2. `./scripts/configure_amazon_mcp.sh`
3. `python3 scripts/run_web.py`
4. Configure Owner account/profile/timezone/ceiling while mode remains Observe.
5. `python3 scripts/preflight.py`
6. `python3 scripts/archive_check.py`
7. Run a daily dry-run and inspect Owner run artifacts.
8. Complete staged live acceptance before choosing Autopilot.

`preflight.py` validates the installed Codex runtime capabilities, production hook/config deployment, Owner audit chain, SQLite integrity and Amazon MCP registration.

## Normal autonomy

Do not add routine approval steps to make the system feel safer. The intended operating model is full-managed autonomy inside the Owner envelope. Change the Owner limits when you want to change authority; otherwise allow Planner → sealed Executor → independent Verifier to operate unattended.

## Emergency stop

Preferred: Owner Web → **紧急停止全部写操作**.

Fallback:

```bash
python3 scripts/ownerctl.py emergency-stop
```

The production PreToolUse hook re-checks Emergency Stop at the final Amazon tool boundary. A request already submitted to Amazon cannot be unsent.

Do not clear Emergency Stop merely to make a failed timer green. Investigate the last run and any uncertain reservations first. `emergency-clear` deliberately returns mode to Observe.

## Stale pre-write state

A `stale_prewrite` result means the entity changed between planning and final release. This is not a permanent policy rejection and normally needs no manual repair.

1. Inspect the fresh-state artifact under the corresponding run directory.
2. Confirm the state change is legitimate.
3. Let the next cycle plan from current Amazon state.
4. Do not force the old sealed action through.

## Unknown/partial write or executor crash

The controller never blindly retries a consumed grant.

1. Keep the system Paused if reconciliation could not prove the result.
2. Inspect `execution-summary.json`, fresh-state/reconciliation artifacts, events and the matching `grants/*.consumed` evidence if retained.
3. Confirm the affected entity directly from Amazon when necessary.
4. Do not manually release/alter SQLite reservation rows to make capacity appear free.
5. If Amazon state exactly matches the sealed intended state, record/repair through code-supported recovery rather than replaying the mutation.
6. If state remains ambiguous, keep the reservation uncertain until the real exposure is understood.

At the start of every new cycle, incomplete `released/executing/success/unknown` actions are reconciled before a new plan is allowed to run.

## Backup

Create a consistent private backup:

```bash
python3 scripts/backup_owner.py
```

The backup contains consistent SQLite snapshots, signing key, production deterministic config/hook files and a SHA-256 manifest. It intentionally does **not** contain Codex/Amazon OAuth auth stores.

Store backup directories with the same sensitivity as the production Owner Home because the signing key is included.

## Host-loss restore

Stop/pause old services first. Restore to a clean Owner Home:

```bash
python3 scripts/restore_owner.py /path/to/backup --owner-home /path/to/new-owner-home
```

For an existing paused/Observe target, `--force` is required.

After restore:

1. confirm restore reported Owner audit/runtime integrity success;
2. re-run `bootstrap.py` if the release deployment requires refreshed deterministic files;
3. re-authenticate Codex/Amazon MCP;
4. run `preflight.py`;
5. run an Observe/dry-run cycle;
6. confirm live Profile/account binding and fresh state;
7. only then switch back to Autopilot.

Restore intentionally leaves the Owner mode in Observe. This is a host-rebinding step, not a reduction of the standing business autonomy model.

## Owner policy rollback

Use the Web revision section or the revision restore API. Restore creates a *new* revision and audit entry, preserving history, and forces mode to Observe.

## Git/code upgrade

1. Emergency stop or Pause.
2. Create a verified runtime backup.
3. Pull/review the new code/tag.
4. Run tests and `archive_check.py`.
5. Run `bootstrap.py` again to deploy the newly vetted frozen PreToolUse hook into Owner Home.
6. Run `preflight.py`; this must pass the Codex capability contract.
7. Run an Observe dry-run.
8. Only then re-enable Autopilot.

Never silently advance `vendor/amazon-postman/CERTIFIED_UPSTREAM.json`. Upstream drift is a review signal; accepting a new contract pin belongs in a new tested release.
