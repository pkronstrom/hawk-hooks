"""Pytest fixtures for captain-hook tests."""

import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory structure.

    Sets up:
    - config.json with default config
    - hooks/{event}/ directories
    - runners/ directory
    """
    config_dir = tmp_path / "captain-hook"
    config_dir.mkdir()

    # Create hooks directories for all events
    hooks_dir = config_dir / "hooks"
    hooks_dir.mkdir()

    events = [
        "pre_tool_use", "post_tool_use", "notification", "stop",
        "subagent_stop", "user_prompt_submit", "session_start",
        "session_end", "pre_compact", "permission_request"
    ]
    for event in events:
        (hooks_dir / event).mkdir()

    # Create runners directory
    (config_dir / "runners").mkdir()

    # Create docs directory
    (config_dir / "docs").mkdir()

    # Create default config
    config = {
        "enabled": {event: [] for event in events},
        "projects": [],
        "debug": False,
        "env": {},
    }
    (config_dir / "config.json").write_text(json.dumps(config, indent=2))

    return config_dir


@pytest.fixture
def temp_claude_settings(tmp_path):
    """Create a temporary Claude settings directory."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    settings = {"hooks": {}}
    (claude_dir / "settings.json").write_text(json.dumps(settings, indent=2))

    return claude_dir


@pytest.fixture
def mock_config_paths(temp_config_dir, temp_claude_settings, monkeypatch):
    """Patch config paths to use temporary directories."""
    home_dir = temp_config_dir.parent

    # Patch config module functions
    monkeypatch.setattr("captain_hook.config.get_config_dir", lambda: temp_config_dir)
    monkeypatch.setattr("captain_hook.config.get_config_path", lambda: temp_config_dir / "config.json")
    monkeypatch.setattr("captain_hook.config.get_hooks_dir", lambda: temp_config_dir / "hooks")
    monkeypatch.setattr("captain_hook.config.get_runners_dir", lambda: temp_config_dir / "runners")
    monkeypatch.setattr("captain_hook.config.get_venv_dir", lambda: temp_config_dir / ".venv")
    monkeypatch.setattr("captain_hook.config.get_venv_python", lambda: temp_config_dir / ".venv" / "bin" / "python")
    monkeypatch.setattr("captain_hook.config.get_docs_dir", lambda: temp_config_dir / "docs")

    # Patch installer paths
    monkeypatch.setattr(
        "captain_hook.installer.get_user_settings_path",
        lambda: temp_claude_settings / "settings.json"
    )

    return {
        "config_dir": temp_config_dir,
        "claude_dir": temp_claude_settings,
        "home": home_dir,
    }


@pytest.fixture
def sample_hook(temp_config_dir):
    """Create a sample hook script."""
    def _create_hook(event: str, name: str, content: str = None, extension: str = ".py"):
        hook_dir = temp_config_dir / "hooks" / event
        hook_dir.mkdir(parents=True, exist_ok=True)

        if content is None:
            content = f'''#!/usr/bin/env python3
"""Sample hook: {name}"""
# DESCRIPTION: A test hook for {event}
import sys
import json
data = json.load(sys.stdin)
print(json.dumps({{"continue": True}}))
'''

        hook_path = hook_dir / f"{name}{extension}"
        hook_path.write_text(content)
        hook_path.chmod(0o755)
        return hook_path

    return _create_hook


@pytest.fixture
def sample_hooks(sample_hook):
    """Create multiple sample hooks for testing."""
    hooks = [
        ("pre_tool_use", "test-guard"),
        ("pre_tool_use", "file-validator"),
        ("post_tool_use", "logger"),
        ("stop", "cleanup"),
    ]

    created = []
    for event, name in hooks:
        path = sample_hook(event, name)
        created.append((event, name, path))

    return created


@pytest.fixture
def cli_runner():
    """Helper to run CLI commands and capture output."""
    import io
    import sys
    from contextlib import redirect_stdout, redirect_stderr

    class CLIRunner:
        def __init__(self):
            self.stdout = ""
            self.stderr = ""
            self.exit_code = 0

        def run(self, func, args=None):
            """Run a CLI function with captured output."""
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()

            try:
                with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                    if args is not None:
                        func(args)
                    else:
                        func()
                self.exit_code = 0
            except SystemExit as e:
                self.exit_code = e.code if e.code is not None else 0
            except Exception as e:
                self.stderr = str(e)
                self.exit_code = 1

            self.stdout = stdout_buffer.getvalue()
            self.stderr += stderr_buffer.getvalue()
            return self

    return CLIRunner()


@pytest.fixture
def mock_args():
    """Factory for creating mock argument objects."""
    class Args:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    return Args
