#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$ROOT/vendor/amazon-postman/postman"
CERT="$ROOT/vendor/amazon-postman/CERTIFIED_UPSTREAM.json"

PIN="$(python3 - "$CERT" <<'PY'
import json,sys
value=json.load(open(sys.argv[1]))
commit=str(value.get('commit') or '')
if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit.lower()):
    raise SystemExit('invalid certified upstream commit')
print(commit)
PY
)"

rm -rf "$TARGET"
mkdir -p "$TARGET/repo"
git -C "$TARGET/repo" init -q
git -C "$TARGET/repo" remote add origin https://github.com/amzn/ads-advanced-tools-docs.git
git -C "$TARGET/repo" sparse-checkout init --cone
git -C "$TARGET/repo" sparse-checkout set postman
git -C "$TARGET/repo" fetch --depth 1 origin "$PIN"
git -C "$TARGET/repo" checkout --detach -q FETCH_HEAD
ACTUAL="$(git -C "$TARGET/repo" rev-parse HEAD)"
if [[ "$ACTUAL" != "$PIN" ]]; then
  echo "certified Amazon upstream mismatch: $ACTUAL != $PIN" >&2
  exit 2
fi
printf '%s\n' "$ACTUAL" > "$TARGET/UPSTREAM_COMMIT"
python3 "$ROOT/scripts/build_postman_index.py"
echo "Certified Amazon Ads Postman contract synced at $ACTUAL"
