#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="${REMOTE:-root@ai-drama-n1}"
REMOTE_WEB_DIR="${REMOTE_WEB_DIR:-/opt/ai-drama/www}"
NGINX_CONF="${NGINX_CONF:-/etc/nginx/conf.d/ai-drama.conf}"

cd "$ROOT_DIR/admin/frontend"
npm run build

ssh "$REMOTE" "mkdir -p '$REMOTE_WEB_DIR'"
rsync -az --delete "$ROOT_DIR/admin/frontend/dist/" "$REMOTE:$REMOTE_WEB_DIR/"

ssh "$REMOTE" bash -s <<EOF
set -euo pipefail
test -f '$NGINX_CONF'
nginx -t
systemctl reload nginx
curl -fsS http://127.0.0.1/login >/tmp/ai-drama-frontend-smoke.html
head -n 5 /tmp/ai-drama-frontend-smoke.html
EOF

echo "Deployed frontend to $REMOTE:$REMOTE_WEB_DIR"
