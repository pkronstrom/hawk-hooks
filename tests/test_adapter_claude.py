"""Tests for the Claude adapter."""

import json

import pytest

from hawk_hooks.adapters.claude import ClaudeAdapter, HAWK_MCP_MARKER
from hawk_hooks.types import ResolvedSet, Tool


@pytest.fixture
def adapter():
    return ClaudeAdapter()


@pytest.fixture
def setup_registry(tmp_path):
    """Create a minimal registry with test components."""
    registry = tmp_path / "registry"

    # Skills
    skill_dir = registry / "skills" / "tdd"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# TDD Skill")

    # Agents
    agents_dir = registry / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "reviewer.md").write_text("# Reviewer Agent")

    # Commands
    commands_dir = registry / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "deploy.md").write_text("# Deploy Command")

    return registry


class TestClaudeAdapter:
    def test_tool(self, adapter):
        assert adapter.tool == Tool.CLAUDE

    def test_global_dir(self, adapter):
        assert str(adapter.get_global_dir()).endswith(".claude")

    def test_project_dir(self, adapter, tmp_path):
        project = tmp_path / "my-project"
        project.mkdir()
        assert adapter.get_project_dir(project) == project / ".claude"


class TestClaudeMCP:
    def test_write_mcp_new_file(self, adapter, tmp_path):
        target = tmp_path / "claude"
        target.mkdir()

        servers = {
            "github": {"command": "gh-mcp", "args": []},
        }
        adapter.write_mcp_config(servers, target)

        mcp_path = target / ".mcp.json"
        assert mcp_path.exists()

        data = json.loads(mcp_path.read_text())
        assert "github" in data["mcpServers"]
        assert data["mcpServers"]["github"][HAWK_MCP_MARKER] is True

    def test_preserves_manual_entries(self, adapter, tmp_path):
        target = tmp_path / "claude"
        target.mkdir()

        # Write manual entry first
        mcp_path = target / ".mcp.json"
        mcp_path.write_text(json.dumps({
            "mcpServers": {
                "manual-server": {"command": "manual", "args": []},
            }
        }))

        # Write hawk-managed entries
        servers = {"github": {"command": "gh-mcp"}}
        adapter.write_mcp_config(servers, target)

        data = json.loads(mcp_path.read_text())
        assert "manual-server" in data["mcpServers"]
        assert "github" in data["mcpServers"]
        # Manual entry should NOT have hawk marker
        assert HAWK_MCP_MARKER not in data["mcpServers"]["manual-server"]

    def test_replaces_old_hawk_entries(self, adapter, tmp_path):
        target = tmp_path / "claude"
        target.mkdir()

        # First write
        adapter.write_mcp_config({"old-server": {"command": "old"}}, target)

        # Second write with different servers
        adapter.write_mcp_config({"new-server": {"command": "new"}}, target)

        data = json.loads((target / ".mcp.json").read_text())
        assert "old-server" not in data["mcpServers"]
        assert "new-server" in data["mcpServers"]

    def test_read_mcp_config(self, adapter, tmp_path):
        target = tmp_path / "claude"
        target.mkdir()

        # Write mixed config
        mcp_path = target / ".mcp.json"
        mcp_path.write_text(json.dumps({
            "mcpServers": {
                "manual": {"command": "manual"},
                "hawk-managed": {"command": "hawk", HAWK_MCP_MARKER: True},
            }
        }))

        hawk_entries = adapter.read_mcp_config(target)
        assert "hawk-managed" in hawk_entries
        assert "manual" not in hawk_entries

    def test_handles_corrupt_mcp(self, adapter, tmp_path):
        target = tmp_path / "claude"
        target.mkdir()
        (target / ".mcp.json").write_text("not json")

        # Should not raise
        adapter.write_mcp_config({"test": {"command": "test"}}, target)
        data = json.loads((target / ".mcp.json").read_text())
        assert "test" in data["mcpServers"]


class TestClaudeSync:
    def test_sync_links_components(self, adapter, tmp_path, setup_registry):
        target = tmp_path / "claude"
        target.mkdir()

        resolved = ResolvedSet(
            skills=["tdd"],
            agents=["reviewer.md"],
            commands=["deploy.md"],
        )

        result = adapter.sync(resolved, target, setup_registry)
        assert "tdd" in result.linked
        assert "reviewer.md" in result.linked
        assert "deploy.md" in result.linked
        assert result.errors == []

        # Verify symlinks exist
        assert (target / "skills" / "tdd").is_symlink()
        assert (target / "agents" / "reviewer.md").is_symlink()
        assert (target / "commands" / "deploy.md").is_symlink()

    def test_sync_unlinks_stale(self, adapter, tmp_path, setup_registry):
        target = tmp_path / "claude"
        target.mkdir()

        # First sync with skill
        resolved1 = ResolvedSet(skills=["tdd"])
        adapter.sync(resolved1, target, setup_registry)
        assert (target / "skills" / "tdd").is_symlink()

        # Second sync without skill
        resolved2 = ResolvedSet(skills=[])
        result = adapter.sync(resolved2, target, setup_registry)
        assert "tdd" in result.unlinked
        assert not (target / "skills" / "tdd").exists()

    def test_sync_skips_missing_registry_items(self, adapter, tmp_path, setup_registry):
        target = tmp_path / "claude"
        target.mkdir()

        resolved = ResolvedSet(skills=["nonexistent-skill"])
        result = adapter.sync(resolved, target, setup_registry)
        # Should not error, just skip
        assert "nonexistent-skill" not in result.linked

    def test_sync_includes_hooks(self, adapter, tmp_path, setup_registry):
        target = tmp_path / "claude"
        target.mkdir()

        resolved = ResolvedSet(hooks=["block-secrets", "lint"])
        result = adapter.sync(resolved, target, setup_registry)
        assert "hook:block-secrets" in result.linked
        assert "hook:lint" in result.linked
