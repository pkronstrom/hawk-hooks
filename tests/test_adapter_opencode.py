"""Tests for the OpenCode adapter."""

import json

import pytest

from hawk_hooks.adapters.opencode import OpenCodeAdapter, HAWK_MCP_MARKER
from hawk_hooks.types import ResolvedSet, Tool


@pytest.fixture
def adapter():
    return OpenCodeAdapter()


class TestOpenCodeAdapter:
    def test_tool(self, adapter):
        assert adapter.tool == Tool.OPENCODE

    def test_global_dir(self, adapter):
        assert str(adapter.get_global_dir()).endswith("opencode")

    def test_project_dir(self, adapter, tmp_path):
        assert adapter.get_project_dir(tmp_path) == tmp_path / ".opencode"

    def test_hook_support_flag(self, adapter):
        assert adapter.hook_support == "bridge"


class TestOpenCodeMCP:
    def test_write_mcp(self, adapter, tmp_path):
        target = tmp_path / "opencode"
        target.mkdir()

        servers = {"github": {"command": "gh-mcp"}}
        adapter.write_mcp_config(servers, target)

        data = json.loads((target / "opencode.json").read_text())
        assert "github" in data["mcp"]
        assert HAWK_MCP_MARKER not in data["mcp"]["github"]

    def test_preserves_manual(self, adapter, tmp_path):
        target = tmp_path / "opencode"
        target.mkdir()

        config_path = target / "opencode.json"
        config_path.write_text(json.dumps({
            "mcp": {"manual": {"command": "m"}},
            "theme": "dark",
        }))

        adapter.write_mcp_config({"hawk": {"command": "h"}}, target)

        data = json.loads(config_path.read_text())
        assert "manual" in data["mcp"]
        assert "hawk" in data["mcp"]
        assert data["theme"] == "dark"

    def test_replaces_hawk_entries(self, adapter, tmp_path):
        target = tmp_path / "opencode"
        target.mkdir()

        adapter.write_mcp_config({"old": {"command": "old"}}, target)
        adapter.write_mcp_config({"new": {"command": "new"}}, target)

        data = json.loads((target / "opencode.json").read_text())
        assert "old" not in data["mcp"]
        assert "new" in data["mcp"]

    def test_migrates_legacy_mcp_servers(self, adapter, tmp_path):
        target = tmp_path / "opencode"
        target.mkdir()

        config_path = target / "opencode.json"
        config_path.write_text(json.dumps({
            "mcpServers": {
                "manual": {"command": "m"},
                "old_hawk": {"command": "old", HAWK_MCP_MARKER: True},
            },
            "other": {"x": 1},
        }))

        adapter.write_mcp_config({"new_hawk": {"command": "new"}}, target)
        data = json.loads(config_path.read_text())

        assert "mcpServers" not in data
        assert "manual" in data["mcp"]
        assert "old_hawk" not in data["mcp"]
        assert "new_hawk" in data["mcp"]
        assert data["other"] == {"x": 1}


class TestOpenCodePrompts:
    def test_prompts_dir_maps_to_commands(self, adapter, tmp_path):
        target = tmp_path / ".opencode"
        assert adapter.get_prompts_dir(target) == target / "commands"


class TestOpenCodeHooks:
    def test_sync_bridges_supported_hook_events(self, adapter, tmp_path):
        registry = tmp_path / "registry"
        hooks = registry / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "guard.py").write_text(
            "#!/usr/bin/env python3\n"
            "# hawk-hook: events=pre_tool_use\n"
            "import sys\n"
        )
        target = tmp_path / "opencode"
        target.mkdir(parents=True)

        result = adapter.sync(ResolvedSet(hooks=["guard.py"]), target, registry)
        assert "hook:guard.py" in result.linked
        assert (target / "runners" / "pre_tool_use.sh").exists()

        plugin_path = target / "plugins" / "hawk-hooks.ts"
        assert plugin_path.exists()
        plugin = plugin_path.read_text()
        assert "tool.execute.before" in plugin
        assert "hawk-hooks managed: opencode-hook-plugin" in plugin

    def test_sync_skips_unsupported_hook_events(self, adapter, tmp_path):
        registry = tmp_path / "registry"
        hooks = registry / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "perm.py").write_text(
            "#!/usr/bin/env python3\n"
            "# hawk-hook: events=permission_request\n"
            "import sys\n"
        )
        target = tmp_path / "opencode"
        target.mkdir(parents=True)

        result = adapter.sync(ResolvedSet(hooks=["perm.py"]), target, registry)
        assert any("permission_request is unsupported by opencode" in e for e in result.skipped)

    def test_generated_plugin_avoids_unconsumed_stdout_pipe(self, adapter, tmp_path):
        registry = tmp_path / "registry"
        hooks = registry / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "guard.py").write_text(
            "#!/usr/bin/env python3\n"
            "# hawk-hook: events=pre_tool_use\n"
            "import sys\n"
        )
        target = tmp_path / "opencode"
        target.mkdir(parents=True)

        adapter.sync(ResolvedSet(hooks=["guard.py"]), target, registry)
        plugin = (target / "plugins" / "hawk-hooks.ts").read_text()

        assert 'stdout: "pipe"' not in plugin
        assert (
            ('stdout: "ignore"' in plugin)
            or ('stdout: "null"' in plugin)
            or ("new Response(proc.stdout)" in plugin)
        )
