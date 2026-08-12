# Codex Evergreen runtime architecture

v0.5 decouples the production Amazon Ads control plane from whichever `codex` executable happens to be first on Linux `PATH`.

## Invariant

A system Codex install or update is a **candidate**, not production authority. Production selects an Owner-owned **ACTIVE** runtime identity from `ADS_OWNER_HOME/codex-runtimes/registry.json`. Each candidate is content-addressed by SHA-256, copied into an Owner-private slot, probed against `config/codex-compatibility.json`, and only becomes ACTIVE through an explicit atomic promotion. The previous ACTIVE remains the rollback target.

The business authority model is unchanged: Codex still has broad freedom inside Owner scope and monetary limits. Evergreen only protects runtime compatibility and availability.

## Runtime layout

```text
ADS_OWNER_HOME/
└── codex-runtimes/
    ├── registry.json
    └── slots/
        └── <binary-sha256>/
            └── codex
```

The production runner verifies the ACTIVE slot fingerprint on every invocation and records the selected runtime beside each structured result as `*.runtime.json`.

## Lifecycle

Inspect production:

```bash
python3 scripts/codex_runtime.py status
python3 scripts/check_codex_runtime.py
```

Install/update the system candidate without changing production:

```bash
./scripts/install_codex_ubuntu.sh
```

Or register an already installed candidate:

```bash
python3 scripts/codex_runtime.py candidate --binary "$(command -v codex)"
```

Promotion is explicit and capability-gated:

```bash
python3 scripts/codex_runtime.py promote <runtime_id>
python3 scripts/preflight.py
python3 scripts/run_cycle.py daily --dry-run
```

If a promoted runtime exhibits a host-specific regression:

```bash
python3 scripts/codex_runtime.py rollback
python3 scripts/preflight.py
```

Bootstrap automatically adopts the installed Codex only when no ACTIVE runtime exists. Once ACTIVE exists, bootstrap never follows a later PATH update automatically.

## Capability contract

Compatibility is determined by stable command/flag behavior and strict-config parsing, not a version-number allowlist. The contract currently probes the non-interactive execution surface, MCP management, plugin/marketplace commands, feature inspection, sandbox, doctor/update commands, structured output flags and strict configuration behavior.

Experimental surfaces such as App Server, remote-control or cloud-specific commands are explicitly not production dependencies. If OpenAI adds features, the system can use them later without making them part of the safety boundary. If a required stable capability disappears or changes incompatibly, the candidate fails and ACTIVE keeps running.

## Continuous drift detection

`.github/workflows/codex-evergreen.yml` installs the current official Codex on Ubuntu 24.04 every day and probes the same capability contract. This is an early-warning source compatibility monitor; it cannot promote a production host.

## Native Codex integration

The repository exposes `plugins/amazon-ads-operator` through `.agents/plugins/marketplace.json`. The plugin packages status, diagnosis, acceptance and autonomy skills for Codex-native use. It intentionally does **not** expose a second privileged Amazon write path. The actual write boundary remains the Owner-controlled sealed controller and dedicated production `CODEX_HOME`.

## Upgrade acceptance rule

A candidate can pass the generic capability probe and still require host/live confirmation before you choose to promote it. For a production host, run preflight, Observe/dry-run, Amazon MCP read checks and at least one controlled verification cycle after promotion. Rollback is available without changing Owner policy or Amazon authority.
