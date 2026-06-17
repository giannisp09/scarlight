# Scarlight offensive sandbox image — `scarlight-kali`.
#
# Layered on the same digest-pinned minimal Kali base that
# `scarlight_constants.DEFAULT_TERMINAL_IMAGE` points at. The base is ~120MB and
# ships almost no tools (Kali's minimal-by-design choice); today the agent
# apt-installs what it needs on first use. This image instead BAKES IN the v1.1
# exploitation toolset so a full kill-chain runs without first-use install
# latency and — critically — without defender-visible egress from the *target*
# (linpeas/winpeas/mimikatz are staged here and served target-ward from the
# sandbox, per skills/offensive/CONVENTIONS.md §11).
#
# This image is OPT-IN. DEFAULT_TERMINAL_IMAGE stays on the public base so fresh
# installs work with no build step. To use this image, build it (docker/kali/
# build.sh) and point Scarlight at it:
#     export TERMINAL_DOCKER_IMAGE=scarlight-kali:latest
# or set terminal.docker_image in cli-config.yaml.
#
# Build for linux/amd64 even on Apple Silicon: the offensive payloads
# (mimikatz.exe, winPEASx64.exe, donut x64 shellcode) target x86/x64, and some
# build steps (donut) assume that toolchain. build.sh pins --platform linux/amd64.
#
# Tool inventory and rationale: specs/exploitation-v1/requirements.md §5.2 and
# skills/offensive/CONVENTIONS.md §11.

# Keep this digest in lockstep with scarlight_constants.DEFAULT_TERMINAL_IMAGE.
FROM kalilinux/kali-last-release@sha256:59a4bea68a92b8e2f7b2490345a49784eb11264ceb7deece037e543b2a7dfd73

LABEL org.opencontainers.image.title="scarlight-kali" \
      org.opencontainers.image.description="Scarlight offensive sandbox — Kali base + v1.1 kill-chain toolset" \
      org.opencontainers.image.source="https://github.com/scarlight"

ENV DEBIAN_FRONTEND=noninteractive

# Where target-delivered binaries are staged. The agent serves these from the
# sandbox (e.g. `python3 -m http.server` in this dir) so a compromised target
# curls them over the engagement's own channel — never from github.com directly.
ENV SCARLIGHT_PAYLOAD_DIR=/opt/scarlight/payloads

# Pinned versions for the binaries we fetch at build time. Bump deliberately.
# NOTE: these download-pin ARGs sit above the apt layer for historical cache
# reasons; bumping one re-runs apt. PEASS_VERSION is declared lower (just before
# the payloads layer) so PEASS bumps DON'T re-run apt.
ARG GOPHISH_VERSION=0.12.1
ARG MIMIKATZ_VERSION=2.2.0-20220919
# PowerSploit is archived; pin a commit so PowerUp.ps1 is reproducible.
ARG POWERSPLOIT_REF=d943001a7defb5e0d1657085a77a0e78609be58f

# ---------- Core offensive toolset (apt) ----------
# The §11 "expected in the base" set — NOT actually in minimal Kali — plus the
# lateral-movement extras (netexec/sshpass/evil-winrm) and build deps for the
# git/source tools below.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates curl wget git unzip jq openssl dnsutils whois \
      openssh-client iproute2 iputils-ping netcat-traditional \
      python3 python3-pip python3-venv \
      build-essential gcc make mingw-w64 \
      nmap gobuster \
      sqlmap commix \
      hashcat john hydra \
      metasploit-framework exploitdb \
      python3-impacket impacket-scripts \
      netexec sshpass evil-winrm \
      seclists wordlists && \
    rm -rf /var/lib/apt/lists/*

# rockyou.txt ships gzipped in Kali; unpack it so password-attack can use it
# directly at /usr/share/wordlists/rockyou.txt (validation §2.2 assumes this).
RUN if [ -f /usr/share/wordlists/rockyou.txt.gz ]; then \
      gunzip -k /usr/share/wordlists/rockyou.txt.gz; \
    fi

# ---------- XSStrike (web-exploit) ----------
# Skill bodies invoke /opt/XSStrike/xsstrike.py — clone to that exact path.
RUN git clone --depth 1 https://github.com/s0md3v/XSStrike /opt/XSStrike && \
    pip install --no-cache-dir --break-system-packages \
      -r /opt/XSStrike/requirements.txt

# ---------- donut (payload-craft) ----------
# PE/.NET → position-independent shellcode for in-memory loaders. Build from
# source; expose the binary on PATH.
RUN git clone --depth 1 https://github.com/TheWover/donut /opt/donut && \
    make -C /opt/donut && \
    ln -sf /opt/donut/donut /usr/local/bin/donut

# ---------- gophish (payload-craft, phishing infra GENERATION only) ----------
RUN mkdir -p /opt/gophish && \
    curl -fsSL -o /tmp/gophish.zip \
      "https://github.com/gophish/gophish/releases/download/v${GOPHISH_VERSION}/gophish-v${GOPHISH_VERSION}-linux-64bit.zip" && \
    unzip -q /tmp/gophish.zip -d /opt/gophish && \
    rm -f /tmp/gophish.zip && \
    chmod +x /opt/gophish/gophish && \
    ln -sf /opt/gophish/gophish /usr/local/bin/gophish

# ---------- Target-delivered binaries (staged, not run in sandbox) ----------
# linpeas / winpeas from PEASS-ng latest, mimikatz from gentilkiwi, PowerUp.ps1
# from the archived PowerSploit. Served target-ward by the agent; see §11.
#
# PEASS-ng release tag, pinned (not `latest`) for reproducibility. Declared here
# (below apt) so a PEASS bump rebuilds only this layer, not the apt layer.
# linpeas.sh + winPEASx64.exe are release assets; winPEAS.ps1 is NOT published as
# an asset, so it's pulled from the repo tree at the same tag.
ARG PEASS_VERSION=20260604-085abf96
RUN mkdir -p "${SCARLIGHT_PAYLOAD_DIR}" && \
    curl -fsSL -o "${SCARLIGHT_PAYLOAD_DIR}/linpeas.sh" \
      "https://github.com/peass-ng/PEASS-ng/releases/download/${PEASS_VERSION}/linpeas.sh" && \
    curl -fsSL -o "${SCARLIGHT_PAYLOAD_DIR}/winPEASx64.exe" \
      "https://github.com/peass-ng/PEASS-ng/releases/download/${PEASS_VERSION}/winPEASx64.exe" && \
    curl -fsSL -o "${SCARLIGHT_PAYLOAD_DIR}/winPEAS.ps1" \
      "https://raw.githubusercontent.com/peass-ng/PEASS-ng/${PEASS_VERSION}/winPEAS/winPEASps1/winPEAS.ps1" && \
    curl -fsSL -o "${SCARLIGHT_PAYLOAD_DIR}/PowerUp.ps1" \
      "https://raw.githubusercontent.com/PowerShellMafia/PowerSploit/${POWERSPLOIT_REF}/Privesc/PowerUp.ps1" && \
    curl -fsSL -o /tmp/mimikatz.zip \
      "https://github.com/gentilkiwi/mimikatz/releases/download/${MIMIKATZ_VERSION}/mimikatz_trunk.zip" && \
    unzip -q -j /tmp/mimikatz.zip "x64/mimikatz.exe" -d "${SCARLIGHT_PAYLOAD_DIR}" && \
    rm -f /tmp/mimikatz.zip && \
    chmod 0644 "${SCARLIGHT_PAYLOAD_DIR}"/* && \
    chmod 0755 "${SCARLIGHT_PAYLOAD_DIR}/linpeas.sh"

# Quick self-check that the core tools resolve on PATH. Fails the build early if
# an apt name drifted. (Staged .exe payloads are intentionally NOT executed.)
RUN for t in nmap sqlmap commix hashcat john hydra msfconsole searchsploit \
             gobuster netexec sshpass donut gophish; do \
      command -v "$t" >/dev/null || { echo "MISSING TOOL: $t" >&2; exit 1; }; \
    done && \
    test -f /opt/XSStrike/xsstrike.py && \
    test -f "${SCARLIGHT_PAYLOAD_DIR}/linpeas.sh" && \
    test -f "${SCARLIGHT_PAYLOAD_DIR}/mimikatz.exe"

WORKDIR /root
CMD ["/bin/bash"]
