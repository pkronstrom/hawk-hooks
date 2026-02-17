"""Tests for the Gemini adapter."""

import json

import pytest

from hawk_hooks.adapters.gemini import GeminiAdapter, HAWK_MCP_MARKER, md_to_toml
from hawk_hooks.types import ResolvedSet, Tool


@pytest.fixture
def adapter():
    return GeminiAdapter()


class TestGeminiAdapter:
    def test_tool(self, adapter):
        assert adapter.tool == Tool.GEMINI

    def test_global_dir(self, adapter):
        assert str(adapter.get_global_dir()).endswith(".gemini")

    def test_project_dir(self, adapter, tmp_path):
        assert adapter.get_project_dir(tmp_path) == tmp_path / ".gemini"


class TestMdToToml:
    def test_plain_markdown(self, tmp_path):
        source = tmp_path / "deploy.md"
        source.write_text("Deploy the application to production.")

        toml = md_to_toml(source)
        assert 'name = "deploy"' in toml
        assert "Deploy the application" in toml

    def test_with_frontmatter(self, tmp_path):
        source = tmp_path / "deploy.md"
        source.write_text("""---
name: deploy
description: Deploy to production
tools: [claude, gemini]
---
Deploy the application to production.
""")

        toml = md_to_toml(source)
        assert 'name = "deploy"' in toml
        assert 'description = "Deploy to production"' in toml
        assert "Deploy the application" in toml

    def test_special_chars_escaped(self, tmp_path):
        source = tmp_path / "test.md"
        source.write_text("""---
name: test "cmd"
description: A test with "quotes"
---
Body content.
""")

        toml = md_to_toml(source)
        assert 'test \\"cmd\\"' in toml


class TestGeminiCommands:
    def test_link_command_creates_toml(self, adapter, tmp_path):
        source = tmp_path / "registry" / "commands" / "deploy.md"
        source.parent.mkdir(parents=True)
        source.write_text("""---
name: deploy
description: Deploy
---
Deploy it.
""")

        target = tmp_path / "gemini"
        target.mkdir()

        dest = adapter.link_command(source, target)
        assert dest.suffix == ".toml"
        assert dest.exists()
        content = dest.read_text()
        assert 'name = "deploy"' in content

    def test_unlink_command_removes_toml(self, adapter, tmp_path):
        target = tmp_path / "gemini"
        commands_dir = target / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "deploy.toml").write_text("test")

        assert adapter.unlink_command("deploy.md", target) is True
        assert not (commands_dir / "deploy.toml").exists()


class TestGeminiMCP:
    def test_write_mcp_to_settings(self, adapter, tmp_path):
        target = tmp_path / "gemini"
        target.mkdir()

        servers = {"github": {"command": "gh-mcp"}}
        adapter.write_mcp_config(servers, target)

        settings = json.loads((target / "settings.json").read_text())
        assert "github" in settings["mcpServers"]
        assert settings["mcpServers"]["github"][HAWK_MCP_MARKER] is True

    def test_preserves_manual_entries(self, adapter, tmp_path):
        target = tmp_path / "gemini"
        target.mkdir()

        settings_path = target / "settings.json"
        settings_path.write_text(json.dumps({
            "mcpServers": {"manual": {"command": "manual"}},
            "other_setting": True,
        }))

        adapter.write_mcp_config({"hawk-server": {"command": "hawk"}}, target)

        settings = json.loads(settings_path.read_text())
        assert "manual" in settings["mcpServers"]
        assert "hawk-server" in settings["mcpServers"]
        assert settings["other_setting"] is True


class TestGeminiSync:
    def test_sync_with_commands(self, adapter, tmp_path):
        registry = tmp_path / "registry"
        commands = registry / "commands"
        commands.mkdir(parents=True)
        (commands / "deploy.md").write_text("---\nname: deploy\ndescription: Deploy\n---\nDeploy.")

        # Also need skills dir
        (registry / "skills").mkdir(parents=True)
        (registry / "agents").mkdir(parents=True)

        target = tmp_path / "gemini"
        target.mkdir()

        resolved = ResolvedSet(commands=["deploy.md"])
        result = adapter.sync(resolved, target, registry)
        # Commands are converted, not symlinked, so they won't appear in sync result
        # (sync_component checks for symlinks pointing to registry)
        assert result.errors == []
