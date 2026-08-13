#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER_HOME="${ADS_OWNER_HOME:-$HOME/.local/share/amazon-ads-codex-owner}"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"

readarray -t CFG < <(PYTHONPATH="$ROOT/src" ADS_OWNER_HOME="$OWNER_HOME" python3 - <<'PY'
from pathlib import Path
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.sealing import Sealer
from ads_autopilot.owner_store import OwnerStore
import os
root=Path(os.environ['PYTHONPATH']).parent
p=RuntimePaths.resolve(root,os.environ['ADS_OWNER_HOME'])
s=OwnerStore(p.owner_db,Sealer.from_path(p.signing_key).key).snapshot()
o=s['operator']; sch=o.get('scheduling',{})
print(o.get('timezone') or 'UTC')
print(int(sch.get('daily_hour_local',4)))
print(str(sch.get('weekly_day') or 'Sun'))
print(int(sch.get('weekly_hour_local',5)))
PY
)
TIMEZONE="${CFG[0]}"; DAILY_HOUR="$(printf '%02d' "${CFG[1]}")"; WEEKLY_DAY="${CFG[2]}"; WEEKLY_HOUR="$(printf '%02d' "${CFG[3]}")"

render(){
  local src="$1" dst="$2"
  sed -e "s#@ROOT@#$ROOT#g" -e "s#@OWNER_HOME@#$OWNER_HOME#g" -e "s#@TIMEZONE@#$TIMEZONE#g" -e "s#@DAILY_HOUR@#$DAILY_HOUR#g" -e "s#@WEEKLY_DAY@#$WEEKLY_DAY#g" -e "s#@WEEKLY_HOUR@#$WEEKLY_HOUR#g" "$src" > "$dst"
}
for name in amazon-ads-codex@.service amazon-ads-owner-web.service amazon-ads-codex-hourly.timer amazon-ads-codex-daily.timer amazon-ads-codex-weekly.timer; do
  render "$ROOT/systemd/$name" "$UNIT_DIR/$name"
done

# Archive/full-stack certification needs to exercise the exact production
# rendering path without changing the CI/validation host's user services.
# Production behavior is unchanged unless this explicit test-only switch is set.
if [[ "${ADS_SYSTEMD_RENDER_ONLY:-0}" == "1" ]]; then
  echo "Rendered systemd user units only: $UNIT_DIR"
  echo "Timers use account timezone: $TIMEZONE"
  exit 0
fi

systemctl --user daemon-reload
systemctl --user enable --now amazon-ads-owner-web.service
systemctl --user enable --now amazon-ads-codex-hourly.timer amazon-ads-codex-daily.timer amazon-ads-codex-weekly.timer
systemctl --user list-timers 'amazon-ads-codex-*' --no-pager || true
echo "Owner Web: http://127.0.0.1:8765"
echo "Timers use account timezone: $TIMEZONE"
