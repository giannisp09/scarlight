# ADR 0003 — Tools are MCP servers; protocols are open

**Status:** Accepted
**Date:** 2026-05-13

## Context

Scarlight needs a tool interface. Options:

- Custom Python plugin API (CAI's approach).
- LangChain Tools (popular, Python-only).
- OpenAI function calling JSON schema (model-coupled).
- **Model Context Protocol (MCP)** — Anthropic-originated, open, multi-vendor support, growing ecosystem.

## Decision

- **MCP-native by default.** Every tool — nmap, sqlmap, burp, radare2, pwntools, browser, file ops — is wrapped as an MCP server.
- **MCP servers run inside the worker MicroVM**, exposed over Unix domain socket to the agent loop.
- **Skills can call MCP tools** via a generated typed client.
- **Standing context** uses AGENTS.md / AGENT.md format.
- **Engagement contracts** are signed YAML (Ed25519); the schema is documented and versioned.

## Rationale

- MCP is the emerging interoperability standard. By being MCP-native, Scarlight tools work with every other MCP-aware harness (Claude Code, Gemini CLI, Codex CLI, OpenCode). Conversely, third-party MCP servers (filesystem, web, GitHub, Linear, etc.) work in Scarlight without bespoke integration.
- This avoids the failure mode where every harness builds its own tool API and ecosystems fragment.
- MCP's transport (stdio, SSE, HTTP) is flexible enough for our worker-isolation model.
- Cost: writing an MCP server is more work than a Python function decorator. Mitigated by a Scarlight library that wraps any CLI in an MCP server with one function call.

## Consequences

- Tool authors target MCP, not Scarlight specifically. Bigger ecosystem.
- Tools are interoperable: a Scarlight-developed `sqlmap-mcp` server runs in Claude Code, OpenCode, etc.
- We benefit from the MCP ecosystem (Microsoft MCP, IBM MCP, modelcontextprotocol/servers official implementations).
- A future protocol successor (A2A, ACP) can be supported alongside MCP; the harness should not couple to one.

## Revisit if

- MCP fragments into incompatible vendor extensions.
- A clearly better open protocol emerges and gains the same multi-vendor support.
