"""MCP configuration helper mixin for adapters."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ...registry import _validate_name

# Shared marker for hawk-managed MCP entries
HAWK_MCP_MARKER = "__hawk_managed"
logger = logging.getLogger(__name__)


class MCPMixin:
    """Provide shared MCP loading and merge helpers."""

    @staticmethod
    def _load_mcp_servers(
        mcp_names: list[str],
        mcp_dir: Path,
    ) -> dict[str, dict[str, Any]]:
        """Load MCP server configs from registry yaml files.

        Each .yaml file in registry/mcp/ defines a server config.
        Returns dict of {server_name: config_dict}.
        """
        import yaml

        servers: dict[str, dict[str, Any]] = {}
        for name in mcp_names:
            try:
                _validate_name(name)
            except ValueError:
                continue

            # Try with and without extension
            candidates = [mcp_dir / name]
            if not name.endswith((".yaml", ".yml", ".json")):
                candidates.extend([
                    mcp_dir / f"{name}.yaml",
                    mcp_dir / f"{name}.yml",
                    mcp_dir / f"{name}.json",
                ])

            for path in candidates:
                if path.exists() and path.is_file():
                    try:
                        data = yaml.safe_load(path.read_text())
                        if isinstance(data, dict):
                            server_name = path.stem
                            servers[server_name] = data
                    except Exception:
                        pass
                    break

        return servers

    @staticmethod
    def _merge_mcp_json(
        config_path: Path,
        servers: dict[str, dict],
        server_key: str = "mcpServers",
    ) -> None:
        """Merge hawk-managed MCP servers into a JSON config file.

        Preserves manually-added entries, replaces hawk-managed ones.
        """
        data: dict = {}
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}

        existing = data.get(server_key, {})
        if not isinstance(existing, dict):
            logger.warning(
                "Expected %s to be a dict in %s, got %s; ignoring malformed section",
                server_key,
                config_path,
                type(existing).__name__,
            )
            existing = {}

        # Remove old hawk-managed entries
        cleaned = {
            k: v for k, v in existing.items() if not (isinstance(v, dict) and v.get(HAWK_MCP_MARKER))
        }

        # Add new hawk-managed entries
        for name, cfg in servers.items():
            cleaned[name] = {**cfg, HAWK_MCP_MARKER: True}

        data[server_key] = cleaned
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2) + "\n")

    @staticmethod
    def _read_mcp_json(
        config_path: Path,
        server_key: str = "mcpServers",
    ) -> dict[str, dict]:
        """Read only hawk-managed MCP entries from a JSON config file."""
        if not config_path.exists():
            return {}
        try:
            data = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
        servers = data.get(server_key, {})
        if not isinstance(servers, dict):
            logger.warning(
                "Expected %s to be a dict in %s, got %s; skipping malformed section",
                server_key,
                config_path,
                type(servers).__name__,
            )
            return {}
        return {k: v for k, v in servers.items() if isinstance(v, dict) and v.get(HAWK_MCP_MARKER)}

    @staticmethod
    def _merge_mcp_sidecar(
        config_path: Path,
        servers: dict[str, dict],
        server_key: str = "mcpServers",
    ) -> None:
        """Merge hawk-managed MCP servers using a sidecar tracking file.

        Like _merge_mcp_json but keeps the server entries clean (no marker
        key injected). Managed server names are tracked in a .hawk-mcp.json
        sidecar file next to the config. Use this for tools with strict
        config validation that reject unknown keys (e.g. Gemini).
        """
        sidecar_path = config_path.parent / ".hawk-mcp.json"

        # Read existing managed names from sidecar
        old_managed: set[str] = set()
        if sidecar_path.exists():
            try:
                old_managed = set(json.loads(sidecar_path.read_text()))
            except (json.JSONDecodeError, OSError):
                pass

        # Also detect legacy inline markers and migrate them
        data: dict = {}
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}

        existing = data.get(server_key, {})
        if not isinstance(existing, dict):
            logger.warning(
                "Expected %s to be a dict in %s, got %s; ignoring malformed section",
                server_key,
                config_path,
                type(existing).__name__,
            )
            existing = {}

        # Collect legacy inline-marked entries
        for k, v in existing.items():
            if isinstance(v, dict) and v.get(HAWK_MCP_MARKER):
                old_managed.add(k)

        # Remove old hawk-managed entries (sidecar-tracked + legacy inline)
        cleaned = {}
        for k, v in existing.items():
            if k in old_managed:
                continue
            # Also strip any leftover inline markers
            if isinstance(v, dict):
                v = {ek: ev for ek, ev in v.items() if ek != HAWK_MCP_MARKER}
            cleaned[k] = v

        # Add new hawk-managed entries (clean, no marker)
        for name, cfg in servers.items():
            cleaned[name] = cfg

        data[server_key] = cleaned
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2) + "\n")

        # Write sidecar with current managed names
        new_managed = sorted(servers.keys())
        if new_managed:
            sidecar_path.write_text(json.dumps(new_managed, indent=2) + "\n")
        elif sidecar_path.exists():
            sidecar_path.unlink()
