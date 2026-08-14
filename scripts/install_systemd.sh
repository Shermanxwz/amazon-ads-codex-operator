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
for key in ('hourly_pacing','daily_optimization','weekly_strategy'):
    if not isinstance(sch.get(key), bool):
        raise SystemExit(f'operator scheduling.{key} must be boolean')
print(o.get('timezone') or 'UTC')
print(int(sch.get('daily_hour_local',4)))
print(str(sch.get('weekly_day') or 'Sun'))
print(int(sch.get('weekly_hour_local',5)))
print('1' if sch['hourly_pacing'] else '0')
print('1' if sch['daily_optimization'] else '0')
print('1' if sch['weekly_strategy'] else '0')
PY
)
TIMEZONE="${CFG[0]}"
DAILY_HOUR="$(printf '%02d' "${CFG[1]}")"
WEEKLY_DAY="${CFG[2]}"
WEEKLY_HOUR="$(printf '%02d' "${CFG[3]}")"
HOURLY_ENABLED="${CFG[4]}"
DAILY_ENABLED="${CFG[5]}"
WEEKLY_ENABLED="${CFG[6]}"

render(){
  local src="$1" dst="$2"
  sed -e "s#@ROOT@#$ROOT#g" -e "s#@OWNER_HOME@#$OWNER_HOME#g" -e "s#@TIMEZONE@#$TIMEZONE#g" -e "s#@DAILY_HOUR@#$DAILY_HOUR#g" -e "s#@WEEKLY_DAY@#$WEEKLY_DAY#g" -e "s#@WEEKLY_HOUR@#$WEEKLY_HOUR#g" "$src" > "$dst"
}
for name in amazon-ads-codex@.service amazon-ads-owner-web.service amazon-ads-codex-hourly.timer amazon-ads-codex-daily.timer amazon-ads-codex-weekly.timer; do
  render "$ROOT/systemd/$name" "$UNIT_DIR/$name"
done

# Archive/full-stack certification exercises the exact rendering path without
# mutating the validation host's user manager.
if [[ "${ADS_SYSTEMD_RENDER_ONLY:-0}" == "1" ]]; then
  echo "Rendered systemd user units only: $UNIT_DIR"
  echo "Timers use account timezone: $TIMEZONE"
  echo "Schedule flags: hourly=$HOURLY_ENABLED daily=$DAILY_ENABLED weekly=$WEEKLY_ENABLED"
  exit 0
fi

# User units are production services, not login-session helpers. Linger is a
# hard host prerequisite so they start after boot and survive logout.
if ! command -v loginctl >/dev/null 2>&1; then
  echo "ERROR: loginctl is required for unattended systemd user services." >&2
  exit 2
fi
USER_NAME="$(id -un)"
LINGER="$(loginctl show-user "$USER_NAME" -p Linger --value 2>/dev/null || true)"
if [[ "$LINGER" != "yes" ]]; then
  if ! loginctl enable-linger "$USER_NAME"; then
    echo "ERROR: could not enable linger for $USER_NAME. Run: sudo loginctl enable-linger $USER_NAME" >&2
    exit 2
  fi
fi
LINGER="$(loginctl show-user "$USER_NAME" -p Linger --value 2>/dev/null || true)"
if [[ "$LINGER" != "yes" ]]; then
  echo "ERROR: linger is not enabled for $USER_NAME; refusing an unreliable unattended install." >&2
  exit 2
fi

systemctl --user daemon-reload
systemctl --user enable --now amazon-ads-owner-web.service

apply_timer(){
  local enabled="$1" unit="$2"
  if [[ "$enabled" == "1" ]]; then
    systemctl --user enable --now "$unit"
  else
    systemctl --user disable --now "$unit" >/dev/null 2>&1 || true
  fi
}
apply_timer "$HOURLY_ENABLED" amazon-ads-codex-hourly.timer
apply_timer "$DAILY_ENABLED" amazon-ads-codex-daily.timer
apply_timer "$WEEKLY_ENABLED" amazon-ads-codex-weekly.timer

systemctl --user list-timers 'amazon-ads-codex-*' --no-pager || true
echo "Owner Web: http://127.0.0.1:8765"
echo "Timers use account timezone: $TIMEZONE"
echo "Schedule flags: hourly=$HOURLY_ENABLED daily=$DAILY_ENABLED weekly=$WEEKLY_ENABLED"
echo "User linger: $LINGER"
