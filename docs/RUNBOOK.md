# Operations runbook

## Normal startup

1. `python3 scripts/bootstrap.py`
2. `./scripts/configure_amazon_mcp.sh`
3. `python3 scripts/run_web.py`
4. Configure Owner account/profile/timezone/ceiling while mode remains Observe.
5. `python3 scripts/preflight.py`
6. `python3 scripts/archive_check.py`
7. Run `python3 scripts/virtual_acceptance.py --report virtual-acceptance-report.json` when certifying a host/source checkout.
8. Run a daily dry-run and inspect Owner run artifacts.
9. Complete staged live acceptance before choosing Autopilot.

`preflight.py` validates the Owner-pinned ACTIVE Codex runtime capabilities/fingerprint, production hook/config deployment, domain-separated Executor-grant key, Owner audit chain, SQLite integrity and Amazon MCP registration.

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

Backup manifest v2 contains:

- consistent `owner.db` / `runtime.db` SQLite snapshots;
- Owner/action master signing key;
- domain-separated Executor-grant key;
- deterministic production Codex config and frozen Hook;
- the Codex runtime registry plus all content-addressed slots referenced by ACTIVE, PREVIOUS and registered candidates;
- SHA-256, size and mode for every archived file.

It intentionally does **not** contain Codex/Amazon OAuth/auth stores. Store backup directories with the same sensitivity as the production Owner Home because signing material is included.

## Host-loss restore

Stop/pause old services first. Restore to a clean Owner Home:

```bash
python3 scripts/restore_owner.py /path/to/backup --owner-home /path/to/new-owner-home
```

For an existing paused/Observe target, `--force` is required. Before reconstitution, restore deliberately removes stale OAuth/auth state, grants, disposable workspaces, run artifacts, old Codex runtime slots/registry, lock files and SQLite sidecars from the target.

After restore:

1. confirm restore reported Owner audit/runtime integrity success;
2. confirm `python3 scripts/codex_runtime.py status` shows the restored ACTIVE identity with valid SHA-256 integrity and PREVIOUS remains available when present in the backup;
3. re-authenticate Codex/Amazon MCP (OAuth is intentionally not restored);
4. run `preflight.py`;
5. run `python3 scripts/virtual_acceptance.py --report virtual-acceptance-report.json` for host/control-plane mechanics when appropriate;
6. run an Observe/dry-run cycle against the real account;
7. confirm live Profile/account binding and fresh Amazon state;
8. only then switch back to Autopilot.

Restore intentionally leaves the Owner mode in Observe. This is a host-rebinding step, not a reduction of the standing business autonomy model.

## Codex update / rollback

1. Record current identity with `python3 scripts/codex_runtime.py status`.
2. Install/update system Codex; production ACTIVE must remain unchanged.
3. Register/probe the new candidate.
4. Do not promote if any required capability fails.
5. Promote explicitly, then run preflight + Observe/dry-run + live read checks.
6. Exercise `python3 scripts/codex_runtime.py rollback` during host certification and verify PREVIOUS becomes ACTIVE.
7. Re-promote only after the rollback drill is proven.

## Owner policy rollback

Use the Web revision section or the revision restore API. Restore creates a *new* revision and audit entry, preserving history, and forces mode to Observe.

## Git/code upgrade

1. Emergency stop or Pause.
2. Create a verified runtime backup.
3. Pull/review the new code/tag.
4. Run tests, `archive_check.py`, and virtual full-stack acceptance.
5. Run `bootstrap.py` again to deploy the newly vetted frozen PreToolUse hook and verify/derive the grant-only key.
6. Run `preflight.py`; this must pass the ACTIVE Codex capability contract.
7. Run an Observe dry-run against the real account.
8. Only then re-enable Autopilot.

Never silently advance `vendor/amazon-postman/CERTIFIED_UPSTREAM.json`. Upstream drift is a review signal; accepting a new contract pin belongs in a new tested release.
