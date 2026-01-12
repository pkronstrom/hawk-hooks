"""Integration tests for prompts feature."""


import pytest

from captain_hook import config, prompt_scanner, sync
from captain_hook.types import PromptType


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    """Set up test environment."""
    # Mock config dir
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    config.ensure_dirs()

    # Create test prompt
    prompts_dir = config.get_prompts_dir()
    (prompts_dir / "test-cmd.md").write_text("""---
name: test-cmd
description: Test command
tools: [claude]
---
Test content.
""")

    # Create test agent
    agents_dir = config.get_agents_dir()
    (agents_dir / "test-agent.md").write_text("""---
name: test-agent
description: Test agent
tools: [claude]
hooks:
  - session_start
---
Agent content.
""")

    # Create destination dirs
    claude_cmds = tmp_path / "claude" / "commands"
    claude_cmds.mkdir(parents=True)
    claude_agents = tmp_path / "claude" / "agents"
    claude_agents.mkdir(parents=True)

    monkeypatch.setattr(
        config, "get_destination", lambda tool, item_type: str(tmp_path / tool / item_type)
    )

    return tmp_path


class TestFullWorkflow:
    """Test complete workflow."""

    def test_scan_enable_sync_disable(self, setup_env):
        # Scan
        prompts = prompt_scanner.scan_prompts()
        assert len(prompts) == 1
        assert prompts[0].name == "test-cmd"

        # Enable
        config.set_prompt_enabled("test-cmd", True)
        assert config.is_prompt_enabled("test-cmd")

        # Sync
        prompt = prompts[0]
        created = sync.sync_prompt(prompt)
        assert len(created) == 1
        assert created[0].exists()

        # Disable
        config.set_prompt_enabled("test-cmd", False)
        removed = sync.unsync_prompt(prompt)
        assert len(removed) == 1
        assert not removed[0].exists()

    def test_agent_with_hooks(self, setup_env):
        agents = prompt_scanner.scan_agents()
        assert len(agents) == 1
        assert agents[0].has_hooks

        # Check hook config
        hooks = agents[0].hooks
        assert hooks[0].event == "session_start"

    def test_scan_all_prompts(self, setup_env):
        all_prompts = prompt_scanner.scan_all_prompts()
        assert len(all_prompts) == 2

        types = {p.prompt_type for p in all_prompts}
        assert PromptType.COMMAND in types
        assert PromptType.AGENT in types

    def test_get_prompt_by_name(self, setup_env):
        prompt = prompt_scanner.get_prompt_by_name("test-cmd")
        assert prompt is not None
        assert prompt.name == "test-cmd"

        agent = prompt_scanner.get_prompt_by_name("test-agent")
        assert agent is not None
        assert agent.prompt_type == PromptType.AGENT

        nonexistent = prompt_scanner.get_prompt_by_name("does-not-exist")
        assert nonexistent is None


class TestConfigPersistence:
    """Test config persistence."""

    def test_prompt_config_survives_reload(self, setup_env):
        # Set enabled
        config.set_prompt_enabled("test-cmd", True, hook_enabled=True)

        # Reload and check
        assert config.is_prompt_enabled("test-cmd")
        assert config.is_prompt_hook_enabled("test-cmd")

    def test_agent_config_survives_reload(self, setup_env):
        config.set_agent_enabled("test-agent", True, hook_enabled=False)

        assert config.is_agent_enabled("test-agent")
        assert not config.is_agent_hook_enabled("test-agent")


class TestMultiToolSync:
    """Test syncing to multiple tools."""

    def test_sync_prompt_to_claude_only(self, setup_env, tmp_path):
        prompts = prompt_scanner.scan_prompts()
        prompt = prompts[0]

        # Sync only to claude
        created = sync.sync_prompt(prompt, ["claude"])
        assert len(created) == 1
        assert "claude" in str(created[0])

    def test_prompt_with_all_tools(self, setup_env, tmp_path):
        # Create prompt targeting all tools
        prompts_dir = config.get_prompts_dir()
        (prompts_dir / "multi-tool.md").write_text("""---
name: multi-tool
description: Multi-tool command
tools: all
---
Works everywhere.
""")

        prompts = prompt_scanner.scan_prompts()
        multi = next(p for p in prompts if p.name == "multi-tool")

        # Should have all tools expanded
        assert "claude" in multi.tools
        assert "gemini" in multi.tools
        assert "codex" in multi.tools
