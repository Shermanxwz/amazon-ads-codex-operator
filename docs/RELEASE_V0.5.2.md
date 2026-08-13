# Amazon Ads Codex Operator v0.5.2

**Long-term reproducibility / provenance maintenance seal.**

v0.5.2 leaves the v0.5.1 control plane, Owner authority model and in-envelope AI autonomy unchanged. It closes the remaining source/archive drift paths that appeared only after a second reverse audit of the already-green v0.5.1 release:

- production signing identity is canonical to the Owner-owned key file; an ambient `ADS_OPERATOR_SIGNING_KEY` can no longer make runtime signatures diverge from the key preserved by disaster recovery;
- certified Python support is explicitly bounded to 3.11/3.12, and both Ubuntu 24.04 full-stack acceptance and sealed release run on Python 3.12;
- GitHub Actions move to Node-24-era `actions/checkout` v7.0.1 and `actions/setup-python` v7.0.0, pinned by exact commit SHA;
- archive/test/build tooling, including pytest transitive dependencies, is fully version-pinned in `config/archive-tooling.txt`;
- PEP 517 setuptools is exactly pinned to the same certified toolchain;
- the archive gate checks complete Git history for forbidden runtime/auth filenames and credential/token patterns, not only the current tree;
- the virtual acceptance and release jobs set `SOURCE_DATE_EPOCH` from the sealed commit and double-build artifacts, requiring byte-identical wheels; release also double-builds the source archive and requires byte identity;
- `RELEASE_IDENTITY.json` records the archive-tooling hash, reproducibility claim and source-date epoch;
- sealed release subjects are signed through GitHub Artifact Attestations / Sigstore using exact-SHA `actions/attest` v4.2.2;
- a scheduled `sealed-release-integrity` workflow re-downloads releases, verifies `SHA256SUMS`, confirms `RELEASE_IDENTITY.commit == tag SHA`, and requires GitHub attestation verification for v0.5.2+;
- local virtual-acceptance build artifacts are ignored so certification does not dirty the checkout.

This is a reproducibility and tamper-evidence seal, not an expansion or reduction of Amazon Ads authority. Real-account OAuth, authenticated live MCP schema binding and controlled real-money acceptance remain host/account-specific and cannot be truthfully replaced by a credential-free virtual environment.
