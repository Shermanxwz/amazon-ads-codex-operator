# Changelog

## 0.5.0 — Codex Evergreen / native integration

- Decoupled production execution from Linux PATH. The controller now selects an Owner-pinned ACTIVE Codex runtime and verifies its SHA-256 fingerprint before every invocation.
- Added a content-addressed Codex runtime registry with candidate registration, capability probe, explicit atomic promotion and rollback to the previous ACTIVE runtime.
- Bootstrap adopts Codex only when no ACTIVE exists; later system `codex` updates cannot silently replace production.
- `install_codex_ubuntu.sh` registers updates as candidates instead of promoting them; Amazon MCP setup uses ACTIVE Codex.
- Expanded the capability contract from a flag list to stable command surfaces plus strict-config smoke testing. Experimental App Server/remote/cloud surfaces are not production dependencies.
- Added daily Ubuntu latest-Codex compatibility CI as an early-warning drift detector.
- Added a repo-scoped `amazon-ads-operator` Codex plugin with status, diagnosis, acceptance and autonomy skills. The plugin is UX/instructions only; privileged writes remain behind the sealed control plane.
- Added automatic green-main release sealing and immutable version/tag identity.
- Added single-main-branch enforcement so GitHub retains only `main`.
- Preserved broad AI decision freedom inside Owner scope and monetary limits; no routine per-action approval was introduced.

## 0.4.0 — Archive hardening / crash-safe sealed execution

- Preserved full-managed AI autonomy inside the Owner-defined scope and monetary envelope; no per-action human approval workflow was introduced.
- Upgraded Executor grants to deterministic v2 one-use capability tickets with atomic replay protection.
- Added final-boundary Owner authority checks, fresh pre-write state validation, crash/restart reconciliation and independent fresh-state verification.
- Added direct production-hook tests, Codex capability checks, immutable Amazon contract pinning, verified backup/restore, pinned CI and sealed release artifacts.

## 0.3.0 — Owner Control / sealed execution

- Added Owner Web as the highest operational authority layer with authenticated mode, scope, monetary limits, emergency stop, immutable revisions and rollback-to-Observe.
- Moved Owner policy, runtime DB, signing key, production Codex home, grants, workspaces and run evidence outside the Git checkout.
- Added HMAC-signed audit history, one-action execution, exact MCP tool/argument grants, budget reservations, cooldowns, recovery breaker and two-phase PAUSED campaign activation.
