"""Tests for type definitions."""

import pytest

from hawk_hooks.types import PromptInfo, PromptType


class TestPromptType:
    """Test PromptType enum."""

    def test_command_type(self):
        assert PromptType.COMMAND.value == "command"

    def test_agent_type(self):
        assert PromptType.AGENT.value == "agent"

    def test_from_string(self):
        assert PromptType.from_string("command") == PromptType.COMMAND
        assert PromptType.from_string("agent") == PromptType.AGENT

    def test_from_string_invalid(self):
        with pytest.raises(ValueError):
            PromptType.from_string("invalid")


class TestPromptInfo:
    """Test PromptInfo dataclass."""

    def test_create_prompt_info(self):
        from pathlib import Path

        from hawk_hooks.frontmatter import HookConfig, PromptFrontmatter

        fm = PromptFrontmatter(
            name="test",
            description="A test",
            tools=["claude"],
            hooks=[HookConfig(event="pre_tool", matchers=["Bash"])],
        )
        info = PromptInfo(
            path=Path("/tmp/test.md"),
            frontmatter=fm,
            prompt_type=PromptType.COMMAND,
        )
        assert info.name == "test"
        assert info.has_hooks is True
        assert "claude" in info.tools
