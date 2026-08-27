"""Tests for the Antigravity adapter.

Layout expectations here mirror what was probed against agy 1.1.10:
global root ~/.gemini/config, workspace root <project>/.agents, skills/agents
as directories, hooks.json for lifecycle hooks, mcp_config.json for MCP.
"""

import json

import pytest

from hawk_hooks.adapters.antigravity import AntigravityAdapter
from hawk_hooks.types import ResolvedSet, Tool


@pytest.fixture
def adapter():
    return AntigravityAdapter()


@pytest.fixture
def registry(tmp_path):
    """A registry with one hook per supported event plus an unsupported one."""
    reg = tmp_path / "registry"
    hooks = reg / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "guard.py").write_text(
        "# hawk-hook: events=pre_tool_use\n# hawk-hook: timeout=12\nprint('guard')\n"
    )
    (hooks / "finish.sh").write_text("# hawk-hook: events=stop\necho done\n")
    (hooks / "notify.sh").write_text("# hawk-hook: events=notification\necho notify\n")
    (reg / "skills").mkdir()
    (reg / "agents").mkdir()
    (reg / "prompts").mkdir()
    return reg


class TestAntigravityAdapter:
    def test_tool(self, adapter):
        assert adapter.tool == Tool.ANTIGRAVITY

    def test_global_dir_is_the_customization_root(self, adapter):
        assert str(adapter.get_global_dir()).endswith(".gemini/config")

    def test_project_dir_is_dot_agents(self, adapter, tmp_path):
        assert adapter.get_project_dir(tmp_path) == tmp_path / ".agents"

    def test_hook_support_flag(self, adapter):
        assert adapter.hook_support == "native"


class TestAntigravityHooks:
    def test_registers_supported_events(self, adapter, registry, tmp_path):
        target = tmp_path / "config"
        registered = adapter.register_hooks(
            ["guard.py", "finish.sh"], target, registry_path=registry
        )
        assert sorted(registered) == ["finish.sh", "guard.py"]

        data = json.loads((target / "hooks.json").read_text())
        assert set(data["hawk"]) == {"PreToolUse", "Stop"}

    def test_pre_tool_use_is_grouped_stop_is_flat(self, adapter, registry, tmp_path):
        target = tmp_path / "config"
        adapter.register_hooks(["guard.py", "finish.sh"], target, registry_path=registry)
        hawk = json.loads((target / "hooks.json").read_text())["hawk"]

        # PreToolUse wraps handlers in a {matcher, hooks} group.
        assert hawk["PreToolUse"][0]["matcher"] == "*"
        assert hawk["PreToolUse"][0]["hooks"][0]["type"] == "command"
        # Stop takes handler objects directly.
        assert hawk["Stop"][0]["type"] == "command"
        assert "hooks" not in hawk["Stop"][0]

    def test_hook_timeout_is_carried_through(self, adapter, registry, tmp_path):
        target = tmp_path / "config"
        adapter.register_hooks(["guard.py"], target, registry_path=registry)
        hawk = json.loads((target / "hooks.json").read_text())["hawk"]
        assert hawk["PreToolUse"][0]["hooks"][0]["timeout"] == 12

    def test_unsupported_event_is_skipped(self, adapter, registry, tmp_path):
        target = tmp_path / "config"
        registered = adapter.register_hooks(["notify.sh"], target, registry_path=registry)
        assert registered == []
        assert any("notification is unsupported" in s for s in adapter._take_hook_skipped())

    def test_prompt_hooks_are_skipped(self, adapter, registry, tmp_path):
        (registry / "hooks" / "ask.prompt.json").write_text(
            json.dumps({"prompt": "check", "hawk-hook": {"events": ["pre_tool_use"]}})
        )
        target = tmp_path / "config"
        adapter.register_hooks(["ask.prompt.json"], target, registry_path=registry)
        assert any("only supports command hooks" in s for s in adapter._take_hook_skipped())

    def test_preserves_foreign_hooks(self, adapter, registry, tmp_path):
        target = tmp_path / "config"
        target.mkdir(parents=True)
        (target / "hooks.json").write_text(
            json.dumps({"lint-checker": {"PostToolUse": [{"matcher": "run_command"}]}})
        )

        adapter.register_hooks(["guard.py"], target, registry_path=registry)
        data = json.loads((target / "hooks.json").read_text())
        assert "lint-checker" in data
        assert "hawk" in data

    def test_clearing_hooks_removes_only_the_hawk_key(self, adapter, registry, tmp_path):
        target = tmp_path / "config"
        adapter.register_hooks(["guard.py"], target, registry_path=registry)
        (target / "hooks.json").write_text(
            json.dumps(
                {
                    **json.loads((target / "hooks.json").read_text()),
                    "lint-checker": {"PostToolUse": []},
                }
            )
        )

        assert adapter.register_hooks([], target, registry_path=registry) == []
        data = json.loads((target / "hooks.json").read_text())
        assert "hawk" not in data
        assert "lint-checker" in data

    def test_hooks_file_removed_when_nothing_left(self, adapter, registry, tmp_path):
        target = tmp_path / "config"
        adapter.register_hooks(["guard.py"], target, registry_path=registry)
        adapter.register_hooks([], target, registry_path=registry)
        assert not (target / "hooks.json").exists()


class TestAntigravityHookBridge:
    """The bridge translates hawk exit codes into Antigravity's JSON contract."""

    def _bridge(self, adapter, registry, tmp_path, hook: str, event: str):
        target = tmp_path / "config"
        adapter.register_hooks([hook], target, registry_path=registry)
        return (target / "runners" / f"antigravity-{event}.sh").read_text()

    def test_pre_tool_use_passes_with_ask_not_allow(self, adapter, registry, tmp_path):
        # "allow" would auto-approve every tool call; "ask" keeps the normal
        # permission flow. An empty {} response denies, so a decision is required.
        script = self._bridge(adapter, registry, tmp_path, "guard.py", "pre_tool_use")
        assert '{"decision":"ask"}' in script
        assert '"allow"' not in script
        assert "'deny'" in script

    def test_stop_continues_only_on_failure(self, adapter, registry, tmp_path):
        script = self._bridge(adapter, registry, tmp_path, "finish.sh", "stop")
        assert "'continue'" in script
        assert "printf '%s\\n' '{}'" in script

    def test_bridge_survives_runner_regeneration(self, adapter, registry, tmp_path):
        # _generate_runners prunes stray .sh files, so bridges must be rewritten
        # after it runs on every sync.
        target = tmp_path / "config"
        for _ in range(2):
            adapter.register_hooks(["guard.py"], target, registry_path=registry)
            assert (target / "runners" / "antigravity-pre_tool_use.sh").is_file()

    def test_bridge_does_not_abort_on_nonzero_hook(self, adapter, registry, tmp_path):
        script = self._bridge(adapter, registry, tmp_path, "guard.py", "pre_tool_use")
        # `set -e` would kill the wrapper before it could report a deny.
        assert "set -uo pipefail" in script
        assert "set -euo pipefail" not in script


class TestAntigravitySync:
    def test_skills_and_agents_are_linked(self, adapter, registry, tmp_path):
        skill = registry / "skills" / "tdd"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: tdd\ndescription: d\n---\n")
        (registry / "agents" / "reviewer.md").write_text("---\nname: r\ndescription: d\n---\n")

        target = tmp_path / "config"
        result = adapter.sync(
            ResolvedSet(skills=["tdd"], agents=["reviewer.md"]), target, registry
        )

        assert (target / "skills" / "tdd" / "SKILL.md").exists()
        assert (target / "agents" / "reviewer.md").exists()
        assert not result.errors

    def test_prompts_are_reported_unsupported(self, adapter, registry, tmp_path):
        (registry / "prompts" / "audit.md").write_text("---\nname: a\ndescription: d\n---\n")
        target = tmp_path / "config"

        result = adapter.sync(ResolvedSet(prompts=["audit.md"]), target, registry)

        assert any("no custom slash commands" in s for s in result.skipped)
        assert not (target / "prompts" / "audit.md").exists()

    def test_legacy_prompt_links_are_cleaned_up(self, adapter, registry, tmp_path):
        source = registry / "prompts" / "audit.md"
        source.write_text("---\nname: a\ndescription: d\n---\n")
        target = tmp_path / "config"
        stale = target / "prompts"
        stale.mkdir(parents=True)
        (stale / "audit.md").symlink_to(source)

        adapter.sync(ResolvedSet(), target, registry)

        assert not (stale / "audit.md").exists()


class TestAntigravityMCP:
    def test_write_mcp_sidecar(self, adapter, tmp_path):
        target = tmp_path / "config"
        target.mkdir(parents=True)

        adapter.write_mcp_config({"gh": {"command": "gh-mcp"}}, target)
        data = json.loads((target / "mcp_config.json").read_text())
        assert data["mcpServers"]["gh"] == {"command": "gh-mcp"}
        sidecar = json.loads((target / ".hawk-mcp.json").read_text())
        assert "gh" in sidecar

    def test_manual_servers_are_preserved(self, adapter, tmp_path):
        target = tmp_path / "config"
        target.mkdir(parents=True)
        (target / "mcp_config.json").write_text(
            json.dumps({"mcpServers": {"mine": {"command": "manual"}}})
        )

        adapter.write_mcp_config({"gh": {"command": "gh-mcp"}}, target)
        servers = json.loads((target / "mcp_config.json").read_text())["mcpServers"]
        assert "mine" in servers
        assert "gh" in servers
