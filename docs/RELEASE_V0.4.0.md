# Amazon Ads Codex Operator v0.4.0

## Release class

**Archive-grade source / crash-safe sealed execution.**

This release preserves full-managed AI autonomy inside the Owner-defined Sponsored Products scope and monetary envelope. It does not introduce routine per-action human approval.

## Engineering hardening

- single-use Executor capability grants with an atomic replay barrier;
- final PreToolUse re-check of Owner mode, Emergency Stop and policy/operator revisions;
- fresh pre-write state validation for existing entities;
- crash/restart reconciliation with no blind replay after a possibly submitted Amazon mutation;
- independent live Amazon state as the final evidence for ambiguous transport results;
- production hook is the directly tested implementation;
- Codex runtime capability contract and host preflight gate;
- immutable certified Amazon Postman reference plus upstream drift detection;
- consistent checksum-manifested Owner/runtime backup and verified restore path;
- reproducible pinned GitHub Actions/tooling and Python 3.11/3.12 archive matrix.

## Autonomy contract

Codex remains free to choose allowed optimization actions inside the standing Owner envelope. The deterministic controller owns the envelope and execution correctness; it does not micromanage strategy.

## Deployment acceptance

This source release being sealed does **not** certify a specific Amazon Ads account or Ubuntu host. Each production deployment must complete `docs/ARCHIVE_ACCEPTANCE.md`, including OAuth/live MCP binding, fresh-state drill, reversible micro-live mutation, crash/restart reconciliation drill, PAUSED-create/verify/enable lifecycle and Emergency Stop drill.

## Certified external contract

The tagged source contains `vendor/amazon-postman/CERTIFIED_UPSTREAM.json`, which identifies the immutable Amazon public Postman commit certified for this release line.

## Recovery

Use `scripts/backup_owner.py` for consistent private runtime backups and `scripts/restore_owner.py` for checksum/audit/integrity-verified host recovery. OAuth auth stores are not included and must be re-established on a recovered host.
