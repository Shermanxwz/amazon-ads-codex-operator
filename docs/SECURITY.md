# Security model

## Security objective

Security controls protect the Owner envelope and execution correctness **without converting the system into per-action human approval**. Inside the standing Owner scope and monetary limits, Codex remains autonomous.

## Non-negotiable invariants

1. AI cannot edit or expand Owner authority.
2. Owner/action signing material and the derived Executor-grant key are never forwarded in the model environment or copied into disposable workspaces.
3. The frozen PreToolUse hook receives only the derived Executor-grant key; it does not possess the Owner master signing key used for audit history and normal sealed-action signatures.
4. The Owner master signing identity is the Owner-owned key file under `ADS_OWNER_HOME`; ambient process environment cannot override that identity.
5. Billing, payment, account-admin, credential/user-management and permanent-delete operations are hard-blocked in code.
6. No live mutation is released without deterministic policy acceptance and HMAC sealing.
7. Atomic Executor receives one exact Amazon MCP tool and one exact argument object.
8. Every Executor grant is a one-use capability: the production PreToolUse hook atomically consumes it before returning `allow`; the same grant cannot authorize a replay.
9. At the final tool boundary, the hook re-reads Owner Autopilot mode, Emergency Stop, Policy revision and Operator revision. A stale authority snapshot cannot authorize a new mutation.
10. Existing-entity mutations receive a fresh Amazon state check before release. A stale sealed `before` state is cancelled/replanned rather than written over newer state.
11. A consumed or otherwise ambiguous mutation is never blindly replayed after transport/process/host failure. Fresh Amazon state is used to reconcile the intended `after` state; unresolved exposure remains uncertain and pauses the system.
12. Independent fresh read verification is required before normal completion.
13. Owner Emergency Stop never auto-clears.
14. Codex JSONL event streams are retained per invocation for forensic reconstruction, but event logs never grant authority.

## Signing-key separation

`secrets/operator_signing_key` is the canonical Owner/controller master used for signed Owner audit history and normal sealed-action signatures. `Sealer.from_path()` reads that file directly; a stale or injected `ADS_OPERATOR_SIGNING_KEY` environment value cannot cause runtime signatures to diverge from backup/restore identity.

`secrets/executor_grant_signing_key` is deterministically domain-separated from that master and is the **only** HMAC secret available to the frozen hook. Executor grants are recognized by their v2 capability shape and are signed with the derived key; ordinary sealed actions remain signed with the Owner master key.

This means a defect isolated to the hook's grant-verification secret cannot be used to forge the Owner audit chain or ordinary sealed-action signatures. Bootstrap and preflight verify that the derived key matches the current Owner master and is stored mode `0600`.

## Codex hooks

The production hook is copied at bootstrap into `ADS_OWNER_HOME/trusted-hooks` and the dedicated Codex config points to that frozen copy. Tests execute this exact production script; there is no second package-level authorization implementation that can drift away from production behavior.

`--dangerously-bypass-hook-trust` is used only because the controller has already vetted and deployed that Owner-controlled hook source; it is **not** the approvals/sandbox bypass flag.

PreToolUse is defense in depth rather than the only trust boundary. The control plane combines:

- deterministic Owner policy and permanent blocks;
- sealed exact action identity;
- one-tool Executor `enabled_tools`;
- read-only shell sandbox;
- live Owner authority re-check;
- grant-only signing-key separation;
- atomic one-use grant consumption;
- fresh pre-write state guard;
- one-action execution;
- conservative receipt/outcome handling;
- crash/restart reconciliation;
- independent fresh-state verification.

The request already inside Amazon's network/request processing path cannot be recalled. The design minimizes this irreducible window by releasing one mutation at a time and checking Owner authority at the latest local authorization point.

## Recovery evidence

The grant lifecycle is part of the durable execution journal:

- `<action_hash>.json` present: grant issued but not consumed;
- `<action_hash>.json.consumed` present: the PreToolUse execution boundary was crossed;
- consumed/ambiguous actions require fresh Amazon reconciliation and are never automatically reissued.

Reservations for unresolved writes remain countable against the Owner spend envelope.

## Codex runtime drift

`config/codex-compatibility.json` records the CLI capabilities production depends on. `scripts/check_codex_runtime.py` and `preflight.py` fail when required structured-output, strict-config, hook-trust or non-interactive execution capabilities disappear. Upgrades are staged through Observe/dry-run rather than silently trusted from a version string.

## Amazon contract drift

`vendor/amazon-postman/CERTIFIED_UPSTREAM.json` pins the public Amazon Postman reference used by the release. The sync script fetches the exact commit; a scheduled workflow compares the `postman/` tree against upstream and reports real contract drift without silently changing the production reference.

Live MCP schema/tool acceptance is still required on the credentialed deployment because the MCP service can evolve independently of the public Postman repository.

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

## Backups

Verified v2 backups contain the Owner master signing key, derived Executor-grant key, Owner/runtime SQLite state, production Codex config/hook and the content-addressed Codex runtime registry/slots needed to restore ACTIVE/PREVIOUS identities. They are therefore as sensitive as the live Owner Home and must remain private and access-controlled.

OAuth/auth stores are intentionally excluded. Restore clears stale OAuth/auth state, grants, disposable workspaces, run artifacts, prior runtime slots/registry, lock files and SQLite sidecars before reconstitution; then it verifies manifest hashes, runtime fingerprints, SQLite integrity and the Owner signed audit chain and returns the recovered runtime to Observe until OAuth and current Amazon state are re-established.

## Virtual acceptance / build provenance

The fresh-Ubuntu `virtual-full-stack` CI path exercises the real Controller, Owner databases, Codex runtime registry, frozen hook, one-use grants, verification, recovery, Emergency Stop and process lock against a credential-free virtual Amazon state. It uses the certified Python/toolchain, builds the wheel twice with commit-derived `SOURCE_DATE_EPOCH` and requires byte identity before the wheel is installed and exercised.

The release workflow repeats the archive gate, double-builds both wheel and source archive, binds their hashes to `RELEASE_IDENTITY.json`, and v0.5.2+ subjects receive GitHub Artifact Attestations backed by Sigstore. A scheduled integrity workflow re-downloads releases and verifies checksums, tag/identity binding and those attestations.

These mechanisms provide reproducibility, provenance and tamper evidence. They do not make a GitHub repository administrator cryptographically unable to rewrite refs; repository branch/ruleset protection is an account-level control outside this source tree.

## GitHub / privacy

The archive gate scans both the current source tree and complete Git history for forbidden runtime/auth/key/database filenames and known credential/token patterns. CI uses a full-history checkout for this purpose.

The repository contains sanitized source/examples only. Before storing any account-specific operational documentation in Git, make the repository Private. Even a private repository should never contain OAuth refresh/access tokens, Codex auth state, signing keys, cookies or Owner/runtime databases.
