"""Tests for prompt/agent scanner."""


import pytest
from captain_hook.prompt_scanner import scan_agents, scan_all_prompts, scan_prompts

from captain_hook.types import PromptType


@pytest.fixture
def prompts_dir(tmp_path):
    """Create a temporary prompts directory with test files."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()

    # Valid prompt
    (prompts / "test-command.md").write_text("""---
name: test-command
description: A test command
tools: [claude]
---
Command content.
""")

    # Prompt with hooks
    (prompts / "guard.md").write_text("""---
name: guard
description: A guard hook
tools: all
hooks:
  - event: pre_tool
    matchers: [Bash]
---
Guard content.
""")

    # Invalid (no frontmatter)
    (prompts / "no-frontmatter.md").write_text("Just content")

    return prompts


@pytest.fixture
def agents_dir(tmp_path):
    """Create a temporary agents directory."""
    agents = tmp_path / "agents"
    agents.mkdir()

    (agents / "reviewer.md").write_text("""---
name: code-reviewer
description: Reviews code
tools: [claude, gemini]
hooks:
  - session_start
---
You are a code reviewer...
""")

    return agents


class TestScanPrompts:
    """Test prompt scanning."""

    def test_scan_finds_valid_prompts(self, prompts_dir):
        results = scan_prompts(prompts_dir)
        names = [p.name for p in results]
        assert "test-command" in names
        assert "guard" in names

    def test_scan_skips_invalid_files(self, prompts_dir):
        results = scan_prompts(prompts_dir)
        names = [p.name for p in results]
        assert "no-frontmatter" not in names

    def test_scan_parses_hooks(self, prompts_dir):
        results = scan_prompts(prompts_dir)
        guard = next(p for p in results if p.name == "guard")
        assert guard.has_hooks is True
        assert guard.hooks[0].event == "pre_tool"

    def test_scan_sets_prompt_type(self, prompts_dir):
        results = scan_prompts(prompts_dir)
        for p in results:
            assert p.prompt_type == PromptType.COMMAND


class TestScanAgents:
    """Test agent scanning."""

    def test_scan_finds_agents(self, agents_dir):
        results = scan_agents(agents_dir)
        assert len(results) == 1
        assert results[0].name == "code-reviewer"

    def test_scan_sets_agent_type(self, agents_dir):
        results = scan_agents(agents_dir)
        assert results[0].prompt_type == PromptType.AGENT


class TestScanAll:
    """Test combined scanning."""

    def test_scan_all_returns_both(self, prompts_dir, agents_dir, monkeypatch):
        from captain_hook import config

        monkeypatch.setattr(config, "get_prompts_dir", lambda: prompts_dir)
        monkeypatch.setattr(config, "get_agents_dir", lambda: agents_dir)

        results = scan_all_prompts()
        types = {p.prompt_type for p in results}
        assert PromptType.COMMAND in types
        assert PromptType.AGENT in types
