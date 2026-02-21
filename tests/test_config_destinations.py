"""Tests for destination configuration."""

from hawk_hooks import config


class TestDestinations:
    """Test destination path management."""

    def test_default_destinations(self):
        dests = config.get_default_destinations()
        assert "claude" in dests
        assert "gemini" in dests
        assert "codex" in dests
        assert dests["claude"]["prompts"] == "~/.claude/commands/"

    def test_get_destination(self, tmp_path, monkeypatch):
        # Use temp config
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        dest = config.get_destination("claude", "prompts")
        assert "/.claude/commands" in dest

    def test_set_destination(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        config.set_destination("claude", "prompts", "/custom/path/")
        dest = config.get_destination("claude", "prompts")
        assert dest == "/custom/path/"


class TestPromptsConfig:
    """Test prompts/agents enabled state management."""

    def test_prompts_default_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        prompts = config.get_prompts_config()
        assert prompts == {}

    def test_set_prompt_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        config.set_prompt_enabled("my-command", True, hook_enabled=False)
        prompts = config.get_prompts_config()
        assert prompts["my-command"]["enabled"] is True
        assert prompts["my-command"]["hook_enabled"] is False

    def test_is_prompt_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        config.set_prompt_enabled("test", True)
        assert config.is_prompt_enabled("test") is True
        assert config.is_prompt_enabled("nonexistent") is False


class TestAgentsConfig:
    """Test agents enabled state management."""

    def test_agents_default_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        agents = config.get_agents_config()
        assert agents == {}

    def test_set_agent_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        config.set_agent_enabled("code-reviewer", True, hook_enabled=True)
        agents = config.get_agents_config()
        assert agents["code-reviewer"]["enabled"] is True
        assert agents["code-reviewer"]["hook_enabled"] is True
