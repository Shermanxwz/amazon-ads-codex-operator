# Security model

## Non-negotiable invariants

1. AI cannot edit Owner authority.
2. The signing key is never forwarded in the model environment or copied into the disposable workspace; supported shell/file tool paths are denied by the frozen PreToolUse hook. Because OpenAI documents that specialized tool paths may opt out of hooks, host isolation and key protection remain part of the trusted computing base.
3. Billing, payment, account-admin, credential/user-management and permanent-delete operations are hard-blocked in code.
4. No live mutation is released without deterministic policy acceptance and HMAC sealing.
5. Atomic Executor is allowed one exact Amazon MCP tool and one exact argument object.
6. Unknown/partial write results fail closed and retain spend exposure.
7. Independent fresh read verification is required before an action is considered complete.
8. Owner Emergency Stop never auto-clears.
9. Codex JSONL event streams are retained per invocation for forensic reconstruction, but event logs never grant authority.

## Codex hooks
The production hook is copied at bootstrap into `ADS_OWNER_HOME/trusted-hooks` and the dedicated Codex config points to that frozen copy. `--dangerously-bypass-hook-trust` is used only because the controller has already vetted and deployed that Owner-controlled hook source; it is **not** the approvals/sandbox bypass flag.

PreToolUse is a strong defense for supported local/MCP tool paths, but OpenAI documentation notes that specialized tool paths can opt out of the default hook path. Therefore this project does not treat the hook as the sole security boundary: it combines one-tool `enabled_tools`, deterministic sealing, read-only shell sandbox, one-action execution, conservative outcome parsing and independent verification.

## Owner Web
- default bind: loopback only;
- password stored as scrypt hash;
- HttpOnly SameSite=Strict session cookie;
- CSRF token required for mutations;
- optional exact Origin validation via `ADS_WEB_PUBLIC_ORIGIN`;
- login rate limits;
- no Agent write API exposed through the Owner Web server;
- CSP / frame denial / no-store response headers.

Prefer SSH tunneling. If reverse-proxying, terminate TLS and do not expose the plain loopback service directly to the Internet.

## GitHub
The repository contains sanitized source/examples only. Before storing any account-specific operational documentation in Git, make the repository Private. Even a private repository should never contain OAuth refresh/access tokens, Codex auth state, the signing key, cookies or Owner/runtime databases.
