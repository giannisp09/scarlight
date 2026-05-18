#!/usr/bin/env bash
# Reset demo state so the next run produces a fresh skill-create event
# (instead of a refine of an existing one). Idempotent.
set -euo pipefail

SKILL_DIR="${SCARLIGHT_HOME:-$HOME/.scarlight}/skills/offensive/juice-shop-fingerprint"

if [[ -d "${SKILL_DIR}" ]]; then
  rm -rf "${SKILL_DIR}"
  echo "→ removed autonomously-created skill at ${SKILL_DIR}"
else
  echo "→ no prior demo skill to remove (clean slate)"
fi
