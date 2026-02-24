"""Tests for v2 sync engine."""

import json

import pytest

from hawk_hooks import v2_config
from hawk_hooks.registry import Registry
from hawk_hooks.types import ComponentType, ResolvedSet, Tool
from hawk_hooks.v2_sync import (
    _cache_key,
    _read_cached_hash,
    _write_cached_hash,
    clean_global,
    count_unsynced_targets,
    format_sync_results,
    purge_global,
    uninstall_all,
    sync_directory,
    sync_global,
    SyncResult,
)


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

    def test_sync_global_writes_mcp_to_user_scope_file(self, v2_env, tmp_path, monkeypatch):
        claude_dir = tmp_path / "home" / ".claude"
        claude_dir.mkdir(parents=True)

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        mcp_dir = v2_env["registry_path"] / "mcp"
        mcp_dir.mkdir(parents=True, exist_ok=True)
        (mcp_dir / "dodo.json").write_text('{"command":"dodo","args":["mcp"]}')

        cfg = v2_config.load_global_config()
        cfg["global"]["mcp"] = ["dodo.json"]
        v2_config.save_global_config(cfg)

        sync_global(tools=[Tool.CLAUDE], force=True)

        user_mcp = claude_dir.parent / ".claude.json"
        assert user_mcp.exists()
        data = json.loads(user_mcp.read_text())
        assert "dodo" in data["mcpServers"]
        assert not (claude_dir / ".mcp.json").exists()


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

    def test_sync_directory_writes_mcp_to_project_root(self, v2_env, tmp_path):
        project = tmp_path / "project"
        project.mkdir()

        mcp_dir = v2_env["registry_path"] / "mcp"
        mcp_dir.mkdir(parents=True, exist_ok=True)
        (mcp_dir / "dodo.json").write_text('{"command":"dodo","args":["mcp"]}')

        cfg = v2_config.load_global_config()
        cfg["global"]["mcp"] = ["dodo.json"]
        v2_config.save_global_config(cfg)

        sync_directory(project, tools=[Tool.CLAUDE], force=True)

        project_mcp = project / ".mcp.json"
        assert project_mcp.exists()
        data = json.loads(project_mcp.read_text())
        assert "dodo" in data["mcpServers"]
        assert not (project / ".claude" / ".mcp.json").exists()


class TestSyncDirectoryWithChain:
    """Tests for sync_directory with hierarchical config chain."""

    def test_sync_inherits_parent_config(self, v2_env, tmp_path, monkeypatch):
        """Child dir should inherit skills from registered parent."""
        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()

        from hawk_hooks.adapters.claude import ClaudeAdapter
        monkeypatch.setattr(ClaudeAdapter, "get_project_dir", lambda self, d: claude_dir)

        # Set up monorepo structure
        root = tmp_path / "monorepo"
        root.mkdir()
        child = root / "packages" / "frontend"
        child.mkdir(parents=True)

        # Root config enables tdd
        v2_config.save_dir_config(root, {"skills": {"enabled": ["tdd"], "disabled": []}})
        v2_config.register_directory(root)

        # Child config adds react
        v2_config.save_dir_config(child, {"skills": {"enabled": ["react"], "disabled": []}})
        v2_config.register_directory(child)

        # Add react to registry so it can be linked
        registry_path = v2_env["registry_path"]
        react_dir = tmp_path / "source" / "react"
        react_dir.mkdir(parents=True)
        (react_dir / "SKILL.md").write_text("# React")
        v2_env["registry"].add(ComponentType.SKILL, "react", react_dir)

        results = sync_directory(child, tools=[Tool.CLAUDE])
        assert len(results) == 1
        # Should have both tdd (from parent) and react (from child)
        linked_names = [item.split(":")[-1] for item in results[0].linked]
        assert "tdd" in linked_names
        assert "react" in linked_names

    def test_sync_child_can_disable_parent_skill(self, v2_env, tmp_path, monkeypatch):
        """Child dir should be able to disable skills from parent."""
        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()

        from hawk_hooks.adapters.claude import ClaudeAdapter
        monkeypatch.setattr(ClaudeAdapter, "get_project_dir", lambda self, d: claude_dir)

        root = tmp_path / "monorepo"
        root.mkdir()
        child = root / "packages" / "backend"
        child.mkdir(parents=True)

        v2_config.save_dir_config(root, {"skills": {"enabled": ["tdd", "react"], "disabled": []}})
        v2_config.register_directory(root)

        # Child disables react
        v2_config.save_dir_config(child, {"skills": {"enabled": [], "disabled": ["react"]}})
        v2_config.register_directory(child)

        # Add react to registry
        react_dir = tmp_path / "source" / "react"
        react_dir.mkdir(parents=True)
        (react_dir / "SKILL.md").write_text("# React")
        v2_env["registry"].add(ComponentType.SKILL, "react", react_dir)

        results = sync_directory(child, tools=[Tool.CLAUDE])
        linked_names = [item.split(":")[-1] for item in results[0].linked]
        assert "tdd" in linked_names
        assert "react" not in linked_names


class TestSyncCache:
    def test_cache_key_global(self):
        key = _cache_key("global", Tool.CLAUDE)
        assert key.endswith("_claude")
        assert "/" not in key
        assert "\\" not in key

    def test_cache_key_directory(self):
        key = _cache_key("/home/user/project", Tool.GEMINI)
        assert key.endswith("_gemini")
        assert "/" not in key
        assert "\\" not in key
        assert key == _cache_key("/home/user/project", Tool.GEMINI)

    def test_cache_key_distinguishes_old_collision_paths(self):
        key_a = _cache_key("/a/b", Tool.CLAUDE)
        key_b = _cache_key("/a_b", Tool.CLAUDE)
        assert key_a != key_b

    def test_read_write_cache(self, v2_env):
        _write_cached_hash("global", Tool.CLAUDE, "abc123")
        assert _read_cached_hash("global", Tool.CLAUDE) == "abc123"

    def test_read_missing_cache(self, v2_env):
        assert _read_cached_hash("nonexistent", Tool.CLAUDE) is None

    def test_cache_skips_unchanged(self, v2_env, tmp_path, monkeypatch):
        """Second sync with same config should produce no changes (cache hit)."""
        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        # First sync — should produce linked items
        results1 = sync_global(tools=[Tool.CLAUDE])
        assert results1[0].linked  # something was linked

        # Second sync — cache hit, no changes
        results2 = sync_global(tools=[Tool.CLAUDE])
        assert not results2[0].linked
        assert not results2[0].unlinked
        assert not results2[0].errors

    def test_force_bypasses_cache(self, v2_env, tmp_path, monkeypatch):
        """--force should sync even when cache matches."""
        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        # First sync
        sync_global(tools=[Tool.CLAUDE])

        # Force sync — should still do work (symlinks already exist so no new links,
        # but it should not short-circuit via cache)
        results = sync_global(tools=[Tool.CLAUDE], force=True)
        # The result is computed by the adapter (not a cache no-op),
        # so tool name should still be set
        assert results[0].tool == "claude"

    def test_capability_change_invalidates_cache(self, v2_env, tmp_path, monkeypatch):
        """Capability fingerprint changes should force a resync attempt."""
        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        sync_calls = {"count": 0}
        original_sync = ClaudeAdapter.sync

        def _counting_sync(self, resolved, target_dir, registry_path):
            sync_calls["count"] += 1
            return original_sync(self, resolved, target_dir, registry_path)

        monkeypatch.setattr(ClaudeAdapter, "sync", _counting_sync)

        sync_global(tools=[Tool.CLAUDE])
        assert sync_calls["count"] == 1

        # Cache hit: no sync call
        sync_global(tools=[Tool.CLAUDE])
        assert sync_calls["count"] == 1

        # Capability change should invalidate cache and invoke sync again
        monkeypatch.setattr(
            ClaudeAdapter,
            "capability_fingerprint",
            lambda self: "hooks:native|events:changed",
            raising=False,
        )
        sync_global(tools=[Tool.CLAUDE])
        assert sync_calls["count"] == 2


class TestUnsyncedCounts:
    def test_count_unsynced_global_before_and_after_sync(self, v2_env, tmp_path, monkeypatch):
        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        unsynced_before, total_before = count_unsynced_targets(tools=[Tool.CLAUDE])
        assert total_before == 1
        assert unsynced_before == 1

        sync_global(tools=[Tool.CLAUDE])

        unsynced_after, total_after = count_unsynced_targets(tools=[Tool.CLAUDE])
        assert total_after == 1
        assert unsynced_after == 0

    def test_count_unsynced_project_scope(self, v2_env, tmp_path, monkeypatch):
        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)
        monkeypatch.setattr(ClaudeAdapter, "get_project_dir", lambda self, _d: claude_dir)

        project = tmp_path / "project"
        project.mkdir()
        v2_config.register_directory(project)
        v2_config.save_dir_config(project, {"skills": {"enabled": ["tdd"], "disabled": []}})

        unsynced_before, total_before = count_unsynced_targets(
            project_dir=project,
            tools=[Tool.CLAUDE],
        )
        # global + project for one tool
        assert total_before == 2
        assert unsynced_before == 2

        sync_global(tools=[Tool.CLAUDE])
        sync_directory(project, tools=[Tool.CLAUDE])

        unsynced_after, total_after = count_unsynced_targets(
            project_dir=project,
            tools=[Tool.CLAUDE],
        )
        assert total_after == 2
        assert unsynced_after == 0


class TestClean:
    def test_clean_removes_symlinks(self, v2_env, tmp_path, monkeypatch):
        """Clean should remove all hawk-managed symlinks."""
        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        # First sync to create symlinks
        results = sync_global(tools=[Tool.CLAUDE])
        assert results[0].linked

        # Verify symlink exists
        assert (claude_dir / "skills" / "tdd").is_symlink()

        # Clean
        clean_results = clean_global(tools=[Tool.CLAUDE])
        assert len(clean_results) == 1
        assert "tdd" in clean_results[0].unlinked

        # Verify symlink is gone
        assert not (claude_dir / "skills" / "tdd").exists()

    def test_clean_clears_cache(self, v2_env, tmp_path, monkeypatch):
        """Clean should clear the sync cache."""
        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        # Sync to populate cache
        sync_global(tools=[Tool.CLAUDE])
        assert _read_cached_hash("global", Tool.CLAUDE) is not None

        # Clean
        clean_global(tools=[Tool.CLAUDE])
        assert _read_cached_hash("global", Tool.CLAUDE) is None

    def test_clean_dry_run(self, v2_env, tmp_path, monkeypatch):
        """Dry-run clean should report but not remove."""
        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        # Sync first
        sync_global(tools=[Tool.CLAUDE])
        assert (claude_dir / "skills" / "tdd").is_symlink()

        # Dry-run clean
        clean_results = clean_global(tools=[Tool.CLAUDE], dry_run=True)
        assert any("tdd" in item for item in clean_results[0].unlinked)

        # Symlink should still exist
        assert (claude_dir / "skills" / "tdd").is_symlink()


class TestPrune:
    def test_purge_global_removes_dangling_hawk_symlink(self, v2_env, tmp_path, monkeypatch):
        claude_dir = tmp_path / "fake-claude"
        commands_dir = claude_dir / "commands"
        commands_dir.mkdir(parents=True)

        # Dangling symlink into hawk config path (legacy/stale)
        stale_target = v2_env["config_dir"] / "prompts" / "old.md"
        (commands_dir / "old.md").symlink_to(stale_target)
        assert (commands_dir / "old.md").is_symlink()
        assert not stale_target.exists()

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        results = purge_global(tools=[Tool.CLAUDE])
        assert len(results) == 1
        assert any("old.md" in item for item in results[0].unlinked)
        assert not (commands_dir / "old.md").exists()

    def test_purge_global_dry_run_keeps_dangling_hawk_symlink(
        self, v2_env, tmp_path, monkeypatch
    ):
        claude_dir = tmp_path / "fake-claude"
        commands_dir = claude_dir / "commands"
        commands_dir.mkdir(parents=True)

        stale_target = v2_env["config_dir"] / "prompts" / "old.md"
        (commands_dir / "old.md").symlink_to(stale_target)

        from hawk_hooks.adapters.claude import ClaudeAdapter

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        results = purge_global(tools=[Tool.CLAUDE], dry_run=True)
        assert len(results) == 1
        assert any("old.md" in item for item in results[0].unlinked)
        assert (commands_dir / "old.md").is_symlink()


class TestUninstall:
    def test_uninstall_all_cleans_state(self, v2_env, tmp_path, monkeypatch):
        from hawk_hooks.adapters.claude import ClaudeAdapter

        # Seed package index
        v2_config.record_package(
            "starter",
            "",
            "",
            [{"type": "skill", "name": "tdd", "hash": "deadbeef"}],
            path=str(tmp_path / "builtins"),
        )

        # Seed directory registration/config
        project = tmp_path / "project"
        project.mkdir()
        v2_config.save_dir_config(project, {"prompts": {"enabled": ["deploy.md"], "disabled": []}})
        v2_config.register_directory(project)

        # Seed global enabled entries
        cfg = v2_config.load_global_config()
        cfg["global"]["skills"] = ["tdd"]
        cfg["global"]["prompts"] = ["deploy.md"]
        cfg["global"]["commands"] = ["deploy.md"]
        cfg.setdefault("tools", {}).setdefault("codex", {})["multi_agent_consent"] = "granted"
        cfg.setdefault("tools", {}).setdefault("codex", {})["allow_multi_agent"] = True
        v2_config.save_global_config(cfg)

        # Seed a stale hawk symlink in tool config to verify purge path is used
        claude_dir = tmp_path / "fake-claude"
        commands_dir = claude_dir / "commands"
        commands_dir.mkdir(parents=True)
        stale_target = v2_env["config_dir"] / "prompts" / "old.md"
        (commands_dir / "old.md").symlink_to(stale_target)

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        uninstall_all(tools=[Tool.CLAUDE])

        cfg_after = v2_config.load_global_config()
        assert cfg_after["global"]["skills"] == []
        assert cfg_after["global"]["prompts"] == []
        assert cfg_after["global"]["commands"] == []
        assert cfg_after["tools"]["codex"]["multi_agent_consent"] == "ask"
        assert cfg_after["tools"]["codex"]["allow_multi_agent"] is False
        assert cfg_after.get("directories", {}) == {}
        assert v2_config.load_packages() == {}
        assert not v2_env["registry"].list(ComponentType.SKILL)[ComponentType.SKILL]
        assert not (project / ".hawk" / "config.yaml").exists()
        assert not (commands_dir / "old.md").exists()

    def test_uninstall_all_dry_run_keeps_state(self, v2_env, tmp_path, monkeypatch):
        from hawk_hooks.adapters.claude import ClaudeAdapter

        v2_config.record_package(
            "starter",
            "",
            "",
            [{"type": "skill", "name": "tdd", "hash": "deadbeef"}],
            path=str(tmp_path / "builtins"),
        )
        cfg = v2_config.load_global_config()
        cfg["global"]["skills"] = ["tdd"]
        cfg["global"]["commands"] = ["deploy.md"]
        v2_config.save_global_config(cfg)

        claude_dir = tmp_path / "fake-claude"
        commands_dir = claude_dir / "commands"
        commands_dir.mkdir(parents=True)
        stale_target = v2_env["config_dir"] / "prompts" / "old.md"
        (commands_dir / "old.md").symlink_to(stale_target)

        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        uninstall_all(tools=[Tool.CLAUDE], dry_run=True)

        cfg_after = v2_config.load_global_config()
        assert cfg_after["global"]["skills"] == ["tdd"]
        assert cfg_after["global"]["commands"] == ["deploy.md"]
        assert "starter" in v2_config.load_packages()
        assert (commands_dir / "old.md").is_symlink()

    def test_uninstall_all_leaves_no_global_unsynced_targets(
        self, v2_env, tmp_path, monkeypatch
    ):
        from hawk_hooks.adapters.claude import ClaudeAdapter

        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()
        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        uninstall_all(tools=[Tool.CLAUDE])

        unsynced, total = count_unsynced_targets(tools=[Tool.CLAUDE])
        assert total == 1
        assert unsynced == 0

    def test_uninstall_all_can_keep_project_local_hawk_files(self, v2_env, tmp_path, monkeypatch):
        from hawk_hooks.adapters.claude import ClaudeAdapter

        project = tmp_path / "project"
        project.mkdir()
        v2_config.save_dir_config(project, {"prompts": {"enabled": ["deploy.md"], "disabled": []}})
        v2_config.register_directory(project)

        claude_dir = tmp_path / "fake-claude"
        claude_dir.mkdir()
        monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_dir)

        uninstall_all(tools=[Tool.CLAUDE], remove_project_configs=False)

        cfg_after = v2_config.load_global_config()
        assert cfg_after.get("directories", {}) == {}
        assert (project / ".hawk" / "config.yaml").exists()


class TestFormatResults:
    def test_format_empty(self):
        results = {"global": [SyncResult(tool="claude")]}
        output = format_sync_results(results)
        assert "no changes" in output

    def test_format_with_changes_compact(self):
        results = {
            "global": [
                SyncResult(
                    tool="claude",
                    linked=["skill:tdd", "command:deploy.md"],
                    unlinked=["prompt:old.md"],
                ),
            ]
        }
        output = format_sync_results(results, verbose=False)
        assert "claude" in output
        assert "+2 linked" in output
        assert "1 removed" in output
        assert "skill:tdd" not in output

    def test_format_with_changes_verbose(self):
        results = {
            "global": [
                SyncResult(tool="claude", linked=["skill:tdd", "command:deploy.md"]),
            ]
        }
        output = format_sync_results(results, verbose=True)
        assert "skill:tdd" in output

    def test_format_with_errors(self):
        results = {
            "global": [
                SyncResult(tool="gemini", errors=["hooks: failed"]),
            ]
        }
        output = format_sync_results(results)
        assert "!1 errors" in output

    def test_format_with_skipped_compact(self):
        results = {
            "global": [
                SyncResult(tool="codex", skipped=["hooks: pre_tool_use is unsupported by codex"]),
            ]
        }
        output = format_sync_results(results, verbose=False)
        assert "~1 skipped" in output
        assert "unsupported by codex" not in output

    def test_format_with_skipped_verbose(self):
        results = {
            "global": [
                SyncResult(tool="codex", skipped=["hooks: pre_tool_use is unsupported by codex"]),
            ]
        }
        output = format_sync_results(results, verbose=True)
        assert "~1 skipped" in output
        assert "~ hooks: pre_tool_use is unsupported by codex" in output
