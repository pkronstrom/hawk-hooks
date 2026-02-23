"""Cursor IDE adapter for hawk-hooks v2.

Cursor uses:
- .cursor/rules/ for rules/skills (.mdc files, but plain .md works too)
- .cursor/mcp.json for MCP servers (key: "mcpServers")
- .cursor/hooks.json for hooks (lifecycle events)
- .cursor/commands/ for custom slash commands/prompts
- Project-level: <project>/.cursor/
- Global: ~/.cursor/

Capability verification notes (2026-02-23):
- Verified (official docs):
  - Rules/project instructions: https://docs.cursor.com/context/rules
  - Custom commands (/ prompts): https://docs.cursor.com/en/agent/chat/commands
  - CLI rules + mcp.json reuse: https://docs.cursor.com/en/cli/using
- Hooks in Cursor CLI:
  - No stable first-party hook event contract found in public docs at verification time.
  - Community indicates partial support only; keep adapter hook support as unsupported
    until official event mapping is documented.
"""

from __future__ import annotations

from pathlib import Path

from ..types import Tool
from .base import ToolAdapter


class CursorAdapter(ToolAdapter):
    """Adapter for Cursor IDE."""
    HOOK_SUPPORT = "unsupported"

    @property
    def tool(self) -> Tool:
        return Tool.CURSOR

    def detect_installed(self) -> bool:
        return self.get_global_dir().exists()

    def get_global_dir(self) -> Path:
        return Path.home() / ".cursor"

    def get_project_dir(self, project: Path) -> Path:
        return project / ".cursor"

    # Skills → .cursor/rules/ (Cursor calls them "rules")
    def get_skills_dir(self, target_dir: Path) -> Path:
        return target_dir / "rules"

    # Agents → .cursor/agents/ (not a native Cursor dir, but harmless)
    def get_agents_dir(self, target_dir: Path) -> Path:
        return target_dir / "agents"

    # Commands/prompts → .cursor/commands/
    def get_commands_dir(self, target_dir: Path) -> Path:
        return target_dir / "commands"

    # Prompts map to Cursor custom commands
    def get_prompts_dir(self, target_dir: Path) -> Path:
        return self.get_commands_dir(target_dir)

    def register_hooks(self, hook_names: list[str], target_dir: Path, registry_path: Path | None = None) -> list[str]:
        """Cursor does not support hooks natively."""
        self._warn_hooks_unsupported("cursor", hook_names)
        return []

    def write_mcp_config(
        self,
        servers: dict[str, dict],
        target_dir: Path,
    ) -> None:
        """Merge hawk-managed MCP servers into .cursor/mcp.json."""
        self._merge_mcp_json(target_dir / "mcp.json", servers)
