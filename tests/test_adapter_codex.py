"""Tests for the Codex adapter."""

import logging
import tomllib

import pytest

from hawk_hooks.adapters.codex import CodexAdapter
from hawk_hooks.types import ResolvedSet, Tool


@pytest.fixture
def adapter():
    return CodexAdapter()


class TestCodexAdapter:
    def test_tool(self, adapter):
        assert adapter.tool == Tool.CODEX
        assert adapter.hook_support == "bridge"

    def test_global_dir(self, adapter):
        assert str(adapter.get_global_dir()).endswith(".codex")

    def test_skills_dir_is_agents_skills(self, adapter, tmp_path):
        codex_dir = tmp_path / ".codex"
        assert adapter.get_skills_dir(codex_dir) == tmp_path / ".agents" / "skills"

    def test_agents_dir_is_codex_agents(self, adapter, tmp_path):
        codex_dir = tmp_path / ".codex"
        assert adapter.get_agents_dir(codex_dir) == codex_dir / "agents"

    def test_commands_dir_is_prompts(self, adapter, tmp_path):
        """Legacy commands map to Codex prompts directory."""
        codex_dir = tmp_path / ".codex"
        assert adapter.get_commands_dir(codex_dir) == codex_dir / "prompts"


class TestCodexMCP:
    def test_write_mcp(self, adapter, tmp_path):
        target = tmp_path / "codex"
        target.mkdir()

        servers = {"github": {"command": "gh-mcp"}}
        adapter.write_mcp_config(servers, target)

        config_path = target / "config.toml"
        assert config_path.exists()
        data = tomllib.loads(config_path.read_text())
        assert "github" in data["mcp_servers"]
        assert data["mcp_servers"]["github"]["command"] == "gh-mcp"
        assert "hawk-hooks managed: codex-mcp-github" in config_path.read_text()

    def test_preserves_manual(self, adapter, tmp_path):
        target = tmp_path / "codex"
        target.mkdir()

        config_path = target / "config.toml"
        config_path.write_text('[mcp_servers.manual]\ncommand = "m"\n')

        adapter.write_mcp_config({"hawk": {"command": "h"}}, target)

        data = tomllib.loads(config_path.read_text())
        assert "manual" in data["mcp_servers"]
        assert "hawk" in data["mcp_servers"]

    def test_conflicts_with_manual_same_name(self, adapter, tmp_path):
        target = tmp_path / "codex"
        target.mkdir()
        config_path = target / "config.toml"
        config_path.write_text('[mcp_servers.github]\ncommand = "manual-gh"\n')

        with pytest.raises(ValueError, match="manual \\[mcp_servers.github\\]"):
            adapter.write_mcp_config({"github": {"command": "gh-mcp"}}, target)


class TestCodexHooks:
    def test_register_hooks_writes_notify_block(self, adapter, tmp_path):
        registry = tmp_path / "registry"
        hooks = registry / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "done.sh").write_text(
            "#!/usr/bin/env bash\n"
            "# hawk-hook: events=stop\n"
            "exit 0\n"
        )

        target = tmp_path / "codex"
        target.mkdir()

        registered = adapter.register_hooks(["done.sh"], target, registry_path=registry)
        assert registered == ["done.sh"]

        config_text = (target / "config.toml").read_text()
        assert "# >>> hawk-hooks notify >>>" in config_text
        assert "runners/stop.sh" in config_text
        assert (target / "runners" / "stop.sh").exists()

    def test_register_hooks_escapes_notify_paths_for_toml(self, adapter, tmp_path):
        registry = tmp_path / "registry"
        hooks = registry / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "done.sh").write_text(
            "#!/usr/bin/env bash\n"
            "# hawk-hook: events=stop\n"
            "exit 0\n"
        )

        target = tmp_path / 'co"dex\\test'
        target.mkdir(parents=True)

        registered = adapter.register_hooks(["done.sh"], target, registry_path=registry)
        assert registered == ["done.sh"]

        config_path = target / "config.toml"
        data = tomllib.loads(config_path.read_text())
        assert len(data["notify"]) == 1
        assert 'co"dex\\test' in data["notify"][0]

    def test_sync_reports_unsupported_events(self, adapter, tmp_path):
        registry = tmp_path / "registry"
        hooks = registry / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "guard.py").write_text(
            "#!/usr/bin/env python3\n"
            "# hawk-hook: events=pre_tool_use\n"
            "import sys\n"
        )

        target = tmp_path / "codex"
        target.mkdir()

        result = adapter.sync(ResolvedSet(hooks=["guard.py"]), target, registry)
        assert any("pre_tool_use is unsupported by codex" in e for e in result.skipped)

    def test_sync_respects_manual_notify_key(self, adapter, tmp_path):
        registry = tmp_path / "registry"
        hooks = registry / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "done.sh").write_text(
            "#!/usr/bin/env bash\n"
            "# hawk-hook: events=stop\n"
            "exit 0\n"
        )

        target = tmp_path / "codex"
        target.mkdir()
        (target / "config.toml").write_text('notify = ["/usr/local/bin/manual-notify"]\n')

        result = adapter.sync(ResolvedSet(hooks=["done.sh"]), target, registry)
        assert any("manual notify key" in e for e in result.errors)

        config_text = (target / "config.toml").read_text()
        assert 'notify = ["/usr/local/bin/manual-notify"]' in config_text
        assert "# >>> hawk-hooks notify >>>" not in config_text


class TestCodexAgents:
    def test_sync_agents_requires_multi_agent_opt_in(self, adapter, tmp_path, monkeypatch):
        registry = tmp_path / "registry"
        agents = registry / "agents"
        agents.mkdir(parents=True)
        (agents / "architecture-reviewer.md").write_text(
            "---\n"
            "name: architecture-reviewer\n"
            "description: Architecture review specialist\n"
            "tools: [codex]\n"
            "---\n\n"
            "Review architecture and boundaries.\n"
        )
        target = tmp_path / ".codex"
        target.mkdir()

        monkeypatch.setattr(
            "hawk_hooks.config.load_global_config",
            lambda: {"tools": {"codex": {"allow_multi_agent": False, "agent_trigger_mode": "skills"}}},
        )

        result = adapter.sync(ResolvedSet(agents=["architecture-reviewer.md"]), target, registry)

        assert any("multi-agent is required" in line for line in result.skipped)
        assert not (target / "agents" / "architecture_reviewer.toml").exists()
        assert not (tmp_path / ".agents" / "skills" / "agent-architecture-reviewer").exists()

    def test_sync_agents_generates_role_and_launcher(self, adapter, tmp_path, monkeypatch):
        registry = tmp_path / "registry"
        agents = registry / "agents"
        agents.mkdir(parents=True)
        (agents / "architecture-reviewer.md").write_text(
            "---\n"
            "name: architecture-reviewer\n"
            "description: Architecture review specialist\n"
            "tools: [codex]\n"
            "---\n\n"
            "Review architecture and identify coupling risks.\n"
        )
        target = tmp_path / ".codex"
        target.mkdir()

        monkeypatch.setattr(
            "hawk_hooks.config.load_global_config",
            lambda: {"tools": {"codex": {"allow_multi_agent": True, "agent_trigger_mode": "skills"}}},
        )

        result = adapter.sync(ResolvedSet(agents=["architecture-reviewer.md"]), target, registry)
        assert any(item == "agent:architecture-reviewer.md" for item in result.linked)
        assert any(item == "skill:agent-architecture-reviewer" for item in result.linked)

        config_text = (target / "config.toml").read_text()
        assert "hawk-hooks managed: codex-multi-agent" in config_text
        assert "[agents.architecture_reviewer]" in config_text
        assert 'config_file = "agents/architecture_reviewer.toml"' in config_text

        role_file = target / "agents" / "architecture_reviewer.toml"
        assert role_file.exists()
        assert "hawk-hooks managed: codex-agent-role" in role_file.read_text()

        launcher_skill = (
            tmp_path
            / ".agents"
            / "skills"
            / "agent-architecture-reviewer"
            / "SKILL.md"
        )
        assert launcher_skill.exists()
        assert "hawk-hooks managed: codex-agent-launcher" in launcher_skill.read_text()

    def test_sync_agents_conflicts_with_manual_features_table(self, adapter, tmp_path, monkeypatch):
        registry = tmp_path / "registry"
        agents = registry / "agents"
        agents.mkdir(parents=True)
        (agents / "architecture-reviewer.md").write_text("# architecture review\n")
        target = tmp_path / ".codex"
        target.mkdir()
        (target / "config.toml").write_text("[features]\nfoo = true\n")

        monkeypatch.setattr(
            "hawk_hooks.config.load_global_config",
            lambda: {"tools": {"codex": {"allow_multi_agent": True, "agent_trigger_mode": "skills"}}},
        )

        result = adapter.sync(ResolvedSet(agents=["architecture-reviewer.md"]), target, registry)
        assert any("manual [features] table" in line for line in result.errors)

    def test_sync_agents_cleanup_stale_managed_outputs(self, adapter, tmp_path, monkeypatch):
        registry = tmp_path / "registry"
        agents = registry / "agents"
        agents.mkdir(parents=True)
        (agents / "architecture-reviewer.md").write_text("# architecture review\n")
        target = tmp_path / ".codex"
        target.mkdir()

        monkeypatch.setattr(
            "hawk_hooks.config.load_global_config",
            lambda: {"tools": {"codex": {"allow_multi_agent": True, "agent_trigger_mode": "skills"}}},
        )

        adapter.sync(ResolvedSet(agents=["architecture-reviewer.md"]), target, registry)
        assert (target / "agents" / "architecture_reviewer.toml").exists()

        result = adapter.sync(ResolvedSet(agents=[]), target, registry)
        assert any(item == "agent:architecture_reviewer" for item in result.unlinked)
        assert not (target / "agents" / "architecture_reviewer.toml").exists()
        assert not (tmp_path / ".agents" / "skills" / "agent-architecture-reviewer").exists()

    def test_sync_agents_with_codex_tool_list_does_not_warn_unknown_frontmatter_tools(
        self, adapter, tmp_path, monkeypatch, caplog
    ):
        registry = tmp_path / "registry"
        agents = registry / "agents"
        agents.mkdir(parents=True)
        (agents / "planner.md").write_text(
            "---\n"
            "name: planner\n"
            "description: Planner agent\n"
            'tools: ["Read", "Grep", "Glob", "Bash"]\n'
            "---\n\n"
            "Plan the next steps.\n"
        )
        target = tmp_path / ".codex"
        target.mkdir()

        monkeypatch.setattr(
            "hawk_hooks.config.load_global_config",
            lambda: {"tools": {"codex": {"allow_multi_agent": True, "agent_trigger_mode": "skills"}}},
        )

        with caplog.at_level(logging.WARNING, logger="hawk_hooks.frontmatter"):
            adapter.sync(ResolvedSet(agents=["planner.md"]), target, registry)

        assert not any("Unknown tools in frontmatter" in rec.message for rec in caplog.records)
