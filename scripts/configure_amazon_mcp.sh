#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER_HOME="${ADS_OWNER_HOME:-$HOME/.local/share/amazon-ads-codex-owner}"
export CODEX_HOME="$OWNER_HOME/codex-home"
mkdir -p "$CODEX_HOME"
chmod 700 "$OWNER_HOME" "$CODEX_HOME" 2>/dev/null || true
cat > "$CODEX_HOME/config.toml" <<'EOF'
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
EOF
chmod 600 "$CODEX_HOME/config.toml"
echo "Using CODEX_HOME=$CODEX_HOME"
codex mcp list
codex mcp login amazon_ads
echo "Amazon Ads MCP OAuth completed for the dedicated production Codex home."
