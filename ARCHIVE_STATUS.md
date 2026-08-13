# v0.5.2 archive status

Status policy: **GREEN MAIN + FULL VIRTUAL STACK + REPRODUCIBLE BUILD + PROVENANCE AUTO-SEALS / REAL-ACCOUNT LIVE ACCEPTANCE REMAINS HOST-SPECIFIC**

v0.5.2 requires the exact `main` SHA to pass the archive matrix on Ubuntu 24.04 for Python 3.11 and 3.12, the independent Python-3.12 `virtual-full-stack`, complete-history privacy checks and byte-reproducible artifact checks. Only then may `sealed-release` create `v0.5.2` at that SHA, create GitHub/Sigstore provenance attestations and publish checksummed release assets.

## Execution / recovery seal

The v0.5.1 trust boundary remains intact: Owner/action master signing and hook-visible Executor-grant signing are domain-separated; one-use grants are atomically consumed; final-boundary Owner mode/Emergency Stop/revision checks remain in the frozen Hook; fresh pre-write state blocks stale intent; ambiguous or crash-surviving writes are reconciled from fresh external state and are never blindly replayed; ACTIVE/PREVIOUS Codex runtimes are content-addressed, fingerprinted, backed up and restored.

The production master signing identity is now canonical to `ADS_OWNER_HOME/secrets/operator_signing_key`. Ambient process environment cannot override that identity, preventing runtime signatures from diverging from the key archived by backup/restore.

## Full virtual-stack seal

The credential-free virtual acceptance continues to drive the real Controller, RuntimePaths, OwnerStore, SQLite ledger/state, Codex Evergreen registry, frozen PreToolUse Hook, one-use grants, runner isolation, verifier, recovery and Linux `flock`. Its eight required scenarios are:

- fresh bootstrap + preflight;
- Observe with no write;
- sealed live happy path;
- Evergreen candidate promotion + rollback;
- backup/restore preserving ACTIVE runtime identity;
- successful write followed by ambiguous transport, recovered without replay;
- grant consumed before write, then restart/uncertainty with no replay;
- final-boundary Emergency Stop plus concurrent-cycle `flock` rejection.

## Reproducibility / supply-chain seal

- certified Python range is exactly 3.11/3.12;
- Ubuntu 24.04 full-stack and sealed release use Python 3.12;
- build/test tooling and pytest transitives are exactly pinned in `config/archive-tooling.txt`;
- GitHub Actions use Node-24-era checkout/setup-python releases pinned to immutable commit SHAs;
- checkout uses complete history for the archive privacy gate;
- current tree **and full Git history** are scanned for forbidden Owner/auth/key/database filenames and known credential/token patterns;
- wheel builds use commit-derived `SOURCE_DATE_EPOCH` and must be byte-identical across two independent build directories;
- release source archives are also built twice and must be byte-identical;
- `RELEASE_IDENTITY.json` records commit, contract/tooling hashes, reproducibility mode and source-date epoch.

## Provenance / post-release integrity seal

v0.5.2 release subjects are attested with GitHub Artifact Attestations backed by Sigstore. A scheduled `sealed-release-integrity` job re-downloads every published sealed release, checks `SHA256SUMS`, verifies `RELEASE_IDENTITY` against the Git tag, and requires GitHub attestation verification for v0.5.2 and later.

The repository still intentionally retains only one branch, `main`. Repository-level branch protection/rulesets are a GitHub account setting rather than a source-tree control; the connected GitHub tool available to this project does not expose a write operation for that setting. The source therefore provides tamper evidence, exact release identity and continuous verification, but does not claim that a repository administrator is cryptographically unable to rewrite Git refs.

## Claim boundary

This is the strongest truthful **source/archive + complete credential-free virtual-production seal** the repository can provide. It still cannot prove a particular Amazon advertiser/profile, OAuth session, the current authenticated Amazon MCP schema, Amazon-side throttling/timing or real-money mutation semantics. Those checks remain mandatory per `docs/ARCHIVE_ACCEPTANCE.md` before a specific Ubuntu host + Amazon account is described as production-accepted.
