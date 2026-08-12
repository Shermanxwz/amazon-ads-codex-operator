# Amazon Ads Codex Operator

A Codex-native **Owner-controlled autonomous Amazon Ads control plane** for Ubuntu. This project is designed for long-running, unattended Sponsored Products operations with a hard separation between **AI reasoning authority** and **Owner monetary/operational authority**.

> Release line: **v0.3.x — Owner Control / sealed execution architecture**. The source tree is designed for archive-grade handoff, but no deployment should be called production-accepted until the real Amazon Ads account has completed the staged live acceptance checklist in `docs/ARCHIVE_ACCEPTANCE.md`.

## The core rule

**Codex may decide what to optimize. Codex may not decide how much authority Codex has.**

The Owner Web/Owner DB defines the standing envelope. The model cannot write that database, the signing key, the production Codex config, or runtime ledger. Each live mutation is released one at a time only after deterministic policy checks and then is independently verified from Amazon.

```text
Owner Web / ownerctl
        │
        ▼
 Owner DB + signed audit chain         Git checkout (read-only in production)
        │                                      │
        ├── policy/operator revisions           ├── prompts / schemas / code
        ├── mode / emergency stop               └── no runtime secrets
        └── monetary envelope
                    │
                    ▼
Planner Codex ──read only──► Amazon Ads MCP
        │
        ▼
structured plan (exact tool_name + exact arguments)
        │
        ▼
Deterministic Python Policy Engine
        │
        ├── spend reservation ledger
        ├── cooldown / creation / budget caps
        ├── permanent operation blocks
        └── HMAC sealed action
                    │
                    ▼
             one-action grant
                    │
                    ▼
Atomic Executor Codex
  ├── only one MCP tool enabled
  ├── read-only shell sandbox
  └── PreToolUse hook requires exact signed arguments
                    │
                    ▼
              Amazon mutation
                    │
                    ▼
Verifier Codex ──read only──► fresh Amazon state
                    │
                    ▼
             verified / fail closed
```

## What the Owner Web controls

The Web UI is not a cosmetic dashboard. It is the highest operational authority layer. It controls:

- `Autopilot / Observe / Paused`
- emergency stop
- daily total ad-spend ceiling
- per-campaign budget ceiling
- daily new-campaign budget pool and creation count
- bid/budget/profile expansion caps and cooldown
- campaign/ad group/ad/keyword/target/negative/state/budget/bid/placement autonomy switches
- advertiser/profile scope, managed ASINs, timezone and objectives
- signed Owner audit chain and runtime integrity
- immutable Policy/Operator revisions with rollback; rollback always returns to Observe
- Owner password rotation

The Web service binds to `127.0.0.1:8765` by default. Prefer an SSH tunnel for remote access. If you put it behind a reverse proxy, use TLS and set `ADS_WEB_PUBLIC_ORIGIN` to the exact HTTPS origin.

## Hard boundaries

The controller permanently blocks billing, payment, credential management, account/user administration and permanent deletion. These blocks exist in code in addition to policy data. The default production-certified ad-product scope in v0.3 is **Sponsored Products**; SB/SD are intentionally not owner-enableable until their live MCP tool contracts receive the same acceptance tests.

Spend-increasing actions require fresh same-day spend evidence and reserve headroom before execution. Unknown/partial write outcomes keep the reservation uncertain instead of releasing it. New autonomous campaigns must be created PAUSED, verified, and only enabled in a later authorized cycle.

## Filesystem isolation

Production runtime data is outside the Git checkout:

```text
~/.local/share/amazon-ads-codex-owner/
├── owner.db                 # Owner authority + revision/audit chain
├── runtime.db               # cycle/action/reservation/verification state
├── secrets/operator_signing_key
├── codex-home/              # dedicated OAuth/MCP config
├── trusted-hooks/           # frozen vetted PreToolUse hook
├── grants/                  # short-lived one-action signed grants
├── runs/                    # forensic cycle artifacts + Codex JSONL event streams
└── codex-workspaces/        # disposable model workspaces
```

`systemd` mounts the Git checkout read-only and grants writes only to this Owner runtime tree. Each Codex invocation gets a disposable workspace and a shell sandbox of `read-only`.

## Ubuntu installation

```bash
cd amazon-ads-codex-operator
./scripts/install_codex_ubuntu.sh
python3 scripts/bootstrap.py
./scripts/configure_amazon_mcp.sh
python3 scripts/run_web.py
# Open http://127.0.0.1:8765
```

The system starts in **Observe**. In Web, configure the real advertiser/profile, correct timezone/currency and a deliberate `owner_daily_spend_ceiling`.

Then run:

```bash
python3 scripts/preflight.py
python3 scripts/archive_check.py
python3 scripts/run_cycle.py daily --dry-run
```

Inspect the run artifacts under the Owner runtime directory. Each Codex invocation also preserves its `*.events.jsonl` machine-readable event stream (plus stderr when present) for forensic reconstruction; those logs are evidence, not authorization. Only after staged acceptance should you switch Web mode to **Autopilot**.

## Emergency controls

Web: **紧急停止全部写操作**.

If Web is unavailable, use the trusted local CLI:

```bash
python3 scripts/ownerctl.py emergency-stop
python3 scripts/ownerctl.py status
python3 scripts/ownerctl.py verify-audit
```

An emergency stop prevents the next mutation from being released. A mutation already inside Amazon's request path cannot be un-sent; the architecture limits this blast radius by releasing only **one mutation per Executor run**, then verifying before another mutation.

## Scheduling

After live acceptance:

```bash
./scripts/install_systemd.sh
```

This installs user-level Owner Web plus hourly/daily/weekly timers. The daily/weekly timer templates are rendered using the Owner-configured account timezone.

## Amazon Postman reference

`./scripts/sync_amazon_postman.sh` sparsely syncs Amazon's official `ads-advanced-tools-docs/postman` folder and builds a local endpoint index. MCP is the primary runtime channel; Postman serves as an API contract/reference and future deterministic fallback surface.

## Development and archive gate

```bash
python3 -m pytest -q
python3 scripts/archive_check.py
```

See `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/THREAT_MODEL.md`, `docs/RUNBOOK.md`, and `docs/ARCHIVE_ACCEPTANCE.md` before enabling a real account.
