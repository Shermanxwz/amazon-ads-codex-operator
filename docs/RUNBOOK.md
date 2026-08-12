# Runbook

## Before live mode
1. Set account/profile IDs in `operator.local.json`.
2. Set the correct account timezone and currency.
3. Set `owner_daily_spend_ceiling` in the local policy.
4. OAuth-login to `amazon_ads` MCP.
5. Run `scripts/preflight.py`.
6. Run at least one `daily --dry-run` and inspect `state/runs/<cycle>/plan.json` and `sealed-actions.json`.

## Emergency stop
Set `recovery.kill_switch` to `true` in `config/autonomy-policy.local.json`. The policy engine will reject every action.

## Exception handling
A cycle exits non-zero when policy blocks, execution is ambiguous, or verification fails. systemd records the failure. Investigate the corresponding run directory before clearing the exception.

## Repository visibility
The GitHub repo should be Private before any real account-specific configuration is ever pushed.
