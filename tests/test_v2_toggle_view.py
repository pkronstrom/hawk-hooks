"""Tests for TUI viewer width/wrapping helpers."""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

if "rich" not in sys.modules:
    rich_module = types.ModuleType("rich")
    rich_console = types.ModuleType("rich.console")
    rich_live = types.ModuleType("rich.live")
    rich_text = types.ModuleType("rich.text")

    class _ConsoleStub:  # pragma: no cover - test import shim
        def __init__(self, *args, **kwargs):
            pass

        def print(self, *args, **kwargs):
            return None

        def clear(self):
            return None

    class _LiveStub:  # pragma: no cover - test import shim
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def update(self, *args, **kwargs):
            return None

        def stop(self):
            return None

        def start(self):
            return None

    class _TextStub(str):  # pragma: no cover - test import shim
        @classmethod
        def from_markup(cls, value):
            return cls(value)

    rich_console.Console = _ConsoleStub
    rich_live.Live = _LiveStub
    rich_text.Text = _TextStub
    rich_module.console = rich_console
    rich_module.live = rich_live
    rich_module.text = rich_text
    sys.modules["rich"] = rich_module
    sys.modules["rich.console"] = rich_console
    sys.modules["rich.live"] = rich_live
    sys.modules["rich.text"] = rich_text

if "readchar" not in sys.modules:
    readchar = types.ModuleType("readchar")

    class _ReadcharKeys:  # pragma: no cover - test import shim
        ENTER = "\n"
        UP = "up"
        DOWN = "down"
        CTRL_C = "\x03"

    readchar.key = _ReadcharKeys()
    readchar.readkey = lambda: "\n"
    sys.modules["readchar"] = readchar

if "simple_term_menu" not in sys.modules:
    simple_term_menu = types.ModuleType("simple_term_menu")

    class _TerminalMenuStub:  # pragma: no cover - test import shim
        def __init__(self, *args, **kwargs):
            self.chosen_accept_key = "enter"

        def show(self):
            return None

    simple_term_menu.TerminalMenu = _TerminalMenuStub
    sys.modules["simple_term_menu"] = simple_term_menu

from hawk_hooks.v2_interactive import toggle


def test_get_view_wrap_width_defaults_and_clamps_to_terminal(monkeypatch):
    monkeypatch.delenv("HAWK_VIEW_WIDTH", raising=False)
    monkeypatch.setattr(toggle.os, "get_terminal_size", lambda: os.terminal_size((140, 40)))
    assert toggle._get_view_wrap_width() == 100

    monkeypatch.setattr(toggle.os, "get_terminal_size", lambda: os.terminal_size((80, 40)))
    assert toggle._get_view_wrap_width() == 78


def test_get_view_wrap_width_respects_env_and_bounds(monkeypatch):
    monkeypatch.setattr(toggle.os, "get_terminal_size", lambda: os.terminal_size((120, 40)))

    monkeypatch.setenv("HAWK_VIEW_WIDTH", "72")
    assert toggle._get_view_wrap_width() == 72

    monkeypatch.setenv("HAWK_VIEW_WIDTH", "20")
    assert toggle._get_view_wrap_width() == toggle.MIN_VIEW_WIDTH

    monkeypatch.setenv("HAWK_VIEW_WIDTH", "500")
    assert toggle._get_view_wrap_width() == 118

    monkeypatch.setenv("HAWK_VIEW_WIDTH", "not-a-number")
    assert toggle._get_view_wrap_width() == 100


def test_get_item_description_prefers_frontmatter_description(tmp_path: Path):
    item = tmp_path / "claude.md"
    item.write_text(
        "---\n"
        "name: claude\n"
        "description: Leverage Anthropic Claude models for autonomous code implementation.\n"
        "tools: [claude]\n"
        "---\n"
        "# Claude\n\n"
        "Body text.\n"
    )

    desc = toggle._get_item_description(item, "prompts")
    assert desc == "Leverage Anthropic Claude models for autonomous code implementation."


def test_get_item_description_reads_hook_comment_metadata(tmp_path: Path):
    item = tmp_path / "guard.py"
    item.write_text(
        "# hawk-hook: events=pre_tool_use,stop\n"
        "# hawk-hook: description=Blocks dangerous shell operations\n"
        "print('ok')\n"
    )

    desc = toggle._get_item_description(item, "hooks")
    assert desc == "Blocks dangerous shell operations"


def test_get_item_description_reads_mcp_command_summary(tmp_path: Path):
    item = tmp_path / "goose.yaml"
    item.write_text(
        "command: npx\n"
        "args:\n"
        "  - -y\n"
        "  - \"@modelcontextprotocol/server-github\"\n"
        "env:\n"
        "  GITHUB_TOKEN: test\n"
    )

    desc = toggle._get_item_description(item, "mcp")
    assert "MCP command: npx -y @modelcontextprotocol/server-github." in desc
    assert "Env vars: 1." in desc


def test_get_item_description_uses_skill_markdown_body_when_no_frontmatter(tmp_path: Path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# My Skill\n\n"
        "Use this skill to generate clean API scaffolding.\n"
    )

    desc = toggle._get_item_description(skill_dir, "skills")
    assert desc == "Use this skill to generate clean API scaffolding."
