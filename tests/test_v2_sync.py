"""Tests for v2 sync engine."""

import pytest

from hawk_hooks import v2_config
from hawk_hooks.registry import Registry
from hawk_hooks.types import ComponentType, ResolvedSet, Tool
from hawk_hooks.v2_sync import format_sync_results, sync_directory, sync_global, SyncResult


@pytest.fixture
def v2_env(tmp_path, monkeypatch):
    """Set up a complete v2 test environment."""
    config_dir = tmp_path / "hawk-hooks"
    config_dir.mkdir()
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

    # Set up registry with test components
    registry_path = config_dir / "registry"
    registry = Registry(registry_path)
    registry.ensure_dirs()

    # Add a test skill
    skill_dir = tmp_path / "source" / "tdd"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# TDD Skill")
    registry.add(ComponentType.SKILL, "tdd", skill_dir)

    # Add a test command
    cmd_file = tmp_path / "source" / "deploy.md"
    cmd_file.parent.mkdir(parents=True, exist_ok=True)
    cmd_file.write_text("# Deploy")
    registry.add(ComponentType.COMMAND, "deploy.md", cmd_file)

    # Set global config
    cfg = v2_config.load_global_config()
    cfg["registry_path"] = str(registry_path)
    cfg["global"]["skills"] = ["tdd"]
    cfg["global"]["commands"] = ["deploy.md"]
    v2_config.save_global_config(cfg)

    return {
        "config_dir": config_dir,
        "registry": registry,
        "registry_path": registry_path,
    }


class TestSyncGlobal:
    def test_sync_creates_symlinks(self, v2_env, tmp_path, monkeypatch):
        # Create a fake .claude dir as the global dir
        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        results = sync_global(tools=[Tool.CLAUDE])
        assert len(results) == 1
        result = results[0]
        assert result.tool == "claude"
        assert "tdd" in result.linked

    def test_sync_dry_run_no_changes(self, v2_env, tmp_path, monkeypatch):
        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        results = sync_global(tools=[Tool.CLAUDE], dry_run=True)
        assert len(results) == 1
        # Dry run should report what would be linked
        result = results[0]
        assert any("tdd" in item for item in result.linked)

        # But no actual symlinks should exist
        assert not (claude_dir / "skills" / "tdd").exists()


class TestSyncDirectory:
    def test_sync_project(self, v2_env, tmp_path, monkeypatch):
        project = tmp_path / "my-project"
        project.mkdir()

        # Register and configure
        v2_config.register_directory(project)
        v2_config.save_dir_config(project, {
            "skills": {"enabled": ["tdd"], "disabled": []},
        })

        results = sync_directory(project, tools=[Tool.CLAUDE])
        assert len(results) == 1
        assert results[0].tool == "claude"

    def test_sync_with_profile(self, v2_env, tmp_path, monkeypatch):
        # Create a profile
        v2_config.save_profile("web", {
            "name": "web",
            "skills": ["tdd"],
            "hooks": [],
        })

        project = tmp_path / "web-project"
        project.mkdir()
        v2_config.save_dir_config(project, {"profile": "web"})

        results = sync_directory(project, tools=[Tool.CLAUDE])
        assert len(results) == 1


class TestFormatResults:
    def test_format_empty(self):
        results = {"global": [SyncResult(tool="claude")]}
        output = format_sync_results(results)
        assert "no changes" in output

    def test_format_with_changes(self):
        results = {
            "global": [
                SyncResult(tool="claude", linked=["skill:tdd", "command:deploy.md"]),
            ]
        }
        output = format_sync_results(results)
        assert "claude" in output
        assert "+2 linked" in output
        assert "skill:tdd" in output

    def test_format_with_errors(self):
        results = {
            "global": [
                SyncResult(tool="gemini", errors=["hooks: failed"]),
            ]
        }
        output = format_sync_results(results)
        assert "!1 errors" in output
