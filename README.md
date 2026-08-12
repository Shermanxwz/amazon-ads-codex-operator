# Amazon Ads Codex Operator

A Codex-native **Owner-controlled autonomous Amazon Ads control plane** for Ubuntu, built for long-running unattended Sponsored Products optimization with a hard separation between **AI reasoning freedom** and **Owner authority**.

> Release line: **v0.5.x — Codex Evergreen / archive-sealed native operator.** AI autonomy is not reduced. The new layer prevents future Codex updates from silently replacing the production runtime.

## Core rule

**Codex may decide what to optimize. Codex may not decide how much authority Codex has.**

Inside Owner-defined scope, monetary ceilings and reversible action families, Codex may choose bids, budgets, placements, keywords/targets/negatives, state changes and allowed structural actions without routine human approval. Billing, payment, credentials, account/user administration and permanent deletion remain outside autonomous authority.

## Sealed execution

```text
Owner Web / ownerctl
        │
        ▼
 Owner DB + signed audit chain
        │
        ▼
Planner Codex ──read only──► Amazon Ads MCP
        │
        ▼
Deterministic Policy + spend reservation
        │
        ▼
fresh pre-write state guard
        │
        ▼
HMAC sealed action + one-use grant
        │
        ▼
Atomic Executor Codex
  ├── exact one MCP write tool
  ├── read-only shell sandbox
  └── final PreToolUse Owner re-check + atomic grant consume
        │
        ▼
Amazon mutation
        │
        ▼
Independent Verifier Codex ──► fresh Amazon state
        │
        ├── verified → complete
        └── ambiguous/crash → reconcile, never blind replay
```

## Codex Evergreen

Production no longer runs whichever `codex` happens to be on PATH. It uses an Owner-private ACTIVE runtime:

```text
ADS_OWNER_HOME/codex-runtimes/
├── registry.json
└── slots/<sha256>/codex
```

A new Codex install/update is only a **candidate**. It is fingerprinted, copied to a content-addressed slot, probed against `config/codex-compatibility.json`, and cannot become ACTIVE until explicit promotion. The previous ACTIVE is retained for rollback. Every production Codex invocation verifies the ACTIVE fingerprint and writes `*.runtime.json` evidence beside its normal JSONL events.

This means a Linux package/self-update can change PATH without changing the production Amazon Ads runtime. If a future Codex release removes or changes a required stable capability, the candidate is rejected while the existing ACTIVE runtime continues to be selected.

Commands:

```bash
python3 scripts/codex_runtime.py status
python3 scripts/check_codex_runtime.py
./scripts/install_codex_ubuntu.sh                    # installs/registers candidate only
python3 scripts/codex_runtime.py candidate --binary "$(command -v codex)"
python3 scripts/codex_runtime.py promote <runtime_id>
python3 scripts/codex_runtime.py rollback
```

Bootstrap promotes the installed Codex only when no ACTIVE runtime exists. It never follows later PATH changes automatically. See `docs/CODEX_EVERGREEN.md`.

## Native Codex plugin

The repository includes a repo marketplace and `plugins/amazon-ads-operator`, packaging four Codex skills:

- operator status and health;
- diagnosis and forensic evidence;
- archive/live acceptance;
- autonomous in-envelope operation.

The plugin improves the Codex UX but is **not** a second security boundary or raw write path. Privileged Amazon mutations still flow only through the sealed Controller/Executor chain.

Repo marketplace:

```text
.agents/plugins/marketplace.json
plugins/amazon-ads-operator/.codex-plugin/plugin.json
plugins/amazon-ads-operator/skills/...
```

## Owner control

The authenticated Owner Web controls `Autopilot / Observe / Paused`, Emergency Stop, advertiser/profile/ASIN scope, daily total spend ceiling, campaign/new-campaign budgets, bid/budget/placement expansion, cooldowns, creation counts and autonomy families. Policy/operator revisions are immutable and audited; rollback returns to Observe.

Web binds to `127.0.0.1:8765` by default. Prefer SSH tunneling or an explicitly secured TLS reverse proxy.

## Filesystem isolation

Runtime state and secrets are outside Git:

```text
~/.local/share/amazon-ads-codex-owner/
├── owner.db
├── runtime.db
├── secrets/operator_signing_key
├── codex-home/
├── codex-runtimes/
├── trusted-hooks/
├── grants/
├── runs/
├── backups/
└── codex-workspaces/
```

Production systemd units treat the checkout as code, not writable state. Disposable Codex workspaces use a read-only shell sandbox.

## Install / bind Amazon MCP

```bash
cd amazon-ads-codex-operator
./scripts/install_codex_ubuntu.sh
python3 scripts/bootstrap.py
./scripts/configure_amazon_mcp.sh
python3 scripts/run_web.py
```

The system starts in Observe. Configure the real advertiser/profile, timezone/currency and a deliberate Owner spend ceiling, then run:

```bash
python3 scripts/preflight.py
python3 scripts/archive_check.py
python3 scripts/run_cycle.py daily --dry-run
```

Only after staged live acceptance should the host be switched to Autopilot and timers installed with `./scripts/install_systemd.sh`.

## Update / rollback behavior

A normal Codex update must never be treated as a production promotion. Register and probe the candidate first. After promotion, run preflight plus Observe/dry-run and live read checks. If a host-specific regression appears, `python3 scripts/codex_runtime.py rollback` restores the previous certified runtime without changing Owner policy.

GitHub also runs `.github/workflows/codex-evergreen.yml` daily against the current official Codex to surface capability drift before it reaches a host.

## Repository and release seal

This repository intentionally keeps **one branch: `main`**. `single-main-branch` removes non-main branches after main pushes.

Every main push runs the Python 3.11/3.12 archive gate. A successful exact main SHA is automatically sealed by `sealed-release`: the version tag is created at that green SHA and the release publishes wheel/source artifacts, `RELEASE_IDENTITY.json` and SHA-256 checksums. A version tag cannot silently move to a later commit; changing sealed source requires a version bump.

## Backup / recovery

```bash
python3 scripts/backup_owner.py
python3 scripts/restore_owner.py /path/to/backup --owner-home /path/to/owner-home
```

OAuth stores are deliberately not copied. Restored hosts return to Observe and must re-bind Amazon MCP, pass preflight and dry-run before returning to Autopilot.

## Claim boundary

Source/archive sealing and real-account production acceptance are separate. GitHub CI cannot prove OAuth, live Amazon MCP schemas, real write semantics, Emergency Stop timing or ambiguous network outcomes for a particular account. Follow `docs/ARCHIVE_ACCEPTANCE.md` before calling a specific Ubuntu + Amazon account deployment production-accepted.
