# v0.5.3 archive status

Status policy: **GREEN MAIN + 10-SCENARIO FULL VIRTUAL STACK + REPRODUCIBLE BUILD + PROVENANCE AUTO-SEALS / REAL-ACCOUNT LIVE ACCEPTANCE REMAINS HOST-SPECIFIC**

v0.5.3 requires the exact `main` SHA to pass the archive matrix on Ubuntu 24.04 for Python 3.11 and 3.12, complete-history privacy checks, byte-reproducible artifact checks and the independent Python-3.12 `virtual-full-stack`. Only then may `sealed-release` create `v0.5.3`, create GitHub/Sigstore provenance attestations and publish checksummed release assets.

## Credential-free full-stack seal

The v0.5.1/v0.5.2 trust and supply-chain controls remain intact: Owner/action and Executor-grant signing domains are separated; one-use grants are atomic; the frozen Hook re-checks live Owner authority; fresh pre-write state blocks stale intent; crash/transport ambiguity is reconciled without blind replay; ACTIVE/PREVIOUS Codex runtimes are content-addressed and recoverable; Owner signing identity is file-canonical; the archive scans complete Git history; Actions/tooling are pinned; wheel/source builds are double-built byte-identically; releases receive checksum identity and GitHub/Sigstore provenance.

The full-stack gate now requires **ten** production scenarios:

1. fresh bootstrap + preflight;
2. Observe no-write;
3. complete sealed write + independent verification;
4. Codex candidate promotion + rollback;
5. backup/restore preserving ACTIVE runtime and clearing stale auth/grants;
6. after-write transport ambiguity reconciled without replay;
7. after-consume/pre-write crash retained as uncertainty and never replayed;
8. final-boundary Emergency Stop + Linux `flock` overlap rejection;
9. real `scripts/run_web.py` loopback HTTP path: UI/readiness, login, CSRF, policy revision, rollback, Autopilot and Emergency Stop;
10. real `scripts/install_systemd.sh` rendering path in an isolated HOME, with all templates resolved and rendered units passing `systemd-analyze verify`.

`ADS_SYSTEMD_RENDER_ONLY=1` exists only to exercise the exact production render path without changing the certification host's user services. Normal production systemd installation is unchanged.

## Repository / release boundary

The repository intentionally retains only `main`. The current GitHub connector does not expose branch-protection/ruleset writes, and repository API status must not be misrepresented as cryptographic immutability. Source controls instead provide exact tag/commit identity, reproducible artifacts, Sigstore/GitHub provenance and continuous release-integrity verification.

## Claim boundary

This is the strongest truthful **source/archive + complete credential-free virtual-production seal** the repository can provide. It cannot prove a particular Amazon advertiser/profile, OAuth session, current authenticated Amazon MCP schema, Amazon-side throttling/timing or real-money mutation semantics. Those remain mandatory host/account-specific acceptance items in `docs/ARCHIVE_ACCEPTANCE.md` before a deployment is called production-accepted.
