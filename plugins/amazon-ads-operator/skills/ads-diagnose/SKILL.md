---
name: ads-diagnose
description: Diagnose Codex runtime, Amazon MCP, audit, recovery, scheduling, and operator failures using the sealed control plane evidence.
---

Start with `python3 scripts/preflight.py`, `python3 scripts/check_codex_runtime.py`, and `python3 scripts/codex_runtime.py status` as appropriate. Correlate runtime evidence under Owner Home with cycle receipts, verifications and JSONL events. Treat PATH Codex as a candidate only; production authority belongs to the Owner-pinned ACTIVE runtime. Do not bypass the one-use grant, Owner authority re-check, fresh-state guard, or independent verification to make a failing run succeed.
