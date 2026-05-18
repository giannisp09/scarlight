#!/usr/bin/env bash
# Tear down the demo lab target.
set -euo pipefail

CONTAINER="scarlight-demo-target"

if [[ "$(docker ps -aq --filter "name=^${CONTAINER}$")" ]]; then
  docker rm -f "${CONTAINER}" >/dev/null
  echo "→ ${CONTAINER} removed"
else
  echo "→ ${CONTAINER} not running"
fi
