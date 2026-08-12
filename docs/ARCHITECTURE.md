# Architecture

## Why this is not “Codex with write permission”
Giving an agent unrestricted mutation access is not the same as autonomous operations. The controller separates reasoning authority from mutation authority.

### Planner
Reads live Amazon state and creates atomic intents with before/after state, evidence, confidence, dependencies and spend exposure.

### Policy engine
Pure Python. It cannot be persuaded by a prompt. It enforces product scope, action type, confidence, change magnitudes, fresh pre-write evidence, campaign-create rules and permanent blocks.

### Budget ledger
Spend-increasing actions reserve daily exposure before execution. Multiple cycles cannot silently over-allocate the same spend headroom.

### Sealed envelope
Each atomic action includes hashes for plan, policy and operator configuration plus an HMAC signature. The executor never receives the signing key. A later stage cannot mutate arguments without breaking verification.

### Executor
Codex is non-interactive and may use Amazon Ads MCP writes, but only for sealed actions.

### Verifier
A separate Codex invocation re-reads Amazon and compares the intended state. Write-tool responses are evidence, not final truth.

### State
SQLite stores cycles, exact released actions, reservations, receipts, verifications and events. This provides cooldown/history material for later planning.

## Two-phase activation
Structural campaign creation should be split:
1. create campaign PAUSED + ad group/ad/targeting;
2. verify exact structure and economics;
3. release ENABLE in a later cycle.
This prevents “create + immediately spend” from bypassing verification.
