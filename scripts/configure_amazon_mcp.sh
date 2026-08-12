#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
codex mcp list
codex mcp login amazon_ads
codex mcp list
