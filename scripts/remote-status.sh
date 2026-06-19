#!/usr/bin/env bash
set -euo pipefail

REMOTE="${REMOTE:-root@ai-drama-n1}"
CONTAINER="${CONTAINER:-ai-drama-server}"

ssh "$REMOTE" "docker ps --filter name='^/$CONTAINER$'; docker logs --tail 80 '$CONTAINER'"
