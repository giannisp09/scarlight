#!/usr/bin/env bash
# Tear down both demo lab containers + the private network.
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${DEMO_DIR}/docker-compose.yml"

if [[ -f "${COMPOSE_FILE}" ]] && docker compose version >/dev/null 2>&1; then
  docker compose -f "${COMPOSE_FILE}" down -v --remove-orphans
  echo "→ lab containers + network removed"
else
  # Best-effort fallback if compose plugin is missing.
  for c in scarlight-demo-web-target scarlight-demo-pivot scarlight-demo-target; do
    if [[ "$(docker ps -aq --filter "name=^${c}$")" ]]; then
      docker rm -f "${c}" >/dev/null
      echo "→ ${c} removed"
    fi
  done
  docker network rm scarlight-demo-lab >/dev/null 2>&1 || true
fi
