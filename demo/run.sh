#!/usr/bin/env bash
# Scarlight v1.1 — recordable demo against the two-container attack-chain lab.
#
# Drives a complete kill-chain engagement end-to-end with timed banners so
# a terminal recording (asciinema / OBS / screen capture) has natural beats:
#
#   1. Refusal beat — try to run without scope, watch the guard refuse.
#   2. Authorization — drop the scope file (2 targets now), show it.
#   3. Lab up — bring up both containers (web-target + pivot-target).
#   4. Engagement — scarlight chat -q with the demo prompt; tool calls
#      stream to the terminal inside the Kali sandbox. Agent runs the full
#      chain: recon → web-exploit → credential-harvest → lateral-movement.
#   5. Payoff — show the captured trophy + the autonomously-created skill.
#   6. Teardown — stop both lab containers.
#
# Usage:
#   demo/run.sh                 # full demo (~7 min)
#   demo/run.sh --no-refusal    # skip the refusal beat
#   demo/run.sh --no-teardown   # leave the lab running after the demo
#
# Requires: docker daemon up, OPENROUTER_API_KEY (or another provider)
# configured, scarlight on PATH (symlink or `uv tool install`).

set -euo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCOPE_FILE="${DEMO_DIR}/engagement.yaml"
PROMPT_FILE="${DEMO_DIR}/prompt.txt"
MODEL="${SCARLIGHT_DEMO_MODEL:-anthropic/claude-sonnet-4.6}"
PROVIDER="${SCARLIGHT_DEMO_PROVIDER:-openrouter}"

SHOW_REFUSAL=1
TEARDOWN=1
for arg in "$@"; do
  case "${arg}" in
    --no-refusal)  SHOW_REFUSAL=0 ;;
    --no-teardown) TEARDOWN=0 ;;
    -h|--help)
      sed -n '2,21p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown flag: ${arg}" >&2; exit 2 ;;
  esac
done

# ── colour + banner helpers ────────────────────────────────────────────
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m'; C_MAGENTA=$'\033[35m'; C_CYAN=$'\033[36m'
else
  C_RESET=''; C_BOLD=''; C_DIM=''; C_RED=''; C_GREEN=''; C_YELLOW=''
  C_BLUE=''; C_MAGENTA=''; C_CYAN=''
fi

banner() {
  local title="$1"
  printf '\n%s┌%s┐%s\n'   "${C_CYAN}" "$(printf '─%.0s' $(seq 1 70))" "${C_RESET}"
  printf '%s│%s %-69s│%s\n' "${C_CYAN}" "${C_BOLD}" "${title}${C_RESET}${C_CYAN}" "${C_RESET}"
  printf '%s└%s┘%s\n\n'   "${C_CYAN}" "$(printf '─%.0s' $(seq 1 70))" "${C_RESET}"
}

note() { printf '%s%s%s\n' "${C_DIM}" "$*" "${C_RESET}"; }
ok()   { printf '%s✓ %s%s\n' "${C_GREEN}" "$*" "${C_RESET}"; }
fail() { printf '%s✗ %s%s\n' "${C_RED}"   "$*" "${C_RESET}"; }
pause(){ sleep "${1:-2}"; }

# ── prerequisite checks ────────────────────────────────────────────────
banner "Scarlight v1 demo · authorized engagement"
note "Cyber Superintelligence for offensive security."
note "Built on the hermes-agent self-improving core, re-aimed at pentest /"
note "bug-bounty / CTF / red-team work. OSS, Apache-2.0. v1 is deliberately"
note "lean: scope guard + Kali sandbox + autonomous skill creation."
pause 3

banner "Prereqs"
command -v docker   >/dev/null || { fail "docker not on PATH"; exit 1; }
command -v scarlight>/dev/null || { fail "scarlight not on PATH — symlink ~/.local/bin/scarlight -> .venv/bin/scarlight"; exit 1; }
docker info >/dev/null 2>&1   || { fail "docker daemon is not running"; exit 1; }
ok "docker daemon up — $(docker info --format '{{.ServerVersion}}')"
ok "scarlight on PATH — $(scarlight --version 2>&1 | head -1)"
ok "model     · ${MODEL}"
ok "provider  · ${PROVIDER}"
pause 2

# ── act 1 — refusal beat (optional) ────────────────────────────────────
if [[ "${SHOW_REFUSAL}" == "1" ]]; then
  banner "Act 1 · the scope guard refuses an engagement without scope"
  note "Scarlight refuses every turn unless a valid engagement.yaml is"
  note "loaded. Watch what happens when we try to chat with no scope on file."
  pause 3

  # The engagement loader checks three paths in order: $SCARLIGHT_ENGAGEMENT,
  # ./engagement.yaml, ~/.scarlight/engagement.yaml. To force a refusal we
  # need all three to miss. Strategy: point the env var at a sure-miss path,
  # run from /tmp (no CWD scope file there), and temporarily move any
  # ~/.scarlight/engagement.yaml aside. A trap restores it if anything fails.
  HOME_SCOPE="${HOME}/.scarlight/engagement.yaml"
  HOME_SCOPE_STASH="${HOME}/.scarlight/engagement.yaml.demo-stash-$$"
  if [[ -f "${HOME_SCOPE}" ]]; then
    mv "${HOME_SCOPE}" "${HOME_SCOPE_STASH}"
    # shellcheck disable=SC2064
    trap "[[ -f '${HOME_SCOPE_STASH}' ]] && mv '${HOME_SCOPE_STASH}' '${HOME_SCOPE}'" EXIT
  fi

  (
    cd /tmp
    SCARLIGHT_ENGAGEMENT="/tmp/scarlight-no-such-scope-$$.yaml" \
    scarlight chat -q "Say hi." --model "${MODEL}" --provider "${PROVIDER}" 2>&1 \
      | head -25
  ) || true

  # Restore immediately (the trap is belt + braces in case of crash above).
  if [[ -f "${HOME_SCOPE_STASH}" ]]; then
    mv "${HOME_SCOPE_STASH}" "${HOME_SCOPE}"
    trap - EXIT
  fi
  pause 3
fi

# ── act 2 — drop scope, show it ────────────────────────────────────────
banner "Act 2 · the operator's authorization scope"
note "engagement.yaml declares the authorized targets, the authorization"
note "reference (contract / bug-bounty program / lab), and the operator's"
note "explicit acknowledgment of CODE_OF_USE.md."
pause 2
echo
cat "${SCOPE_FILE}"
echo
pause 3

# Reset prior demo state so we get a fresh skill-create event.
banner "Act 3 · reset prior demo state"
"${DEMO_DIR}/reset.sh"
pause 2

# Bring up the lab.
banner "Act 4 · bring up the lab (web-target + pivot-target)"
note "Two purpose-built Linux containers: a Flask app with intentional"
note "command injection (web-target, port 8080), and an alpine + sshd"
note "pivot host (pivot-target, port 2222) that trusts a key planted on"
note "web-target. Both bound to host loopback only."
"${DEMO_DIR}/start-lab.sh"
pause 2

# ── act 5 — engagement ─────────────────────────────────────────────────
banner "Act 5 · engagement — full kill chain (Kali sandbox)"
note "The guard accepts the scope (both targets are listed). TERMINAL_ENV"
note "defaults to docker because a real engagement is active — every shell"
note "command runs inside a freshly-launched kalilinux/kali-last-release"
note "container, NOT on the operator's host. Watch the agent run:"
note "  recon → web-exploit (command injection on /ping)"
note "       → credential-harvest (steal /root/.ssh/id_rsa)"
note "       → lateral-movement (ssh into pivot-target)"
note "       → trophy (cat /root/flag.txt)"
note "Each step writes an entry to ~/.scarlight/audit/exploitation.jsonl."
pause 5

SCARLIGHT_ENGAGEMENT="${SCOPE_FILE}" scarlight chat \
  -q "$(cat "${PROMPT_FILE}")" \
  --model "${MODEL}" \
  --provider "${PROVIDER}"

# ── act 6 — payoff ─────────────────────────────────────────────────────
banner "Act 6 · payoff — trophy + audit trail + new skill"

# Trophy — agent should have written it into the session, but we can also
# verify the flag is reachable from the operator side as ground truth.
TROPHY="$(ssh -i "${DEMO_DIR}/lab/web-target/id_rsa" \
            -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            -o ConnectTimeout=5 \
            -o BatchMode=yes \
            -p 2222 root@127.0.0.1 'cat /root/flag.txt' 2>/dev/null || true)"
if [[ -n "${TROPHY}" ]]; then
  ok "trophy on pivot-target (operator-side verification): ${TROPHY}"
else
  note "(could not verify trophy from operator side; check the agent transcript above)"
fi

# Audit log — bind-mounted out of the Kali sandbox to the operator host at the
# canonical path by engagement_scope._persist_engagement_audit_trail(), and
# each line is stamped with the engagement_id.
AUDIT_LOG="${SCARLIGHT_HOME:-$HOME/.scarlight}/audit/exploitation.jsonl"
if [[ -f "${AUDIT_LOG}" ]]; then
  COUNT="$(wc -l <"${AUDIT_LOG}" | tr -d ' ')"
  ok "audit log: ${COUNT} entries at ${AUDIT_LOG}"
  note "    last 3 skills logged (skill · outcome · target · engagement):"
  if command -v jq >/dev/null 2>&1; then
    tail -3 "${AUDIT_LOG}" | jq -r '"        \(.ts)  \(.skill_name)  \(.outcome)  \(.target)  [\(.engagement_id)]"' 2>/dev/null \
      || tail -3 "${AUDIT_LOG}" | sed 's/^/        /'
  else
    tail -3 "${AUDIT_LOG}" | sed 's/^/        /'
  fi
else
  note "(no audit-log file found at ${AUDIT_LOG})"
fi
echo

# New skill — agent should have written one capturing this chain.
for SKILL_NAME in nettools-exploit chain-demo; do
  SKILL_DIR="${SCARLIGHT_HOME:-$HOME/.scarlight}/skills/offensive/${SKILL_NAME}"
  if [[ -f "${SKILL_DIR}/SKILL.md" ]]; then
    ok "new skill written: ${SKILL_DIR}/SKILL.md"
    echo
    note "Frontmatter:"
    sed -n '1,/^---$/{/^---$/d;p;}' "${SKILL_DIR}/SKILL.md" | head -15 | sed 's/^/    /'
    echo
    note "Every future engagement against this kind of target will load this card."
    break
  fi
done
pause 4

# Session record — proof the engagement was captured.
LATEST_SESSION="$(ls -1t "${SCARLIGHT_HOME:-$HOME/.scarlight}"/sessions/session_*.json 2>/dev/null | head -1 || true)"
if [[ -n "${LATEST_SESSION}" ]]; then
  ok "session record: $(basename "${LATEST_SESSION}")"
  note "    $(stat -f '%z bytes · %Sm' "${LATEST_SESSION}")"
fi

# ── act 7 — teardown ───────────────────────────────────────────────────
if [[ "${TEARDOWN}" == "1" ]]; then
  banner "Act 7 · teardown"
  "${DEMO_DIR}/stop-lab.sh"
  pause 1
fi

banner "Demo complete"
note "OSS · Apache-2.0 · https://github.com/giannisp09/scarlight"
echo
