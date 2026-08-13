# Amazon Ads Codex Operator

A Codex-native **Owner-controlled autonomous Amazon Ads control plane** for Ubuntu, built for long-running unattended Sponsored Products optimization with a hard separation between **AI reasoning freedom** and **Owner authority**.

> Release line: **v0.5.x — Codex Evergreen / archive-sealed native operator.** AI autonomy is not reduced. The Evergreen layer prevents future Codex updates from silently replacing the production runtime; v0.5.1 adds full virtual-stack acceptance, grant-key domain separation and complete Codex-runtime disaster recovery.

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
HMAC sealed action + domain-separated one-use grant
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

The Owner/action master signing key is not given to the frozen Hook. Executor v2 grants are signed with a deterministic domain-separated key stored separately under Owner Home, so Hook grant verification cannot forge Owner audit history or ordinary sealed-action signatures.

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
├── secrets/executor_grant_signing_key
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
python3 scripts/virtual_acceptance.py --report virtual-acceptance-report.json
python3 scripts/run_cycle.py daily --dry-run
```

Only after staged live acceptance should the host be switched to Autopilot and timers installed with `./scripts/install_systemd.sh`.

## Full virtual-stack acceptance

The source gate includes a fresh Ubuntu 24.04 `virtual-full-stack` job. It creates an isolated Python virtual environment, builds/installs the wheel, then drives the real Controller, Owner DB, runtime DB, Codex runtime registry, frozen PreToolUse Hook, one-use grants, verifier, recovery logic and Linux process lock against a credential-free virtual Codex/Amazon boundary.

The scenarios cover fresh bootstrap/preflight, Observe no-write behavior, a complete sealed mutation and independent verification, Codex candidate promotion/rollback, backup/restore, transport failure after a write, crash after grant consumption before a write, restart reconciliation, final-boundary Emergency Stop and overlapping-cycle rejection.

This proves the control-plane mechanics without real credentials. It deliberately does **not** claim to prove a particular Amazon profile, authenticated live MCP schema or real-money mutation semantics.

## Update / rollback behavior

A normal Codex update must never be treated as a production promotion. Register and probe the candidate first. After promotion, run preflight plus Observe/dry-run and live read checks. If a host-specific regression appears, `python3 scripts/codex_runtime.py rollback` restores the previous certified runtime without changing Owner policy.

GitHub also runs `.github/workflows/codex-evergreen.yml` daily against the current official Codex to surface capability drift before it reaches a host.

## Repository and release seal

This repository intentionally keeps **one branch: `main`**. `single-main-branch` removes non-main branches after main pushes.

Every main push runs the Python 3.11/3.12 archive gate plus the isolated Ubuntu virtual full-stack gate. A successful exact main SHA is automatically sealed by `sealed-release`: the version tag is created at that green SHA and the release publishes wheel/source artifacts, `RELEASE_IDENTITY.json` and SHA-256 checksums. A version tag cannot silently move to a later commit; changing sealed source requires a version bump.

## Backup / recovery

```bash
python3 scripts/backup_owner.py
python3 scripts/restore_owner.py /path/to/backup --owner-home /path/to/owner-home
```

Backup manifest v2 preserves consistent Owner/runtime SQLite snapshots, both signing domains, deterministic production Codex config/Hook, the Codex runtime registry and all content-addressed runtime slots referenced by ACTIVE/PREVIOUS/candidates. OAuth stores are deliberately not copied.

Restore clears stale OAuth/auth, grant, workspace/run, prior runtime-slot/registry, lock and SQLite-sidecar state before reconstruction; it verifies checksums, runtime fingerprints, SQLite integrity and the signed Owner audit chain. A restored host always starts in Observe and must re-bind Amazon MCP, pass preflight and dry-run before returning to Autopilot.

## Claim boundary

Source/archive sealing and real-account production acceptance are separate. GitHub CI and the virtual Amazon harness cannot prove OAuth, a particular advertiser/profile binding, the current authenticated Amazon MCP schemas, Amazon-side timing/429 behavior or real-money semantics. Follow `docs/ARCHIVE_ACCEPTANCE.md` before calling a specific Ubuntu + Amazon account deployment production-accepted.
