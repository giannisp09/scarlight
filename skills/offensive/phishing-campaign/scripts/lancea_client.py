#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.0"]
# ///
"""Thin MCP-over-HTTP client for Lancea — a dumb typed transport.

Scarlight's `phishing-campaign` skill drives Lancea (the authorized
social-engineering platform) by calling its MCP tools. Lancea ships
"no agent loop of its own — bring your own agent"; Scarlight IS that
agent. This script carries one tool call over the streamable-HTTP MCP
transport and prints the result as JSON. It makes NO decisions: the
agent composes the arguments (per references/lancea-tools.md) and
interprets the output. All judgement — lure copy, cadence, reading
stats — stays in the agent; this file is the wire.

Because it ships a PEP 723 inline-metadata header, it is launched with
`uv run` and needs nothing pre-installed (uv builds an ephemeral env
with `mcp`). It imports NOTHING from the Lancea codebase, so it stays
clean of Lancea's separate (proprietary) license.

Endpoint resolution (first wins):
    --url  >  $LANCEA_MCP_URL  >  http://127.0.0.1:8743/v1/mcp

Usage:
    # convenience verbs
    lancea_client.py health
    lancea_client.py list-tools

    # generic transport — the agent supplies the JSON args
    lancea_client.py call create_engagement --json '{"scope_path": "/abs/lab.signed.toml"}'
    lancea_client.py call ingest_targets   --json-file /tmp/ingest.json
    lancea_client.py call render_lure       --stdin   < /tmp/render.json
    lancea_client.py call query_events      --json '{"engagement_id": "lab-2026", "include_sends": true}'

Argument wrapping: every Lancea tool except `health` takes a single
`payload:` model, so the wire arguments are {"payload": <your-json>}.
This script wraps automatically; pass --no-wrap to send <your-json> at
the top level (escape hatch for any future non-payload tool).

Exit codes: 0 ok · 1 tool/server error · 2 usage / connection error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# Lancea mounts FastMCP (default path `/mcp`) under `/v1/mcp`, so the
# streamable-HTTP endpoint is the doubled `/v1/mcp/mcp`.
DEFAULT_URL = "http://127.0.0.1:8743/v1/mcp/mcp"


def _eprint(*a: object) -> None:
    print(*a, file=sys.stderr)


def _resolve_url(cli_url: str | None) -> str:
    return cli_url or os.environ.get("LANCEA_MCP_URL") or DEFAULT_URL


def _load_args(ns: argparse.Namespace) -> dict[str, Any]:
    """Read the tool arguments from --json / --json-file / --stdin."""
    sources = [bool(ns.json), bool(ns.json_file), bool(ns.stdin)]
    if sum(sources) > 1:
        _eprint("error: pass at most one of --json / --json-file / --stdin")
        raise SystemExit(2)
    raw: str | None = None
    if ns.json:
        raw = ns.json
    elif ns.json_file:
        try:
            with open(ns.json_file, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            _eprint(f"error: cannot read --json-file {ns.json_file}: {exc}")
            raise SystemExit(2) from exc
    elif ns.stdin:
        raw = sys.stdin.read()
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        _eprint(f"error: arguments are not valid JSON: {exc}")
        raise SystemExit(2) from exc
    if not isinstance(parsed, dict):
        _eprint("error: tool arguments must be a JSON object")
        raise SystemExit(2)
    return parsed


def _extract(result: Any) -> Any:
    """Pull the structured payload out of an mcp CallToolResult.

    Prefer `structuredContent` (Lancea tools return dicts/lists); fall
    back to JSON-decoding the first text content block, then to the raw
    text. Mirrors the extraction the Lancea integration tests use.
    """
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, (dict, list)):
        return structured
    content = getattr(result, "content", None)
    if content:
        for block in content:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
    return None


async def _call(url: str, tool: str, arguments: dict[str, Any]) -> tuple[bool, Any]:
    # Imported lazily so --help works even before uv resolves `mcp`.
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            return bool(getattr(result, "isError", False)), _extract(result)


async def _list_tools(url: str) -> list[dict[str, str]]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            out: list[dict[str, str]] = []
            for tool in listing.tools:
                desc = (tool.description or "").strip().splitlines()
                out.append({"name": tool.name, "summary": desc[0] if desc else ""})
            return out


def _run(coro: Any) -> Any:
    import anyio

    try:
        return anyio.run(lambda: coro)
    except Exception as exc:  # noqa: BLE001 — surface any transport error cleanly
        _eprint(f"error: MCP call failed against the Lancea server: {exc}")
        _eprint("hint: is `lancea server start` running and is LANCEA_MCP_URL correct?")
        raise SystemExit(2) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lancea_client.py",
        description="Thin MCP-over-HTTP transport for driving Lancea from Scarlight.",
    )
    parser.add_argument(
        "--url",
        default=None,
        help=f"Lancea MCP endpoint (default: $LANCEA_MCP_URL or {DEFAULT_URL}).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="Probe the server (no arguments).")
    sub.add_parser("list-tools", help="List the Lancea MCP tools the server exposes.")

    p_call = sub.add_parser("call", help="Call one Lancea MCP tool by name.")
    p_call.add_argument("tool", help="MCP tool name, e.g. create_engagement.")
    p_call.add_argument("--json", default=None, help="Inline JSON object of arguments.")
    p_call.add_argument("--json-file", default=None, help="Path to a JSON args file.")
    p_call.add_argument(
        "--stdin", action="store_true", help="Read JSON arguments from stdin."
    )
    p_call.add_argument(
        "--no-wrap",
        action="store_true",
        help="Send args at the top level instead of under `payload`.",
    )

    ns = parser.parse_args(argv)
    url = _resolve_url(ns.url)

    if ns.cmd == "health":
        is_err, payload = _run(_call(url, "health", {}))
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return 1 if is_err else 0

    if ns.cmd == "list-tools":
        tools = _run(_list_tools(url))
        print(json.dumps(tools, indent=2, sort_keys=True))
        return 0

    # ns.cmd == "call"
    args = _load_args(ns)
    if ns.tool == "health":
        arguments: dict[str, Any] = {}
    elif ns.no_wrap:
        arguments = args
    else:
        arguments = {"payload": args}

    is_err, payload = _run(_call(url, ns.tool, arguments))
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    if is_err:
        _eprint(f"error: Lancea tool `{ns.tool}` returned an error result.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
