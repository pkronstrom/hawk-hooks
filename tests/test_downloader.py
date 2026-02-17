"""Tests for the downloader module."""

from pathlib import Path

import pytest

from hawk_hooks.downloader import (
    ClassifiedContent,
    ClassifiedItem,
    add_items_to_registry,
    check_clashes,
    classify,
)
from hawk_hooks.registry import Registry
from hawk_hooks.types import ComponentType


@pytest.fixture
def registry(tmp_path):
    reg = Registry(tmp_path / "registry")
    reg.ensure_dirs()
    return reg


class TestClassify:
    def test_structured_skills_dir(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        tdd = skills / "tdd"
        tdd.mkdir()
        (tdd / "SKILL.md").write_text("# TDD")

        content = classify(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.SKILL
        assert content.items[0].name == "tdd"

    def test_structured_commands_dir(self, tmp_path):
        commands = tmp_path / "commands"
        commands.mkdir()
        (commands / "deploy.md").write_text("# Deploy")
        (commands / "test.md").write_text("# Test")

        content = classify(tmp_path)
        assert len(content.items) == 2
        types = {i.component_type for i in content.items}
        assert types == {ComponentType.COMMAND}

    def test_structured_hooks_dir(self, tmp_path):
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        (hooks / "guard.py").write_text("import sys")

        content = classify(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.HOOK

    def test_structured_agents_dir(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        (agents / "reviewer.md").write_text("# Reviewer")

        content = classify(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.AGENT

    def test_mcp_dir(self, tmp_path):
        mcp = tmp_path / "mcp"
        mcp.mkdir()
        (mcp / "github.yaml").write_text("command: gh-mcp")

        content = classify(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.MCP

    def test_top_level_fallback_md(self, tmp_path):
        (tmp_path / "my-skill.md").write_text("# Skill")

        content = classify(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.SKILL

    def test_top_level_fallback_script(self, tmp_path):
        (tmp_path / "guard.py").write_text("import sys")

        content = classify(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.HOOK

    def test_mixed_structure(self, tmp_path):
        (tmp_path / "skills").mkdir()
        (tmp_path / "skills" / "tdd.md").write_text("TDD")
        (tmp_path / "hooks").mkdir()
        (tmp_path / "hooks" / "guard.sh").write_text("#!/bin/bash")
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "deploy.md").write_text("Deploy")

        content = classify(tmp_path)
        types = {i.component_type for i in content.items}
        assert ComponentType.SKILL in types
        assert ComponentType.HOOK in types
        assert ComponentType.COMMAND in types

    def test_empty_dir(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        content = classify(empty)
        assert content.items == []

    def test_nonexistent_dir(self, tmp_path):
        content = classify(tmp_path / "nonexistent")
        assert content.items == []

    def test_skips_dotfiles(self, tmp_path):
        (tmp_path / "skills").mkdir()
        (tmp_path / "skills" / ".hidden").write_text("hidden")
        (tmp_path / "skills" / "visible.md").write_text("visible")

        content = classify(tmp_path)
        names = [i.name for i in content.items]
        assert ".hidden" not in names
        assert "visible.md" in names


class TestByType:
    def test_group_by_type(self):
        items = [
            ClassifiedItem(ComponentType.SKILL, "a", Path("a")),
            ClassifiedItem(ComponentType.SKILL, "b", Path("b")),
            ClassifiedItem(ComponentType.HOOK, "c", Path("c")),
        ]
        content = ClassifiedContent(items=items)
        by_type = content.by_type
        assert len(by_type[ComponentType.SKILL]) == 2
        assert len(by_type[ComponentType.HOOK]) == 1


class TestClashDetection:
    def test_detects_existing(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("existing")
        registry.add(ComponentType.SKILL, "skill.md", source)

        items = [ClassifiedItem(ComponentType.SKILL, "skill.md", source)]
        clashes = check_clashes(items, registry)
        assert len(clashes) == 1

    def test_no_clash(self, registry, tmp_path):
        items = [ClassifiedItem(ComponentType.SKILL, "new.md", tmp_path / "new.md")]
        clashes = check_clashes(items, registry)
        assert len(clashes) == 0


class TestAddToRegistry:
    def test_add_items(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("content")

        items = [ClassifiedItem(ComponentType.SKILL, "skill.md", source)]
        added, skipped = add_items_to_registry(items, registry)
        assert len(added) == 1
        assert len(skipped) == 0
        assert registry.has(ComponentType.SKILL, "skill.md")

    def test_skip_existing(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("content")
        registry.add(ComponentType.SKILL, "skill.md", source)

        items = [ClassifiedItem(ComponentType.SKILL, "skill.md", source)]
        added, skipped = add_items_to_registry(items, registry)
        assert len(added) == 0
        assert len(skipped) == 1

    def test_replace_existing(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("v1")
        registry.add(ComponentType.SKILL, "skill.md", source)

        source.write_text("v2")
        items = [ClassifiedItem(ComponentType.SKILL, "skill.md", source)]
        added, skipped = add_items_to_registry(items, registry, replace=True)
        assert len(added) == 1
        assert registry.get_path(ComponentType.SKILL, "skill.md").read_text() == "v2"
