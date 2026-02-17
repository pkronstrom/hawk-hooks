"""Gemini CLI adapter for hawk-hooks v2."""

from __future__ import annotations

from pathlib import Path

from ..types import Tool
from .base import ToolAdapter


class GeminiAdapter(ToolAdapter):
    """Adapter for Gemini CLI. Full implementation in M3."""

    @property
    def tool(self) -> Tool:
        return Tool.GEMINI

    def detect_installed(self) -> bool:
        return self.get_global_dir().exists()

    def get_global_dir(self) -> Path:
        return Path.home() / ".gemini"

    def get_project_dir(self, project: Path) -> Path:
        return project / ".gemini"

    def get_commands_dir(self, target_dir: Path) -> Path:
        """Gemini uses commands/ directory."""
        return target_dir / "commands"

    def link_command(self, source: Path, target_dir: Path) -> Path:
        """Gemini commands need TOML conversion from markdown."""
        # TODO M3: implement md -> toml conversion
        # For now, symlink as-is
        dest = self.get_commands_dir(target_dir) / source.name
        self._create_symlink(source, dest)
        return dest

    def register_hooks(self, hook_names: list[str], target_dir: Path) -> list[str]:
        # TODO M3: Gemini settings.json hooks + bash runner
        return list(hook_names)

    def write_mcp_config(self, servers: dict[str, dict], target_dir: Path) -> None:
        # TODO M3: merge into .gemini/settings.json
        pass
