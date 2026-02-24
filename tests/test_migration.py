"""Tests for v1 -> v2 migration."""

import json

import pytest

from hawk_hooks import migration, v2_config


@pytest.fixture
def v2_env(tmp_path, monkeypatch):
    """Set up a temp config environment."""
    config_dir = tmp_path / "hawk-hooks"
    config_dir.mkdir()
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
    return config_dir


class TestMigrateConfig:
    def test_basic_migration(self):
        v1 = {
            "enabled": {
                "pre_tool_use": ["file-guard", "block-secrets"],
                "stop": ["notify"],
            },
            "debug": True,
            "projects": ["/home/user/project1"],
            "destinations": {
                "claude": {"prompts": "~/.claude/commands/"},
            },
            "prompts": {"my-cmd": {"enabled": True, "hook_enabled": False}},
            "agents": {"reviewer": {"enabled": True, "hook_enabled": True}},
            "env": {"MY_VAR": "hello"},
        }

        v2 = migration.migrate_config(v1)

        assert v2["debug"] is True
        assert "file-guard" in v2["global"]["hooks"]
        assert "block-secrets" in v2["global"]["hooks"]
        assert "notify" in v2["global"]["hooks"]
        assert "my-cmd" in v2["global"]["prompts"]
        assert "reviewer" in v2["global"]["agents"]
        assert "/home/user/project1" in v2["directories"]
        assert v2["env"]["MY_VAR"] == "hello"
        assert v2["tools"]["claude"]["destinations"]["prompts"] == "~/.claude/commands/"

    def test_empty_v1(self):
        v2 = migration.migrate_config({})
        assert v2["debug"] is False
        assert v2["global"]["hooks"] == []
        assert v2["global"]["prompts"] == []
        assert v2["directories"] == {}

    def test_disabled_prompts_not_migrated(self):
        v1 = {
            "prompts": {"disabled-cmd": {"enabled": False}},
            "agents": {"disabled-agent": {"enabled": False}},
        }
        v2 = migration.migrate_config(v1)
        assert "disabled-cmd" not in v2["global"]["prompts"]
        assert "disabled-agent" not in v2["global"]["agents"]

    def test_deduplicates_hooks(self):
        v1 = {
            "enabled": {
                "pre_tool_use": ["hook-a"],
                "post_tool_use": ["hook-a"],  # same hook in different event
            }
        }
        v2 = migration.migrate_config(v1)
        assert v2["global"]["hooks"].count("hook-a") == 1

    def test_migrated_tools_include_cursor_and_antigravity(self):
        v2 = migration.migrate_config({})
        assert "cursor" in v2["tools"]
        assert "antigravity" in v2["tools"]

    def test_migrated_output_contains_default_global_config_keys(self):
        v2 = migration.migrate_config({})

        def _assert_default_shape(default_obj, got_obj):
            assert isinstance(got_obj, dict)
            for key, value in default_obj.items():
                assert key in got_obj
                if isinstance(value, dict):
                    _assert_default_shape(value, got_obj[key])

        _assert_default_shape(v2_config.DEFAULT_GLOBAL_CONFIG, v2)


class TestDetectV1:
    def test_detects_existing(self, v2_env):
        config_json = v2_env / "config.json"
        config_json.write_text("{}")
        assert migration.detect_v1_config() == config_json

    def test_returns_none_when_missing(self, v2_env):
        assert migration.detect_v1_config() is None


class TestRunMigration:
    def test_full_migration(self, v2_env):
        # Write v1 config
        v1_data = {
            "enabled": {"pre_tool_use": ["guard"]},
            "debug": False,
            "projects": [],
            "destinations": {},
            "prompts": {},
            "agents": {},
            "env": {},
        }
        v1_path = v2_env / "config.json"
        v1_path.write_text(json.dumps(v1_data))

        success, msg = migration.run_migration()
        assert success is True
        assert "Migrated" in msg

        # v2 config should exist
        v2_path = v2_config.get_global_config_path()
        assert v2_path.exists()

        # Backup should exist
        assert v1_path.with_suffix(".json.v1-backup").exists()

        # Content should be correct
        cfg = v2_config.load_global_config()
        assert "guard" in cfg["global"]["hooks"]

    def test_skip_if_v2_exists(self, v2_env):
        # Write both configs
        (v2_env / "config.json").write_text("{}")
        v2_config.save_global_config({"debug": False})

        success, msg = migration.run_migration()
        assert success is False
        assert "already exists" in msg

    def test_skip_if_no_v1(self, v2_env):
        success, msg = migration.run_migration()
        assert success is False
        assert "No v1" in msg

    def test_handles_malformed_v1_shapes_gracefully(self, v2_env):
        v1_path = v2_env / "config.json"
        v1_path.write_text(json.dumps({
            "enabled": "not-a-dict",
            "projects": "not-a-list",
            "destinations": ["bad"],
            "prompts": ["bad"],
            "agents": "bad",
            "env": ["bad"],
        }))

        success, msg = migration.run_migration()

        assert success is True
        assert "Migrated" in msg
        cfg = v2_config.load_global_config()
        assert cfg["global"]["hooks"] == []
        assert cfg["directories"] == {}
