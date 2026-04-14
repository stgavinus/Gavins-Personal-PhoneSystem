#!/bin/bash
# Build images on Mac and ship directly to VPS over SSH.
# Usage: ./ship.sh [asterisk|ai-server|both]
set -e

TARGET=${1:-both}
VPS=GeneralVPS
VPS_DIR=/home/ubuntu/VoiceProject

ship() {
    local service=$1
    local image=$2
    echo "==> Building $service..."
    docker compose build $service
    echo "==> Shipping $service to VPS..."
    docker save $image | ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=40 $VPS docker load
}

if [ "$TARGET" = "asterisk" ] || [ "$TARGET" = "both" ]; then
    ship asterisk voiceproject-asterisk:latest
fi

if [ "$TARGET" = "ai-server" ] || [ "$TARGET" = "both" ]; then
    ship ai-server voiceproject-ai-server:latest
fi

echo "==> Syncing docker-compose.yml..."
scp docker-compose.yml $VPS:$VPS_DIR/docker-compose.yml

echo "==> Restarting containers on VPS..."
ssh $VPS "cd $VPS_DIR && docker compose up -d"

echo "==> Done."
