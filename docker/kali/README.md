# `scarlight-kali` — offensive sandbox image

The v1.1 exploitation skills (`web-exploit`, `password-attack`, `service-exploit`,
`payload-craft`, `privesc-linux`, `privesc-windows`, `credential-harvest`,
`lateral-movement`) run their tools inside the agent's terminal sandbox. The
default sandbox — `kalilinux/kali-last-release`, pinned in
`scarlight_constants.DEFAULT_TERMINAL_IMAGE` — is **minimal by design** (~120MB)
and ships almost none of those tools; today the agent apt-installs each on first
use.

This image bakes the whole kill-chain toolset into one Kali-based image so:

- a full engagement runs with no first-use install latency, and
- target-delivered binaries (linpeas/winpeas/mimikatz/PowerUp) are **staged in
  the sandbox** and served target-ward over the engagement's own channel —
  never curled from `github.com` on the target, which is defender-visible egress
  (see [`skills/offensive/CONVENTIONS.md`](../../skills/offensive/CONVENTIONS.md) §11).

## What's in it

Layered on the same pinned Kali base as `DEFAULT_TERMINAL_IMAGE`:

| Category | Tools |
|---|---|
| Recon / web | `nmap`, `gobuster`, `sqlmap`, `commix`, `XSStrike` (`/opt/XSStrike`) |
| Cracking | `hashcat`, `john` (incl. `keepass2john`/`unshadow`), `hydra` |
| Exploitation | `metasploit-framework` (`msfconsole`/`msfvenom`), `exploitdb` (`searchsploit`) |
| Post-ex / creds | `impacket-scripts` (`secretsdump` etc.), `netexec`, `evil-winrm`, `sshpass` |
| Payloads | `donut` (`/usr/local/bin/donut`), `gophish` (`/opt/gophish`, generation only) |
| Wordlists | `seclists`, `wordlists`, unpacked `rockyou.txt` |
| Staged for targets | `$SCARLIGHT_PAYLOAD_DIR` (`/opt/scarlight/payloads`): `linpeas.sh`, `winPEASx64.exe`, `winPEAS.ps1`, `PowerUp.ps1`, `mimikatz.exe` |

The build ends with a self-check that every core tool resolves on PATH, so an
apt-name drift fails the build instead of an engagement.

## Build

```bash
docker/kali/build.sh            # → scarlight-kali:latest (linux/amd64)
docker/kali/build.sh --digest   # also print image id / repo digests
```

Built for **linux/amd64** on purpose (the Windows/x64 payloads and the `donut`
toolchain assume it); on Apple Silicon it builds under emulation.

## Use it

The image is **opt-in**. `DEFAULT_TERMINAL_IMAGE` stays on the public base so a
fresh install needs no build. To switch the sandbox to this image:

```bash
export TERMINAL_DOCKER_IMAGE=scarlight-kali:latest
scarlight chat
```

or set `terminal.docker_image: scarlight-kali:latest` in `cli-config.yaml`.

## Pinning / publishing

A local build has no registry digest, so it can't be digest-pinned the way
`DEFAULT_TERMINAL_IMAGE` is. Once this image is published to a registry
(e.g. GHCR), capture the manifest-list digest with
`docker buildx imagetools inspect <ref>` and — if it becomes the default —
update `DEFAULT_TERMINAL_IMAGE`. Until then it's an explicit per-operator opt-in.

Bump baked binary versions via the `ARG`s at the top of the `Dockerfile`
(`GOPHISH_VERSION`, `MIMIKATZ_VERSION`, `POWERSPLOIT_REF`); linpeas/winpeas track
PEASS-ng `latest`.
