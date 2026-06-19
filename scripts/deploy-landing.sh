#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="${REMOTE:-root@ai-drama-n1}"
REMOTE_WEB_DIR="${REMOTE_WEB_DIR:-/opt/ai-drama/landing}"
NGINX_CONF="${NGINX_CONF:-/etc/nginx/conf.d/ai-drama-landing.conf}"
SERVER_NAME="${SERVER_NAME:-ai-drama-landing-135668366.ap-southeast-1.elb.amazonaws.com}"

cd "$ROOT_DIR/client/landing"
npm run build

ssh "$REMOTE" "mkdir -p '$REMOTE_WEB_DIR'"
rsync -az --delete "$ROOT_DIR/client/landing/dist/" "$REMOTE:$REMOTE_WEB_DIR/"

ssh "$REMOTE" bash -s <<EOF
set -euo pipefail
cat > '$NGINX_CONF' <<'NGINX'
server_names_hash_bucket_size 128;

server {
    listen 80;
    listen [::]:80;
    server_name $SERVER_NAME;

    root $REMOTE_WEB_DIR;
    index index.html;

    client_max_body_size 2g;
    client_body_timeout 1800s;

    location /api/ {
        proxy_pass http://127.0.0.1:8080/api/;
        proxy_http_version 1.1;
        proxy_request_buffering off;
        proxy_connect_timeout 1800s;
        proxy_send_timeout 1800s;
        proxy_read_timeout 1800s;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /uploads/ {
        proxy_pass http://127.0.0.1:8080/uploads/;
        proxy_http_version 1.1;
        proxy_connect_timeout 1800s;
        proxy_send_timeout 1800s;
        proxy_read_timeout 1800s;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX
nginx -t
systemctl reload nginx
curl -fsS -H 'Host: $SERVER_NAME' http://127.0.0.1/ >/tmp/ai-drama-landing-smoke.html
head -n 5 /tmp/ai-drama-landing-smoke.html
EOF

echo "Deployed landing to $REMOTE:$REMOTE_WEB_DIR"
echo "URL: http://$SERVER_NAME/"
