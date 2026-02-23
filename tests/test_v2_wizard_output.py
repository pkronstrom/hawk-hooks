"""Wizard output tests that run without optional UI dependencies."""

from __future__ import annotations

import importlib
import sys
import types

import pytest

from hawk_hooks import v2_config


if "rich" not in sys.modules:
    rich_module = types.ModuleType("rich")
    rich_console = types.ModuleType("rich.console")
    rich_live = types.ModuleType("rich.live")
    rich_text = types.ModuleType("rich.text")

    class _ConsoleStub:
        def __init__(self, *args, **kwargs):
            pass

        def print(self, *args, **kwargs):
            return None

        def clear(self):
            return None

        def input(self, *args, **kwargs):
            return ""

    class _LiveStub:
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

    class _TextStub(str):
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

if "simple_term_menu" not in sys.modules:
    simple_term_menu = types.ModuleType("simple_term_menu")

    class _TerminalMenuStub:
        def __init__(self, *args, **kwargs):
            pass

        def show(self):
            return 0

    simple_term_menu.TerminalMenu = _TerminalMenuStub
    sys.modules["simple_term_menu"] = simple_term_menu

if "readchar" not in sys.modules:
    readchar = types.ModuleType("readchar")

    class _ReadcharKeys:
        ENTER = "\n"
        CTRL_C = "\x03"

    readchar.key = _ReadcharKeys()
    readchar.readkey = lambda: "\n"
    sys.modules["readchar"] = readchar

wizard = importlib.import_module("hawk_hooks.v2_interactive.wizard")


@pytest.fixture
def v2_env(tmp_path, monkeypatch):
    config_dir = tmp_path / "hawk-hooks"
    config_dir.mkdir()
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
    return config_dir


class _AdapterStub:
    def detect_installed(self):
        return False


def test_wizard_next_steps_do_not_recommend_manual_sync(v2_env, monkeypatch):
    printed: list[str] = []

    def _capture_print(*args, **kwargs):
        printed.append(" ".join(str(a) for a in args))

    monkeypatch.setattr(wizard, "get_adapter", lambda _tool: _AdapterStub())
    monkeypatch.setattr(wizard, "_offer_builtins_install", lambda: None)
    monkeypatch.setattr(
        wizard,
        "TerminalMenu",
        type("TerminalMenuStub", (), {"__init__": lambda self, *a, **k: None, "show": lambda self: 0}),
    )
    monkeypatch.setattr(wizard.console, "input", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(wizard.console, "print", _capture_print)

    assert wizard.run_wizard() is True

    output = "\n".join(printed)
    assert "hawk sync" not in output
