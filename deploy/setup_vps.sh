#!/usr/bin/env bash
# =============================================================================
# setup_vps.sh — One-time VPS setup
# Ubuntu 24.04 LTS (noble), Python 3.12, direct Asterisk install (no Docker).
#
# Usage:
#   ssh GeneralVPS 'bash -s' < deploy/setup_vps.sh
# =============================================================================
set -euo pipefail

PROJECT_DIR=/home/ubuntu/VoiceProject
VENV_DIR=$PROJECT_DIR/venv
DATA_DIR=$PROJECT_DIR/data
SPOOL_DIR=/var/spool/asterisk
DEPLOY_USER=ubuntu

echo "==> Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    asterisk \
    python3 \
    python3-venv \
    python3-pip \
    sqlite3 \
    rsync

echo "==> Creating project directory structure..."
sudo mkdir -p "$PROJECT_DIR" "$DATA_DIR/chroma" "$SPOOL_DIR/outgoing" "$SPOOL_DIR/tmp"
sudo chown -R "$DEPLOY_USER:$DEPLOY_USER" "$PROJECT_DIR"
sudo chown -R asterisk:asterisk "$SPOOL_DIR"

echo "==> Creating Python venv..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip wheel

echo "==> Installing Python dependencies (ai-server)..."
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/ai-server/requirements.txt"

echo "==> Installing Python dependencies (bridge)..."
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/bridge/requirements.txt"

echo "==> Configuring Asterisk..."
# Symlink project configs into /etc/asterisk so Asterisk reads our files directly
sudo ln -sf "$PROJECT_DIR/asterisk/etc/pjsip.conf"      /etc/asterisk/pjsip.conf
sudo ln -sf "$PROJECT_DIR/asterisk/etc/extensions.conf"  /etc/asterisk/extensions.conf

echo "==> Installing systemd services..."
sudo cp "$PROJECT_DIR/deploy/bridge.service"    /etc/systemd/system/bridge.service
sudo cp "$PROJECT_DIR/deploy/ai-server.service" /etc/systemd/system/ai-server.service
sudo systemctl daemon-reload
sudo systemctl enable bridge ai-server asterisk
sudo systemctl restart asterisk

echo ""
echo "==> Setup complete."
echo "    Next: copy your .env to $PROJECT_DIR/.env then run: ./deploy/deploy.sh all"
