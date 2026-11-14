#!/usr/bin/env python3
"""
Voice Bridge MCP Server.

Exposes the AI phone system as tools any MCP-compatible agent can use
(Claude desktop, Hermes, etc.).

Configuration (env vars or .env file):
    VOICE_BRIDGE_URL      VPS ai-server base URL  (required)
    VOICE_BRIDGE_API_KEY  ai-server API key        (required)
    VOICE_EXTENSION       your SIP extension       (default: 101)
"""
import os
import httpx
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

_URL = os.environ["VOICE_BRIDGE_URL"]
_KEY = os.environ["VOICE_BRIDGE_API_KEY"]
_EXT = os.environ.get("VOICE_EXTENSION", "101")

mcp = FastMCP("voice-bridge")


@mcp.tool()
def call_me() -> str:
    """Call the user's phone and start a live AI voice conversation."""
    r = httpx.post(
        f"{_URL}/trigger/call",
        json={"extension": _EXT},
        headers={"X-API-Key": _KEY},
        timeout=10.0,
    )
    r.raise_for_status()
    return f"Calling extension {_EXT} — pick up your phone."


@mcp.tool()
def call_extension(extension: str) -> str:
    """Call a specific SIP extension and start a voice AI conversation."""
    r = httpx.post(
        f"{_URL}/trigger/call",
        json={"extension": extension},
        headers={"X-API-Key": _KEY},
        timeout=10.0,
    )
    r.raise_for_status()
    return f"Calling extension {extension} — pick up your phone."


if __name__ == "__main__":
    mcp.run()
