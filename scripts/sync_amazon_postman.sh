#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$ROOT/vendor/amazon-postman/postman"
rm -rf "$TARGET"
mkdir -p "$TARGET"
git clone --depth 1 --filter=blob:none --sparse https://github.com/amzn/ads-advanced-tools-docs.git "$TARGET/repo"
git -C "$TARGET/repo" sparse-checkout set postman
git -C "$TARGET/repo" rev-parse HEAD > "$TARGET/UPSTREAM_COMMIT"
python3 "$ROOT/scripts/build_postman_index.py"
