"""Tests for v2 YAML config management."""

import pytest
import yaml

from hawk_hooks import v2_config
from hawk_hooks.types import Tool


@pytest.fixture
def v2_env(tmp_path, monkeypatch):
    """Set up a temp v2 config environment."""
    config_dir = tmp_path / "hawk-hooks"
    config_dir.mkdir()
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
    return config_dir


class TestGlobalConfig:
    def test_load_defaults_when_missing(self, v2_env):
        cfg = v2_config.load_global_config()
        assert cfg["debug"] is False
        assert "claude" in cfg["tools"]
        assert cfg["global"]["skills"] == []

    def test_save_and_load(self, v2_env):
        cfg = v2_config.load_global_config()
        cfg["debug"] = True
        cfg["global"]["skills"] = ["tdd"]
        v2_config.save_global_config(cfg)

        loaded = v2_config.load_global_config()
        assert loaded["debug"] is True
        assert loaded["global"]["skills"] == ["tdd"]

    def test_deep_merge_with_defaults(self, v2_env):
        # Write partial config
        config_path = v2_config.get_global_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            yaml.dump({"debug": True}, f)

        cfg = v2_config.load_global_config()
        assert cfg["debug"] is True
        # Defaults should fill in
        assert "tools" in cfg
        assert "global" in cfg

    def test_handles_corrupt_yaml(self, v2_env):
        config_path = v2_config.get_global_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(":::invalid yaml:::")

        cfg = v2_config.load_global_config()
        # Should return defaults
        assert cfg["debug"] is False


class TestProfiles:
    def test_save_and_load(self, v2_env):
        data = {
            "name": "web-fullstack",
            "skills": ["tdd", "react-patterns"],
            "hooks": ["block-secrets"],
        }
        v2_config.save_profile("web-fullstack", data)
        loaded = v2_config.load_profile("web-fullstack")
        assert loaded is not None
        assert loaded["skills"] == ["tdd", "react-patterns"]

    def test_load_missing_returns_none(self, v2_env):
        assert v2_config.load_profile("nonexistent") is None

    def test_list_profiles(self, v2_env):
        v2_config.save_profile("web", {"name": "web"})
        v2_config.save_profile("api", {"name": "api"})
        profiles = v2_config.list_profiles()
        assert profiles == ["api", "web"]

    def test_list_profiles_empty(self, v2_env):
        assert v2_config.list_profiles() == []


class TestDirConfig:
    def test_save_and_load(self, v2_env, tmp_path):
        project = tmp_path / "my-project"
        project.mkdir()

        data = {
            "profile": "web-fullstack",
            "skills": {"enabled": ["tdd"], "disabled": []},
        }
        v2_config.save_dir_config(project, data)
        loaded = v2_config.load_dir_config(project)
        assert loaded is not None
        assert loaded["profile"] == "web-fullstack"

    def test_load_missing_returns_none(self, tmp_path):
        assert v2_config.load_dir_config(tmp_path / "nonexistent") is None


class TestDirectoryIndex:
    def test_register_and_list(self, v2_env, tmp_path):
        project = tmp_path / "my-project"
        project.mkdir()

        v2_config.register_directory(project, profile="web")
        dirs = v2_config.get_registered_directories()
        assert str(project.resolve()) in dirs
        assert dirs[str(project.resolve())]["profile"] == "web"

    def test_unregister(self, v2_env, tmp_path):
        project = tmp_path / "my-project"
        project.mkdir()

        v2_config.register_directory(project)
        v2_config.unregister_directory(project)
        dirs = v2_config.get_registered_directories()
        assert str(project.resolve()) not in dirs


class TestEnabledTools:
    def test_all_enabled_by_default(self, v2_env):
        tools = v2_config.get_enabled_tools()
        assert Tool.CLAUDE in tools
        assert Tool.GEMINI in tools
        assert len(tools) == 6

    def test_disable_tool(self, v2_env):
        cfg = v2_config.load_global_config()
        cfg["tools"]["gemini"]["enabled"] = False
        v2_config.save_global_config(cfg)

        tools = v2_config.get_enabled_tools()
        assert Tool.GEMINI not in tools
        assert Tool.CLAUDE in tools


class TestToolGlobalDir:
    def test_default_dirs(self, v2_env):
        path = v2_config.get_tool_global_dir(Tool.CLAUDE)
        assert str(path).endswith(".claude")

    def test_custom_dir(self, v2_env):
        cfg = v2_config.load_global_config()
        cfg["tools"]["claude"]["global_dir"] = "/custom/path"
        v2_config.save_global_config(cfg)

        path = v2_config.get_tool_global_dir(Tool.CLAUDE)
        assert str(path) == "/custom/path"


class TestConfigChain:
    def test_empty_chain_when_no_dirs_registered(self, v2_env, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        chain = v2_config.get_config_chain(project)
        assert chain == []

    def test_single_dir_in_chain(self, v2_env, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        v2_config.save_dir_config(project, {"skills": {"enabled": ["tdd"]}})
        v2_config.register_directory(project)

        chain = v2_config.get_config_chain(project)
        assert len(chain) == 1
        assert chain[0][0] == project.resolve()
        assert chain[0][1]["skills"]["enabled"] == ["tdd"]

    def test_nested_dirs_outermost_first(self, v2_env, tmp_path):
        root = tmp_path / "monorepo"
        root.mkdir()
        child = root / "packages" / "frontend"
        child.mkdir(parents=True)

        v2_config.save_dir_config(root, {"profile": "fullstack"})
        v2_config.register_directory(root)
        v2_config.save_dir_config(child, {"skills": {"enabled": ["react"]}})
        v2_config.register_directory(child)

        chain = v2_config.get_config_chain(child)
        assert len(chain) == 2
        assert chain[0][0] == root.resolve()  # outermost first
        assert chain[1][0] == child.resolve()

    def test_unrelated_dirs_excluded(self, v2_env, tmp_path):
        project_a = tmp_path / "project-a"
        project_a.mkdir()
        project_b = tmp_path / "project-b"
        project_b.mkdir()

        v2_config.save_dir_config(project_a, {"skills": {"enabled": ["a"]}})
        v2_config.register_directory(project_a)
        v2_config.save_dir_config(project_b, {"skills": {"enabled": ["b"]}})
        v2_config.register_directory(project_b)

        chain = v2_config.get_config_chain(project_a)
        assert len(chain) == 1
        assert chain[0][0] == project_a.resolve()

    def test_subdir_without_own_config(self, v2_env, tmp_path):
        """Subdir that isn't registered but is inside a registered parent."""
        root = tmp_path / "monorepo"
        root.mkdir()
        child = root / "packages" / "backend"
        child.mkdir(parents=True)

        v2_config.save_dir_config(root, {"profile": "fullstack"})
        v2_config.register_directory(root)

        # child has no config, but is inside root
        chain = v2_config.get_config_chain(child)
        assert len(chain) == 1
        assert chain[0][0] == root.resolve()


class TestAutoRegister:
    def test_auto_registers_when_config_exists(self, v2_env, tmp_path):
        project = tmp_path / "cloned"
        project.mkdir()
        v2_config.save_dir_config(project, {"profile": "web"})

        dirs = v2_config.get_registered_directories()
        assert str(project.resolve()) not in dirs

        v2_config.auto_register_if_needed(project)
        dirs = v2_config.get_registered_directories()
        assert str(project.resolve()) in dirs

    def test_no_op_when_already_registered(self, v2_env, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        v2_config.save_dir_config(project, {})
        v2_config.register_directory(project)

        v2_config.auto_register_if_needed(project)
        dirs = v2_config.get_registered_directories()
        assert str(project.resolve()) in dirs

    def test_no_op_when_no_config(self, v2_env, tmp_path):
        project = tmp_path / "bare"
        project.mkdir()

        v2_config.auto_register_if_needed(project)
        dirs = v2_config.get_registered_directories()
        assert str(project.resolve()) not in dirs


class TestPruneStale:
    def test_removes_stale_entries(self, v2_env, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        v2_config.save_dir_config(project, {})
        v2_config.register_directory(project)

        # Delete the config
        (project / ".hawk" / "config.yaml").unlink()

        pruned = v2_config.prune_stale_directories()
        assert str(project.resolve()) in pruned
        dirs = v2_config.get_registered_directories()
        assert str(project.resolve()) not in dirs

    def test_keeps_valid_entries(self, v2_env, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        v2_config.save_dir_config(project, {})
        v2_config.register_directory(project)

        pruned = v2_config.prune_stale_directories()
        assert pruned == []
        dirs = v2_config.get_registered_directories()
        assert str(project.resolve()) in dirs

    def test_prune_returns_empty_when_no_dirs(self, v2_env):
        pruned = v2_config.prune_stale_directories()
        assert pruned == []


class TestEnsureDirs:
    def test_creates_registry_dirs(self, v2_env):
        v2_config.ensure_v2_dirs()
        registry = v2_config.get_registry_path()
        assert (registry / "skills").exists()
        assert (registry / "hooks").exists()
        assert (registry / "commands").exists()
        assert (registry / "agents").exists()
        assert (registry / "mcp").exists()
        assert (registry / "prompts").exists()
