# Threat model

The v0.4 security objective is **not** to micromanage the AI. Codex remains free to optimize inside the standing Owner envelope. Controls below protect the execution boundary, money, identity and recovery semantics around that autonomy.

| Threat | Primary controls | Residual risk |
|---|---|---|
| Planner prompt injection proposes dangerous write | Owner scope/monetary policy; permanent blocks; sealed exact action | An incorrect but still in-envelope recommendation can pass; conservative limits and independent verification reduce impact |
| Model edits its future budget/authority | Owner DB/signing material outside model workspace; read-only shell sandbox; read-only production checkout | A trusted/compromised OS user can still alter local files or DBs |
| Executor changes approved MCP args | one enabled MCP tool + signed exact arguments + canonical PreToolUse comparison | Amazon/Codex MCP implementation bugs remain upstream dependencies |
| Executor repeats the same exact write | deterministic action-hash grant + atomic `O_EXCL` consumed marker | A mutation already accepted by Amazon cannot be recalled |
| Owner presses Emergency Stop while Executor is reasoning | PreToolUse re-reads mode/Emergency Stop/revisions immediately before mutation authorization | If Amazon request submission has already begun, local software cannot unsend it |
| Owner policy/operator changes after planning | controller authority token checks + final PreToolUse revision re-check | Owner may intentionally change Amazon state outside this controller |
| Amazon entity changes between planning and execution | fresh pre-write read + deterministic sealed-before comparison | Amazon may still change after the final read and before its write is applied; live acceptance must characterize this residual window |
| Executor/host crashes after Amazon may have applied a write | one-use consumed evidence + restart reconciliation + independent fresh Amazon read; never blind replay | If live state cannot prove the intended result, system pauses and requires investigation |
| Ambiguous transport result hides successful mutation | verifier/fresh reconciliation treats remote state as final evidence | Some complex mutations may not be fully observable immediately; those remain uncertain until proven |
| New campaign spends before validation | create PAUSED + verification lineage + later separate enable | Amazon-side semantics/latency must be live-tested |
| Multiple schedulers overspend | Linux process lock + transactional SQLite reservation ledger | External/manual Amazon changes are outside the process lock; fresh spend evidence/buffer compensates but cannot eliminate platform latency |
| Codex CLI changes underneath an archived deployment | explicit capability contract + host preflight | An upstream behavioral change could preserve flags while changing semantics; staged upgrades remain required |
| Amazon public contract changes | immutable certified Postman commit + scheduled drift detection | Runtime MCP can change independently of Postman; live MCP/schema acceptance remains required |
| Web account takeover | scrypt password, CSRF, Origin checks, rate limits, loopback bind, TLS guidance | Host compromise defeats local Web controls |
| Audit rewrite | HMAC-signed hash chain + immutable revisions | Signing-key compromise permits forged future/rebuilt local history; protect host and verified backups |
| Host/disk loss | SQLite-safe checksum-manifested backup + verified restore + audit-chain verification | OAuth/auth stores are deliberately not backed up; recovery requires re-authentication |

## Autonomy boundary

Engineering hardening must not be confused with routine approval gating. v0.4 intentionally keeps in-envelope Sponsored Products decisions autonomous. The Owner controls the envelope; the AI controls optimization choices inside it.

## Out of scope for v0.4 certification

Sponsored Brands and Sponsored Display autonomous writes are not production-certified by this release. SP-API commerce/profit inputs are also not yet part of the hard control plane. A real Amazon deployment is not production-accepted until the credentialed staged acceptance checklist has passed.
