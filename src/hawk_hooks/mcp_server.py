"""FastMCP server for hawk-hooks.

Thin wrapper that creates the MCP server, registers the single 'hawk' tool,
and delegates to mcp_handler.handle_action().

Usage:
    hawk mcp          # starts stdio server
"""

from __future__ import annotations

from fastmcp import FastMCP

from .mcp_handler import handle_action

mcp = FastMCP(
    "hawk",
    instructions=(
        "Hawk component manager. Single tool with action dispatch.\n"
        "Use action='describe' to see all available actions and their parameters.\n"
        "Use action='describe', params={action_name: '<name>'} for details on one action.\n"
        "Actions: describe, list, status, list_packages, add, remove, "
        "enable, disable, sync, download, update, remove_package."
    ),
)


@mcp.tool(
    description=(
        "Hawk component manager: manage skills, hooks, commands, agents, "
        "MCP servers, and prompts for AI tools.\n\n"
        "Use action='describe' to see all available actions and parameters."
    ),
)
async def hawk(action: str, params: dict | None = None) -> dict:
    """Dispatch a hawk action."""
    data = {**(params or {}), "action": action}
    return await handle_action(data)
