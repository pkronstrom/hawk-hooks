"""Tests for frontmatter parsing."""

import pytest
from hawk_hooks.frontmatter import PromptFrontmatter, parse_frontmatter


class TestParseFrontmatter:
    """Test frontmatter parsing from markdown content."""

    def test_parse_basic_frontmatter(self):
        content = """---
name: my-command
description: A test command
tools: [claude]
---

Command content here.
"""
        fm, body = parse_frontmatter(content)
        assert fm.name == "my-command"
        assert fm.description == "A test command"
        assert fm.tools == ["claude"]
        assert fm.hooks == []
        assert body.strip() == "Command content here."

    def test_parse_tools_all_shorthand(self):
        content = """---
name: universal
description: Works everywhere
tools: all
---
Content.
"""
        fm, body = parse_frontmatter(content)
        assert fm.tools == ["claude", "gemini", "codex"]

    def test_parse_with_hooks(self):
        content = """---
name: my-guard
description: Guards dangerous operations
tools: [claude, gemini]
hooks:
  - event: pre_tool
    matchers: [Bash, Edit]
  - session_start
---
Content.
"""
        fm, body = parse_frontmatter(content)
        assert len(fm.hooks) == 2
        assert fm.hooks[0].event == "pre_tool"
        assert fm.hooks[0].matchers == ["Bash", "Edit"]
        assert fm.hooks[1].event == "session_start"
        assert fm.hooks[1].matchers == []

    def test_parse_no_frontmatter(self):
        content = "Just plain content without frontmatter."
        fm, body = parse_frontmatter(content)
        assert fm is None
        assert body == content

    def test_parse_empty_frontmatter(self):
        content = """---
---
Content only.
"""
        fm, body = parse_frontmatter(content)
        assert fm is None
        assert body.strip() == "Content only."

    def test_missing_required_fields(self):
        content = """---
name: incomplete
---
Content.
"""
        with pytest.raises(ValueError, match="Missing required field"):
            parse_frontmatter(content)


class TestPromptFrontmatter:
    """Test PromptFrontmatter dataclass."""

    def test_has_hooks(self):
        fm = PromptFrontmatter(
            name="test",
            description="Test",
            tools=["claude"],
            hooks=[],
        )
        assert fm.has_hooks is False

    def test_has_hooks_with_hooks(self):
        from hawk_hooks.frontmatter import HookConfig

        fm = PromptFrontmatter(
            name="test",
            description="Test",
            tools=["claude"],
            hooks=[HookConfig(event="pre_tool", matchers=[])],
        )
        assert fm.has_hooks is True
