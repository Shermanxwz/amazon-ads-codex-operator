#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$HOME/.config/systemd/user"
sed "s|@ROOT@|$ROOT|g" "$ROOT/systemd/amazon-ads-codex@.service" > "$HOME/.config/systemd/user/amazon-ads-codex@.service"
cp "$ROOT/systemd/amazon-ads-codex-hourly.timer" "$HOME/.config/systemd/user/"
cp "$ROOT/systemd/amazon-ads-codex-daily.timer" "$HOME/.config/systemd/user/"
cp "$ROOT/systemd/amazon-ads-codex-weekly.timer" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now amazon-ads-codex-hourly.timer amazon-ads-codex-daily.timer amazon-ads-codex-weekly.timer
systemctl --user list-timers 'amazon-ads-codex-*'
