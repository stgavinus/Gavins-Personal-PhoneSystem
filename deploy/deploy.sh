#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Sync code to VPS and restart services
# Replaces ship.sh (Docker-based).
#
# Usage:
#   ./deploy.sh [bridge|ai-server|asterisk|all]   (default: all)
# =============================================================================
set -euo pipefail

TARGET=${1:-all}
VPS=GeneralVPS
REMOTE=/home/ubuntu/VoiceProject

rsync_push() {
    local src=$1 dst=$2
    echo "==> rsync $src → $VPS:$dst"
    rsync -az --delete \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.env' \
        --exclude='data/' \
        "$src" "$VPS:$dst"
}

restart() {
    local svc=$1
    echo "==> Restarting $svc..."
    ssh "$VPS" "sudo systemctl restart $svc"
}

if [[ "$TARGET" == "bridge" || "$TARGET" == "all" ]]; then
    rsync_push bridge/ "$REMOTE/bridge/"
    restart bridge
fi

if [[ "$TARGET" == "ai-server" || "$TARGET" == "all" ]]; then
    rsync_push ai-server/ "$REMOTE/ai-server/"
    restart ai-server
fi

if [[ "$TARGET" == "asterisk" || "$TARGET" == "all" ]]; then
    rsync_push asterisk/ "$REMOTE/asterisk/"
    # Copy configs into /etc/asterisk as the asterisk user can't read /home/ubuntu
    ssh "$VPS" "sudo cp $REMOTE/asterisk/etc/pjsip.conf /etc/asterisk/pjsip.conf && \
                sudo cp $REMOTE/asterisk/etc/extensions.conf /etc/asterisk/extensions.conf && \
                sudo chown asterisk:asterisk /etc/asterisk/pjsip.conf /etc/asterisk/extensions.conf && \
                sudo asterisk -rx 'core reload'"
fi

echo "==> Done."
