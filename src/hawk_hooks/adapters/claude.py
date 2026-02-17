"""Claude Code adapter for hawk-hooks v2."""

from __future__ import annotations

from pathlib import Path

from ..types import Tool
from .base import HAWK_MCP_MARKER, ToolAdapter


class ClaudeAdapter(ToolAdapter):
    """Adapter for Claude Code."""

    @property
    def tool(self) -> Tool:
        return Tool.CLAUDE

    def detect_installed(self) -> bool:
        return self.get_global_dir().exists()

    def get_global_dir(self) -> Path:
        return Path.home() / ".claude"

    def get_project_dir(self, project: Path) -> Path:
        return project / ".claude"

    # Claude uses standard symlink behavior for skills, agents, commands
    # (inherited from base class)

    def register_hooks(self, hook_names: list[str], target_dir: Path) -> list[str]:
        """Register hooks via settings.json + bash runners.

        For v2, hook registration delegates to the existing generator/installer
        infrastructure. This method is a thin wrapper that records which hooks
        are active.
        """
        return list(hook_names)

    def write_mcp_config(
        self,
        servers: dict[str, dict],
        target_dir: Path,
    ) -> None:
        """Merge hawk-managed MCP servers into .mcp.json."""
        self._merge_mcp_json(target_dir / ".mcp.json", servers)

    def read_mcp_config(self, target_dir: Path) -> dict[str, dict]:
        """Read current MCP config, returning only hawk-managed entries."""
        return self._read_mcp_json(target_dir / ".mcp.json")
