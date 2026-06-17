#!/usr/bin/env bash
# Build the Scarlight offensive sandbox image (`scarlight-kali`).
#
# Builds for linux/amd64 regardless of host arch — the baked offensive payloads
# (mimikatz.exe, winPEASx64.exe, donut x64 shellcode) target x86/x64, and donut
# builds against that toolchain. On Apple Silicon this runs under emulation.
#
# Usage:
#   docker/kali/build.sh                 # build scarlight-kali:latest
#   TAG=scarlight-kali:2026-06 docker/kali/build.sh
#   docker/kali/build.sh --digest        # build, then print the local image digest
#
# After building, point Scarlight at it for offensive work:
#   export TERMINAL_DOCKER_IMAGE=scarlight-kali:latest
# or set terminal.docker_image in cli-config.yaml. DEFAULT_TERMINAL_IMAGE is left
# on the public base so fresh installs need no build.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG="${TAG:-scarlight-kali:latest}"
PLATFORM="${PLATFORM:-linux/amd64}"

echo "==> Building ${TAG} (${PLATFORM}) from ${HERE}/Dockerfile"
docker build \
  --platform "${PLATFORM}" \
  -t "${TAG}" \
  -f "${HERE}/Dockerfile" \
  "${HERE}"

echo "==> Built ${TAG}"

if [[ "${1:-}" == "--digest" ]]; then
  echo "==> RepoDigests (publish to a registry to get a pinnable digest):"
  docker image inspect "${TAG}" --format '{{json .RepoDigests}}' || true
  echo "==> Local image ID:"
  docker image inspect "${TAG}" --format '{{.Id}}'
fi

cat <<EOF

Next:
  export TERMINAL_DOCKER_IMAGE=${TAG}
  scarlight chat        # offensive tools now resolve inside the sandbox

Verify the toolset inside the image:
  docker run --rm --platform ${PLATFORM} ${TAG} \\
    bash -lc 'for t in nmap sqlmap hashcat msfconsole searchsploit netexec donut gophish; do command -v \$t; done'
EOF
