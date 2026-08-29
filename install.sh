#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo apt update
sudo apt install -y python3-venv git gh

python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install --upgrade pip
"$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"
"$ROOT/.venv/bin/python" -m playwright install --with-deps chromium

chmod +x "$ROOT/fetch_bursley.py" "$ROOT/sync_menu.sh"

mkdir -p "$HOME/.config/systemd/user"

cat > "$HOME/.config/systemd/user/bursley-menu.service" <<SERVICE
[Unit]
Description=Sync Bursley Dining menu to GitHub
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$ROOT
ExecStart=$ROOT/sync_menu.sh
SERVICE

cp "$ROOT/systemd/bursley-menu.timer" \
  "$HOME/.config/systemd/user/bursley-menu.timer"

systemctl --user daemon-reload

echo
echo "Installation complete."
echo "Authenticate GitHub if needed with:"
echo "  gh auth login"
echo
echo "Then test a sync with:"
echo "  $ROOT/sync_menu.sh"
echo
echo "Enable automatic updates with:"
echo "  systemctl --user enable --now bursley-menu.timer"
