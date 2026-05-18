#!/usr/bin/env bash
# Bring up the demo lab target: OWASP Juice Shop in Docker, bound to
# host loopback only. Pulls the image on first run (~700 MB).
set -euo pipefail

CONTAINER="scarlight-demo-target"
IMAGE="bkimminich/juice-shop:latest"
PORT=3000

if [[ "$(docker ps -q --filter "name=^${CONTAINER}$")" ]]; then
  echo "lab target already running: ${CONTAINER}"
  exit 0
fi

docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true

echo "→ pulling ${IMAGE} (first run only) …"
docker pull "${IMAGE}" >/dev/null

echo "→ starting ${CONTAINER} on 127.0.0.1:${PORT} …"
docker run -d --rm \
  -p "127.0.0.1:${PORT}:${PORT}" \
  --name "${CONTAINER}" \
  "${IMAGE}" >/dev/null

echo -n "→ waiting for HTTP 200"
for _ in $(seq 1 30); do
  code="$(curl -sS --connect-timeout 1 -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" 2>/dev/null || true)"
  if [[ "${code}" == "200" ]]; then
    echo " — ready"
    echo
    echo "lab target alive at http://127.0.0.1:${PORT}/"
    echo "(reachable from the Kali sandbox at http://host.docker.internal:${PORT}/)"
    exit 0
  fi
  echo -n "."
  sleep 1
done

echo
echo "ERROR: ${CONTAINER} did not respond with HTTP 200 within 30s" >&2
docker logs "${CONTAINER}" 2>&1 | tail -20 >&2
exit 1
