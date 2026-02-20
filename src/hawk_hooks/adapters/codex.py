"""Codex CLI adapter for hawk-hooks v2."""

from __future__ import annotations

from pathlib import Path

from ..types import Tool
from .base import HAWK_MCP_MARKER, ToolAdapter


class CodexAdapter(ToolAdapter):
    """Adapter for Codex CLI."""

    @property
    def tool(self) -> Tool:
        return Tool.CODEX

    def detect_installed(self) -> bool:
        return self.get_global_dir().exists()

    def get_global_dir(self) -> Path:
        return Path.home() / ".codex"

    def get_project_dir(self, project: Path) -> Path:
        return project / ".codex"

    def get_skills_dir(self, target_dir: Path) -> Path:
        """Codex uses a flat agents/ dir for skills."""
        return target_dir / "agents"

    def get_agents_dir(self, target_dir: Path) -> Path:
        """Codex doesn't have a separate agents concept, reuse agents/."""
        return target_dir / "agents"

    def get_commands_dir(self, target_dir: Path) -> Path:
        """Codex doesn't have slash commands; commands become skills."""
        return target_dir / "agents"

    def register_hooks(self, hook_names: list[str], target_dir: Path, registry_path: Path | None = None) -> list[str]:
        """Codex does not support hooks natively."""
        return []

    def write_mcp_config(
        self,
        servers: dict[str, dict],
        target_dir: Path,
    ) -> None:
        """Write MCP config for Codex (mcp.json)."""
        self._merge_mcp_json(target_dir / "mcp.json", servers)
