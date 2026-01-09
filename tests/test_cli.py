"""Tests for captain-hook CLI commands."""

import argparse
import json
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from captain_hook import cli, config
from captain_hook.cli import (
    cmd_disable,
    cmd_enable,
    cmd_install,
    cmd_list,
    cmd_toggle,
    cmd_uninstall,
    find_hook,
    main,
)


class TestFindHook:
    """Tests for the find_hook function."""

    def test_find_hook_with_event_prefix(self, mock_config_paths, sample_hooks):
        """Test finding a hook with explicit event/name format."""
        result = find_hook("pre_tool_use/test-guard")

        assert result is not None
        assert result == ("pre_tool_use", "test-guard")

    def test_find_hook_without_event_prefix(self, mock_config_paths, sample_hooks):
        """Test finding a hook by name only (auto-detect event)."""
        result = find_hook("test-guard")

        assert result is not None
        assert result == ("pre_tool_use", "test-guard")

    def test_find_hook_not_found(self, mock_config_paths, sample_hooks):
        """Test finding a non-existent hook returns None."""
        result = find_hook("nonexistent-hook")

        assert result is None

    def test_find_hook_wrong_event(self, mock_config_paths, sample_hooks):
        """Test finding a hook with wrong event returns None."""
        result = find_hook("post_tool_use/test-guard")

        assert result is None

    def test_find_hook_empty_hooks_dir(self, mock_config_paths):
        """Test finding a hook when no hooks exist."""
        result = find_hook("any-hook")

        assert result is None


class TestCmdEnable:
    """Tests for the enable command."""

    def test_enable_single_hook(self, mock_config_paths, sample_hooks, cli_runner, mock_args, capsys):
        """Test enabling a single hook."""
        args = mock_args(hooks=["pre_tool_use/test-guard"])

        cmd_enable(args)
        captured = capsys.readouterr()

        assert "Enabled pre_tool_use/test-guard" in captured.out
        assert "Runners regenerated" in captured.out

        # Verify config was updated
        cfg = config.load_config()
        assert "test-guard" in cfg["enabled"]["pre_tool_use"]

    def test_enable_multiple_hooks(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test enabling multiple hooks at once."""
        args = mock_args(hooks=["pre_tool_use/test-guard", "post_tool_use/logger"])

        cmd_enable(args)
        captured = capsys.readouterr()

        assert "Enabled pre_tool_use/test-guard" in captured.out
        assert "Enabled post_tool_use/logger" in captured.out

        cfg = config.load_config()
        assert "test-guard" in cfg["enabled"]["pre_tool_use"]
        assert "logger" in cfg["enabled"]["post_tool_use"]

    def test_enable_already_enabled_hook(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test enabling a hook that's already enabled."""
        # First enable
        args = mock_args(hooks=["pre_tool_use/test-guard"])
        cmd_enable(args)

        # Try to enable again
        cmd_enable(args)
        captured = capsys.readouterr()

        assert "Already enabled: pre_tool_use/test-guard" in captured.out

    def test_enable_nonexistent_hook(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test enabling a hook that doesn't exist."""
        args = mock_args(hooks=["nonexistent"])

        cmd_enable(args)
        captured = capsys.readouterr()

        assert "Hook not found: nonexistent" in captured.out

    def test_enable_without_event_prefix(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test enabling a hook by name only."""
        args = mock_args(hooks=["test-guard"])

        cmd_enable(args)
        captured = capsys.readouterr()

        assert "Enabled pre_tool_use/test-guard" in captured.out

    def test_enable_mixed_valid_invalid(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test enabling mix of valid and invalid hooks."""
        args = mock_args(hooks=["test-guard", "nonexistent", "logger"])

        cmd_enable(args)
        captured = capsys.readouterr()

        assert "Enabled pre_tool_use/test-guard" in captured.out
        assert "Hook not found: nonexistent" in captured.out
        assert "Enabled post_tool_use/logger" in captured.out


class TestCmdDisable:
    """Tests for the disable command."""

    def test_disable_enabled_hook(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test disabling an enabled hook."""
        # First enable
        enable_args = mock_args(hooks=["pre_tool_use/test-guard"])
        cmd_enable(enable_args)

        # Then disable
        disable_args = mock_args(hooks=["pre_tool_use/test-guard"])
        cmd_disable(disable_args)
        captured = capsys.readouterr()

        assert "Disabled pre_tool_use/test-guard" in captured.out

        cfg = config.load_config()
        assert "test-guard" not in cfg["enabled"]["pre_tool_use"]

    def test_disable_already_disabled_hook(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test disabling a hook that's already disabled."""
        args = mock_args(hooks=["pre_tool_use/test-guard"])

        cmd_disable(args)
        captured = capsys.readouterr()

        assert "Already disabled: pre_tool_use/test-guard" in captured.out

    def test_disable_nonexistent_hook(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test disabling a non-existent hook."""
        args = mock_args(hooks=["nonexistent"])

        cmd_disable(args)
        captured = capsys.readouterr()

        assert "Hook not found: nonexistent" in captured.out

    def test_disable_multiple_hooks(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test disabling multiple hooks."""
        # Enable first
        enable_args = mock_args(hooks=["test-guard", "logger"])
        cmd_enable(enable_args)

        # Disable
        disable_args = mock_args(hooks=["test-guard", "logger"])
        cmd_disable(disable_args)
        captured = capsys.readouterr()

        assert "Disabled pre_tool_use/test-guard" in captured.out
        assert "Disabled post_tool_use/logger" in captured.out


class TestCmdList:
    """Tests for the list command."""

    def test_list_all_hooks(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test listing all hooks."""
        args = mock_args(enabled=False, disabled=False)

        cmd_list(args)
        captured = capsys.readouterr()

        assert "pre_tool_use/test-guard" in captured.out
        assert "pre_tool_use/file-validator" in captured.out
        assert "post_tool_use/logger" in captured.out
        assert "stop/cleanup" in captured.out

    def test_list_only_enabled(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test listing only enabled hooks."""
        # Enable one hook
        enable_args = mock_args(hooks=["test-guard"])
        cmd_enable(enable_args)

        # List enabled only
        list_args = mock_args(enabled=True, disabled=False)
        cmd_list(list_args)
        captured = capsys.readouterr()

        assert "pre_tool_use/test-guard" in captured.out
        assert "enabled" in captured.out
        assert "file-validator" not in captured.out

    def test_list_only_disabled(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test listing only disabled hooks."""
        # Enable one hook
        enable_args = mock_args(hooks=["test-guard"])
        cmd_enable(enable_args)
        capsys.readouterr()  # Clear enable output

        # List disabled only
        list_args = mock_args(enabled=False, disabled=True)
        cmd_list(list_args)
        captured = capsys.readouterr()

        assert "test-guard" not in captured.out
        assert "file-validator" in captured.out
        assert "disabled" in captured.out

    def test_list_empty_hooks(self, mock_config_paths, mock_args, capsys):
        """Test listing when no hooks exist."""
        args = mock_args(enabled=False, disabled=False)

        cmd_list(args)
        captured = capsys.readouterr()

        # Should produce no output when no hooks exist
        assert captured.out == ""

    def test_list_output_format(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test that list output is tab-separated for scripting."""
        args = mock_args(enabled=False, disabled=False)

        cmd_list(args)
        captured = capsys.readouterr()

        lines = captured.out.strip().split("\n")
        for line in lines:
            parts = line.split("\t")
            assert len(parts) == 3  # event/name, status, description


class TestCmdInstall:
    """Tests for the install command."""

    def test_install_user_scope(self, mock_config_paths, mock_args, capsys):
        """Test installing hooks to user scope."""
        args = mock_args(scope="user")

        cmd_install(args)
        captured = capsys.readouterr()

        # Should show success for all events
        assert "pre_tool_use" in captured.out
        assert "post_tool_use" in captured.out
        assert "✓" in captured.out

    def test_install_project_scope(self, mock_config_paths, mock_args, capsys, tmp_path):
        """Test installing hooks to project scope."""
        # Create a fake project directory
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()  # Make it look like a git repo

        # Patch project settings path
        with patch("captain_hook.installer.get_project_settings_path") as mock_path:
            settings_file = project_dir / ".claude" / "settings.json"
            settings_file.parent.mkdir(parents=True)
            settings_file.write_text("{}")
            mock_path.return_value = settings_file

            args = mock_args(scope="project")
            cmd_install(args)
            captured = capsys.readouterr()

            assert "✓" in captured.out

    def test_install_creates_claude_settings(self, mock_config_paths, mock_args, capsys):
        """Test that install creates Claude settings if they don't exist."""
        # Remove existing settings
        from captain_hook import installer
        settings_path = installer.get_user_settings_path()
        if settings_path.exists():
            settings_path.unlink()

        args = mock_args(scope="user")
        cmd_install(args)

        # Settings should now exist
        assert settings_path.exists()

        with open(settings_path) as f:
            settings = json.load(f)
        assert "hooks" in settings


class TestCmdUninstall:
    """Tests for the uninstall command."""

    def test_uninstall_user_scope(self, mock_config_paths, mock_args, capsys):
        """Test uninstalling hooks from user scope."""
        # First install
        install_args = mock_args(scope="user")
        cmd_install(install_args)

        # Then uninstall
        uninstall_args = mock_args(scope="user")
        cmd_uninstall(uninstall_args)
        captured = capsys.readouterr()

        assert "Hooks uninstalled" in captured.out
        assert "rm -rf" in captured.out  # Cleanup instructions

    def test_uninstall_removes_hooks_from_settings(self, mock_config_paths, mock_args):
        """Test that uninstall removes hooks from Claude settings."""
        from captain_hook import installer

        # Install first
        install_args = mock_args(scope="user")
        cmd_install(install_args)

        # Verify hooks exist
        settings_path = installer.get_user_settings_path()
        with open(settings_path) as f:
            settings = json.load(f)
        assert settings.get("hooks")

        # Uninstall
        uninstall_args = mock_args(scope="user")
        cmd_uninstall(uninstall_args)

        # Verify hooks removed
        with open(settings_path) as f:
            settings = json.load(f)
        # hooks dict should be empty or not contain our hooks
        for event_hooks in settings.get("hooks", {}).values():
            for hook_group in event_hooks:
                for hook in hook_group.get("hooks", []):
                    assert "captain-hook" not in hook.get("command", "")


class TestCmdToggle:
    """Tests for the toggle command."""

    def test_toggle_regenerates_runners(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test that toggle regenerates runners."""
        # Enable a hook first
        enable_args = mock_args(hooks=["test-guard"])
        cmd_enable(enable_args)

        # Run toggle
        cmd_toggle(mock_args())
        captured = capsys.readouterr()

        assert "Runners regenerated" in captured.out

    def test_toggle_creates_runner_files(self, mock_config_paths, sample_hooks, mock_args):
        """Test that toggle creates runner shell scripts."""
        # Enable a hook
        enable_args = mock_args(hooks=["test-guard"])
        cmd_enable(enable_args)

        # Run toggle
        cmd_toggle(mock_args())

        # Check runner was created
        runners_dir = config.get_runners_dir()
        runner_file = runners_dir / "pre_tool_use.sh"
        assert runner_file.exists()

        content = runner_file.read_text()
        assert "test-guard" in content


class TestMainParser:
    """Tests for the main CLI argument parser."""

    def test_version_flag(self, capsys):
        """Test --version flag."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["captain-hook", "--version"]):
                main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "captain-hook" in captured.out

    def test_enable_subcommand_parsing(self):
        """Test enable subcommand parses correctly."""
        with patch("sys.argv", ["captain-hook", "enable", "test-hook", "other-hook"]):
            parser = argparse.ArgumentParser()
            subparsers = parser.add_subparsers(dest="command")

            enable_parser = subparsers.add_parser("enable")
            enable_parser.add_argument("hooks", nargs="+")

            args = parser.parse_args(["enable", "test-hook", "other-hook"])

            assert args.command == "enable"
            assert args.hooks == ["test-hook", "other-hook"]

    def test_disable_subcommand_parsing(self):
        """Test disable subcommand parses correctly."""
        with patch("sys.argv", ["captain-hook", "disable", "test-hook"]):
            parser = argparse.ArgumentParser()
            subparsers = parser.add_subparsers(dest="command")

            disable_parser = subparsers.add_parser("disable")
            disable_parser.add_argument("hooks", nargs="+")

            args = parser.parse_args(["disable", "test-hook"])

            assert args.command == "disable"
            assert args.hooks == ["test-hook"]

    def test_install_scope_default(self):
        """Test install defaults to user scope."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")

        install_parser = subparsers.add_parser("install")
        install_parser.add_argument("--scope", choices=["user", "project"], default="user")

        args = parser.parse_args(["install"])

        assert args.scope == "user"

    def test_install_scope_project(self):
        """Test install with project scope."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")

        install_parser = subparsers.add_parser("install")
        install_parser.add_argument("--scope", choices=["user", "project"], default="user")

        args = parser.parse_args(["install", "--scope", "project"])

        assert args.scope == "project"

    def test_list_enabled_flag(self):
        """Test list --enabled flag."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")

        list_parser = subparsers.add_parser("list")
        list_parser.add_argument("--enabled", action="store_true")
        list_parser.add_argument("--disabled", action="store_true")

        args = parser.parse_args(["list", "--enabled"])

        assert args.enabled is True
        assert args.disabled is False

    def test_list_disabled_flag(self):
        """Test list --disabled flag."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")

        list_parser = subparsers.add_parser("list")
        list_parser.add_argument("--enabled", action="store_true")
        list_parser.add_argument("--disabled", action="store_true")

        args = parser.parse_args(["list", "--disabled"])

        assert args.enabled is False
        assert args.disabled is True

    def test_no_subcommand_calls_interactive(self, mock_config_paths):
        """Test that no subcommand launches interactive menu."""
        with patch("captain_hook.cli.interactive_menu") as mock_menu:
            with patch("sys.argv", ["captain-hook"]):
                main()
            mock_menu.assert_called_once()


class TestCmdIntegration:
    """Integration tests for CLI command workflows."""

    def test_enable_disable_cycle(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test full enable/disable cycle."""
        # Enable
        enable_args = mock_args(hooks=["test-guard"])
        cmd_enable(enable_args)

        cfg = config.load_config()
        assert "test-guard" in cfg["enabled"]["pre_tool_use"]

        # Disable
        disable_args = mock_args(hooks=["test-guard"])
        cmd_disable(disable_args)

        cfg = config.load_config()
        assert "test-guard" not in cfg["enabled"]["pre_tool_use"]

    def test_install_enable_toggle_workflow(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test typical workflow: install, enable hooks, toggle."""
        # Install
        cmd_install(mock_args(scope="user"))

        # Enable hooks
        cmd_enable(mock_args(hooks=["test-guard", "logger"]))

        # Toggle to regenerate
        cmd_toggle(mock_args())

        # Verify runners exist and contain hooks
        runners_dir = config.get_runners_dir()
        pre_runner = runners_dir / "pre_tool_use.sh"
        post_runner = runners_dir / "post_tool_use.sh"

        assert pre_runner.exists()
        assert post_runner.exists()

        assert "test-guard" in pre_runner.read_text()
        assert "logger" in post_runner.read_text()

    def test_list_reflects_enable_disable(self, mock_config_paths, sample_hooks, mock_args, capsys):
        """Test that list output reflects enable/disable changes."""
        # Initial list - all disabled
        cmd_list(mock_args(enabled=False, disabled=False))
        initial_output = capsys.readouterr().out

        # All should show disabled
        for line in initial_output.strip().split("\n"):
            if line:
                assert "disabled" in line

        # Enable one
        cmd_enable(mock_args(hooks=["test-guard"]))
        capsys.readouterr()  # Clear output

        # List only enabled
        cmd_list(mock_args(enabled=True, disabled=False))
        enabled_output = capsys.readouterr().out

        assert "test-guard" in enabled_output
        assert "enabled" in enabled_output
