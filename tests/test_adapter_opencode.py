"""Tests for the OpenCode adapter."""

import json

import pytest

from hawk_hooks.adapters.opencode import OpenCodeAdapter, HAWK_MCP_MARKER
from hawk_hooks.types import ResolvedSet, Tool


@pytest.fixture
def adapter():
    return OpenCodeAdapter()


class TestOpenCodeAdapter:
    def test_tool(self, adapter):
        assert adapter.tool == Tool.OPENCODE

    def test_global_dir(self, adapter):
        assert str(adapter.get_global_dir()).endswith("opencode")

    def test_project_dir(self, adapter, tmp_path):
        assert adapter.get_project_dir(tmp_path) == tmp_path / ".opencode"

    def test_hook_support_flag(self, adapter):
        assert adapter.hook_support == "unsupported"


class TestOpenCodeMCP:
    def test_write_mcp(self, adapter, tmp_path):
        target = tmp_path / "opencode"
        target.mkdir()

        servers = {"github": {"command": "gh-mcp"}}
        adapter.write_mcp_config(servers, target)

        data = json.loads((target / "opencode.json").read_text())
        assert "github" in data["mcpServers"]
        assert data["mcpServers"]["github"][HAWK_MCP_MARKER] is True

    def test_preserves_manual(self, adapter, tmp_path):
        target = tmp_path / "opencode"
        target.mkdir()

        config_path = target / "opencode.json"
        config_path.write_text(json.dumps({
            "mcpServers": {"manual": {"command": "m"}},
            "theme": "dark",
        }))

        adapter.write_mcp_config({"hawk": {"command": "h"}}, target)

        data = json.loads(config_path.read_text())
        assert "manual" in data["mcpServers"]
        assert "hawk" in data["mcpServers"]
        assert data["theme"] == "dark"

    def test_replaces_hawk_entries(self, adapter, tmp_path):
        target = tmp_path / "opencode"
        target.mkdir()

        adapter.write_mcp_config({"old": {"command": "old"}}, target)
        adapter.write_mcp_config({"new": {"command": "new"}}, target)

        data = json.loads((target / "opencode.json").read_text())
        assert "old" not in data["mcpServers"]
        assert "new" in data["mcpServers"]


class TestOpenCodeHooks:
    def test_sync_warns_when_hooks_configured(self, adapter, tmp_path):
        registry = tmp_path / "registry"
        target = tmp_path / "opencode"
        target.mkdir(parents=True)

        result = adapter.sync(ResolvedSet(hooks=["guard.py"]), target, registry)
        assert any("opencode hook registration is unsupported" in e for e in result.skipped)
