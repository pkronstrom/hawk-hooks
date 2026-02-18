"""Google Antigravity adapter for hawk-hooks v2.

Antigravity is Google's agentic IDE. It uses:
- ~/.gemini/antigravity/skills/ for skills (SKILL.md files)
- mcp_config.json for MCP servers
- Project-level: <project>/.antigravity/ or workspace settings
- Global: ~/.gemini/antigravity/
"""

from __future__ import annotations

from pathlib import Path

from ..types import Tool
from .base import ToolAdapter


class AntigravityAdapter(ToolAdapter):
    """Adapter for Google Antigravity."""

    @property
    def tool(self) -> Tool:
        return Tool.ANTIGRAVITY

    def detect_installed(self) -> bool:
        return self.get_global_dir().exists()

    def get_global_dir(self) -> Path:
        return Path.home() / ".gemini" / "antigravity"

    def get_project_dir(self, project: Path) -> Path:
        return project / ".antigravity"

    # Skills → ~/.gemini/antigravity/skills/
    def get_skills_dir(self, target_dir: Path) -> Path:
        return target_dir / "skills"

    def register_hooks(self, hook_names: list[str], target_dir: Path, registry_path: Path | None = None) -> list[str]:
        """Antigravity hook support TBD — record names for now."""
        return list(hook_names)

    def write_mcp_config(
        self,
        servers: dict[str, dict],
        target_dir: Path,
    ) -> None:
        """Merge hawk-managed MCP servers into mcp_config.json."""
        self._merge_mcp_json(target_dir / "mcp_config.json", servers)
