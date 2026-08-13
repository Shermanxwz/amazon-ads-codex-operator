# v0.6.1 archive status

Status policy: **GREEN MAIN + OWNER DIRECT OVERRIDE CONTRACT + SP OPTIMIZATION-INTELLIGENCE CONTRACT + 10-SCENARIO FULL VIRTUAL STACK + REPRODUCIBLE BUILD + PROVENANCE AUTO-SEALS / REAL-ACCOUNT LIVE ACCEPTANCE REMAINS HOST-SPECIFIC**

v0.6.1 requires the exact `main` SHA to pass the archive matrix on Ubuntu 24.04 for Python 3.11 and 3.12, the direct-override and optimization architecture/unit contracts, complete-history privacy checks, byte-reproducible artifact checks and the independent Python-3.12 `virtual-full-stack`. Only then may `sealed-release` create `v0.6.1`, create GitHub/Sigstore provenance attestations and publish checksummed release assets.

## Owner Direct Override seal

The authenticated Owner Control Plane can arm a 30-minute, 1-hour, 2-hour or permanent authorization window. The AI cannot arm or extend this window itself. An armed window is a capability only: routine hourly/daily/weekly optimization keeps the normal Owner policy, and unrestricted direct policy is injected only while an explicit natural-language Owner instruction is bound to a `direct` cycle.

Each arm, direct-command start, direct-command finish, clear, expiry and authority-changing event advances the Owner policy revision. Previously issued Executor grants therefore fail the frozen Hook's live revision check. Direct Executor grant expiry is additionally capped to the time-window expiry. Timed windows return to the pre-override mode; permanent authorization remains until Owner action or Emergency Stop.

During a bound direct command the normal autonomy matrix, automation monetary/bid/placement caps, creation quotas, cooldowns, naming/PAUSED-first constraints, managed-ASIN filter, routine confidence thresholds and routine irreversible-ad restrictions are not business limits. Configured advertiser/profile identity, Sponsored Products scope, Emergency Stop, exact sealed MCP binding, fresh pre-write state, one-use grants, independent verification, ambiguity recovery and the signed audit chain remain mandatory. Billing/payment, credentials/OAuth, user management, account administration and account deletion remain outside the capability.

## Sponsored Products optimization-intelligence seal

The v0.6.0 production cycle adds a read-only research/learning plane before the existing Planner and persists normalized Sponsored Products evidence, Owner ASIN economics, portfolio candidates, causal experiments and verified action outcomes. The Planner receives Bayesian evidence-confidence, attribution-tail, short/long trend, temporal-pattern, impression-share/headroom and expected marginal-profit signals.

This plane is explicitly **not an authority tier**. Owner Control remains the only business authority boundary. If optimization observation or telemetry degrades, the normal Planner still retains its configured autonomy and uses fresh Amazon evidence; no human approval or new advertising micro-limit is introduced.

The durable Planner contract requires `learning_snapshot` on every plan, including zero-write cycles. Unit/archive tests seal the presence of persistent learning tables, portfolio-profit reasoning, Sponsored Products-native feature awareness and the production optimization entrypoint.

## Credential-free full-stack seal

The v0.5.1-v0.6.0 trust and supply-chain controls remain intact: Owner/action and Executor-grant signing domains are separated; one-use grants are atomic; the frozen Hook re-checks live Owner authority; fresh pre-write state blocks stale intent; crash/transport ambiguity is reconciled without blind replay; ACTIVE/PREVIOUS Codex runtimes are content-addressed and recoverable; Owner signing identity is file-canonical; the archive scans complete Git history; Actions/tooling are pinned; wheel/source builds are double-built byte-identically; releases receive checksum identity and GitHub/Sigstore provenance.

The credential-free full-stack gate retains **ten** production scenarios:

1. fresh bootstrap + preflight;
2. Observe no-write;
3. complete sealed write + independent verification;
4. Codex candidate promotion + rollback;
5. backup/restore preserving ACTIVE runtime and clearing stale auth/grants;
6. after-write transport ambiguity reconciled without replay;
7. after-consume/pre-write crash retained as uncertainty and never replayed;
8. final-boundary Emergency Stop + Linux `flock` overlap rejection;
9. real `scripts/run_web.py` loopback HTTP path: UI/readiness, login, CSRF, policy revision, rollback, Autopilot, Owner Direct Override surface compatibility and Emergency Stop;
10. real `scripts/install_systemd.sh` rendering path in an isolated HOME, with all templates resolved and rendered units passing `systemd-analyze verify`.

`ADS_SYSTEMD_RENDER_ONLY=1` exists only to exercise the exact production render path without changing the certification host's user services. Normal production systemd installation is unchanged.

## Repository / release boundary

The repository intentionally retains only `main`. Source controls provide exact tag/commit identity, reproducible artifacts, Sigstore/GitHub provenance and continuous release-integrity verification.

## Claim boundary

The source can seal the Owner Direct Override lifecycle, revocation/invalidation mechanics, optimization architecture, deterministic statistics, prompt/schema contracts and credential-free production path. It still cannot prove the realized advertising lift or Amazon-side acceptance of a particular exceptional command without a live account, nor can it prove a particular OAuth session, authenticated MCP schema, Amazon-side throttling/timing or real-money mutation semantics. Those remain account/host-specific acceptance items.
