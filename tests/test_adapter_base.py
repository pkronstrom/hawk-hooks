"""Tests for the adapter base class and registry."""

import pytest

from hawk_hooks.adapters import get_adapter, list_adapters
from hawk_hooks.adapters.base import ToolAdapter
from hawk_hooks.types import Tool


class TestToolAdapterABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            ToolAdapter()

    def test_requires_all_abstract_methods(self):
        # Incomplete implementation should fail
        class IncompleteAdapter(ToolAdapter):
            @property
            def tool(self):
                return Tool.CLAUDE

        with pytest.raises(TypeError):
            IncompleteAdapter()


class TestAdapterRegistry:
    def test_get_claude_adapter(self):
        adapter = get_adapter(Tool.CLAUDE)
        assert adapter.tool == Tool.CLAUDE

    def test_get_gemini_adapter(self):
        adapter = get_adapter(Tool.GEMINI)
        assert adapter.tool == Tool.GEMINI

    def test_get_codex_adapter(self):
        adapter = get_adapter(Tool.CODEX)
        assert adapter.tool == Tool.CODEX

    def test_get_opencode_adapter(self):
        adapter = get_adapter(Tool.OPENCODE)
        assert adapter.tool == Tool.OPENCODE

    def test_list_adapters(self):
        adapters = list_adapters()
        assert len(adapters) == 4
        assert Tool.CLAUDE in adapters


class TestBaseSymlinkOps:
    def test_link_and_unlink_skill(self, tmp_path):
        adapter = get_adapter(Tool.CLAUDE)
        source = tmp_path / "registry" / "skills" / "tdd"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("# TDD")

        target = tmp_path / "claude"
        target.mkdir()

        dest = adapter.link_skill(source, target)
        assert dest.is_symlink()
        assert (dest / "SKILL.md").read_text() == "# TDD"

        assert adapter.unlink_skill(source.name, target) is True
        assert not dest.exists()

    def test_link_and_unlink_agent(self, tmp_path):
        adapter = get_adapter(Tool.CLAUDE)
        source = tmp_path / "registry" / "agents" / "reviewer.md"
        source.parent.mkdir(parents=True)
        source.write_text("# Reviewer")

        target = tmp_path / "claude"
        target.mkdir()

        dest = adapter.link_agent(source, target)
        assert dest.is_symlink()

        assert adapter.unlink_agent(source.name, target) is True

    def test_link_and_unlink_command(self, tmp_path):
        adapter = get_adapter(Tool.CLAUDE)
        source = tmp_path / "registry" / "commands" / "deploy.md"
        source.parent.mkdir(parents=True)
        source.write_text("# Deploy")

        target = tmp_path / "claude"
        target.mkdir()

        dest = adapter.link_command(source, target)
        assert dest.is_symlink()

        assert adapter.unlink_command(source.name, target) is True

    def test_unlink_nonexistent_returns_false(self, tmp_path):
        adapter = get_adapter(Tool.CLAUDE)
        target = tmp_path / "claude"
        target.mkdir()
        (target / "skills").mkdir()

        assert adapter.unlink_skill("nonexistent", target) is False

    def test_link_replaces_existing(self, tmp_path):
        adapter = get_adapter(Tool.CLAUDE)
        source1 = tmp_path / "v1" / "skill.md"
        source1.parent.mkdir()
        source1.write_text("v1")

        source2 = tmp_path / "v2" / "skill.md"
        source2.parent.mkdir()
        source2.write_text("v2")

        target = tmp_path / "claude"
        target.mkdir()

        adapter.link_skill(source1, target)
        adapter.link_skill(source2, target)

        dest = adapter.get_skills_dir(target) / "skill.md"
        assert dest.read_text() == "v2"
