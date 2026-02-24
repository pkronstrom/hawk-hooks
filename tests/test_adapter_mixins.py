"""Tests for adapter mixins extracted from ToolAdapter."""

from __future__ import annotations

import json

from hawk_hooks.adapters.claude import ClaudeAdapter
from hawk_hooks.adapters.mixins import HookRunnerMixin, MCPMixin


class TestMixinsStandalone:
    def test_mixins_are_instantiable(self) -> None:
        runner = HookRunnerMixin()
        mcp = MCPMixin()

        assert isinstance(runner, HookRunnerMixin)
        assert isinstance(mcp, MCPMixin)

    def test_load_mcp_servers_missing_dir_returns_empty(self, tmp_path) -> None:
        missing_dir = tmp_path / "missing"

        servers = MCPMixin._load_mcp_servers(["example"], missing_dir)

        assert servers == {}

    def test_merge_mcp_json_creates_marker(self, tmp_path) -> None:
        cfg_path = tmp_path / "settings.json"

        MCPMixin._merge_mcp_json(
            cfg_path,
            {"github": {"command": "uvx", "args": ["mcp-server-github"]}},
        )

        data = json.loads(cfg_path.read_text())
        assert data["mcpServers"]["github"]["__hawk_managed"] is True


class TestToolAdapterInheritance:
    def test_claude_adapter_has_mixin_methods(self) -> None:
        adapter = ClaudeAdapter()

        assert hasattr(adapter, "_generate_runners")
        assert hasattr(adapter, "_load_mcp_servers")
        assert hasattr(adapter, "_merge_mcp_json")
        assert hasattr(adapter, "_read_mcp_json")
        assert hasattr(adapter, "_merge_mcp_sidecar")
