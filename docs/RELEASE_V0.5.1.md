# Amazon Ads Codex Operator v0.5.1

**Final acceptance / disaster-recovery archive seal.**

v0.5.1 keeps the v0.5.0 Codex Evergreen architecture and broad in-envelope AI autonomy, then closes the remaining source-level proof gaps:

- Executor grants now use a domain-separated grant-only key; the frozen hook no longer receives the Owner master key used for audit/action signing;
- a fresh Ubuntu 24.04 `virtual-full-stack` gate now drives the real Controller through bootstrap, Owner configuration, Observe, sealed execution, the frozen PreToolUse hook, independent verification, ambiguous-write recovery, restart reconciliation, Emergency Stop and the process lock using a credential-free virtual Amazon/Codex boundary;
- disaster-recovery backups now preserve the Owner-pinned ACTIVE/PREVIOUS Codex runtime registry and content-addressed runtime slots, while restore explicitly clears stale OAuth/auth, grants, workspaces, run artifacts and SQLite sidecars before reconstituting the archived runtime and returning Owner mode to Observe.

The virtual acceptance gate proves control-plane mechanics without real credentials. It does not replace the account-specific OAuth, live Amazon MCP schema binding and controlled real-account acceptance required by `docs/ARCHIVE_ACCEPTANCE.md`.
