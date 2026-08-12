#!/usr/bin/env bash
set -euo pipefail
curl -fsSL https://chatgpt.com/codex/install.sh | sh
codex --version
