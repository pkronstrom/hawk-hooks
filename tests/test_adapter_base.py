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
        assert len(adapters) == 6
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


class TestSyncForeignProtection:
    """Sync should not overwrite items managed by other tools."""

    def test_skips_foreign_symlink(self, tmp_path):
        """Sync should skip a skill that's already symlinked by another tool."""
        from hawk_hooks.types import ResolvedSet, SyncResult

        adapter = get_adapter(Tool.CLAUDE)

        # Set up hawk registry with a skill called "tdd"
        registry = tmp_path / "registry"
        hawk_skill = registry / "skills" / "tdd"
        hawk_skill.mkdir(parents=True)
        (hawk_skill / "SKILL.md").write_text("# Hawk TDD")

        # Set up target dir with "tdd" already linked by something else (e.g. obra)
        target = tmp_path / "claude"
        skills_dir = target / "skills"
        skills_dir.mkdir(parents=True)

        foreign_source = tmp_path / "obra" / "tdd"
        foreign_source.mkdir(parents=True)
        (foreign_source / "SKILL.md").write_text("# Obra TDD")
        (skills_dir / "tdd").symlink_to(foreign_source)

        # Sync should skip tdd and report it
        resolved = ResolvedSet(skills=["tdd"])
        result = adapter.sync(resolved, target, registry)

        assert "tdd" not in result.linked
        assert any("skip tdd" in e and "not managed by hawk" in e for e in result.errors)
        # Foreign symlink should be untouched
        assert (skills_dir / "tdd").resolve() == foreign_source.resolve()

    def test_skips_regular_file(self, tmp_path):
        """Sync should skip if a regular file (not symlink) already exists."""
        from hawk_hooks.types import ResolvedSet, SyncResult

        adapter = get_adapter(Tool.CLAUDE)

        registry = tmp_path / "registry"
        hawk_skill = registry / "skills" / "my-skill.md"
        (registry / "skills").mkdir(parents=True)
        hawk_skill.write_text("# My skill")

        target = tmp_path / "claude"
        skills_dir = target / "skills"
        skills_dir.mkdir(parents=True)
        # Regular file already there
        (skills_dir / "my-skill.md").write_text("# Manual file")

        resolved = ResolvedSet(skills=["my-skill.md"])
        result = adapter.sync(resolved, target, registry)

        assert "my-skill.md" not in result.linked
        assert any("skip my-skill.md" in e for e in result.errors)
        # Original file untouched
        assert (skills_dir / "my-skill.md").read_text() == "# Manual file"

    def test_replaces_own_symlink(self, tmp_path):
        """Sync should replace a symlink that already points into hawk registry."""
        from hawk_hooks.types import ResolvedSet, SyncResult

        adapter = get_adapter(Tool.CLAUDE)

        registry = tmp_path / "registry"
        hawk_skill = registry / "skills" / "tdd"
        hawk_skill.mkdir(parents=True)
        (hawk_skill / "SKILL.md").write_text("# TDD v2")

        target = tmp_path / "claude"
        skills_dir = target / "skills"
        skills_dir.mkdir(parents=True)
        # Already linked to our own registry (simulating previous sync)
        (skills_dir / "tdd").symlink_to(hawk_skill)

        resolved = ResolvedSet(skills=["tdd"])
        result = adapter.sync(resolved, target, registry)

        # Should not report as error - it's ours, already current
        assert not any("skip tdd" in e for e in result.errors)
