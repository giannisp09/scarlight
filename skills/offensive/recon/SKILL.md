---
name: recon
description: "Basic offensive recon: enumerate hosts, open ports, services, and tech fingerprints on an authorized target. Non-destructive scans only; produces a findings record the next skill (e.g. web-basic, exploit) builds on."
version: 0.1.0
license: Apache-2.0
author: Scarlight contributors
platforms: [linux, macos]
prerequisites:
  commands: [nmap, dig, whois]
metadata:
  scarlight:
    tags: [recon, enumeration, nmap, offensive]
    phase: discovery
    related_skills: [web-basic]
---

# Recon — basic enumeration

Map an authorized target's externally-visible attack surface so later skills (web exploitation, service-specific exploitation, lateral movement) can act with grounded knowledge instead of guesses.

This skill is **passive-to-light-active only**. No DoS, no credential brute-force, no destructive nmap scripts. If the engagement needs deeper or more intrusive recon, *create a new skill* — don't grow this one.

## When to use

- Start of an engagement against a host or small set of hosts that are in scope.
- When the target list is known but service/port topology is not.
- Before any exploitation skill — exploitation without recon wastes turns and tips off detection.

## Hard prerequisite — authorization

Before any command in this skill runs, the agent **must** confirm the target is in the active engagement scope. Until the engagement-scope guard lands (fork-runbook Step 7), confirm by:

1. Reading the user-supplied scope file (`engagement.toml` / equivalent) into context.
2. Checking the target hostname or CIDR is explicitly listed.
3. Refusing to proceed if no scope file is loaded.

Out-of-scope recon is a contract violation regardless of how non-destructive the commands are.

## Procedure

### 1. Host liveness + DNS context

```bash
dig +short A   "$TARGET"
dig +short AAAA "$TARGET"
dig +short MX  "$TARGET"
whois "$TARGET" | head -40
```

Capture: resolved IP(s), MX records, registrar, ASN, org name. These shape the rest of the engagement (cloud-hosted vs on-prem, hosting provider quirks, related domains).

### 2. Top-port sweep — fast pass

```bash
nmap -sS -Pn --top-ports 100 -T3 -oN "recon/$TARGET-top100.nmap" "$TARGET"
```

Notes:
- `-sS` (SYN) requires root; if unavailable, fall back to `-sT` (TCP connect).
- `-Pn` skips host-discovery ping — many targets block ICMP and would otherwise be misreported as down.
- `-T3` is the polite default. **Do not raise to `-T4`/`-T5` unless the scope file explicitly authorizes faster scanning** — aggressive timing can be read as DoS.

### 3. Service + version detection on open ports

After the sweep identifies open ports, fingerprint just those:

```bash
PORTS=$(awk '/open/{split($1,p,"/"); printf "%s,",p[1]}' "recon/$TARGET-top100.nmap")
nmap -sV -Pn -p "${PORTS%,}" -oN "recon/$TARGET-services.nmap" "$TARGET"
```

Capture per port: service name, product, version, banner. Versions feed CVE lookups; banners feed misconfiguration checks.

### 4. Light fingerprinting on web ports (only if 80/443/8080/8443 are open)

```bash
curl -skI "https://$TARGET/"        # headers, server, framework hints
curl -sk  "https://$TARGET/robots.txt"
curl -sk  "https://$TARGET/sitemap.xml"
```

If a web port is open, hand off to the [`web-basic`](../web-basic/SKILL.md) skill rather than going deeper here.

## Output — what to record

Persist (via the agent's memory layer) one record per engagement target:

- Resolved IPs, ASN/org, registrar
- Open ports with service/product/version
- Web tech hints (server header, framework, CMS) if applicable
- Timestamp + scan parameters used (so re-runs are reproducible)
- Anything anomalous (filtered ports clustered weirdly, mismatched banners, expired certs)

## What this skill is NOT for

- Brute-force / credential spraying — out of scope, separate skill.
- Vulnerability *exploitation* — recon stops at fingerprinting.
- Destructive nmap scripts (`--script vuln`, `--script intrusive`, `--script dos`) — never from this skill.
- Targets not in the active engagement scope — refuse, don't run.
