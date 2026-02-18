"""Integration tests for the v2 system."""

import pytest

from hawk_hooks import v2_config
from hawk_hooks.adapters import get_adapter
from hawk_hooks.registry import Registry
from hawk_hooks.resolver import resolve
from hawk_hooks.types import ComponentType, ResolvedSet, Tool
from hawk_hooks.v2_sync import sync_directory, sync_global


@pytest.fixture
def full_env(tmp_path, monkeypatch):
    """Set up a complete v2 environment for integration testing."""
    config_dir = tmp_path / "hawk-hooks"
    config_dir.mkdir()
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

    # Set up registry
    registry_path = config_dir / "registry"
    registry = Registry(registry_path)
    registry.ensure_dirs()

    # Add test skill
    skill_source = tmp_path / "sources" / "tdd"
    skill_source.mkdir(parents=True)
    (skill_source / "SKILL.md").write_text("# TDD Skill\nWrite tests first.")
    registry.add(ComponentType.SKILL, "tdd", skill_source)

    # Add test command
    cmd_source = tmp_path / "sources" / "deploy.md"
    cmd_source.parent.mkdir(parents=True, exist_ok=True)
    cmd_source.write_text("---\nname: deploy\ndescription: Deploy\n---\nDeploy the app.")
    registry.add(ComponentType.COMMAND, "deploy.md", cmd_source)

    # Add test agent
    agent_source = tmp_path / "sources" / "reviewer.md"
    agent_source.write_text("# Code Reviewer Agent")
    registry.add(ComponentType.AGENT, "reviewer.md", agent_source)

    # Configure global
    cfg = v2_config.load_global_config()
    cfg["registry_path"] = str(registry_path)
    cfg["global"]["skills"] = ["tdd"]
    cfg["global"]["commands"] = ["deploy.md"]
    cfg["global"]["agents"] = ["reviewer.md"]
    v2_config.save_global_config(cfg)

    # Create a fake claude dir
    claude_global = tmp_path / "fake-claude-global"
    claude_global.mkdir()

    from hawk_hooks.adapters.claude import ClaudeAdapter

    monkeypatch.setattr(ClaudeAdapter, "get_global_dir", lambda self: claude_global)

    return {
        "config_dir": config_dir,
        "registry": registry,
        "registry_path": registry_path,
        "claude_global": claude_global,
    }


class TestRoundTrip:
    """Test full init -> add -> sync -> verify -> remove -> sync -> verify cycle."""

    def test_global_roundtrip(self, full_env):
        claude_dir = full_env["claude_global"]

        # Sync global
        results = sync_global(tools=[Tool.CLAUDE])
        assert len(results) == 1
        r = results[0]
        assert "tdd" in r.linked
        assert "deploy.md" in r.linked
        assert "reviewer.md" in r.linked

        # Verify symlinks
        assert (claude_dir / "skills" / "tdd").is_symlink()
        assert (claude_dir / "skills" / "tdd" / "SKILL.md").read_text() == "# TDD Skill\nWrite tests first."
        assert (claude_dir / "commands" / "deploy.md").is_symlink()
        assert (claude_dir / "agents" / "reviewer.md").is_symlink()

        # Remove skill from global config
        cfg = v2_config.load_global_config()
        cfg["global"]["skills"] = []
        v2_config.save_global_config(cfg)

        # Re-sync
        results = sync_global(tools=[Tool.CLAUDE])
        r = results[0]
        assert "tdd" in r.unlinked

        # Verify removed
        assert not (claude_dir / "skills" / "tdd").exists()
        # Other components still there
        assert (claude_dir / "commands" / "deploy.md").is_symlink()

    def test_directory_with_profile(self, full_env, tmp_path):
        # Create a profile
        v2_config.save_profile("web", {
            "name": "web",
            "skills": ["tdd"],
            "commands": ["deploy.md"],
        })

        # Init a project directory
        project = tmp_path / "my-web-app"
        project.mkdir()

        v2_config.save_dir_config(project, {"profile": "web"})
        v2_config.register_directory(project, profile="web")

        # Sync
        results = sync_directory(project, tools=[Tool.CLAUDE])
        r = results[0]
        assert "tdd" in r.linked

        # Verify
        claude_project = project / ".claude"
        assert (claude_project / "skills" / "tdd").is_symlink()

    def test_directory_disable_overrides(self, full_env, tmp_path):
        project = tmp_path / "project"
        project.mkdir()

        # Dir config disables tdd
        v2_config.save_dir_config(project, {
            "skills": {"enabled": [], "disabled": ["tdd"]},
        })

        results = sync_directory(project, tools=[Tool.CLAUDE])
        r = results[0]
        # tdd should not be linked since it's disabled
        assert "tdd" not in r.linked


class TestResolverIntegration:
    def test_full_resolution_chain(self, full_env):
        cfg = v2_config.load_global_config()

        # Global only
        resolved = resolve(cfg)
        assert "tdd" in resolved.skills
        assert "deploy.md" in resolved.commands

        # With profile
        profile = {"skills": ["react-patterns"]}
        resolved = resolve(cfg, profile=profile)
        assert "tdd" in resolved.skills
        assert "react-patterns" in resolved.skills

        # With dir config that disables
        dir_cfg = {
            "skills": {"enabled": ["local"], "disabled": ["tdd"]},
        }
        resolved = resolve(cfg, profile=profile, dir_config=dir_cfg)
        assert "tdd" not in resolved.skills
        assert "local" in resolved.skills
        assert "react-patterns" in resolved.skills

        # Per-tool override
        dir_cfg["tools"] = {
            "claude": {"skills": {"extra": ["claude-only"]}},
        }
        resolved = resolve(cfg, profile=profile, dir_config=dir_cfg, tool=Tool.CLAUDE)
        assert "claude-only" in resolved.skills


class TestPackageRemoval:
    """Test removing a package cleans up registry and config."""

    def test_remove_package_cleans_everything(self, full_env, tmp_path):
        registry = full_env["registry"]

        # Record a package with items that are in the registry
        v2_config.save_packages({
            "test-pkg": {
                "url": "https://github.com/test/pkg",
                "installed": "2026-02-18",
                "commit": "abc123",
                "items": [
                    {"type": "skill", "name": "tdd", "hash": "deadbeef"},
                    {"type": "command", "name": "deploy.md", "hash": "cafebabe"},
                ],
            }
        })

        # Verify items exist
        assert registry.has(ComponentType.SKILL, "tdd")
        assert registry.has(ComponentType.COMMAND, "deploy.md")

        # Verify global config has them enabled
        cfg = v2_config.load_global_config()
        assert "tdd" in cfg["global"]["skills"]
        assert "deploy.md" in cfg["global"]["commands"]

        # Create a directory config that also has them
        project = tmp_path / "project"
        project.mkdir()
        v2_config.save_dir_config(project, {
            "skills": {"enabled": ["tdd"]},
        })
        v2_config.register_directory(project)

        # Simulate remove-package logic (from cmd_remove_package)
        packages = v2_config.load_packages()
        pkg_data = packages["test-pkg"]
        items = pkg_data.get("items", [])

        # Remove from registry
        for item in items:
            ct = ComponentType(item["type"])
            registry.remove(ct, item["name"])

        # Remove from global config
        cfg = v2_config.load_global_config()
        global_section = cfg.get("global", {})
        for item in items:
            field = ComponentType(item["type"]).registry_dir
            enabled = global_section.get(field, [])
            global_section[field] = [n for n in enabled if n != item["name"]]
        cfg["global"] = global_section
        v2_config.save_global_config(cfg)

        # Remove from dir configs
        dir_cfg = v2_config.load_dir_config(project)
        skills_section = dir_cfg.get("skills", {})
        if isinstance(skills_section, dict):
            skills_section["enabled"] = [
                n for n in skills_section.get("enabled", []) if n != "tdd"
            ]
            dir_cfg["skills"] = skills_section
        v2_config.save_dir_config(project, dir_cfg)

        # Remove package entry
        v2_config.remove_package("test-pkg")

        # Verify cleanup
        assert not registry.has(ComponentType.SKILL, "tdd")
        assert not registry.has(ComponentType.COMMAND, "deploy.md")

        cfg = v2_config.load_global_config()
        assert "tdd" not in cfg["global"]["skills"]
        assert "deploy.md" not in cfg["global"]["commands"]

        dir_cfg = v2_config.load_dir_config(project)
        assert "tdd" not in dir_cfg["skills"]["enabled"]

        assert v2_config.load_packages() == {}


class TestRegistryIntegration:
    def test_add_and_sync(self, full_env, tmp_path):
        registry = full_env["registry"]

        # Add a new skill
        new_skill = tmp_path / "new-skill"
        new_skill.mkdir()
        (new_skill / "SKILL.md").write_text("# New")
        registry.add(ComponentType.SKILL, "new-skill", new_skill)

        # Update config
        cfg = v2_config.load_global_config()
        cfg["global"]["skills"].append("new-skill")
        v2_config.save_global_config(cfg)

        # Sync
        results = sync_global(tools=[Tool.CLAUDE])
        r = results[0]
        assert "new-skill" in r.linked
