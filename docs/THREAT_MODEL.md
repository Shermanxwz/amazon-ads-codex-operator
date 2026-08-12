# Threat model

| Threat | Primary controls | Residual risk |
|---|---|---|
| Planner prompt injection proposes dangerous write | Planner read-only role; policy code; permanent blocks | Incorrect but in-envelope recommendation can still pass; staged limits and verification reduce impact |
| Model edits its future budget/authority | Owner DB outside workspace; read-only shell; project read-only in systemd | Trusted OS user can still edit local files/DB |
| Executor changes approved MCP args | exact tool allow-list + HMAC one-action grant + PreToolUse canonical argument comparison | Codex docs state specialized tool paths may bypass hooks; other controls remain mandatory |
| Executor calls another write tool | `enabled_tools=[exact_tool]`, hook tool-name equality | MCP server/tool metadata bugs remain an upstream dependency |
| Duplicate/ambiguous Amazon mutation | atomic execution, conservative outcome parser, uncertain ledger reservation, pause | Remote platform may apply a write while returning ambiguous response; requires operator investigation |
| New campaign spends before validation | create PAUSED + verification lineage + later enable | Amazon-side semantics/latency must be live-tested |
| Multiple schedulers overspend | process lock + SQLite reservation ledger | External/manual Amazon changes are outside controller lock; live spend evidence/buffer compensates but cannot eliminate this |
| Web account takeover | scrypt password, CSRF, rate limits, loopback bind, TLS guidance | Host compromise defeats local controls |
| Audit rewrite | HMAC-signed hash chain + immutable revisions | Signing-key compromise allows forged future/rebuilt chains; protect host/backups |
| Emergency stop during active call | authority checked between atomic actions | The single already-submitted mutation cannot be recalled |

## Out of scope for v0.3 certification
Sponsored Brands and Sponsored Display autonomous writes are not production-certified by this release. SP-API commerce/profit inputs are also not yet part of the hard control plane.
