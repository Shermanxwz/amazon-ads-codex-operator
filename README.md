# Amazon Ads Codex Operator

A Codex-native **Owner-controlled autonomous Amazon Ads control plane** for Ubuntu, designed for unattended Sponsored Products optimization while keeping AI reasoning freedom strictly inside Owner-defined authority and money boundaries.

> Release line: **v0.5.x — Codex Evergreen / archive-sealed native operator.** v0.5.3 closes the credential-free end-to-end surface by exercising the real Owner Web entrypoint and production systemd rendering path in addition to the sealed execution/recovery chain.

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

The Owner/action master signing key is file-canonical under Owner Home and is never given to the frozen Hook. Executor v2 grants use a deterministic domain-separated key stored separately; Hook grant verification therefore cannot forge Owner audit history or normal sealed-action signatures.

## Codex Evergreen

Production does not run whichever `codex` happens to be on PATH. It uses an Owner-private, SHA-256-verified ACTIVE runtime:

```text
ADS_OWNER_HOME/codex-runtimes/
├── registry.json
└── slots/<sha256>/codex
```

A new Codex install/update becomes only a **candidate**. It is snapshotted into a content-addressed slot, capability-probed against `config/codex-compatibility.json`, and can become ACTIVE only through explicit promotion. The previous ACTIVE is retained for rollback. Every production Codex invocation re-verifies the ACTIVE fingerprint and records runtime identity evidence.

```bash
python3 scripts/codex_runtime.py status
python3 scripts/check_codex_runtime.py
./scripts/install_codex_ubuntu.sh                    # installs/registers candidate only
python3 scripts/codex_runtime.py candidate --binary "$(command -v codex)"
python3 scripts/codex_runtime.py promote <runtime_id>
python3 scripts/codex_runtime.py rollback
```

## Native Codex plugin

The repo includes `.agents/plugins/marketplace.json` and `plugins/amazon-ads-operator` with status, diagnosis, acceptance and autonomy skills. The plugin is the native Codex operator UX, not a parallel privileged mutation path: Amazon writes still go only through the sealed Controller/Executor chain.

## Owner control

The authenticated Owner Web controls `Autopilot / Observe / Paused`, Emergency Stop, advertiser/profile/ASIN scope, daily spend ceiling, campaign/new-campaign budgets, bid/budget/placement expansion, cooldowns, creation counts and autonomy families. Policy/operator revisions are immutable and audited; revision restore returns to Observe.

Web binds to `127.0.0.1:8765` by default. Prefer SSH tunneling or an explicitly secured TLS reverse proxy.

## Filesystem isolation

Runtime state and secrets live outside Git:

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
make virtual-acceptance
python3 scripts/run_cycle.py daily --dry-run
```

Only after staged live acceptance should the host enter Autopilot and enable timers with `./scripts/install_systemd.sh`.

## Ten-scenario full virtual-stack acceptance

The fresh Ubuntu 24.04 Python-3.12 `virtual-full-stack` gate creates an isolated venv, installs the fully pinned archive toolchain, double-builds the wheel with commit-derived `SOURCE_DATE_EPOCH` and requires byte identity, installs that wheel, then runs two cooperating harnesses.

The control-plane harness proves eight scenarios: fresh bootstrap/preflight; Observe no-write; complete sealed mutation and independent verification; Codex candidate promotion/rollback; backup/restore; after-write transport ambiguity reconciled without replay; consumed-grant/pre-write crash and restart uncertainty with no replay; and final-boundary Emergency Stop plus Linux `flock` overlap rejection.

The production-surface harness adds two more scenarios. It launches the real `scripts/run_web.py` on loopback and exercises static UI/security headers/readiness, unauthenticated denial, password login, CSRF rejection/enforcement, policy revision, revision restore, Autopilot and Emergency Stop. It also runs the real `scripts/install_systemd.sh` rendering path inside an isolated HOME and verifies all rendered units with no unresolved placeholders plus `systemd-analyze verify` when available.

`ADS_SYSTEMD_RENDER_ONLY=1` is a certification-only switch that exits **after** exact production template rendering and **before** any `systemctl` call; normal production installation behavior is unchanged.

This virtual stack substitutes only the external Amazon/Codex network boundary and actual host service activation. The Controller, Owner/runtime databases, policy/ledger, runtime registry, frozen Hook, grants, verifier, recovery logic, Owner Web server and systemd rendering logic are the production implementations.

## Backup / recovery

```bash
python3 scripts/backup_owner.py
python3 scripts/restore_owner.py /path/to/backup --owner-home /path/to/new-owner-home
```

Backup manifest v2 preserves consistent Owner/runtime SQLite snapshots, both signing domains, deterministic production Codex config/Hook, the Codex runtime registry and content-addressed slots referenced by ACTIVE/PREVIOUS/candidates. OAuth stores are intentionally excluded.

Restore clears stale OAuth/auth, grants, workspaces/runs, prior runtime slots/registry, locks and SQLite sidecars before reconstruction; it verifies checksums, runtime fingerprints, SQLite integrity and the Owner audit chain. A restored host returns to Observe and must re-bind Amazon MCP, pass preflight and dry-run before Autopilot.

## Repository / release seal

The repo intentionally retains one branch: `main`. Every main push runs the Python 3.11/3.12 archive matrix, complete-history privacy scan and Python-3.12 ten-scenario virtual full stack. GitHub Actions and archive/build tooling are exact-version/SHA pinned.

A successful exact main SHA is processed by `sealed-release`. Wheel and source archive are each built twice and must be byte-identical. `RELEASE_IDENTITY.json` binds the commit, certified Amazon contract, Codex compatibility contract, archive-tooling hash and reproducibility epoch; `SHA256SUMS` covers published subjects. v0.5.2+ release subjects receive GitHub Artifact Attestations backed by Sigstore, and `sealed-release-integrity` periodically re-downloads releases to verify checksums, tag/identity binding and attestations.

Changed source requires a new version; the release workflow refuses to reuse a sealed version for another SHA. Repository-level branch protection/rulesets remain a GitHub account setting rather than a source-tree control, so the project claims exact identity/tamper evidence/provenance rather than pretending an administrator cannot rewrite refs.

## Claim boundary

Source/archive sealing and real-account production acceptance are separate. Credential-free CI cannot prove a particular advertiser/profile, OAuth session, current authenticated Amazon MCP schemas, Amazon-side timing/429 behavior or real-money mutation semantics. Follow `docs/ARCHIVE_ACCEPTANCE.md` before calling a specific Ubuntu + Amazon account deployment production-accepted.
