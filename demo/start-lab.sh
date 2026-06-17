#!/usr/bin/env bash
# Bring up the demo lab — two-container Linux chain for the v1.1 attack-chain
# showcase. Both containers are built locally on first run from
# demo/lab/{web-target,pivot-target}/Dockerfile and bound to host loopback.
#
#   web-target   : http://127.0.0.1:8080/   (Flask app, command-injection on /ping)
#   pivot-target : ssh -p 2222 root@127.0.0.1 (alpine + sshd, accepts the
#                                              planted key from web-target)
#
# From inside the Kali sandbox the scarlight agent reaches them at
# http://host.docker.internal:8080/ and host.docker.internal:2222.

set -euo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${DEMO_DIR}/docker-compose.yml"

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose plugin is required (try 'docker compose version')" >&2
  exit 1
fi

echo "→ building + bringing up demo lab (web-target + pivot-target) …"
docker compose -f "${COMPOSE_FILE}" up -d --build

echo -n "→ waiting for web-target HTTP 200 on 127.0.0.1:8080 "
for _ in $(seq 1 40); do
  code="$(curl -sS --connect-timeout 1 -o /dev/null -w '%{http_code}' "http://127.0.0.1:8080/health" 2>/dev/null || true)"
  if [[ "${code}" == "200" ]]; then
    echo "— ready"
    break
  fi
  echo -n "."
  sleep 1
done

if [[ "${code:-}" != "200" ]]; then
  echo
  echo "ERROR: web-target did not respond with HTTP 200 within 40s" >&2
  docker compose -f "${COMPOSE_FILE}" logs --tail=30 web-target >&2 || true
  exit 1
fi

echo -n "→ waiting for pivot-target sshd on 127.0.0.1:2222 "
for _ in $(seq 1 30); do
  if (echo > /dev/tcp/127.0.0.1/2222) >/dev/null 2>&1; then
    echo "— ready"
    break
  fi
  echo -n "."
  sleep 1
done

if ! (echo > /dev/tcp/127.0.0.1/2222) >/dev/null 2>&1; then
  echo
  echo "ERROR: pivot-target sshd did not open port 2222 within 30s" >&2
  docker compose -f "${COMPOSE_FILE}" logs --tail=30 pivot-target >&2 || true
  exit 1
fi

echo
echo "lab up:"
echo "  web-target   → http://127.0.0.1:8080/  (Kali: http://host.docker.internal:8080/)"
echo "  pivot-target → ssh -p 2222 root@127.0.0.1  (Kali: host.docker.internal:2222)"
