"""Tests for the Gemini adapter."""

import json

import pytest

from hawk_hooks.adapters.gemini import GeminiAdapter, md_to_toml
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
        # Sidecar approach: no __hawk_managed in server entry
        assert "__hawk_managed" not in settings["mcpServers"]["github"]
        # Managed names tracked in sidecar
        sidecar = json.loads((target / ".hawk-mcp.json").read_text())
        assert "github" in sidecar

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
        # Manual entry stays clean
        assert "__hawk_managed" not in settings["mcpServers"]["manual"]

    def test_removes_old_hawk_entries_on_resync(self, adapter, tmp_path):
        """Re-syncing with different servers removes old ones."""
        target = tmp_path / "gemini"
        target.mkdir()

        adapter.write_mcp_config({"old-server": {"command": "old"}}, target)
        adapter.write_mcp_config({"new-server": {"command": "new"}}, target)

        settings = json.loads((target / "settings.json").read_text())
        assert "new-server" in settings["mcpServers"]
        assert "old-server" not in settings["mcpServers"]

    def test_clean_removes_all_hawk_entries(self, adapter, tmp_path):
        """Syncing with empty servers removes all hawk-managed entries."""
        target = tmp_path / "gemini"
        target.mkdir()

        adapter.write_mcp_config({"hawk-server": {"command": "hawk"}}, target)
        adapter.write_mcp_config({}, target)

        settings = json.loads((target / "settings.json").read_text())
        assert "hawk-server" not in settings["mcpServers"]
        # Sidecar cleaned up
        assert not (target / ".hawk-mcp.json").exists()

    def test_migrates_legacy_inline_markers(self, adapter, tmp_path):
        """Legacy __hawk_managed markers in server entries get cleaned up."""
        target = tmp_path / "gemini"
        target.mkdir()

        # Write legacy format (inline marker)
        settings_path = target / "settings.json"
        settings_path.write_text(json.dumps({
            "mcpServers": {
                "legacy": {"command": "legacy", "__hawk_managed": True},
                "manual": {"command": "manual"},
            }
        }))

        # Resync — legacy entry should be replaced, manual preserved
        adapter.write_mcp_config({"new-server": {"command": "new"}}, target)

        settings = json.loads(settings_path.read_text())
        assert "legacy" not in settings["mcpServers"]
        assert "manual" in settings["mcpServers"]
        assert "new-server" in settings["mcpServers"]
        assert "__hawk_managed" not in settings["mcpServers"]["manual"]


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
