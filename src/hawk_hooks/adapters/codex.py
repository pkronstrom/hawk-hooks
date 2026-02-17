"""Codex CLI adapter for hawk-hooks v2."""

from __future__ import annotations

from pathlib import Path

from ..types import Tool
from .base import ToolAdapter


class CodexAdapter(ToolAdapter):
    """Adapter for Codex CLI. Full implementation in M3."""

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
        """Codex stores skills under agents/skills/."""
        return target_dir / "agents" / "skills"

    def get_agents_dir(self, target_dir: Path) -> Path:
        """Codex doesn't have separate agents concept."""
        return target_dir / "agents"

    def register_hooks(self, hook_names: list[str], target_dir: Path) -> list[str]:
        # TODO M3: Codex notify array in config.toml
        return list(hook_names)

    def write_mcp_config(self, servers: dict[str, dict], target_dir: Path) -> None:
        # TODO M3: merge into .codex/config.toml
        pass
