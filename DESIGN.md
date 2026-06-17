# Scarlight — DESIGN.md

> Stitch design brief for the Scarlight desktop application (Tauri/Electron shell) and the web companion (Vite/React, same component system). One product, one design language, two delivery surfaces.

---

## 1. Product overview

**Scarlight is the operator console for cyber superintelligence — a self-improving, scope-aware agent for authorized offensive security work.**

It is not a chatbot. It is an **instrument panel for an autonomous adversary you own**: an agent that runs reconnaissance, exploitation, post-exploitation, and lateral movement on systems you are *authorized* to test, while writing its own skills, remembering past engagements, and getting measurably better with every run.

The UI must communicate three ideas at all times:

1. **This is offensive-security infrastructure, not a toy.** Every action is scoped, signed, audited. The shell looks closer to a SOC console or a satellite-ops dashboard than a consumer chat app.
2. **The agent compounds.** The user sees, in real time, the skill library growing, memory accumulating, and the agent's capability curve climbing.
3. **The operator is in command.** Scope, authorization, kill-switch, and audit are first-class surfaces — never buried in settings.

The product tagline lives in the empty state: **"An adversary that learns. Under your authorization."**

---

## 2. Target users

- **Penetration testers** running engagements under signed scope.
- **Bug bounty hunters** working inside published program rules.
- **CTF competitors** clearing boxes against event infrastructure.
- **Red teamers** running authorized adversary-emulation.
- **Security researchers** running their own labs.

They are technical, terminal-fluent, and skeptical of "AI security" hype. The UI should reward fluency — keyboard-first, dense, no condescending tooltips — while still making the agent's autonomous behavior legible at a glance.

---

## 3. Design language

### Visual identity

- **Mood:** mission-control after-hours. Dark, low-light, high-signal. Think Stripe radar × Wireshark × a Nostromo console.
- **Palette:**
  - Background: deep near-black `#070A0E` with a faint 1px hairline grid (~`#0F141A`) to evoke a CRT / oscilloscope graticule.
  - Surface: `#0D1218` panels with `#1A2230` borders.
  - Primary accent: **scarlight crimson** `#FF3D55` — used *sparingly*, only for live/armed/active state and the wordmark.
  - Secondary accent: **signal cyan** `#5DE5FF` — used for agent output, links, model identity.
  - Success / authorized: muted phosphor green `#3FE08C`.
  - Warning / risk: amber `#FFB347`.
  - Danger / blocked / unauthorized: hot red `#FF5C5C` with a stop-icon glyph.
  - Text primary: `#E6EDF3`. Text muted: `#7B8794`.
- **Typography:**
  - UI: Inter / Geist Sans.
  - Code, command, audit log, IPs, hashes, tokens: JetBrains Mono / Berkeley Mono.
  - The wordmark "SCARLIGHT" is set in a slightly wider monospace, all caps, letter-spaced.
- **Iconography:** thin-stroke, 1.5px, lucide-style. Custom glyphs for: *engagement*, *skill*, *target*, *scope-seal*, *kill-switch*, *audit*.
- **Motion:** restrained. Status changes use a 120ms ease-out fade + a 1px border-glow pulse on armed/active panels. No bouncy spring animations. The interface should feel like a *console*, not a marketing site.
- **Texture:** the empty state, login, and engagement-start screens carry a faint scanline / phosphor flicker (~3% opacity) — present but never distracting.

### Tone of UI copy

Terse, accurate, operator-grade. Imperative verbs. No "Oops!", no "Let's get started!". Examples:

- Empty state: *"No engagement loaded. Sign a scope to arm the agent."*
- Blocked target: *"Refused. `192.0.2.4` is not in the active scope."*
- Skill written: *"Scarlight wrote a new skill: `juice-shop-fingerprint`. Promoted to library."*

---

## 4. Information architecture

Scarlight uses a **three-pane shell** on every screen: left navigation, center work surface, right telemetry. This is the same layout on desktop (Tauri window, native chrome) and web (full-bleed, browser chrome). The shell is responsive: below 1280px the right pane collapses to a slide-over; below 960px the left pane collapses to a rail.

### Top-level navigation (left sidebar)

The left sidebar has two stacked sections.

**A. Engagement switcher (top half)**

- **Active engagement badge** — replaces the model picker from the reference. Shows the engagement name (e.g. `acme-q2-pentest`), a scope-seal icon, and the authorization status dot (green = signed, amber = unsigned-lab, red = expired).
- **Search bar** — `⌘K` palette. Searches across engagements, targets, skills, findings, audit entries.
- **Engagement history list** — recent engagements, with a tiny sparkline of activity. Click to switch context. New-engagement `+` button top-right.

**B. Primary navigation (bottom half, fixed)**

| # | Tab | Glyph | Purpose |
|---|-----|-------|---------|
| 1 | **Console** | terminal | Live agent REPL — the "chat" surface, but for an offensive agent. |
| 2 | **Engagements** | crosshair | Mission browser — past and active engagements, ROE, scope, timeline. |
| 3 | **Targets** | globe-network | The target graph — hosts, services, creds, findings discovered so far. |
| 4 | **Codex** | book-circuit | The skill library — every skill the agent can run, including ones it wrote itself. |
| 5 | **Memory** | brain-grid | Cross-session memory — what the agent remembers about operators, targets, tradecraft. |
| 6 | **Audit** | seal | Signed, append-only audit log of every exploitation action. Exportable. |
| 7 | **Lab** | flask | One-click lab environments (Juice Shop, DVWA, Metasploitable, HTB Starting Point) for training the agent. |
| 8 | **Settings** | sliders | Models, providers, sandboxes, deployment mode (air-gapped / local / hybrid / cloud), keys. |
| 9 | **Get Started** | compass | Onboarding, scope-signing walkthrough, CODE_OF_USE.md anchor. |

### Right pane (telemetry rail) — global

The right pane is **"OPERATIONS"** and is always present (collapsible). It is the analogue of OpenJarvis's "SYSTEM" panel, re-aimed at offensive ops. It has five fixed sections:

1. **SCOPE** — the most important panel in the entire app.
   - Engagement name.
   - Authorization status (signed / expired / lab / `--no-scope` warning banner).
   - Permitted targets (count + first 3, "view all").
   - Permitted risk level (`passive` / `active` / `destructive`).
   - A red **KILL** button — immediate abort of all agent activity. Confirms with `⌘⇧K`.

2. **AGENT** — live state.
   - Current model + provider (e.g. `claude-opus-4-7` via Anthropic, or `qwen3:32b` via local Ollama).
   - Current skill being executed, with a 1-line stop-condition.
   - Coordinator depth (1 / 2 / 3) and worker count, when fan-out is active.

3. **ENGAGEMENT METRICS** — this session.
   - Requests, output tokens (mirroring the reference).
   - Findings count (severity-binned: crit / high / med / low / info).
   - Skills used / **skills written** (the compounding signal — emphasize).
   - Wall-clock + cost.

4. **COST & MODEL COMPARISON** — same shape as the reference (Local / Claude / GPT / Gemini) but extended with a "session cost so far" and a "local-mode would have cost $0" callout when running cloud.

5. **AUDIT TAIL** — last 5 audit-log entries, scrolling. Click to jump to the Audit tab pre-filtered.

### Bottom command bar (global)

A single-row bar pinned to the bottom of the work surface (the equivalent of OpenJarvis's message input), but operator-grade:

- **Slash-command palette** on the left (`/recon`, `/exploit`, `/skill new`, `/scope show`, `/kill`).
- **Risk-level chip** — current run's permitted risk (`passive` / `active` / `destructive`), color-coded.
- **Prompt input** — multiline, monospace, with `↵` to send, `⇧↵` for newline.
- **Mic** (for desktop only — voice-to-prompt, off by default for opsec).
- **Send / Arm** button — label flips between *Send* (chat) and *ARM* (when the next command will trigger an active-exploitation skill). Arming requires holding the button for 600ms (deliberate-action affordance).

---

## 5. Screens — detailed

### 5.1 Console (default screen)

The center surface is a hybrid terminal/chat. It is **not** a bubble-style chat.

- **Empty state** — centered sigil (the Scarlight wordmark over a single horizontal hairline) + the line *"An adversary that learns. Under your authorization."* + four quick-start cards: `Load Engagement`, `Spin Up Lab`, `Browse Codex`, `Read CODE_OF_USE`.
- **Active state** — a single scrolling transcript in monospace. Each turn is one of:
  - **Operator** — left-aligned, dim chevron `>` prefix, white text.
  - **Agent** — left-aligned, cyan glyph prefix, no avatar.
  - **Tool call** — a collapsible card: tool name, args (redacted by default — secrets masked), exit code, stdout/stderr in a `<pre>`.
  - **Skill invocation** — a richer card with skill name, risk level, target, stop-condition, live progress, and an inline link to the audit entry.
  - **Finding** — a severity-tagged callout (red/amber/green border-left) with title, evidence, and a "promote to report" action.
  - **Skill writeback** — a celebratory but restrained banner: *"Scarlight wrote `juice-shop-fingerprint`. +1 skill in Codex."*
- **Above the transcript:** a thin breadcrumb — `Engagement › Target › Current Phase` (Recon / Initial Access / Post-Exploitation / Lateral / Reporting).
- **Right pane** shows the live OPERATIONS rail described above.

### 5.2 Engagements

- A table of past + active engagements: name, client/lab, scope summary, start date, status, findings count, skills-written count, last-active.
- Click a row → an engagement detail view with four sub-tabs: **Overview**, **Scope (ROE)**, **Timeline**, **Report draft**.
- The **Scope (ROE)** sub-tab renders the `engagement.yaml` as a human-readable card: targets, permitted/forbidden actions, time window, signing identity, expiry. A "Re-sign" button regenerates the signature.
- A `+ New engagement` button launches a wizard: client name → scope import (paste YAML / drag file / pick lab preset) → authorization confirmation → arm.

### 5.3 Targets

- A **target graph** (force-directed) is the hero element: hosts as nodes, services as sub-nodes, credentials/findings as attached chips. Edges show observed reachability and pivots.
- Sidebar lists targets in a tree (subnet → host → service → finding).
- Selecting a node opens a detail drawer: open ports, fingerprinted software, known CVEs, credentials harvested (masked), exploitation history, attached audit entries.
- Out-of-scope IPs are rendered struck-through with a red "REFUSED" badge — visible proof the scope guard fired.

### 5.4 Codex (skill library)

- A grid of skill cards. Each card: name, risk-level chip (`passive` / `active` / `destructive`), category (recon / web-exploit / privesc / lateral / …), invocation count, last-used, **and an "AUTHORED BY: Scarlight" badge** when the skill was written by the agent itself.
- Filters: risk level, category, hand-authored vs. agent-authored, last-modified.
- Click a card → full skill view: SKILL.md rendered, code preview, history (every diff Scarlight made to it), usage analytics.
- Top of page: a live **"Codex growth"** sparkline — total skill count over time. This is the compounding signal made visible.

### 5.5 Memory

- Three tabs: **Operator** (what Scarlight remembers about *you* — your preferences, tradecraft, past missions), **Targets** (cross-engagement target memory), **Sessions** (full-text-searchable transcripts of every past run).
- Memory entries are editable and deletable — operator stays in control.
- Search is `⌘K`-accessible from anywhere.

### 5.6 Audit

- A monospace, append-only log table. Columns: timestamp (ISO-8601 UTC), engagement, target, skill, risk-level, exit-code, signature.
- Filter chips at top: engagement, risk-level, date range, target.
- Every row expands to show full args, stdout/stderr, and the signed-hash chain.
- Top-right: **Export** (JSONL, CSV, signed PDF for reports).
- A persistent banner at the top reminds the operator: *"Audit log is append-only. Entries cannot be edited or deleted."*

### 5.7 Lab

- Card grid of one-click lab environments: OWASP Juice Shop, DVWA, Metasploitable 2/3, HTB Starting Point box, custom Docker Compose.
- Each card: status (running / stopped), reachable IP, recommended risk level, "Arm engagement against this lab" CTA.
- Spinning up a lab auto-creates a pre-signed `engagement.yaml` with the lab's IP in scope.

### 5.8 Settings

- Sections: **Models & providers** (Anthropic, OpenAI, Google, Ollama, vLLM, SGLang, MLX — local-first highlighted), **Deployment mode** (`air_gapped` / `local_default` / `hybrid` / `cloud`), **Sandbox** (Docker / microVM / native), **Keys & secrets** (stored in OS keychain on desktop; encrypted at rest on web), **Telemetry** (opt-in only), **Appearance**, **Keyboard**.
- The deployment-mode picker is a four-card radio — air-gapped is the recommended default, prominently styled.

### 5.9 Get Started

- A linear onboarding: (1) read & accept CODE_OF_USE; (2) pick deployment mode; (3) configure first provider; (4) load or sign first scope; (5) launch first lab engagement.
- Skippable for power users but the CODE_OF_USE step is **non-skippable** and the accept button is disabled until scroll-to-bottom.

---

## 6. Component system

- **Panel** — `#0D1218` surface, 1px `#1A2230` border, 12px radius, 16px inner padding. Optional 1px crimson border-glow when armed.
- **Chip** — small pill with a colored dot prefix. Variants: `scope-ok`, `scope-warn`, `scope-blocked`, `risk-passive`, `risk-active`, `risk-destructive`, `model-local`, `model-cloud`.
- **Severity callout** — left-border 3px in severity color, monospace title, evidence in a nested `<pre>`.
- **Tool-call card** — collapsible, monospace header with tool name + duration + exit code; body is stdout/stderr.
- **Skill card** — Codex grid item, described above.
- **Metric tile** — number + unit + label, optionally with a sparkline below (matches the reference's `Requests` / `Power` tiles).
- **Kill button** — square, red, with a stop glyph. Always visible in OPERATIONS pane. Confirms via `⌘⇧K` modifier-hold to avoid mis-clicks.
- **Slash-command palette** — `⌘K` modal, fuzzy-searchable, with inline argument hints.

---

## 7. States to design explicitly

Stitch should render mocks for each of the following — they are the moments that define Scarlight's character:

1. **Empty state — no engagement loaded.** Scope is null, KILL is dimmed, prompt input is disabled, copy invites the operator to sign or load a scope.
2. **Scope refusal.** Operator targets `8.8.8.8`; Console renders a red `REFUSED — out of scope` block; right pane SCOPE panel pulses red briefly; audit log gets an entry.
3. **Live exploitation.** Mid-engagement, an `web-exploit` skill is running against a lab target. Console shows live tool output; OPERATIONS pane shows current skill, risk chip is amber, KILL button is armed (full red).
4. **Skill writeback.** The agent has just authored a new skill. Console shows the celebratory banner; Codex tab badge animates a `+1`.
5. **Air-gapped mode.** A subtle "AIR-GAPPED" chip is pinned in the top-right; cloud model rows in COST COMPARISON are greyed with a lock icon.
6. **`--no-scope` mode (CTF / training).** A persistent amber banner across the top: *"Running without engagement scope. Authorized for personal labs / CTF only."*

---

## 8. Desktop-only vs. web-only affordances

- **Desktop (Tauri):** native menu bar (File / Engagement / Agent / View / Window / Help), global hotkey for KILL (`⌘⇧K`), OS keychain for secrets, native file-drop for `engagement.yaml`, system-tray icon with engagement status dot.
- **Web:** same shell, but secrets are entered per-session and stored encrypted in IndexedDB with a session passphrase. Engagement files are uploaded. A persistent banner advises desktop for production engagements.

Both surfaces share 100% of the component system; only the chrome and the secret-storage layer differ.

---

## 9. North-star screen for Stitch to anchor on

If Stitch generates only one screen first, generate the **Console — live exploitation** state:

- Left sidebar: `acme-q2-pentest` active engagement badge with green scope-seal, search bar, two recent engagements, primary nav.
- Center: breadcrumb `acme-q2-pentest › 10.10.10.42 › Initial Access`. Transcript shows: operator prompt → agent reasoning → a `web-exploit.sqli` skill card mid-run with live stdout → a high-severity finding callout → a "Scarlight wrote a new skill: `acme-login-bypass`" banner.
- Bottom command bar: `/exploit` slash chip, `risk: active` amber chip, prompt input, **ARM** button (deliberate-hold).
- Right OPERATIONS rail: SCOPE green, AGENT showing `claude-opus-4-7` + current skill, ENGAGEMENT METRICS (12 findings, 3 skills written), COST COMPARISON with local highlighted, AUDIT TAIL scrolling.

That single screen, rendered well, communicates the entire product: a scope-sealed, model-flexible, self-improving offensive-security agent — under operator command.

---

## 10. What this design must never look like

- A consumer chatbot with a sidebar.
- A SOC / SIEM dashboard (we are not defensive; the visual cues should be *adversarial*, not protective).
- A "hacker aesthetic" parody — no green Matrix rain, no skulls, no glitch fonts. Scarlight is a serious instrument; the restraint *is* the aesthetic.
- A marketing site. No hero gradient, no testimonial carousel, no pricing tiles inside the app.

The product is an operator console for a learning adversary. Every pixel should earn its place against that brief.
