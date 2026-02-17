"""Claude Code adapter for hawk-hooks v2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..types import Tool
from .base import ToolAdapter

# Marker for hawk-managed MCP entries
HAWK_MCP_MARKER = "__hawk_managed"


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
        # In v2, hook registration is handled by the sync command
        # which calls generator.generate_all_runners() + installer.install_hooks()
        # This adapter just tracks what should be registered
        return list(hook_names)

    def write_mcp_config(
        self,
        servers: dict[str, dict],
        target_dir: Path,
    ) -> None:
        """Merge hawk-managed MCP servers into .mcp.json.

        Preserves manually-added entries. Hawk-managed entries are marked
        with a __hawk_managed: true field.
        """
        mcp_path = target_dir / ".mcp.json"

        # Load existing config
        existing: dict[str, Any] = {}
        if mcp_path.exists():
            try:
                with open(mcp_path) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = {}

        if not isinstance(existing, dict):
            existing = {}

        mcp_servers = existing.get("mcpServers", {})
        if not isinstance(mcp_servers, dict):
            mcp_servers = {}

        # Remove old hawk-managed entries
        to_remove = [
            name
            for name, cfg in mcp_servers.items()
            if isinstance(cfg, dict) and cfg.get(HAWK_MCP_MARKER)
        ]
        for name in to_remove:
            del mcp_servers[name]

        # Add new hawk-managed entries
        for name, server_cfg in servers.items():
            entry = dict(server_cfg)
            entry[HAWK_MCP_MARKER] = True
            mcp_servers[name] = entry

        existing["mcpServers"] = mcp_servers

        # Write back
        mcp_path.parent.mkdir(parents=True, exist_ok=True)
        with open(mcp_path, "w") as f:
            json.dump(existing, f, indent=2)

    def read_mcp_config(self, target_dir: Path) -> dict[str, dict]:
        """Read current MCP config, returning only hawk-managed entries."""
        mcp_path = target_dir / ".mcp.json"
        if not mcp_path.exists():
            return {}

        try:
            with open(mcp_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

        mcp_servers = data.get("mcpServers", {})
        return {
            name: cfg
            for name, cfg in mcp_servers.items()
            if isinstance(cfg, dict) and cfg.get(HAWK_MCP_MARKER)
        }
