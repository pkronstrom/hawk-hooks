"""Tests for v2 dashboard auto-sync behavior."""

from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace

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

        def input(self, *args, **kwargs):
            return ""

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

if "simple_term_menu" not in sys.modules:
    simple_term_menu = types.ModuleType("simple_term_menu")

    class _TerminalMenuStub:  # pragma: no cover - test import shim
        def __init__(self, *args, **kwargs):
            pass

        def show(self):
            return None

    simple_term_menu.TerminalMenu = _TerminalMenuStub
    sys.modules["simple_term_menu"] = simple_term_menu

if "readchar" not in sys.modules:
    readchar = types.ModuleType("readchar")

    class _ReadcharKeys:  # pragma: no cover - test import shim
        ENTER = "\n"
        CTRL_C = "\x03"

    readchar.key = _ReadcharKeys()
    readchar.readkey = lambda: "\n"
    sys.modules["readchar"] = readchar

dashboard = importlib.import_module("hawk_hooks.v2_interactive.dashboard")

from hawk_hooks.types import SyncResult, Tool


def _minimal_state() -> dict:
    resolved = SimpleNamespace(skills=[], hooks=[], prompts=[], agents=[], mcp=[])
    return {
        "cfg": {"tools": {"codex": {"enabled": True, "multi_agent_consent": "ask"}}},
        "resolved_global": resolved,
        "resolved_active": resolved,
        "scope": "global",
        "project_dir": None,
        "contents": {},
        "tools_status": {tool: {"installed": False, "enabled": True} for tool in Tool.all()},
    }


def test_build_menu_options_has_no_manual_sync_entry():
    options = dashboard._build_menu_options(_minimal_state())
    assert not any(action == "sync" for _, action in options)
    assert any(action == "environment" for _, action in options)
    assert not any(action == "tools" for _, action in options)
    assert not any(action == "projects" for _, action in options)
    assert not any(action == "settings" for _, action in options)


def test_build_menu_options_shows_codex_setup_item_when_required():
    state = _minimal_state()
    state["resolved_active"].agents = ["architecture-reviewer.md"]
    state["codex_multi_agent_consent"] = "ask"
    state["codex_multi_agent_required"] = True

    options = dashboard._build_menu_options(state)
    assert any(action == "codex_multi_agent_setup" for _, action in options)


def test_build_menu_options_hides_codex_setup_item_when_not_required():
    state = _minimal_state()
    state["resolved_active"].agents = ["architecture-reviewer.md"]
    state["codex_multi_agent_consent"] = "denied"
    state["codex_multi_agent_required"] = False

    options = dashboard._build_menu_options(state)
    assert not any(action == "codex_multi_agent_setup" for _, action in options)


def test_codex_setup_prompt_sets_granted(monkeypatch):
    state = _minimal_state()
    state["resolved_active"].agents = ["architecture-reviewer.md"]
    state["codex_multi_agent_consent"] = "ask"

    monkeypatch.setattr(
        dashboard,
        "TerminalMenu",
        lambda *args, **kwargs: SimpleNamespace(show=lambda: 0),
    )

    saved_cfg: dict = {}

    def _save(cfg):
        saved_cfg.clear()
        saved_cfg.update(cfg)

    monkeypatch.setattr("hawk_hooks.v2_config.save_global_config", _save)

    changed = dashboard._handle_codex_multi_agent_setup(state)
    assert changed is True
    codex_cfg = saved_cfg["tools"]["codex"]
    assert codex_cfg["multi_agent_consent"] == "granted"
    assert codex_cfg["allow_multi_agent"] is True


def test_auto_sync_after_change_returns_clean_on_success(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "_sync_all_with_preflight",
        lambda scope_dir=None: {"global": [SyncResult(tool="claude")]},
    )
    monkeypatch.setattr(
        "hawk_hooks.v2_sync.format_sync_results",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr(dashboard, "wait_for_continue", lambda *_args, **_kwargs: None)

    dirty_after = dashboard._apply_auto_sync_if_needed(True)
    assert dirty_after is False


def test_auto_sync_after_change_keeps_dirty_on_errors(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "_sync_all_with_preflight",
        lambda scope_dir=None: {"global": [SyncResult(tool="codex", errors=["hooks: failed"])]},
    )
    monkeypatch.setattr(
        "hawk_hooks.v2_sync.format_sync_results",
        lambda *_args, **_kwargs: "error summary",
    )
    monkeypatch.setattr(dashboard, "wait_for_continue", lambda *_args, **_kwargs: None)

    dirty_after = dashboard._apply_auto_sync_if_needed(True)
    assert dirty_after is True
