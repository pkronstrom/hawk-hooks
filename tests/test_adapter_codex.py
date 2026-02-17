"""Tests for the Codex adapter."""

import json

import pytest

from hawk_hooks.adapters.codex import CodexAdapter, HAWK_MCP_MARKER
from hawk_hooks.types import Tool


@pytest.fixture
def adapter():
    return CodexAdapter()


class TestCodexAdapter:
    def test_tool(self, adapter):
        assert adapter.tool == Tool.CODEX

    def test_global_dir(self, adapter):
        assert str(adapter.get_global_dir()).endswith(".codex")

    def test_skills_dir_is_agents(self, adapter, tmp_path):
        assert adapter.get_skills_dir(tmp_path) == tmp_path / "agents"

    def test_agents_dir_is_agents(self, adapter, tmp_path):
        assert adapter.get_agents_dir(tmp_path) == tmp_path / "agents"

    def test_commands_dir_is_agents(self, adapter, tmp_path):
        """Codex doesn't have slash commands, so commands go to agents/."""
        assert adapter.get_commands_dir(tmp_path) == tmp_path / "agents"


class TestCodexMCP:
    def test_write_mcp(self, adapter, tmp_path):
        target = tmp_path / "codex"
        target.mkdir()

        servers = {"github": {"command": "gh-mcp"}}
        adapter.write_mcp_config(servers, target)

        data = json.loads((target / "mcp.json").read_text())
        assert "github" in data["mcpServers"]
        assert data["mcpServers"]["github"][HAWK_MCP_MARKER] is True

    def test_preserves_manual(self, adapter, tmp_path):
        target = tmp_path / "codex"
        target.mkdir()

        mcp_path = target / "mcp.json"
        mcp_path.write_text(json.dumps({
            "mcpServers": {"manual": {"command": "m"}}
        }))

        adapter.write_mcp_config({"hawk": {"command": "h"}}, target)

        data = json.loads(mcp_path.read_text())
        assert "manual" in data["mcpServers"]
        assert "hawk" in data["mcpServers"]
