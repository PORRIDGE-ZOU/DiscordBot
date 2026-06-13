#!/usr/bin/env bash
# One-command deploy, run ON the EC2 server from the project directory:
#   ./deploy.sh
# Pulls the latest code from GitHub, installs any new dependencies, and restarts
# the systemd service. Safe to run anytime — git never touches untracked files
# (.env, venv/, jobs.sqlite), so secrets and live reminders are preserved.
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Pulling latest from GitHub..."
git pull --ff-only

echo "==> Installing dependencies..."
source venv/bin/activate
pip install -q -r requirements.txt

echo "==> Restarting qlpbot service..."
sudo systemctl restart qlpbot

echo "==> Recent logs:"
sleep 2
journalctl -u qlpbot -n 15 --no-pager
echo "==> Done."
