# Amazon Ads Codex Operator

Codex-native autonomous Amazon Ads control plane for Ubuntu. The project is designed for **full-managed operation**, not recommendation-only assistance.

## Autonomy model

The previous scaffold treated Codex writes as exceptional. This version flips that model:

- **Codex has broad operational authority** through the official Amazon Ads MCP server.
- **The deterministic controller is the authorization boundary**. Human approval is not required for in-envelope actions.
- Bid, budget, placement, keyword/target, negatives, campaign/ad-group/ad creation, pause, enable and restructuring can be autonomous.
- New campaigns are created **PAUSED**, independently verified, then enabled by a later released action.
- Every released action is bound to the exact plan, policy and operator config using an HMAC sealed envelope. The signing key is never passed to Codex.
- Spend-increasing actions reserve capacity in a SQLite daily budget ledger before execution.
- Every write is followed by an independent Amazon read; tool output alone is not treated as proof of success.
- Billing, account administration, credentials, user management and permanent delete remain permanently blocked.

This deliberately mirrors the strongest ideas from the archived Hermes control plane—closed-loop execution, standing authorization, budget reservation, exact-payload sealing, outcome parsing and independent verification—while making Codex CLI + Amazon Ads MCP the native runtime.

## Control loop

```text
systemd timer
  -> Planner Codex (live Amazon reads)
  -> structured plan.json
  -> deterministic policy engine
  -> daily spend reservation ledger
  -> HMAC sealed exact actions
  -> Executor Codex (Amazon Ads MCP writes, no interactive approval)
  -> structured receipt
  -> independent Verifier Codex (fresh Amazon reads)
  -> SQLite outcome/history
  -> next cycle learns from recent state
```

## Ubuntu setup

```bash
./scripts/install_codex_ubuntu.sh
codex                         # sign in, then exit
./scripts/configure_amazon_mcp.sh
python3 scripts/bootstrap.py
```

Edit `config/operator.local.json` and `config/autonomy-policy.local.json`. The most important owner boundary is:

```json
"owner_daily_spend_ceiling": 500.0
```

Until that is set, the system can still plan and make spend-reducing/non-spend-increasing changes, but it will reject autonomous spend increases.

Then:

```bash
python3 scripts/preflight.py
python3 scripts/run_cycle.py daily --dry-run
python3 scripts/run_cycle.py daily
./scripts/install_systemd.sh
```

## Three autonomous cadences

- **Hourly:** pacing, anomaly response, conservative bid/budget adjustments.
- **Daily:** full portfolio optimization, search-term harvesting, negatives, target/keyword changes, budget reallocation.
- **Weekly:** structural changes, new campaigns/ad groups/targets and broader strategy.

Timers are examples. Adjust them for the account timezone before enabling.

## Secrets

Never commit Amazon credentials, Codex `auth.json`, cookies, refresh/access tokens or account-specific runtime secrets. The project stores the controller signing key under `.secrets/`, which is gitignored and chmod 600. Codex is spawned with that key removed from its environment.

## Amazon Postman contract

`./scripts/sync_amazon_postman.sh` sparsely clones Amazon's official `ads-advanced-tools-docs/postman` folder and builds a local endpoint index. MCP remains the primary runtime interface; Postman is a contract/reference and future deterministic fallback surface.

## Current scope

The default standing authorization is Sponsored Products. Expand `allowed_ad_products` only after validating MCP tool coverage, schemas and policy tests for the additional ad product.
