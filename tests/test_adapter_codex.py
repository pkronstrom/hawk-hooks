"""Tests for the Codex adapter."""

import json

import pytest

from hawk_hooks.adapters.codex import CodexAdapter, HAWK_MCP_MARKER
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

    def test_skills_dir_is_agents(self, adapter, tmp_path):
        assert adapter.get_skills_dir(tmp_path) == tmp_path / "agents"

    def test_agents_dir_is_agents(self, adapter, tmp_path):
        assert adapter.get_agents_dir(tmp_path) == tmp_path / "agents"

    def test_commands_dir_is_agents(self, adapter, tmp_path):
        """Codex doesn't have slash commands, so commands go to agents/."""
        assert adapter.get_commands_dir(tmp_path) == tmp_path / "agents"


class TestCodexMCP:
    def test_write_mcp(self, adapter, tmp_path):
        target = tmp_path / "codex"
        target.mkdir()

        servers = {"github": {"command": "gh-mcp"}}
        adapter.write_mcp_config(servers, target)

        data = json.loads((target / "mcp.json").read_text())
        assert "github" in data["mcpServers"]
        assert data["mcpServers"]["github"][HAWK_MCP_MARKER] is True

    def test_preserves_manual(self, adapter, tmp_path):
        target = tmp_path / "codex"
        target.mkdir()

        mcp_path = target / "mcp.json"
        mcp_path.write_text(json.dumps({
            "mcpServers": {"manual": {"command": "m"}}
        }))

        adapter.write_mcp_config({"hawk": {"command": "h"}}, target)

        data = json.loads(mcp_path.read_text())
        assert "manual" in data["mcpServers"]
        assert "hawk" in data["mcpServers"]


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
        assert any("pre_tool_use is unsupported by codex" in e for e in result.errors)

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
