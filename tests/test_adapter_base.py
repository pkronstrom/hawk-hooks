"""Tests for the adapter base class and registry."""

import pytest

from hawk_hooks.adapters import get_adapter, list_adapters
from hawk_hooks.adapters.base import ToolAdapter
from hawk_hooks.types import Tool


class TestToolAdapterABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            ToolAdapter()

    def test_requires_all_abstract_methods(self):
        # Incomplete implementation should fail
        class IncompleteAdapter(ToolAdapter):
            @property
            def tool(self):
                return Tool.CLAUDE

        with pytest.raises(TypeError):
            IncompleteAdapter()


class TestAdapterRegistry:
    def test_get_claude_adapter(self):
        adapter = get_adapter(Tool.CLAUDE)
        assert adapter.tool == Tool.CLAUDE

    def test_get_gemini_adapter(self):
        adapter = get_adapter(Tool.GEMINI)
        assert adapter.tool == Tool.GEMINI

    def test_get_codex_adapter(self):
        adapter = get_adapter(Tool.CODEX)
        assert adapter.tool == Tool.CODEX

    def test_get_opencode_adapter(self):
        adapter = get_adapter(Tool.OPENCODE)
        assert adapter.tool == Tool.OPENCODE

    def test_list_adapters(self):
        adapters = list_adapters()
        assert len(adapters) == 6
        assert Tool.CLAUDE in adapters


class TestBaseSymlinkOps:
    def test_link_and_unlink_skill(self, tmp_path):
        adapter = get_adapter(Tool.CLAUDE)
        source = tmp_path / "registry" / "skills" / "tdd"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("# TDD")

        target = tmp_path / "claude"
        target.mkdir()

        dest = adapter.link_skill(source, target)
        assert dest.is_symlink()
        assert (dest / "SKILL.md").read_text() == "# TDD"

        assert adapter.unlink_skill(source.name, target) is True
        assert not dest.exists()

    def test_link_and_unlink_agent(self, tmp_path):
        adapter = get_adapter(Tool.CLAUDE)
        source = tmp_path / "registry" / "agents" / "reviewer.md"
        source.parent.mkdir(parents=True)
        source.write_text("# Reviewer")

        target = tmp_path / "claude"
        target.mkdir()

        dest = adapter.link_agent(source, target)
        assert dest.is_symlink()

        assert adapter.unlink_agent(source.name, target) is True

    def test_link_and_unlink_command(self, tmp_path):
        adapter = get_adapter(Tool.CLAUDE)
        source = tmp_path / "registry" / "commands" / "deploy.md"
        source.parent.mkdir(parents=True)
        source.write_text("# Deploy")

        target = tmp_path / "claude"
        target.mkdir()

        dest = adapter.link_command(source, target)
        assert dest.is_symlink()

        assert adapter.unlink_command(source.name, target) is True

    def test_unlink_nonexistent_returns_false(self, tmp_path):
        adapter = get_adapter(Tool.CLAUDE)
        target = tmp_path / "claude"
        target.mkdir()
        (target / "skills").mkdir()

        assert adapter.unlink_skill("nonexistent", target) is False

    def test_link_replaces_existing(self, tmp_path):
        adapter = get_adapter(Tool.CLAUDE)
        source1 = tmp_path / "v1" / "skill.md"
        source1.parent.mkdir()
        source1.write_text("v1")

        source2 = tmp_path / "v2" / "skill.md"
        source2.parent.mkdir()
        source2.write_text("v2")

        target = tmp_path / "claude"
        target.mkdir()

        adapter.link_skill(source1, target)
        adapter.link_skill(source2, target)

        dest = adapter.get_skills_dir(target) / "skill.md"
        assert dest.read_text() == "v2"


class TestSyncForeignProtection:
    """Sync should not overwrite items managed by other tools."""

    def test_skips_foreign_symlink(self, tmp_path):
        """Sync should skip a skill that's already symlinked by another tool."""
        from hawk_hooks.types import ResolvedSet, SyncResult

        adapter = get_adapter(Tool.CLAUDE)

        # Set up hawk registry with a skill called "tdd"
        registry = tmp_path / "registry"
        hawk_skill = registry / "skills" / "tdd"
        hawk_skill.mkdir(parents=True)
        (hawk_skill / "SKILL.md").write_text("# Hawk TDD")

        # Set up target dir with "tdd" already linked by something else (e.g. obra)
        target = tmp_path / "claude"
        skills_dir = target / "skills"
        skills_dir.mkdir(parents=True)

        foreign_source = tmp_path / "obra" / "tdd"
        foreign_source.mkdir(parents=True)
        (foreign_source / "SKILL.md").write_text("# Obra TDD")
        (skills_dir / "tdd").symlink_to(foreign_source)

        # Sync should skip tdd and report it
        resolved = ResolvedSet(skills=["tdd"])
        result = adapter.sync(resolved, target, registry)

        assert "tdd" not in result.linked
        assert any("skip tdd" in e and "not managed by hawk" in e for e in result.errors)
        # Foreign symlink should be untouched
        assert (skills_dir / "tdd").resolve() == foreign_source.resolve()

    def test_skips_regular_file(self, tmp_path):
        """Sync should skip if a regular file (not symlink) already exists."""
        from hawk_hooks.types import ResolvedSet, SyncResult

        adapter = get_adapter(Tool.CLAUDE)

        registry = tmp_path / "registry"
        hawk_skill = registry / "skills" / "my-skill.md"
        (registry / "skills").mkdir(parents=True)
        hawk_skill.write_text("# My skill")

        target = tmp_path / "claude"
        skills_dir = target / "skills"
        skills_dir.mkdir(parents=True)
        # Regular file already there
        (skills_dir / "my-skill.md").write_text("# Manual file")

        resolved = ResolvedSet(skills=["my-skill.md"])
        result = adapter.sync(resolved, target, registry)

        assert "my-skill.md" not in result.linked
        assert any("skip my-skill.md" in e for e in result.errors)
        # Original file untouched
        assert (skills_dir / "my-skill.md").read_text() == "# Manual file"

    def test_replaces_own_symlink(self, tmp_path):
        """Sync should replace a symlink that already points into hawk registry."""
        from hawk_hooks.types import ResolvedSet, SyncResult

        adapter = get_adapter(Tool.CLAUDE)

        registry = tmp_path / "registry"
        hawk_skill = registry / "skills" / "tdd"
        hawk_skill.mkdir(parents=True)
        (hawk_skill / "SKILL.md").write_text("# TDD v2")

        target = tmp_path / "claude"
        skills_dir = target / "skills"
        skills_dir.mkdir(parents=True)
        # Already linked to our own registry (simulating previous sync)
        (skills_dir / "tdd").symlink_to(hawk_skill)

        resolved = ResolvedSet(skills=["tdd"])
        result = adapter.sync(resolved, target, registry)

        # Should not report as error - it's ours, already current
        assert not any("skip tdd" in e for e in result.errors)


class TestGenerateRunnersWithMeta:
    """Test _generate_runners with hawk-hook metadata (flat files)."""

    @pytest.fixture(autouse=True)
    def _patch_config_dir(self, tmp_path, monkeypatch):
        from hawk_hooks import v2_config
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: tmp_path / "config")

    def test_groups_by_metadata_events(self, tmp_path):
        """Hook with hawk-hook header groups by declared events."""
        adapter = get_adapter(Tool.CLAUDE)
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "guard.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")

        runners = adapter._generate_runners(["guard.py"], registry, runners_dir)
        assert "pre_tool_use" in runners
        assert runners["pre_tool_use"].exists()
        content = runners["pre_tool_use"].read_text()
        assert "guard.py" in content

    def test_multi_event_hook(self, tmp_path):
        """Hook targeting multiple events appears in multiple runners."""
        adapter = get_adapter(Tool.CLAUDE)
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "notify.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=stop,notification\nimport sys\n")

        runners = adapter._generate_runners(["notify.py"], registry, runners_dir)
        assert "stop" in runners
        assert "notification" in runners

    def test_content_hook_with_frontmatter(self, tmp_path):
        """Markdown hook with frontmatter generates cat call."""
        adapter = get_adapter(Tool.CLAUDE)
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "check.md"
        hook.write_text("---\nhawk-hook:\n  events: [stop]\n---\nVerify completion.\n")

        runners = adapter._generate_runners(["check.md"], registry, runners_dir)
        assert "stop" in runners
        content = runners["stop"].read_text()
        assert "check.md" in content

    def test_hook_without_metadata_skipped(self, tmp_path):
        """Hook with no hawk-hook header and no event dir fallback is skipped."""
        adapter = get_adapter(Tool.CLAUDE)
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "random.py"
        hook.write_text("#!/usr/bin/env python3\nimport sys\n")

        runners = adapter._generate_runners(["random.py"], registry, runners_dir)
        assert runners == {}

    def test_invalid_event_names_rejected(self, tmp_path):
        """Hooks with invalid/traversal event names are silently skipped."""
        adapter = get_adapter(Tool.CLAUDE)
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "evil.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=../../etc\nimport sys\n")

        runners = adapter._generate_runners(["evil.py"], registry, runners_dir)
        assert runners == {}
        # No runner files should exist
        if runners_dir.exists():
            assert list(runners_dir.iterdir()) == []

    def test_unknown_event_names_rejected(self, tmp_path):
        """Hooks with unknown event names are silently skipped."""
        adapter = get_adapter(Tool.CLAUDE)
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "hook.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=made_up_event\nimport sys\n")

        runners = adapter._generate_runners(["hook.py"], registry, runners_dir)
        assert runners == {}

    def test_stale_runners_cleaned(self, tmp_path):
        """Runners for events no longer in use are deleted."""
        adapter = get_adapter(Tool.CLAUDE)
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"
        runners_dir.mkdir(parents=True)

        # Create a stale runner
        stale = runners_dir / "old_event.sh"
        stale.write_text("#!/bin/bash\nexit 0\n")

        hook = hooks_dir / "guard.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")

        adapter._generate_runners(["guard.py"], registry, runners_dir)
        assert not stale.exists()

    def test_env_vars_exported_in_runner(self, tmp_path, monkeypatch):
        """Env vars with values should be exported before hook calls."""
        from hawk_hooks import v2_config
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: tmp_path / "config")

        adapter = get_adapter(Tool.CLAUDE)
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "hook.py"
        hook.write_text(
            "#!/usr/bin/env python3\n"
            "# hawk-hook: events=pre_tool_use\n"
            "# hawk-hook: env=API_KEY=secret123\n"
            "# hawk-hook: env=VERBOSE\n"
            "import sys\n"
        )

        runners = adapter._generate_runners(["hook.py"], registry, runners_dir)
        content = runners["pre_tool_use"].read_text()
        # Env with = should be exported (simple values don't need quoting)
        assert "export API_KEY=secret123" in content
        # Env without = (informational only) should NOT be exported
        assert "export VERBOSE" not in content

    def test_env_var_shell_injection_prevented(self, tmp_path, monkeypatch):
        """Env var values with shell metacharacters should be safely quoted."""
        from hawk_hooks import v2_config
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: tmp_path / "config")

        adapter = get_adapter(Tool.CLAUDE)
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "hook.py"
        hook.write_text(
            "#!/usr/bin/env python3\n"
            "# hawk-hook: events=pre_tool_use\n"
            "# hawk-hook: env=MALICIOUS=$(rm -rf /)\n"
            "import sys\n"
        )

        runners = adapter._generate_runners(["hook.py"], registry, runners_dir)
        content = runners["pre_tool_use"].read_text()
        # Value should be quoted, preventing shell expansion
        assert "export MALICIOUS='$(rm -rf /)'" in content
        # The raw unquoted version must NOT appear
        assert "export MALICIOUS=$(rm -rf /)" not in content

    def test_venv_python_used_when_available(self, tmp_path, monkeypatch):
        """When venv exists, runners should use venv python path."""
        from hawk_hooks import v2_config
        config_dir = tmp_path / "config"
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

        # Create fake venv python
        venv_bin = config_dir / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        venv_python = venv_bin / "python"
        venv_python.write_text("#!/bin/sh\n")
        venv_python.chmod(0o755)

        adapter = get_adapter(Tool.CLAUDE)
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "hook.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")

        runners = adapter._generate_runners(["hook.py"], registry, runners_dir)
        content = runners["pre_tool_use"].read_text()
        assert str(venv_python) in content

    def test_system_python_when_no_venv(self, tmp_path, monkeypatch):
        """When no venv exists, runners should use system python3."""
        from hawk_hooks import v2_config
        config_dir = tmp_path / "config"
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

        adapter = get_adapter(Tool.CLAUDE)
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "hook.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")

        runners = adapter._generate_runners(["hook.py"], registry, runners_dir)
        content = runners["pre_tool_use"].read_text()
        assert "python3" in content
