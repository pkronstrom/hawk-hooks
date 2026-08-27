"""Tests for cleanup of the removed Gemini CLI integration."""

import json

import pytest

from hawk_hooks import config, legacy_gemini
from hawk_hooks.legacy_gemini import cleanup_legacy_gemini


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A fake home with a hawk registry and a populated ~/.gemini."""
    home = tmp_path / "home"
    registry = tmp_path / "registry"
    (registry / "prompts").mkdir(parents=True)
    (registry / "agents").mkdir(parents=True)
    (registry / "prompts" / "review.md").write_text("---\nname: review\n---\n")
    (registry / "agents" / "reviewer.md").write_text("---\nname: reviewer\n---\n")

    monkeypatch.setattr(legacy_gemini.Path, "home", staticmethod(lambda: home), raising=False)
    monkeypatch.setattr(config, "get_registry_path", lambda cfg=None: registry)
    monkeypatch.setattr(config, "get_registered_directories", lambda: {})

    gemini = home / ".gemini"
    (gemini / "runners").mkdir(parents=True)
    (gemini / "commands").mkdir()
    (gemini / "agents").mkdir()

    (gemini / "runners" / "pre_tool_use.sh").write_text("#!/bin/bash\n")
    (gemini / "commands" / "review.toml").write_text('name = "review"\n')
    (gemini / "commands" / "handwritten.toml").write_text('name = "handwritten"\n')
    (gemini / "agents" / "reviewer.md").symlink_to(registry / "agents" / "reviewer.md")
    (gemini / "agents" / "manual.md").write_text("manual agent\n")
    (gemini / ".hawk-mcp.json").write_text(json.dumps(["linear"]))
    (gemini / "settings.json").write_text(
        json.dumps(
            {
                "security": {"auth": {"selectedType": "oauth-personal"}},
                "mcpServers": {
                    "linear": {"url": "https://mcp.linear.app/mcp"},
                    "mine": {"command": "manual"},
                },
                "hooks": {
                    "BeforeTool": [
                        {"hooks": [{"command": "/r/pre.sh", "__hawk_managed": True}]}
                    ],
                    "AfterAgent": [
                        {"hooks": [{"command": "/user/own.sh"}]},
                        {"hooks": [{"command": "/r/stop.sh", "__hawk_managed": True}]},
                    ],
                },
            }
        )
    )
    return gemini


def _settings(env):
    return json.loads((env / "settings.json").read_text())


class TestCleanup:
    def test_removes_hawk_hooks_only(self, env):
        cleanup_legacy_gemini()
        hooks = _settings(env)["hooks"]

        assert "BeforeTool" not in hooks
        assert len(hooks["AfterAgent"]) == 1
        assert hooks["AfterAgent"][0]["hooks"][0]["command"] == "/user/own.sh"

    def test_removes_only_tracked_mcp_servers(self, env):
        cleanup_legacy_gemini()
        servers = _settings(env)["mcpServers"]

        assert "linear" not in servers
        assert "mine" in servers

    def test_preserves_unrelated_settings(self, env):
        cleanup_legacy_gemini()
        assert _settings(env)["security"]["auth"]["selectedType"] == "oauth-personal"

    def test_removes_sidecar_and_runners(self, env):
        cleanup_legacy_gemini()
        assert not (env / ".hawk-mcp.json").exists()
        assert not (env / "runners").exists()

    def test_removes_only_converted_commands(self, env):
        cleanup_legacy_gemini()
        assert not (env / "commands" / "review.toml").exists()
        assert (env / "commands" / "handwritten.toml").exists()

    def test_removes_only_registry_agent_symlinks(self, env):
        cleanup_legacy_gemini()
        assert not (env / "agents" / "reviewer.md").exists()
        assert (env / "agents" / "manual.md").exists()

    def test_dry_run_changes_nothing(self, env):
        before = (env / "settings.json").read_text()

        actions = cleanup_legacy_gemini(dry_run=True)

        assert actions
        assert (env / "settings.json").read_text() == before
        assert (env / "runners").exists()
        assert (env / ".hawk-mcp.json").exists()

    def test_is_idempotent(self, env):
        cleanup_legacy_gemini()
        assert cleanup_legacy_gemini() == []

    def test_settings_file_removed_when_fully_emptied(self, env):
        hawk_only = {
            "hooks": {"BeforeTool": [{"hooks": [{"command": "/r.sh", "__hawk_managed": True}]}]}
        }
        (env / "settings.json").write_text(json.dumps(hawk_only))
        cleanup_legacy_gemini()
        assert not (env / "settings.json").exists()

    def test_skips_missing_scopes(self, env, tmp_path):
        # A registered directory without a .gemini dir must not raise.
        assert cleanup_legacy_gemini(project_dir=tmp_path / "nope") is not None


class TestScopes:
    def test_project_scope_included(self, env, tmp_path, monkeypatch):
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(config, "get_registered_directories", lambda: {str(project): {}})

        scopes = legacy_gemini.legacy_scopes()

        assert project / ".gemini" in scopes

    def test_global_scope_is_first(self, env):
        assert legacy_gemini.legacy_scopes()[0] == env

    def test_project_dir_not_duplicated(self, env, tmp_path, monkeypatch):
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(config, "get_registered_directories", lambda: {str(project): {}})

        scopes = legacy_gemini.legacy_scopes(project_dir=project)

        assert scopes.count(project / ".gemini") == 1
