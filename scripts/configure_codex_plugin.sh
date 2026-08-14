#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER_HOME="${ADS_OWNER_HOME:-$HOME/.local/share/amazon-ads-codex-owner}"
export CODEX_HOME="$OWNER_HOME/codex-home"
CODEX_BIN="$(PYTHONPATH="$ROOT/src" python3 - "$ROOT" <<'PY'
from pathlib import Path
import sys
from ads_autopilot.codex_compat import resolve_active_binary
from ads_autopilot.paths import RuntimePaths
root=Path(sys.argv[1]).resolve()
print(resolve_active_binary(RuntimePaths.resolve(root),allow_path_fallback=False))
PY
)"

MARKETPLACE_JSON="$(mktemp)"
PLUGIN_JSON="$(mktemp)"
trap 'rm -f "$MARKETPLACE_JSON" "$PLUGIN_JSON"' EXIT

"$CODEX_BIN" plugin marketplace add "$ROOT" --json >"$MARKETPLACE_JSON"
"$CODEX_BIN" plugin add amazon-ads-operator@amazon-ads-codex-operator --json >"$PLUGIN_JSON"
"$CODEX_BIN" plugin list --json | python3 -c 'import json,sys; v=json.load(sys.stdin); rows=v.get("installed",[]); ok=any(x.get("name")=="amazon-ads-operator" and x.get("installed") is not False and x.get("enabled") is not False for x in rows); raise SystemExit(0 if ok else "amazon-ads-operator plugin installation verification failed")'
echo "Codex plugin installed and verified in $CODEX_HOME"
