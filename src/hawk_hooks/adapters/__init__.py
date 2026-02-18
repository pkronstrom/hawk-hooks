"""Tool adapters for hawk-hooks v2.

Each adapter knows how to sync components to a specific AI CLI tool.
"""

from __future__ import annotations

from ..types import Tool
from .base import ToolAdapter


def get_adapter(tool: Tool) -> ToolAdapter:
    """Get the adapter instance for a tool."""
    from .claude import ClaudeAdapter
    from .gemini import GeminiAdapter
    from .codex import CodexAdapter
    from .opencode import OpenCodeAdapter
    from .cursor import CursorAdapter
    from .antigravity import AntigravityAdapter

    adapters: dict[Tool, type[ToolAdapter]] = {
        Tool.CLAUDE: ClaudeAdapter,
        Tool.GEMINI: GeminiAdapter,
        Tool.CODEX: CodexAdapter,
        Tool.OPENCODE: OpenCodeAdapter,
        Tool.CURSOR: CursorAdapter,
        Tool.ANTIGRAVITY: AntigravityAdapter,
    }

    adapter_cls = adapters.get(tool)
    if adapter_cls is None:
        raise ValueError(f"No adapter for tool: {tool}")
    return adapter_cls()


def list_adapters() -> dict[Tool, ToolAdapter]:
    """Get all available adapters."""
    result = {}
    for tool in Tool.all():
        try:
            result[tool] = get_adapter(tool)
        except (ValueError, ImportError):
            pass
    return result
