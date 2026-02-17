"""OpenCode adapter for hawk-hooks v2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..types import Tool
from .base import ToolAdapter

HAWK_MCP_MARKER = "__hawk_managed"


class OpenCodeAdapter(ToolAdapter):
    """Adapter for OpenCode."""

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
        """OpenCode hooks use JS plugin wrappers."""
        # JS plugin wrapper concept - stub for now
        return list(hook_names)

    def write_mcp_config(
        self,
        servers: dict[str, dict],
        target_dir: Path,
    ) -> None:
        """Write MCP config into opencode.json."""
        config_path = target_dir / "opencode.json"

        existing: dict[str, Any] = {}
        if config_path.exists():
            try:
                with open(config_path) as f:
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

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(existing, f, indent=2)
