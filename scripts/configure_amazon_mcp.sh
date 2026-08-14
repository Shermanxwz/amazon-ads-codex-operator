#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER_HOME="${ADS_OWNER_HOME:-$HOME/.local/share/amazon-ads-codex-owner}"
export CODEX_HOME="$OWNER_HOME/codex-home"
mkdir -p "$CODEX_HOME"
chmod 700 "$OWNER_HOME" "$CODEX_HOME" 2>/dev/null || true
cat > "$CODEX_HOME/config.toml" <<'CFG'
# Production MCP configuration. Planner/Verifier use write-gated mode.
# The sealed Executor overrides this per invocation to approve.
[features]
hooks = true

[mcp_servers.amazon_ads]
url = "https://advertising-ai.amazon.com/mcp"
auth = "oauth"
enabled = true
required = true
startup_timeout_sec = 30
tool_timeout_sec = 180
default_tools_approval_mode = "writes"
CFG
chmod 600 "$CODEX_HOME/config.toml"
CODEX_BIN="$(PYTHONPATH="$ROOT/src" python3 - "$ROOT" <<'PY'
from pathlib import Path
import sys
from ads_autopilot.codex_compat import resolve_active_binary
from ads_autopilot.paths import RuntimePaths
root = Path(sys.argv[1]).resolve()
print(resolve_active_binary(RuntimePaths.resolve(root), allow_path_fallback=False))
PY
)"
echo "Using CODEX_HOME=$CODEX_HOME"
echo "Using ACTIVE Codex=$CODEX_BIN"
"$CODEX_BIN" mcp list
"$CODEX_BIN" mcp login amazon_ads
"$ROOT/scripts/configure_codex_plugin.sh"
echo "Amazon Ads MCP OAuth and native amazon-ads-operator plugin setup completed for the dedicated production Codex home."
