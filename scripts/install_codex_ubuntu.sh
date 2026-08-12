#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
curl -fsSL https://chatgpt.com/codex/install.sh | sh
CODEX_BIN="$(command -v codex)"
"$CODEX_BIN" --version
# A system update is only a candidate. It cannot replace production ACTIVE.
python3 "$ROOT/scripts/codex_runtime.py" candidate --binary "$CODEX_BIN"
echo "Codex candidate registered. Production remains on the Owner-pinned ACTIVE runtime until explicitly promoted."
