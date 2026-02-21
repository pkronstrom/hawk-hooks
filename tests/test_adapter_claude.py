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

    # Prompts
    prompts_dir = registry / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "deploy.md").write_text("# Deploy Prompt")

    # Hooks (flat layout with hawk-hook headers)
    hooks_dir = registry / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "file-guard.py").write_text(
        "#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys, json\nprint(json.dumps({'decision': 'approve'}))\n"
    )
    (hooks_dir / "dangerous-cmd.sh").write_text(
        "#!/bin/bash\n# hawk-hook: events=pre_tool_use\nexit 0\n"
    )
    (hooks_dir / "notify.py").write_text(
        "#!/usr/bin/env python3\n# hawk-hook: events=stop\nimport sys\nprint('')\n"
    )
    (hooks_dir / "completion-check.md").write_text(
        "---\nhawk-hook:\n  events: [stop]\n---\n# Completion check\n"
    )

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
            prompts=["deploy.md"],
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
            "file-guard.py",
            "notify.py",
        ])
        result = adapter.sync(resolved, target, setup_registry)
        assert "hook:file-guard.py" in result.linked
        assert "hook:notify.py" in result.linked

    def test_sync_hooks_without_metadata_skipped(self, adapter, tmp_path, setup_registry, monkeypatch):
        """Hook names without hawk-hook metadata are silently skipped."""
        target = tmp_path / "claude"
        target.mkdir()
        config_dir = tmp_path / "hawk-config"
        config_dir.mkdir()
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

        resolved = ResolvedSet(hooks=["nonexistent-hook"])
        result = adapter.sync(resolved, target, setup_registry)
        assert not any("nonexistent-hook" in h for h in result.linked)


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
        hooks_dir.mkdir(parents=True)

        # pre_tool_use hooks (flat with hawk-hook headers)
        (hooks_dir / "file-guard.py").write_text(
            "#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys, json\nprint(json.dumps({'decision': 'approve'}))\n"
        )
        (hooks_dir / "dangerous-cmd.sh").write_text(
            "#!/bin/bash\n# hawk-hook: events=pre_tool_use\nexit 0\n"
        )

        # stop hooks
        (hooks_dir / "notify.py").write_text(
            "#!/usr/bin/env python3\n# hawk-hook: events=stop\nprint('')\n"
        )
        (hooks_dir / "completion-check.md").write_text(
            "---\nhawk-hook:\n  events: [stop]\n---\n# Completion check\nDid you finish all tasks?\n"
        )

        # session_start hooks
        (hooks_dir / "greet.sh").write_text(
            "#!/bin/bash\n# hawk-hook: events=session_start\necho 'Hello'\n"
        )

        target = tmp_path / "claude"
        target.mkdir()

        return {
            "config_dir": config_dir,
            "registry": registry,
            "target": target,
            "runners_dir": target / "runners",
        }

    def test_generates_runner_per_event(self, hook_env):
        adapter = ClaudeAdapter()
        hook_names = [
            "file-guard.py",
            "dangerous-cmd.sh",
            "notify.py",
        ]
        registered = adapter.register_hooks(
            hook_names, hook_env["target"], registry_path=hook_env["registry"]
        )

        runners_dir = hook_env["runners_dir"]
        assert (runners_dir / "pre_tool_use.sh").exists()
        assert (runners_dir / "stop.sh").exists()
        # session_start not in hook_names, so no runner
        assert not (runners_dir / "session_start.sh").exists()

        assert "file-guard.py" in registered
        assert "dangerous-cmd.sh" in registered
        assert "notify.py" in registered

    def test_runner_content_chains_hooks(self, hook_env):
        adapter = ClaudeAdapter()
        hook_names = [
            "file-guard.py",
            "dangerous-cmd.sh",
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

    def test_runner_handles_content_hooks(self, hook_env):
        adapter = ClaudeAdapter()
        hook_names = ["completion-check.md"]
        adapter.register_hooks(
            hook_names, hook_env["target"], registry_path=hook_env["registry"]
        )

        content = (hook_env["runners_dir"] / "stop.sh").read_text()
        # Content hooks use cat
        assert "cat" in content
        assert "completion-check.md" in content

    def test_runner_handles_py_hooks(self, hook_env):
        adapter = ClaudeAdapter()
        hook_names = ["file-guard.py"]
        adapter.register_hooks(
            hook_names, hook_env["target"], registry_path=hook_env["registry"]
        )

        content = (hook_env["runners_dir"] / "pre_tool_use.sh").read_text()
        assert "python3" in content
        assert "file-guard.py" in content

    def test_runner_handles_sh_hooks(self, hook_env):
        adapter = ClaudeAdapter()
        hook_names = ["dangerous-cmd.sh"]
        adapter.register_hooks(
            hook_names, hook_env["target"], registry_path=hook_env["registry"]
        )

        content = (hook_env["runners_dir"] / "pre_tool_use.sh").read_text()
        assert "dangerous-cmd.sh" in content

    def test_settings_json_registration(self, hook_env):
        adapter = ClaudeAdapter()
        hook_names = [
            "file-guard.py",
            "notify.py",
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
        """Verify canonical snake_case -> Claude PascalCase mapping."""
        adapter = ClaudeAdapter()
        hook_names = [
            "file-guard.py",
            "notify.py",
            "greet.sh",
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
            ["file-guard.py"],
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
            ["file-guard.py"],
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
            ["file-guard.py", "notify.py"],
            hook_env["target"],
            registry_path=hook_env["registry"],
        )
        assert (hook_env["runners_dir"] / "pre_tool_use.sh").exists()
        assert (hook_env["runners_dir"] / "stop.sh").exists()

        # Now: only register pre_tool_use
        adapter.register_hooks(
            ["file-guard.py"],
            hook_env["target"],
            registry_path=hook_env["registry"],
        )
        assert (hook_env["runners_dir"] / "pre_tool_use.sh").exists()
        assert not (hook_env["runners_dir"] / "stop.sh").exists()

    def test_per_hook_granularity(self, hook_env):
        """Only enabled hooks appear in runner, not all hooks in registry."""
        adapter = ClaudeAdapter()

        # Only enable file-guard, not dangerous-cmd
        adapter.register_hooks(
            ["file-guard.py"],
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
            ["file-guard.py"],
            hook_env["target"],
            registry_path=hook_env["registry"],
        )

        runner = hook_env["runners_dir"] / "pre_tool_use.sh"
        mode = os.stat(runner).st_mode
        assert mode & stat.S_IXUSR  # Owner execute bit

    def test_runners_are_per_project(self, tmp_path, monkeypatch):
        """Each project should get its own runners directory, not a shared global one."""
        config_dir = tmp_path / "hawk-config"
        config_dir.mkdir()
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "guard.py").write_text(
            "#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n"
        )

        adapter = ClaudeAdapter()

        # Project A
        target_a = tmp_path / "project-a" / ".claude"
        target_a.mkdir(parents=True)
        adapter.register_hooks(["guard.py"], target_a, registry_path=registry)

        # Project B
        target_b = tmp_path / "project-b" / ".claude"
        target_b.mkdir(parents=True)
        adapter.register_hooks(["guard.py"], target_b, registry_path=registry)

        # Each project has its own runners dir
        assert (target_a / "runners" / "pre_tool_use.sh").exists()
        assert (target_b / "runners" / "pre_tool_use.sh").exists()

        # Global config dir should NOT have runners
        assert not (config_dir / "runners").exists()


class TestClaudePromptHooks:
    """Tests for .prompt.json native Claude hook registration."""

    @pytest.fixture
    def prompt_hook_env(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "hawk-config"
        config_dir.mkdir()
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)

        target = tmp_path / "claude"
        target.mkdir()

        return {"registry": registry, "target": target, "hooks_dir": hooks_dir}

    def test_prompt_json_registered_as_type_prompt(self, prompt_hook_env):
        hooks_dir = prompt_hook_env["hooks_dir"]
        (hooks_dir / "guard.prompt.json").write_text(json.dumps({
            "prompt": "Evaluate if this action is safe.",
            "timeout": 30,
            "hawk-hook": {"events": ["pre_tool_use"]},
        }))

        adapter = ClaudeAdapter()
        registered = adapter.register_hooks(
            ["guard.prompt.json"],
            prompt_hook_env["target"],
            registry_path=prompt_hook_env["registry"],
        )

        assert "guard.prompt.json" in registered

        settings = json.loads((prompt_hook_env["target"] / "settings.json").read_text())
        hawk_hooks = [h for h in settings["hooks"] if any(
            hh.get("__hawk_managed") for hh in h.get("hooks", [])
        )]
        assert len(hawk_hooks) == 1
        entry = hawk_hooks[0]
        assert entry["matcher"] == "PreToolUse"
        assert entry["hooks"][0]["type"] == "prompt"
        assert entry["hooks"][0]["prompt"] == "Evaluate if this action is safe."
        assert entry["hooks"][0]["timeout"] == 30

    def test_prompt_json_default_event(self, prompt_hook_env):
        """Prompt hooks without explicit events default to pre_tool_use."""
        hooks_dir = prompt_hook_env["hooks_dir"]
        (hooks_dir / "check.prompt.json").write_text(json.dumps({
            "prompt": "Check this operation.",
            "hawk-hook": {"events": []},
        }))

        adapter = ClaudeAdapter()
        adapter.register_hooks(
            ["check.prompt.json"],
            prompt_hook_env["target"],
            registry_path=prompt_hook_env["registry"],
        )

        settings = json.loads((prompt_hook_env["target"] / "settings.json").read_text())
        hawk_hooks = [h for h in settings["hooks"] if any(
            hh.get("__hawk_managed") for hh in h.get("hooks", [])
        )]
        assert len(hawk_hooks) == 1
        assert hawk_hooks[0]["matcher"] == "PreToolUse"

    def test_mixed_script_and_prompt_hooks(self, prompt_hook_env):
        """Both script and prompt hooks can be registered together."""
        hooks_dir = prompt_hook_env["hooks_dir"]
        (hooks_dir / "guard.py").write_text(
            "#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n"
        )
        (hooks_dir / "eval.prompt.json").write_text(json.dumps({
            "prompt": "Evaluate safety.",
            "hawk-hook": {"events": ["stop"]},
        }))

        adapter = ClaudeAdapter()
        registered = adapter.register_hooks(
            ["guard.py", "eval.prompt.json"],
            prompt_hook_env["target"],
            registry_path=prompt_hook_env["registry"],
        )

        assert "guard.py" in registered
        assert "eval.prompt.json" in registered

        settings = json.loads((prompt_hook_env["target"] / "settings.json").read_text())
        hawk_hooks = [h for h in settings["hooks"] if any(
            hh.get("__hawk_managed") for hh in h.get("hooks", [])
        )]
        assert len(hawk_hooks) == 2

        types = {h["hooks"][0]["type"] for h in hawk_hooks}
        assert types == {"command", "prompt"}

    def test_prompt_json_without_prompt_field_skipped(self, prompt_hook_env):
        """Prompt hooks without a prompt field are skipped."""
        hooks_dir = prompt_hook_env["hooks_dir"]
        (hooks_dir / "bad.prompt.json").write_text(json.dumps({
            "hawk-hook": {"events": ["pre_tool_use"]},
        }))

        adapter = ClaudeAdapter()
        registered = adapter.register_hooks(
            ["bad.prompt.json"],
            prompt_hook_env["target"],
            registry_path=prompt_hook_env["registry"],
        )

        # File exists in registry, so it's in registered list, but no settings entry
        settings_path = prompt_hook_env["target"] / "settings.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
            hawk_hooks = [h for h in settings.get("hooks", []) if any(
                hh.get("__hawk_managed") for hh in h.get("hooks", [])
            )]
            assert len(hawk_hooks) == 0


class TestClaudeTimeoutPropagation:
    """Tests for timeout propagation in hook entries."""

    @pytest.fixture
    def timeout_env(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "hawk-config"
        config_dir.mkdir()
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)

        target = tmp_path / "claude"
        target.mkdir()

        return {"registry": registry, "target": target, "hooks_dir": hooks_dir}

    def test_timeout_propagated_to_settings(self, timeout_env):
        hooks_dir = timeout_env["hooks_dir"]
        (hooks_dir / "guard.py").write_text(
            "#!/usr/bin/env python3\n"
            "# hawk-hook: events=pre_tool_use\n"
            "# hawk-hook: timeout=60\n"
            "import sys\n"
        )

        adapter = ClaudeAdapter()
        adapter.register_hooks(
            ["guard.py"],
            timeout_env["target"],
            registry_path=timeout_env["registry"],
        )

        settings = json.loads((timeout_env["target"] / "settings.json").read_text())
        hawk_hooks = [h for h in settings["hooks"] if any(
            hh.get("__hawk_managed") for hh in h.get("hooks", [])
        )]
        assert hawk_hooks[0]["hooks"][0].get("timeout") == 60

    def test_max_timeout_across_hooks(self, timeout_env):
        hooks_dir = timeout_env["hooks_dir"]
        (hooks_dir / "fast.py").write_text(
            "#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\n# hawk-hook: timeout=10\nimport sys\n"
        )
        (hooks_dir / "slow.py").write_text(
            "#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\n# hawk-hook: timeout=120\nimport sys\n"
        )

        adapter = ClaudeAdapter()
        adapter.register_hooks(
            ["fast.py", "slow.py"],
            timeout_env["target"],
            registry_path=timeout_env["registry"],
        )

        settings = json.loads((timeout_env["target"] / "settings.json").read_text())
        hawk_hooks = [h for h in settings["hooks"] if any(
            hh.get("__hawk_managed") for hh in h.get("hooks", [])
        )]
        pre_tool = [h for h in hawk_hooks if h["matcher"] == "PreToolUse"][0]
        assert pre_tool["hooks"][0]["timeout"] == 120

    def test_no_timeout_when_zero(self, timeout_env):
        hooks_dir = timeout_env["hooks_dir"]
        (hooks_dir / "guard.py").write_text(
            "#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n"
        )

        adapter = ClaudeAdapter()
        adapter.register_hooks(
            ["guard.py"],
            timeout_env["target"],
            registry_path=timeout_env["registry"],
        )

        settings = json.loads((timeout_env["target"] / "settings.json").read_text())
        hawk_hooks = [h for h in settings["hooks"] if any(
            hh.get("__hawk_managed") for hh in h.get("hooks", [])
        )]
        assert "timeout" not in hawk_hooks[0]["hooks"][0]


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
