"""Tests for the downloader module."""

from pathlib import Path

import pytest

from hawk_hooks.downloader import (
    ClassifiedContent,
    ClassifiedItem,
    PackageMeta,
    add_items_to_registry,
    check_clashes,
    classify,
    get_head_commit,
    scan_directory,
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


    def test_skips_symlinks(self, tmp_path):
        (tmp_path / "skills").mkdir()
        real_file = tmp_path / "skills" / "real.md"
        real_file.write_text("real")
        (tmp_path / "skills" / "link.md").symlink_to(real_file)

        content = classify(tmp_path)
        names = [i.name for i in content.items]
        assert "real.md" in names
        assert "link.md" not in names

    def test_skips_symlinks_top_level(self, tmp_path):
        real_file = tmp_path / "real.md"
        real_file.write_text("real")
        (tmp_path / "link.md").symlink_to(real_file)

        content = classify(tmp_path)
        names = [i.name for i in content.items]
        assert "real.md" in names
        assert "link.md" not in names

    def test_skips_symlinks_mcp(self, tmp_path):
        (tmp_path / "mcp").mkdir()
        real_file = tmp_path / "mcp" / "real.yaml"
        real_file.write_text("x")
        (tmp_path / "mcp" / "link.yaml").symlink_to(real_file)

        content = classify(tmp_path)
        names = [i.name for i in content.items]
        assert "real.yaml" in names
        assert "link.yaml" not in names


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


class TestGetHeadCommit:
    def test_returns_hash_for_git_repo(self, tmp_path):
        """Test with a real git repo."""
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
        (repo / "file.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)

        result = get_head_commit(repo)
        assert len(result) == 40
        assert all(c in "0123456789abcdef" for c in result)

    def test_returns_empty_for_non_repo(self, tmp_path):
        result = get_head_commit(tmp_path)
        assert result == ""


class TestScanDirectory:
    def test_finds_skill_dirs(self, tmp_path):
        """Skill directories with SKILL.md are detected."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# My Skill")

        content = scan_directory(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.SKILL
        assert content.items[0].name == "my-skill"

    def test_finds_nested_skill_dirs(self, tmp_path):
        """Skills nested inside subdirectories are found."""
        nested = tmp_path / "packages" / "frontend" / "my-skill"
        nested.mkdir(parents=True)
        (nested / "SKILL.md").write_text("# Nested Skill")

        content = scan_directory(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].name == "my-skill"

    def test_finds_commands_in_commands_dir(self, tmp_path):
        """Markdown files in commands/ directories are classified as commands."""
        cmds = tmp_path / "commands"
        cmds.mkdir()
        (cmds / "deploy.md").write_text("---\nname: deploy\n---\nDeploy it.")

        content = scan_directory(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.COMMAND

    def test_finds_agents(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        (agents / "reviewer.md").write_text("# Reviewer")

        content = scan_directory(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.AGENT

    def test_finds_hooks(self, tmp_path):
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        (hooks / "pre_check.py").write_text("print('checking')")

        content = scan_directory(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.HOOK

    def test_finds_mcp_configs(self, tmp_path):
        mcp = tmp_path / "mcp"
        mcp.mkdir()
        (mcp / "server.yaml").write_text("command: npx server")

        content = scan_directory(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.MCP

    def test_finds_prompts(self, tmp_path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        (prompts / "review.md").write_text("Review this code.")

        content = scan_directory(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.PROMPT

    def test_skips_git_and_node_modules(self, tmp_path):
        """Skipped directories are not scanned."""
        git = tmp_path / ".git" / "commands"
        git.mkdir(parents=True)
        (git / "internal.md").write_text("git internal")

        nm = tmp_path / "node_modules" / "commands"
        nm.mkdir(parents=True)
        (nm / "dep.md").write_text("dep command")

        content = scan_directory(tmp_path)
        assert len(content.items) == 0

    def test_respects_max_depth(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "d" / "e" / "f" / "commands"
        deep.mkdir(parents=True)
        (deep / "deep.md").write_text("# Deep")

        content = scan_directory(tmp_path, max_depth=3)
        assert len(content.items) == 0

        content = scan_directory(tmp_path, max_depth=10)
        assert len(content.items) == 1

    def test_mixed_types(self, tmp_path):
        """Multiple component types in one tree are all found."""
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "deploy.md").write_text("Deploy")

        skill = tmp_path / "my-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("# Skill")

        (tmp_path / "agents").mkdir()
        (tmp_path / "agents" / "bot.md").write_text("# Bot")

        content = scan_directory(tmp_path)
        types = {item.component_type for item in content.items}
        assert ComponentType.COMMAND in types
        assert ComponentType.SKILL in types
        assert ComponentType.AGENT in types

    def test_empty_directory(self, tmp_path):
        content = scan_directory(tmp_path)
        assert len(content.items) == 0

    def test_frontmatter_md_detected_as_command(self, tmp_path):
        """Standalone .md with name/description frontmatter → command."""
        f = tmp_path / "custom.md"
        f.write_text("---\nname: custom\ndescription: A custom command\n---\nDo the thing.")

        content = scan_directory(tmp_path)
        assert len(content.items) == 1
        assert content.items[0].component_type == ComponentType.COMMAND


class TestClassifyFlatHooks:
    """Test classify() with flat hook files (hawk-hook headers)."""

    def test_flat_hook_with_header(self, tmp_path):
        """File directly in hooks/ with hawk-hook header is classified as hook."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook = hooks_dir / "guard.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")

        content = classify(tmp_path)
        hook_items = [i for i in content.items if i.component_type == ComponentType.HOOK]
        assert len(hook_items) == 1
        assert hook_items[0].name == "guard.py"

    def test_legacy_event_dir_still_works(self, tmp_path):
        """Files in hooks/event_name/ dirs still classified as hooks."""
        hooks_dir = tmp_path / "hooks" / "pre_tool_use"
        hooks_dir.mkdir(parents=True)
        hook = hooks_dir / "guard.py"
        hook.write_text("#!/usr/bin/env python3\nimport sys\n")

        content = classify(tmp_path)
        hook_items = [i for i in content.items if i.component_type == ComponentType.HOOK]
        assert len(hook_items) >= 1

    def test_md_with_frontmatter_is_hook(self, tmp_path):
        """Markdown file in hooks/ with hawk-hook frontmatter is classified as hook."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook = hooks_dir / "check.md"
        hook.write_text("---\nhawk-hook:\n  events: [stop]\n---\nContent\n")

        content = classify(tmp_path)
        hook_items = [i for i in content.items if i.component_type == ComponentType.HOOK]
        assert len(hook_items) == 1
        assert hook_items[0].name == "check.md"

    def test_md_without_frontmatter_not_hook(self, tmp_path):
        """Plain markdown in hooks/ without hawk-hook frontmatter is NOT classified."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        readme = hooks_dir / "README.md"
        readme.write_text("# My Hooks\nDocumentation here.\n")

        content = classify(tmp_path)
        hook_items = [i for i in content.items if i.component_type == ComponentType.HOOK]
        assert not any(i.name == "README.md" for i in hook_items)


    def test_legacy_event_dir_skips_non_hooks(self, tmp_path):
        """Non-hook files (README.md) in legacy event dirs are skipped."""
        hooks_dir = tmp_path / "hooks" / "pre_tool_use"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "guard.py").write_text("#!/usr/bin/env python3\nimport sys\n")
        (hooks_dir / "README.md").write_text("# Documentation\nNot a hook.\n")
        (hooks_dir / "config.yaml").write_text("key: value\n")

        content = classify(tmp_path)
        hook_items = [i for i in content.items if i.component_type == ComponentType.HOOK]
        names = [i.name for i in hook_items]
        assert "guard.py" in names
        assert "README.md" not in names
        assert "config.yaml" not in names


class TestBatchDuplicateDetection:
    """Test that check_clashes detects intra-batch duplicate filenames."""

    def test_detects_duplicate_in_batch(self, registry, tmp_path):
        """Two items with same type+name in one batch are flagged as clashes."""
        source1 = tmp_path / "a" / "guard.py"
        source1.parent.mkdir()
        source1.write_text("v1")
        source2 = tmp_path / "b" / "guard.py"
        source2.parent.mkdir()
        source2.write_text("v2")

        items = [
            ClassifiedItem(ComponentType.HOOK, "guard.py", source1),
            ClassifiedItem(ComponentType.HOOK, "guard.py", source2),
        ]
        clashes = check_clashes(items, registry)
        assert len(clashes) == 1
        assert clashes[0].source_path == source2

    def test_no_false_positive_different_types(self, registry, tmp_path):
        """Same name but different types is not a clash."""
        source = tmp_path / "item.md"
        source.write_text("content")

        items = [
            ClassifiedItem(ComponentType.SKILL, "item.md", source),
            ClassifiedItem(ComponentType.COMMAND, "item.md", source),
        ]
        clashes = check_clashes(items, registry)
        assert len(clashes) == 0


class TestScanDirectoryHooks:
    """Test scan_directory() hook detection with hawk-hook headers."""

    def test_detects_hawk_hook_header(self, tmp_path):
        """scan_directory finds scripts with hawk-hook headers in hooks/."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook = hooks_dir / "notify.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=stop\nimport sys\n")

        content = scan_directory(tmp_path)
        hook_items = [i for i in content.items if i.component_type == ComponentType.HOOK]
        assert any(i.name == "notify.py" for i in hook_items)


class TestPackageManifest:
    """Test hawk-package.yaml manifest detection."""

    def test_classify_detects_manifest(self, tmp_path):
        """classify() populates package_meta when hawk-package.yaml exists."""
        (tmp_path / "hawk-package.yaml").write_text(
            "name: my-pkg\ndescription: Test package\nversion: '1.0.0'\n"
        )
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "hello.md").write_text("# Hello")

        content = classify(tmp_path)
        assert content.package_meta is not None
        assert content.package_meta.name == "my-pkg"
        assert content.package_meta.description == "Test package"
        assert content.package_meta.version == "1.0.0"
        assert len(content.items) == 1

    def test_classify_no_manifest(self, tmp_path):
        """classify() returns None package_meta when no manifest."""
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "hello.md").write_text("# Hello")

        content = classify(tmp_path)
        assert content.package_meta is None

    def test_classify_manifest_missing_name(self, tmp_path):
        """Manifest without 'name' field returns None."""
        (tmp_path / "hawk-package.yaml").write_text("description: no name\n")

        content = classify(tmp_path)
        assert content.package_meta is None

    def test_classify_manifest_invalid_yaml(self, tmp_path):
        """Invalid YAML manifest returns None."""
        (tmp_path / "hawk-package.yaml").write_text(": : invalid\n  bad yaml\n")

        content = classify(tmp_path)
        assert content.package_meta is None

    def test_classify_manifest_name_only(self, tmp_path):
        """Manifest with only 'name' field works."""
        (tmp_path / "hawk-package.yaml").write_text("name: minimal\n")
        (tmp_path / "skills").mkdir()
        (tmp_path / "skills" / "test.md").write_text("# Test")

        content = classify(tmp_path)
        assert content.package_meta is not None
        assert content.package_meta.name == "minimal"
        assert content.package_meta.description == ""
        assert content.package_meta.version == ""

    def test_scan_directory_detects_manifest(self, tmp_path):
        """scan_directory() populates package_meta when hawk-package.yaml exists."""
        (tmp_path / "hawk-package.yaml").write_text(
            "name: scanned-pkg\ndescription: A scanned package\n"
        )
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "deploy.md").write_text("# Deploy")

        content = scan_directory(tmp_path)
        assert content.package_meta is not None
        assert content.package_meta.name == "scanned-pkg"
        assert len(content.items) == 1

    def test_scan_directory_no_manifest(self, tmp_path):
        """scan_directory() returns None package_meta when no manifest."""
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "deploy.md").write_text("# Deploy")

        content = scan_directory(tmp_path)
        assert content.package_meta is None

    def test_classify_manifest_whitespace_name(self, tmp_path):
        """Manifest with whitespace-only name returns None."""
        (tmp_path / "hawk-package.yaml").write_text("name: '  '\n")

        content = classify(tmp_path)
        assert content.package_meta is None

    def test_classify_manifest_null_values(self, tmp_path):
        """Manifest with null description/version defaults to empty string."""
        (tmp_path / "hawk-package.yaml").write_text(
            "name: test\ndescription:\nversion:\n"
        )

        content = classify(tmp_path)
        assert content.package_meta is not None
        assert content.package_meta.description == ""
        assert content.package_meta.version == ""

    def test_classify_manifest_name_stripped(self, tmp_path):
        """Manifest name gets whitespace stripped."""
        (tmp_path / "hawk-package.yaml").write_text("name: '  my-pkg  '\n")

        content = classify(tmp_path)
        assert content.package_meta is not None
        assert content.package_meta.name == "my-pkg"
