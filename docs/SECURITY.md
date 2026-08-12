# Security model

- Keep the GitHub repository private for real operations. If it is public, commit only sanitized source and examples.
- Do not commit `config/*.local.json`, `.secrets/`, `.env`, Codex auth, Amazon OAuth tokens, account IDs, customer/order data or runtime logs.
- The controller signing key is local-only and excluded from the Codex child-process environment.
- MCP writes are auto-approved only because deterministic policy/sealing happens before the executor invocation.
- The controller never authorizes billing, payment, credential, account-admin, user-management or permanent-delete operations.
- Run the systemd service as a non-root user.
