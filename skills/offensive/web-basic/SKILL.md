---
name: web-basic
description: "Web-app surface mapping and low-hanging-issue triage on an authorized target: tech fingerprint, content discovery, header / cookie / cert hygiene, and common-file disclosure checks. Stops short of active exploitation."
version: 0.1.0
license: Apache-2.0
author: Scarlight contributors
platforms: [linux, macos]
prerequisites:
  commands: [curl, gobuster]
metadata:
  scarlight:
    tags: [web, recon, fingerprinting, offensive]
    phase: discovery
    related_skills: [recon]
---

# Web-basic — surface map + low-hanging triage

Map the visible structure and configuration of a web application that is in the active engagement scope. Output feeds an exploitation skill (separate). This skill does **not** attempt SQLi, XSS payloads, command injection, or auth bypass — it surfaces signal that justifies (or rules out) trying.

## When to use

- After the [`recon`](../recon/SKILL.md) skill identified an open HTTP/HTTPS port.
- When you need to know what stack you're dealing with before choosing exploitation tooling.
- For CTF web challenges where the source/binary isn't given and you must enumerate from outside.

## Hard prerequisite — authorization

The target URL must be in the active engagement scope. Until the scope guard lands (fork-runbook Step 7), confirm by reading the engagement scope file and checking the host is listed. Refuse if no scope file is loaded. Active web probing is **not** safe by default — gobuster and intrusive header tests can be read as attack traffic.

## Procedure

### 1. Fingerprint the stack

```bash
curl -skI "$URL"
```

Capture: `Server`, `X-Powered-By`, `X-AspNet-Version`, `X-Generator`, framework cookies (`PHPSESSID`, `JSESSIONID`, `connect.sid`, `laravel_session`, `csrftoken`, …). These narrow the exploitation surface fast.

For TLS:

```bash
echo | openssl s_client -connect "${HOST}:443" -servername "$HOST" 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

Note: certificate SANs frequently leak sibling hostnames worth adding to scope (with the operator's approval — do not auto-pivot).

### 2. Check well-known files

```bash
for p in robots.txt sitemap.xml security.txt .well-known/security.txt \
         crossdomain.xml clientaccesspolicy.xml humans.txt; do
  echo "--- $p"
  curl -sk -o- -w "[%{http_code}]\n" "$URL/$p"
done
```

`robots.txt` Disallow paths frequently point at the *interesting* parts of an app. `security.txt` tells you whether responsible-disclosure is invited (changes the engagement posture).

### 3. Header and cookie hygiene

For each interesting endpoint, capture and inspect:

- `Strict-Transport-Security` (present? `max-age` reasonable?)
- `Content-Security-Policy` (present? `unsafe-inline`, wildcard sources?)
- `X-Frame-Options` / frame-ancestors
- `Set-Cookie` flags: `Secure`, `HttpOnly`, `SameSite`
- `Access-Control-Allow-Origin: *` paired with credentialed endpoints

Missing/weak headers and missing cookie flags rarely *are* the bug, but they raise the prior on classes of bugs being exploitable (XSS → cookie theft when `HttpOnly` is missing; CSRF when `SameSite=None` and no token; clickjacking when frame-ancestors is unset).

### 4. Content discovery — light

Use a small, targeted wordlist before reaching for big ones. Big lists generate noise that gets engagements flagged.

```bash
gobuster dir -u "$URL" \
  -w /usr/share/seclists/Discovery/Web-Content/common.txt \
  -t 10 -q -x php,html,js,txt,json \
  -o "web/$HOST-gobuster-common.txt"
```

Notes:
- `-t 10` (10 threads) is intentionally polite. Raising it requires explicit scope authorization.
- If the target is a SPA, also pull `/index.html` and grep its JS bundle URLs — modern apps reveal more from JS than from filesystem path scans.

### 5. JS-source signal (SPAs / API-heavy apps)

```bash
curl -sk "$URL/" | grep -Eo '(href|src)="[^"]+\.js[^"]*"' | sort -u
```

For each bundle, fetch and grep for: API base URLs (`/api/`, `/v1/`, `/graphql`), route definitions, hardcoded keys, debug flags, S3/GCS bucket names, internal hostnames. JS bundles routinely leak more recon than the rendered DOM does.

## Output — what to record

Persist per target:

- Detected stack (server, framework, CMS, language)
- Cookie/session names (helps later auth-related work)
- Header posture summary (which protections are missing)
- Discovered paths and their status codes
- API base paths and any internal-looking hostnames found in JS
- TLS findings (cert SANs, weak algorithms, soon-to-expire dates)

## What this skill is NOT for

- Active exploitation: SQLi, XSS, SSRF, command injection — **separate skill**.
- Auth brute-force / credential stuffing — **separate skill**, requires explicit scope.
- DoS-shaped probing (large gobuster lists, high concurrency) — out of scope.
- Targets not in the engagement scope — refuse, don't run.

When the surface map is clear enough to choose a likely vulnerability class, hand off to the appropriate exploitation skill rather than expanding this one.
