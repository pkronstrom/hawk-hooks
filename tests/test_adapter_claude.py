"""Tests for the Claude adapter."""

import json

import pytest

from hawk_hooks.adapters.claude import ClaudeAdapter, HAWK_MCP_MARKER
from hawk_hooks.types import ResolvedSet, Tool
from hawk_hooks import v2_config


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

    # Hooks (event directories with scripts)
    hook_dir = registry / "hooks" / "pre_tool_use"
    hook_dir.mkdir(parents=True)
    (hook_dir / "file-guard.py").write_text("#!/usr/bin/env python3\nimport sys, json\nprint(json.dumps({'decision': 'approve'}))\n")
    (hook_dir / "dangerous-cmd.sh").write_text("#!/bin/bash\nexit 0\n")

    stop_dir = registry / "hooks" / "stop"
    stop_dir.mkdir(parents=True)
    (stop_dir / "notify.py").write_text("#!/usr/bin/env python3\nimport sys\nprint('')\n")
    (stop_dir / "completion-check.stdout.md").write_text("# Completion check\n")

    # Prompts
    prompts_dir = registry / "prompts"
    prompts_dir.mkdir(parents=True)

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

    def test_sync_includes_hooks(self, adapter, tmp_path, setup_registry, monkeypatch):
        target = tmp_path / "claude"
        target.mkdir()
        config_dir = tmp_path / "hawk-config"
        config_dir.mkdir()
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

        resolved = ResolvedSet(hooks=[
            "pre_tool_use/file-guard.py",
            "stop/notify.py",
        ])
        result = adapter.sync(resolved, target, setup_registry)
        assert "hook:pre_tool_use/file-guard.py" in result.linked
        assert "hook:stop/notify.py" in result.linked

    def test_sync_hooks_without_slash_skipped(self, adapter, tmp_path, setup_registry, monkeypatch):
        """Hook names without event/ prefix are silently skipped."""
        target = tmp_path / "claude"
        target.mkdir()
        config_dir = tmp_path / "hawk-config"
        config_dir.mkdir()
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

        resolved = ResolvedSet(hooks=["bare-hook-name"])
        result = adapter.sync(resolved, target, setup_registry)
        assert not any("bare-hook-name" in h for h in result.linked)


class TestClaudeHookWiring:
    """Tests for hook runner generation and settings.json registration."""

    @pytest.fixture
    def hook_env(self, tmp_path, monkeypatch):
        """Set up env for hook wiring tests."""
        config_dir = tmp_path / "hawk-config"
        config_dir.mkdir()
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"

        # pre_tool_use hooks
        (hooks_dir / "pre_tool_use").mkdir(parents=True)
        (hooks_dir / "pre_tool_use" / "file-guard.py").write_text(
            "#!/usr/bin/env python3\nimport sys, json\nprint(json.dumps({'decision': 'approve'}))\n"
        )
        (hooks_dir / "pre_tool_use" / "dangerous-cmd.sh").write_text(
            "#!/bin/bash\nexit 0\n"
        )

        # stop hooks
        (hooks_dir / "stop").mkdir(parents=True)
        (hooks_dir / "stop" / "notify.py").write_text(
            "#!/usr/bin/env python3\nprint('')\n"
        )
        (hooks_dir / "stop" / "completion-check.stdout.md").write_text(
            "# Completion check\nDid you finish all tasks?\n"
        )

        # session_start hooks
        (hooks_dir / "session_start").mkdir(parents=True)
        (hooks_dir / "session_start" / "greet.sh").write_text(
            "#!/bin/bash\necho 'Hello'\n"
        )

        target = tmp_path / "claude"
        target.mkdir()

        return {
            "config_dir": config_dir,
            "registry": registry,
            "target": target,
            "runners_dir": config_dir / "runners",
        }

    def test_generates_runner_per_event(self, hook_env):
        adapter = ClaudeAdapter()
        hook_names = [
            "pre_tool_use/file-guard.py",
            "pre_tool_use/dangerous-cmd.sh",
            "stop/notify.py",
        ]
        registered = adapter.register_hooks(
            hook_names, hook_env["target"], registry_path=hook_env["registry"]
        )

        runners_dir = hook_env["runners_dir"]
        assert (runners_dir / "pre_tool_use.sh").exists()
        assert (runners_dir / "stop.sh").exists()
        # session_start not in hook_names, so no runner
        assert not (runners_dir / "session_start.sh").exists()

        assert "pre_tool_use/file-guard.py" in registered
        assert "pre_tool_use/dangerous-cmd.sh" in registered
        assert "stop/notify.py" in registered

    def test_runner_content_chains_hooks(self, hook_env):
        adapter = ClaudeAdapter()
        hook_names = [
            "pre_tool_use/file-guard.py",
            "pre_tool_use/dangerous-cmd.sh",
        ]
        adapter.register_hooks(
            hook_names, hook_env["target"], registry_path=hook_env["registry"]
        )

        runner = hook_env["runners_dir"] / "pre_tool_use.sh"
        content = runner.read_text()

        # Should have shebang
        assert content.startswith("#!/usr/bin/env bash")
        # Should reference both hooks
        assert "file-guard.py" in content
        assert "dangerous-cmd.sh" in content
        # Should capture INPUT
        assert 'INPUT=$(cat)' in content

    def test_runner_handles_stdout_hooks(self, hook_env):
        adapter = ClaudeAdapter()
        hook_names = ["stop/completion-check.stdout.md"]
        adapter.register_hooks(
            hook_names, hook_env["target"], registry_path=hook_env["registry"]
        )

        content = (hook_env["runners_dir"] / "stop.sh").read_text()
        # Stdout hooks use cat, not echo "$INPUT" |
        assert "cat" in content
        assert "completion-check.stdout.md" in content
        # Should NOT pipe INPUT to stdout hooks
        assert 'echo "$INPUT" | ' not in content.split("completion-check.stdout.md")[0].split("\n")[-1]

    def test_runner_handles_py_hooks(self, hook_env):
        adapter = ClaudeAdapter()
        hook_names = ["pre_tool_use/file-guard.py"]
        adapter.register_hooks(
            hook_names, hook_env["target"], registry_path=hook_env["registry"]
        )

        content = (hook_env["runners_dir"] / "pre_tool_use.sh").read_text()
        assert "python3" in content
        assert "file-guard.py" in content

    def test_runner_handles_sh_hooks(self, hook_env):
        adapter = ClaudeAdapter()
        hook_names = ["pre_tool_use/dangerous-cmd.sh"]
        adapter.register_hooks(
            hook_names, hook_env["target"], registry_path=hook_env["registry"]
        )

        content = (hook_env["runners_dir"] / "pre_tool_use.sh").read_text()
        assert "dangerous-cmd.sh" in content

    def test_settings_json_registration(self, hook_env):
        adapter = ClaudeAdapter()
        hook_names = [
            "pre_tool_use/file-guard.py",
            "stop/notify.py",
        ]
        adapter.register_hooks(
            hook_names, hook_env["target"], registry_path=hook_env["registry"]
        )

        settings_path = hook_env["target"] / "settings.json"
        assert settings_path.exists()

        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", [])

        # Should have 2 entries (one per event)
        hawk_hooks = [h for h in hooks if any(
            hh.get("__hawk_managed") for hh in h.get("hooks", [])
        )]
        assert len(hawk_hooks) == 2

        # Check matchers use PascalCase Claude event names
        matchers = {h["matcher"] for h in hawk_hooks}
        assert "PreToolUse" in matchers
        assert "Stop" in matchers

    def test_event_name_mapping(self, hook_env):
        """Verify canonical snake_case → Claude PascalCase mapping."""
        adapter = ClaudeAdapter()
        hook_names = [
            "pre_tool_use/file-guard.py",
            "stop/notify.py",
            "session_start/greet.sh",
        ]
        adapter.register_hooks(
            hook_names, hook_env["target"], registry_path=hook_env["registry"]
        )

        settings = json.loads((hook_env["target"] / "settings.json").read_text())
        matchers = {h["matcher"] for h in settings["hooks"]}
        assert "PreToolUse" in matchers
        assert "Stop" in matchers
        assert "SessionStart" in matchers
        # Should NOT have snake_case
        assert "pre_tool_use" not in matchers
        assert "session_start" not in matchers

    def test_preserves_user_hooks(self, hook_env):
        """Hawk should not remove manually-added hook entries."""
        # Write a user hook first
        settings_path = hook_env["target"] / "settings.json"
        settings_path.write_text(json.dumps({
            "hooks": [{
                "matcher": "PreToolUse",
                "hooks": [{"type": "command", "command": "/usr/local/bin/my-hook"}],
            }]
        }))

        adapter = ClaudeAdapter()
        adapter.register_hooks(
            ["pre_tool_use/file-guard.py"],
            hook_env["target"],
            registry_path=hook_env["registry"],
        )

        settings = json.loads(settings_path.read_text())
        hooks = settings["hooks"]

        # User hook preserved
        user_hooks = [h for h in hooks if not any(
            hh.get("__hawk_managed") for hh in h.get("hooks", [])
        )]
        assert len(user_hooks) == 1
        assert user_hooks[0]["hooks"][0]["command"] == "/usr/local/bin/my-hook"

        # Hawk hook added
        hawk_hooks = [h for h in hooks if any(
            hh.get("__hawk_managed") for hh in h.get("hooks", [])
        )]
        assert len(hawk_hooks) == 1

    def test_cleanup_on_empty_hooks(self, hook_env):
        """When hook list becomes empty, remove all hawk entries from settings.json."""
        adapter = ClaudeAdapter()

        # First: register hooks
        adapter.register_hooks(
            ["pre_tool_use/file-guard.py"],
            hook_env["target"],
            registry_path=hook_env["registry"],
        )
        settings = json.loads((hook_env["target"] / "settings.json").read_text())
        assert len(settings["hooks"]) > 0

        # Add a user hook
        settings["hooks"].append({
            "matcher": "Stop",
            "hooks": [{"type": "command", "command": "/usr/local/bin/my-stop-hook"}],
        })
        (hook_env["target"] / "settings.json").write_text(json.dumps(settings, indent=2))

        # Now: register with empty hooks
        adapter.register_hooks(
            [],
            hook_env["target"],
            registry_path=hook_env["registry"],
        )

        settings = json.loads((hook_env["target"] / "settings.json").read_text())
        # User hook preserved
        assert len(settings["hooks"]) == 1
        assert settings["hooks"][0]["hooks"][0]["command"] == "/usr/local/bin/my-stop-hook"

    def test_stale_runners_cleaned_up(self, hook_env):
        """Runners for events that no longer have hooks should be deleted."""
        adapter = ClaudeAdapter()

        # First: register pre_tool_use and stop
        adapter.register_hooks(
            ["pre_tool_use/file-guard.py", "stop/notify.py"],
            hook_env["target"],
            registry_path=hook_env["registry"],
        )
        assert (hook_env["runners_dir"] / "pre_tool_use.sh").exists()
        assert (hook_env["runners_dir"] / "stop.sh").exists()

        # Now: only register pre_tool_use
        adapter.register_hooks(
            ["pre_tool_use/file-guard.py"],
            hook_env["target"],
            registry_path=hook_env["registry"],
        )
        assert (hook_env["runners_dir"] / "pre_tool_use.sh").exists()
        assert not (hook_env["runners_dir"] / "stop.sh").exists()

    def test_per_hook_granularity(self, hook_env):
        """Only enabled hooks appear in runner, not all hooks in event dir."""
        adapter = ClaudeAdapter()

        # Only enable file-guard, not dangerous-cmd
        adapter.register_hooks(
            ["pre_tool_use/file-guard.py"],
            hook_env["target"],
            registry_path=hook_env["registry"],
        )

        content = (hook_env["runners_dir"] / "pre_tool_use.sh").read_text()
        assert "file-guard.py" in content
        assert "dangerous-cmd.sh" not in content

    def test_runner_is_executable(self, hook_env):
        import os
        import stat
        adapter = ClaudeAdapter()
        adapter.register_hooks(
            ["pre_tool_use/file-guard.py"],
            hook_env["target"],
            registry_path=hook_env["registry"],
        )

        runner = hook_env["runners_dir"] / "pre_tool_use.sh"
        mode = os.stat(runner).st_mode
        assert mode & stat.S_IXUSR  # Owner execute bit


class TestClaudePromptSync:
    """Tests for prompt syncing via the commands directory."""

    def test_prompts_go_to_commands_dir(self, adapter, tmp_path):
        """Claude maps prompts to commands/."""
        target = tmp_path / "claude"
        target.mkdir()
        assert adapter.get_prompts_dir(target) == adapter.get_commands_dir(target)

    def test_sync_links_prompts(self, adapter, tmp_path, setup_registry):
        target = tmp_path / "claude"
        target.mkdir()

        # Add a prompt to registry
        prompts_dir = setup_registry / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        (prompts_dir / "code-audit.md").write_text("# Code Audit\nReview this code.")

        resolved = ResolvedSet(prompts=["code-audit.md"])
        result = adapter.sync(resolved, target, setup_registry)

        assert "code-audit.md" in result.linked
        # Should be in commands/ dir since Claude maps prompts there
        assert (target / "commands" / "code-audit.md").is_symlink()
