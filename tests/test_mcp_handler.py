"""Tests for the MCP handler dispatch logic."""

import asyncio
import pytest

from hawk_hooks.mcp_handler import handle_action


def run(coro):
    """Helper to run async handle_action in sync tests."""
    return asyncio.run(coro)


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def hawk_env(tmp_path, monkeypatch):
    """Set up an isolated hawk environment with registry + config."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    registry_dir = config_dir / "registry"
    registry_dir.mkdir()
    for sub in ("skills", "hooks", "prompts", "agents", "mcp", "commands"):
        (registry_dir / sub).mkdir()

    # Write minimal global config
    import yaml
    global_config = {
        "registry_path": str(registry_dir),
        "global": {"skills": [], "hooks": [], "prompts": [], "agents": [], "mcp": []},
        "tools": {},
        "directories": {},
    }
    config_file = config_dir / "config.yaml"
    config_file.write_text(yaml.dump(global_config))

    # Patch config to use our temp dirs
    monkeypatch.setattr("hawk_hooks.config.get_config_dir", lambda: config_dir)
    monkeypatch.setattr("hawk_hooks.config.get_global_config_path", lambda: config_file)
    monkeypatch.setattr("hawk_hooks.config.get_registry_path", lambda cfg=None: registry_dir)

    # Packages file
    packages_file = config_dir / "packages.yaml"
    packages_file.write_text("{}")
    monkeypatch.setattr(
        "hawk_hooks.config.load_packages",
        lambda: yaml.safe_load(packages_file.read_text()) or {},
    )

    # Patch CWD for context hints
    monkeypatch.setattr("hawk_hooks.mcp_handler.os.getcwd", lambda: str(tmp_path))

    return {
        "config_dir": config_dir,
        "registry_dir": registry_dir,
        "config_file": config_file,
        "tmp_path": tmp_path,
    }


# ── describe ─────────────────────────────────────────────────────────────

class TestDescribe:
    def test_describe_all(self):
        result = run(handle_action({"action": "describe"}))
        assert "actions" in result
        assert "add" in result["actions"]
        assert "list" in result["actions"]
        assert "sync" in result["actions"]

    def test_describe_single(self):
        result = run(handle_action({"action": "describe", "action_name": "add"}))
        assert result["action"] == "add"
        assert "params" in result

    def test_describe_unknown(self):
        result = run(handle_action({"action": "describe", "action_name": "nope"}))
        assert "error" in result


# ── list ─────────────────────────────────────────────────────────────────

class TestList:
    def test_list_empty_registry(self, hawk_env):
        result = run(handle_action({"action": "list"}))
        assert "components" in result
        assert "context" in result

    def test_list_with_items(self, hawk_env):
        # Add a skill to registry
        skill_path = hawk_env["registry_dir"] / "skills" / "test-skill.md"
        skill_path.write_text("# Test Skill")

        result = run(handle_action({"action": "list"}))
        assert "skills" in result["components"]
        names = [item["name"] for item in result["components"]["skills"]]
        assert "test-skill.md" in names

    def test_list_with_type_filter(self, hawk_env):
        skill_path = hawk_env["registry_dir"] / "skills" / "test-skill.md"
        skill_path.write_text("# Test Skill")
        hook_path = hawk_env["registry_dir"] / "hooks" / "test-hook.py"
        hook_path.write_text("#!/usr/bin/env python3")

        result = run(handle_action({"action": "list", "type": "skill"}))
        assert "skills" in result["components"]
        assert "hooks" not in result["components"]

    def test_list_invalid_type(self, hawk_env):
        result = run(handle_action({"action": "list", "type": "invalid"}))
        assert "error" in result


# ── add ──────────────────────────────────────────────────────────────────

class TestAdd:
    def test_add_with_content(self, hawk_env):
        result = run(handle_action({
            "action": "add",
            "type": "skill",
            "content": "# My MCP Skill\nDoes stuff",
            "name": "mcp-skill.md",
        }))
        assert result["added"] == "mcp-skill.md"
        assert result["type"] == "skill"
        assert "registry_path" in result
        # Verify file exists
        reg_file = hawk_env["registry_dir"] / "skills" / "mcp-skill.md"
        assert reg_file.exists()
        assert reg_file.read_text() == "# My MCP Skill\nDoes stuff"

    def test_add_with_path(self, hawk_env):
        source = hawk_env["tmp_path"] / "my-agent.md"
        source.write_text("# Agent\nI do things")

        result = run(handle_action({
            "action": "add",
            "type": "agent",
            "path": str(source),
        }))
        assert result["added"] == "my-agent.md"
        assert result["type"] == "agent"

    def test_add_with_enable(self, hawk_env):
        result = run(handle_action({
            "action": "add",
            "type": "skill",
            "content": "# Skill",
            "name": "enabled-skill.md",
            "enable": True,
        }))
        assert result.get("enabled") is True

        # Verify it's in global config
        import yaml
        cfg = yaml.safe_load(hawk_env["config_file"].read_text())
        assert "enabled-skill.md" in cfg.get("global", {}).get("skills", [])

    def test_add_content_without_name_fails(self, hawk_env):
        result = run(handle_action({
            "action": "add",
            "type": "skill",
            "content": "# Skill",
        }))
        assert "error" in result
        assert "name" in result["error"].lower()

    def test_add_both_path_and_content_fails(self, hawk_env):
        result = run(handle_action({
            "action": "add",
            "type": "skill",
            "path": "/some/path",
            "content": "# Skill",
            "name": "x.md",
        }))
        assert "error" in result

    def test_add_missing_type_fails(self, hawk_env):
        result = run(handle_action({
            "action": "add",
            "content": "# Skill",
            "name": "x.md",
        }))
        assert "error" in result

    def test_add_duplicate_without_force_fails(self, hawk_env):
        # First add
        run(handle_action({
            "action": "add",
            "type": "skill",
            "content": "# v1",
            "name": "dup.md",
        }))
        # Second add without force
        result = run(handle_action({
            "action": "add",
            "type": "skill",
            "content": "# v2",
            "name": "dup.md",
        }))
        assert "error" in result
        assert "force" in result["error"].lower()

    def test_add_duplicate_with_force(self, hawk_env):
        run(handle_action({
            "action": "add",
            "type": "skill",
            "content": "# v1",
            "name": "dup.md",
        }))
        result = run(handle_action({
            "action": "add",
            "type": "skill",
            "content": "# v2",
            "name": "dup.md",
            "force": True,
        }))
        assert result["added"] == "dup.md"
        reg_file = hawk_env["registry_dir"] / "skills" / "dup.md"
        assert reg_file.read_text() == "# v2"


# ── remove ───────────────────────────────────────────────────────────────

class TestRemove:
    def test_remove_existing(self, hawk_env):
        # Add first
        skill_path = hawk_env["registry_dir"] / "skills" / "to-remove.md"
        skill_path.write_text("# Remove me")

        result = run(handle_action({
            "action": "remove",
            "type": "skill",
            "name": "to-remove.md",
        }))
        assert result["removed"] == "skill/to-remove.md"
        assert not skill_path.exists()

    def test_remove_nonexistent(self, hawk_env):
        result = run(handle_action({
            "action": "remove",
            "type": "skill",
            "name": "nope.md",
        }))
        assert "error" in result


# ── enable / disable ─────────────────────────────────────────────────────

class TestEnableDisable:
    def test_enable_by_type_name(self, hawk_env):
        # Add a skill to registry
        skill_path = hawk_env["registry_dir"] / "skills" / "my-skill.md"
        skill_path.write_text("# My Skill")

        result = run(handle_action({
            "action": "enable",
            "target": "skills/my-skill.md",
        }))
        assert "skills/my-skill.md" in result["enabled"]

    def test_disable(self, hawk_env):
        skill_path = hawk_env["registry_dir"] / "skills" / "my-skill.md"
        skill_path.write_text("# My Skill")

        # Enable first
        run(handle_action({"action": "enable", "target": "skills/my-skill.md"}))

        # Then disable
        result = run(handle_action({"action": "disable", "target": "skills/my-skill.md"}))
        assert "skills/my-skill.md" in result["disabled"]

    def test_enable_nonexistent_fails(self, hawk_env):
        result = run(handle_action({
            "action": "enable",
            "target": "skills/nope.md",
        }))
        assert "error" in result


# ── unknown action ───────────────────────────────────────────────────────

class TestUnknown:
    def test_unknown_action(self):
        result = run(handle_action({"action": "bad_action"}))
        assert "error" in result
        assert "hint" in result

    def test_missing_action(self):
        result = run(handle_action({}))
        assert "error" in result


# ── list_packages ────────────────────────────────────────────────────────

class TestListPackages:
    def test_list_packages_empty(self, hawk_env):
        result = run(handle_action({"action": "list_packages"}))
        assert result["packages"] == []


# ── status ───────────────────────────────────────────────────────────────

class TestStatus:
    def test_status_global(self, hawk_env, monkeypatch):
        # Patch out adapter detection and sync counting
        monkeypatch.setattr(
            "hawk_hooks.mcp_handler.config.get_registered_directories",
            lambda: {},
        )
        result = run(handle_action({"action": "status"}))
        assert result["scope"] == "global"
        assert "tools" in result
        assert "context" in result


# ── sync ─────────────────────────────────────────────────────────────────

class TestSync:
    def test_sync_dry_run(self, hawk_env):
        result = run(handle_action({"action": "sync", "dry_run": True}))
        assert result["dry_run"] is True
        assert "results" in result

    def test_sync_invalid_tool(self, hawk_env):
        result = run(handle_action({"action": "sync", "tool": "nonexistent"}))
        assert "error" in result


# ── download ─────────────────────────────────────────────────────────────

class TestDownload:
    def test_download_missing_url(self, hawk_env):
        result = run(handle_action({"action": "download"}))
        assert "error" in result
        assert "url" in result["error"].lower()


# ── update ───────────────────────────────────────────────────────────────

class TestUpdate:
    def test_update_nonexistent_package(self, hawk_env):
        result = run(handle_action({"action": "update", "package": "nope"}))
        # When no packages installed at all, update_packages reports no changes
        # rather than raising PackageNotFoundError
        assert result.get("any_changes") is False or "error" in result

    def test_update_check_no_packages(self, hawk_env):
        result = run(handle_action({"action": "update", "check": True}))
        # No packages → no changes
        assert result.get("any_changes") is False


# ── remove_package ───────────────────────────────────────────────────────

class TestRemovePackage:
    def test_remove_package_missing_name(self, hawk_env):
        result = run(handle_action({"action": "remove_package"}))
        assert "error" in result

    def test_remove_package_nonexistent(self, hawk_env):
        result = run(handle_action({"action": "remove_package", "name": "nope"}))
        assert "error" in result
