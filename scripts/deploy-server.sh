#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="${REMOTE:-root@ai-drama-n1}"
REMOTE_DIR="${REMOTE_DIR:-/opt/ai-drama}"
REMOTE_ENV="${REMOTE_ENV:-$REMOTE_DIR/server.env}"
IMAGE="${IMAGE:-ai-drama-server}"
TAG="${TAG:-$(date +%Y%m%d%H%M%S)}"
CONTAINER="${CONTAINER:-ai-drama-server}"
HOST_PORT="${HOST_PORT:-8080}"
MONGODB_URI="${MONGODB_URI:-mongodb://172.31.39.95:27017/ai_drama}"
AIDRAMA_JWT_SECRET="${AIDRAMA_JWT_SECRET:-$(openssl rand -hex 32)}"
AIDRAMA_ADMIN_USERNAME="${AIDRAMA_ADMIN_USERNAME:-admin}"
AIDRAMA_ADMIN_PASSWORD="${AIDRAMA_ADMIN_PASSWORD:-admin123}"

ssh "$REMOTE" "mkdir -p '$REMOTE_DIR/source' '$REMOTE_DIR/uploads' '$REMOTE_DIR/downloads'"

ssh "$REMOTE" "test -f '$REMOTE_ENV' || cat > '$REMOTE_ENV'" <<EOF
MONGODB_URI=$MONGODB_URI
AIDRAMA_JWT_SECRET=$AIDRAMA_JWT_SECRET
AIDRAMA_ADMIN_USERNAME=$AIDRAMA_ADMIN_USERNAME
AIDRAMA_ADMIN_PASSWORD=$AIDRAMA_ADMIN_PASSWORD
EOF

rsync -az --delete --delete-excluded \
  --include='/Dockerfile' \
  --include='/.dockerignore' \
  --include='/admin/' \
  --exclude='/admin/server/target/***' \
  --exclude='/admin/server/uploads/***' \
  --exclude='/admin/server/uploads-test/***' \
  --exclude='/admin/server/backend.log' \
  --include='/admin/server/***' \
  --exclude='*' \
  "$ROOT_DIR/" "$REMOTE:$REMOTE_DIR/source/"

ssh "$REMOTE" bash -s <<EOF
set -euo pipefail
cd '$REMOTE_DIR/source'
docker build -t '$IMAGE:$TAG' -t '$IMAGE:latest' .
docker rm -f '$CONTAINER' >/dev/null 2>&1 || true
docker run -d \
  --name '$CONTAINER' \
  --restart unless-stopped \
  -p '$HOST_PORT:8080' \
  --env-file '$REMOTE_ENV' \
  -v '$REMOTE_DIR/uploads:/app/uploads' \
  -v '$REMOTE_DIR/downloads:/app/downloads' \
  '$IMAGE:$TAG'
docker ps --filter name='^/$CONTAINER$'
EOF

echo "Deployed $IMAGE:$TAG to $REMOTE on port $HOST_PORT"
