# v0.6.0 archive status

Status policy: **GREEN MAIN + SP OPTIMIZATION-INTELLIGENCE CONTRACT + 10-SCENARIO FULL VIRTUAL STACK + REPRODUCIBLE BUILD + PROVENANCE AUTO-SEALS / REAL-ACCOUNT LIVE ACCEPTANCE REMAINS HOST-SPECIFIC**

v0.6.0 requires the exact `main` SHA to pass the archive matrix on Ubuntu 24.04 for Python 3.11 and 3.12, the optimization architecture/unit contracts, complete-history privacy checks, byte-reproducible artifact checks and the independent Python-3.12 `virtual-full-stack`. Only then may `sealed-release` create `v0.6.0`, create GitHub/Sigstore provenance attestations and publish checksummed release assets.

## Sponsored Products optimization-intelligence seal

The v0.6.0 production cycle adds a read-only research/learning plane before the existing Planner and persists normalized Sponsored Products evidence, Owner ASIN economics, portfolio candidates, causal experiments and verified action outcomes. The Planner receives Bayesian evidence-confidence, attribution-tail, short/long trend, temporal-pattern, impression-share/headroom and expected marginal-profit signals.

This plane is explicitly **not an authority tier**. Owner Control remains the only business authority boundary. If optimization observation or telemetry degrades, the normal Planner still retains its configured autonomy and uses fresh Amazon evidence; no human approval or new advertising micro-limit is introduced.

The durable Planner contract now requires `learning_snapshot` on every plan, including zero-write cycles. Unit/archive tests seal the presence of persistent learning tables, portfolio-profit reasoning, Sponsored Products-native feature awareness and the production `OptimizationController` entrypoint.

## Credential-free full-stack seal

The v0.5.1-v0.5.3 trust and supply-chain controls remain intact: Owner/action and Executor-grant signing domains are separated; one-use grants are atomic; the frozen Hook re-checks live Owner authority; fresh pre-write state blocks stale intent; crash/transport ambiguity is reconciled without blind replay; ACTIVE/PREVIOUS Codex runtimes are content-addressed and recoverable; Owner signing identity is file-canonical; the archive scans complete Git history; Actions/tooling are pinned; wheel/source builds are double-built byte-identically; releases receive checksum identity and GitHub/Sigstore provenance.

The credential-free full-stack gate retains **ten** production scenarios:

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

The repository intentionally retains only `main`. Source controls provide exact tag/commit identity, reproducible artifacts, Sigstore/GitHub provenance and continuous release-integrity verification.

## Claim boundary

The source can seal the optimization architecture, deterministic statistics, prompt/schema contracts and credential-free production path. It still cannot prove the realized advertising lift of a particular account without live historical/live Amazon data, nor can it prove a particular OAuth session, authenticated MCP schema, Amazon-side throttling/timing or real-money mutation semantics. Those remain account/host-specific acceptance items.
