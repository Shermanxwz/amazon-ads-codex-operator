# v0.4.0 archive status

Status: **SOURCE ARCHIVE GATE PASSED / REAL-ACCOUNT LIVE ACCEPTANCE PENDING**

The v0.4.0 source candidate has passed the credential-free archive gate on Ubuntu 24.04 in both supported CI runtimes:

- Python 3.11: **41/41 tests passed; 50/50 archive checks passed**.
- Python 3.12: **41/41 tests passed; 50/50 archive checks passed**.
- Python source compiled successfully.
- Package and runtime version agree on `0.4.0`.
- Production hook is tested directly; the duplicate hook implementation was removed.
- One-use Executor grant replay barrier is present and behavior-tested.
- Final PreToolUse boundary re-checks Owner Autopilot mode, Emergency Stop and Policy/Operator revisions.
- Existing-entity execution path includes fresh pre-write state validation.
- Crash/restart reconciliation distinguishes unconsumed actions from consumed/ambiguous actions and never blindly replays the latter.
- Backup/restore round-trip verifies manifest hashes, SQLite integrity and the signed Owner audit chain.
- Codex runtime capability contract and host compatibility checker are included.
- Amazon Postman reference is pinned to an immutable certified upstream commit with a separate contract-drift workflow.
- All shell scripts passed `bash -n`.
- Offline wheel build succeeded and contains Owner Web static assets.
- Rendered systemd service/timer units passed `systemd-analyze verify`; all timer calendars parsed successfully.
- Source scan found no Amazon OAuth client-id pattern, bearer token, PEM private key or AWS access-key pattern.
- Archive CI pins GitHub Actions SHAs and test tooling versions and runs a Python 3.11/3.12 matrix.
- A tag-triggered sealed-release workflow re-runs the archive gate and emits wheel/source artifacts, SHA-256 sums and release identity before publishing a GitHub Release.

## Autonomy status

v0.4 does **not** add routine per-action Owner approval. Codex remains free to optimize inside the Owner-defined Sponsored Products scope and monetary envelope. The new controls harden execution correctness, replay resistance, recovery and reproducibility rather than shrinking the business decision space.

## What this status does not certify

Credential-free CI cannot certify a real Amazon Ads deployment. OAuth, live MCP tool/schema binding, fresh-state race drill, micro-live reversible writes, crash/restart reconciliation against real Amazon state, PAUSED-create/verify/enable lifecycle, Emergency Stop timing and ambiguous-failure behavior remain required per `docs/ARCHIVE_ACCEPTANCE.md` before a **specific Ubuntu host + Amazon account** can be called production-accepted.

Source sealing and live deployment acceptance are intentionally separate claims.
