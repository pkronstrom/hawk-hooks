"""OpenCode adapter for hawk-hooks v2."""

from __future__ import annotations

from pathlib import Path

from ..types import Tool
from .base import ToolAdapter


class OpenCodeAdapter(ToolAdapter):
    """Adapter for OpenCode. Full implementation in M3."""

    @property
    def tool(self) -> Tool:
        return Tool.OPENCODE

    def detect_installed(self) -> bool:
        return self.get_global_dir().exists()

    def get_global_dir(self) -> Path:
        return Path.home() / ".config" / "opencode"

    def get_project_dir(self, project: Path) -> Path:
        return project / ".opencode"

    def register_hooks(self, hook_names: list[str], target_dir: Path) -> list[str]:
        # TODO M3: JS plugin wrapper in .opencode/plugins/
        return list(hook_names)

    def write_mcp_config(self, servers: dict[str, dict], target_dir: Path) -> None:
        # TODO M3: merge into opencode.json
        pass
