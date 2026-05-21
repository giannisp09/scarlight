#!/usr/bin/env bash
# Reset demo state so the next run starts from a clean slate.
# - Removes any agent-autonomously-created demo skills.
# - Truncates the demo audit-log file inside the sandbox FS (if present).
# Idempotent.
set -euo pipefail

SCARLIGHT_HOME_DIR="${SCARLIGHT_HOME:-$HOME/.scarlight}"

# Skills the agent might create during a demo run. Add to this list as new
# demo narratives invite new skill names.
for skill in juice-shop-fingerprint nettools-exploit chain-demo; do
  dir="${SCARLIGHT_HOME_DIR}/skills/offensive/${skill}"
  if [[ -d "${dir}" ]]; then
    rm -rf "${dir}"
    echo "→ removed autonomously-created skill at ${dir}"
  fi
done

# Audit log — truncate so the demo's "see the audit trail" beat shows only
# this run's events. As of engagement_scope._persist_engagement_audit_trail()
# the log is bind-mounted out of the sandbox to the canonical host path.
AUDIT_LOG="${SCARLIGHT_HOME_DIR}/audit/exploitation.jsonl"
if [[ -f "${AUDIT_LOG}" ]]; then
  : > "${AUDIT_LOG}"
  echo "→ truncated audit log ${AUDIT_LOG}"
fi
# Legacy: pre-fix runs left a copy inside the sandbox overlay. Clear it too so
# stale takes don't confuse the demo.
LEGACY_AUDIT="${SCARLIGHT_HOME_DIR}/sandboxes/docker/default/home/.scarlight/audit/exploitation.jsonl"
if [[ -f "${LEGACY_AUDIT}" ]]; then
  : > "${LEGACY_AUDIT}"
fi
