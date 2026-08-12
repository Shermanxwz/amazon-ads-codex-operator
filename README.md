# Amazon Ads Codex Operator

A Codex-native **Owner-controlled autonomous Amazon Ads control plane** for Ubuntu. It is designed for long-running, unattended Sponsored Products operations with a hard separation between **AI reasoning authority** and **Owner monetary/operational authority**.

> Release line: **v0.4.x — archive-hardening / crash-safe sealed execution**. The design intentionally preserves broad AI freedom inside the Owner-defined envelope. v0.4 hardens replay, stale-state, crash/restart, runtime compatibility, contract reproducibility and disaster recovery; it does **not** turn the system into recommendation-only or per-action human approval.

A source release may be archive-ready while a particular Amazon account is still live-acceptance pending. No deployment should be called production-accepted until that real account has completed `docs/ARCHIVE_ACCEPTANCE.md`.

## The core rule

**Codex may decide what to optimize. Codex may not decide how much authority Codex has.**

The Owner Web/Owner DB defines standing limits. Inside those limits, Codex may choose bids, budgets, placements, keywords/targets/negatives, state changes and allowed structural actions without routine human approval. The model cannot expand its own scope, monetary ceiling or permanent safety boundary.

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
          fresh pre-write state check
                    │
                    ▼
        signed one-use action grant
                    │
                    ▼
Atomic Executor Codex
  ├── only one MCP tool enabled
  ├── read-only shell sandbox
  └── PreToolUse re-checks Owner authority,
      validates exact signed arguments and
      atomically consumes the grant once
                    │
                    ▼
              Amazon mutation
                    │
                    ▼
Verifier Codex ──read only──► fresh Amazon state
        │
        ├── verified → durable completion
        └── ambiguous/crash → fresh reconciliation, never blind replay
```

## What the Owner Web controls

The Web UI is the highest operational authority layer. It controls:

- `Autopilot / Observe / Paused`
- emergency stop
- daily total ad-spend ceiling
- per-campaign budget ceiling
- daily new-campaign budget pool and creation count
- bid/budget/profile expansion caps and cooldown
- campaign/ad group/ad/keyword/target/negative/state/budget/bid/placement autonomy switches
- advertiser/profile scope, managed ASINs, timezone and objectives
- signed Owner audit chain and runtime integrity
- immutable Policy/Operator revisions with rollback; rollback returns to Observe
- Owner password rotation

The Web service binds to `127.0.0.1:8765` by default. Prefer an SSH tunnel for remote access. If you put it behind a reverse proxy, use TLS and set `ADS_WEB_PUBLIC_ORIGIN` to the exact HTTPS origin.

## Hard boundaries without micromanaging the AI

The controller permanently blocks billing, payment, credential management, account/user administration and permanent deletion. The production-certified autonomous ad-product scope remains **Sponsored Products** until other product contracts receive equivalent live acceptance.

Within the Owner envelope, the AI remains autonomous. Engineering guards only prevent unsafe execution mechanics: stale writes, duplicate grant use, blind replay after crashes, authority changes after planning and unverified outcomes.

Spend-increasing actions require fresh same-day spend evidence and reserve headroom before execution. Existing-entity mutations receive a fresh state check immediately before release. New autonomous campaigns must be created PAUSED, verified, and only enabled in a later authorized cycle.

## Replay and crash safety

Every Executor grant is named by the sealed action hash and can cross the `PreToolUse` boundary only once. The hook atomically creates a consumed marker before returning `allow`. At that same final boundary it re-reads Owner mode, Emergency Stop and policy/operator revisions.

If the Executor or host fails:

- an unconsumed grant proves the write was never authorized and can be cancelled safely;
- a consumed/ambiguous grant is **never replayed blindly**;
- the controller independently reads Amazon and accepts the action only if live state proves the sealed `after` state;
- otherwise the reservation remains uncertain and the system pauses for investigation.

## Filesystem isolation

Production runtime data is outside the Git checkout:

```text
~/.local/share/amazon-ads-codex-owner/
├── owner.db                 # Owner authority + revision/audit chain
├── runtime.db               # cycle/action/reservation/verification state
├── secrets/operator_signing_key
├── codex-home/              # dedicated OAuth/MCP config
├── trusted-hooks/           # frozen vetted PreToolUse hook
├── grants/                  # issued/consumed one-use grant evidence
├── runs/                    # forensic cycle artifacts + Codex JSONL events
├── backups/                 # optional verified runtime backups
└── codex-workspaces/        # disposable model workspaces
```

`systemd` mounts the Git checkout read-only and grants writes only to the Owner runtime tree. Each Codex invocation gets a disposable workspace and a shell sandbox of `read-only`.

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

`preflight.py` also checks the installed Codex CLI against `config/codex-compatibility.json`. This is capability-gated rather than trusting a cosmetic version string.

Inspect Owner run artifacts. Each Codex invocation preserves its machine-readable `*.events.jsonl` stream (and stderr when present) for forensic reconstruction. Logs are evidence, not authorization. Only after staged acceptance should you switch Web mode to **Autopilot**.

## Emergency controls

Web: **紧急停止全部写操作**.

Fallback:

```bash
python3 scripts/ownerctl.py emergency-stop
python3 scripts/ownerctl.py status
python3 scripts/ownerctl.py verify-audit
```

The final PreToolUse authorization boundary re-checks Emergency Stop immediately before allowing a mutation. A request already submitted to Amazon cannot be recalled; one-action release plus independent verification bounds that residual risk.

## Scheduling

After live acceptance:

```bash
./scripts/install_systemd.sh
```

This installs user-level Owner Web plus hourly/daily/weekly timers. `scripts/run_cycle.py` uses a Linux `flock` single-instance lock so the three cadences cannot overlap on the same Owner runtime.

## Backup and host recovery

Create a consistent, checksum-manifested backup of Owner/runtime state:

```bash
python3 scripts/backup_owner.py
```

Restore onto a clean host or an explicitly paused/Observe runtime:

```bash
python3 scripts/restore_owner.py /path/to/backup --owner-home /path/to/owner-home
```

OAuth/auth stores are deliberately not copied. A restored host starts in **Observe**; re-authenticate Amazon MCP, run `preflight.py` and a dry-run, then return to Autopilot when the host is re-bound to live Amazon state.

## Amazon contract reference

`vendor/amazon-postman/CERTIFIED_UPSTREAM.json` records the exact Amazon `ads-advanced-tools-docs` commit certified for this release line. `./scripts/sync_amazon_postman.sh` fetches that immutable commit, not whatever happens to be upstream HEAD. A scheduled CI drift check alerts when the upstream Postman contract changes; changing the certified pin requires explicit review.

MCP remains the primary runtime channel. Postman serves as an independent API contract/reference and future deterministic fallback surface.

## Development and archive gate

```bash
python3 -m pytest -q
python3 scripts/archive_check.py
```

See `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/THREAT_MODEL.md`, `docs/RUNBOOK.md`, and `docs/ARCHIVE_ACCEPTANCE.md` before enabling a real account.
