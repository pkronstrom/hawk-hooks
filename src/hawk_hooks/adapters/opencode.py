"""OpenCode adapter for hawk-hooks v2."""

from __future__ import annotations

import json
from pathlib import Path

from ..types import Tool
from .base import HAWK_MCP_MARKER, ToolAdapter


class OpenCodeAdapter(ToolAdapter):
    """Adapter for OpenCode."""
    HOOK_SUPPORT = "unsupported"

    @property
    def tool(self) -> Tool:
        return Tool.OPENCODE

    def detect_installed(self) -> bool:
        return self.get_global_dir().exists()

    def get_global_dir(self) -> Path:
        return Path.home() / ".config" / "opencode"

    def get_project_dir(self, project: Path) -> Path:
        return project / ".opencode"

    def get_prompts_dir(self, target_dir: Path) -> Path:
        """OpenCode prompts map to command markdown files."""
        return self.get_commands_dir(target_dir)

    def register_hooks(self, hook_names: list[str], target_dir: Path, registry_path: Path | None = None) -> list[str]:
        """OpenCode does not support hooks natively."""
        self._warn_hooks_unsupported("opencode", hook_names)
        return []

    def write_mcp_config(
        self,
        servers: dict[str, dict],
        target_dir: Path,
    ) -> None:
        """Write MCP config into opencode.json under the native `mcp` key.

        - Preserves manual entries in either legacy `mcpServers` or native `mcp`
        - Migrates legacy manual entries into `mcp`
        - Tracks hawk-managed names via sidecar (no inline marker injection)
        """
        config_path = target_dir / "opencode.json"
        sidecar_path = target_dir / ".hawk-mcp.json"

        data: dict = {}
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}

        native = data.get("mcp", {})
        legacy = data.get("mcpServers", {})
        if not isinstance(native, dict):
            native = {}
        if not isinstance(legacy, dict):
            legacy = {}

        old_managed: set[str] = set()
        if sidecar_path.exists():
            try:
                old_managed = set(json.loads(sidecar_path.read_text()))
            except (json.JSONDecodeError, OSError):
                old_managed = set()

        for bucket in (native, legacy):
            for name, cfg in bucket.items():
                if isinstance(cfg, dict) and cfg.get(HAWK_MCP_MARKER):
                    old_managed.add(name)

        merged: dict[str, dict] = {}
        for name, cfg in native.items():
            if name in old_managed:
                continue
            if isinstance(cfg, dict):
                cfg = {k: v for k, v in cfg.items() if k != HAWK_MCP_MARKER}
            merged[name] = cfg

        # Backward-compatible migration: carry manual legacy mcpServers entries.
        for name, cfg in legacy.items():
            if name in old_managed or name in merged:
                continue
            if isinstance(cfg, dict):
                cfg = {k: v for k, v in cfg.items() if k != HAWK_MCP_MARKER}
            merged[name] = cfg

        for name, cfg in servers.items():
            merged[name] = cfg

        data["mcp"] = merged
        data.pop("mcpServers", None)

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2) + "\n")

        managed_names = sorted(servers.keys())
        if managed_names:
            sidecar_path.write_text(json.dumps(managed_names, indent=2) + "\n")
        elif sidecar_path.exists():
            sidecar_path.unlink()
