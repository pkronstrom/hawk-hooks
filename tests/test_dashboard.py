"""Tests for v2 dashboard auto-sync behavior."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
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

dashboard = importlib.import_module("hawk_hooks.interactive.dashboard")

from hawk_hooks.types import ComponentType, SyncResult, Tool


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


def test_build_menu_options_hides_sync_now_when_clean():
    options = dashboard._build_menu_options(_minimal_state())
    assert not any(action == "sync_now" for _, action in options)
    assert any(action == "environment" for _, action in options)
    assert not any(action == "registry" for _, action in options)
    assert not any(action == "tools" for _, action in options)
    assert not any(action == "projects" for _, action in options)
    assert not any(action == "settings" for _, action in options)


def test_build_menu_options_shows_sync_now_when_unsynced():
    state = _minimal_state()
    state["unsynced_targets"] = 3
    state["sync_targets_total"] = 6

    options = dashboard._build_menu_options(state)
    sync_rows = [(label, action) for label, action in options if action == "sync_now"]
    assert len(sync_rows) == 1
    assert "3 pending of 6" in sync_rows[0][0]


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


def test_build_menu_options_shows_missing_components_item_when_required():
    state = _minimal_state()
    state["missing_components_required"] = True
    state["missing_components_total"] = 3

    options = dashboard._build_menu_options(state)
    assert any(action == "resolve_missing_components" for _, action in options)


def test_missing_components_setup_lists_missing_names(monkeypatch):
    printed: list[str] = []

    def _capture_print(*args, **kwargs):
        if args and isinstance(args[0], str):
            printed.append(args[0])

    monkeypatch.setattr(dashboard.console, "print", _capture_print)
    monkeypatch.setattr(dashboard, "_find_package_lock_path", lambda _state: None)
    monkeypatch.setattr(
        dashboard,
        "TerminalMenu",
        lambda *args, **kwargs: SimpleNamespace(show=lambda: 2),
    )

    changed = dashboard._handle_missing_components_setup(
        {
            "missing_components": {
                "skills": ["python-core-reviewer.md"],
                "prompts": ["deploy.md"],
            },
            "missing_components_total": 2,
        }
    )
    assert changed is False
    rendered = "\n".join(printed)
    assert "python-core-reviewer.md" in rendered
    assert "deploy.md" in rendered


def test_confirm_registry_item_delete_requires_explicit_yes(monkeypatch):
    monkeypatch.setattr(dashboard.readchar, "readkey", lambda: "n")
    assert dashboard._confirm_registry_item_delete(ComponentType.SKILL, "demo.md") is False

    monkeypatch.setattr(dashboard.readchar, "readkey", lambda: "y")
    assert dashboard._confirm_registry_item_delete(ComponentType.SKILL, "demo.md") is True


def test_compute_missing_components_treats_mcp_yaml_as_present():
    resolved = SimpleNamespace(
        skills=["python-core-reviewer.md"],
        hooks=[],
        prompts=["deploy.md"],
        agents=[],
        mcp=["goose"],
    )
    contents = {
        ComponentType.SKILL: [],
        ComponentType.PROMPT: ["deploy.md"],
        ComponentType.MCP: ["goose.yaml"],
    }

    missing = dashboard._compute_missing_components(resolved, contents)
    assert missing == {"skills": ["python-core-reviewer.md"]}


def test_build_environment_menu_entries_includes_status_context(monkeypatch):
    state = _minimal_state()
    state["tools_status"] = {
        Tool.CLAUDE: {"enabled": True, "installed": True},
        Tool.GEMINI: {"enabled": False, "installed": True},
        Tool.CODEX: {"enabled": True, "installed": True},
        Tool.OPENCODE: {"enabled": True, "installed": False},
        Tool.CURSOR: {"enabled": False, "installed": False},
        Tool.ANTIGRAVITY: {"enabled": True, "installed": False},
    }
    state["cfg"] = {"sync_on_exit": "always"}
    state["codex_multi_agent_required"] = True
    state["missing_components_required"] = True
    monkeypatch.setattr("hawk_hooks.config.get_registered_directories", lambda: {"/tmp/p": {}})

    entries, title = dashboard._build_environment_menu_entries(state)

    assert entries[0].startswith("Tool Integrations")
    assert "4/6 enabled" in entries[0]
    assert "1 registered" in entries[1]
    assert "sync on exit: always" in entries[2]
    assert "(destructive)" in entries[3]
    assert "Pending one-time setup" in title


def test_handle_tools_toggle_prunes_when_disabling(monkeypatch):
    state = _minimal_state()
    tools = Tool.all()
    selected = tuple(i for i, tool in enumerate(tools) if tool != Tool.CLAUDE)

    monkeypatch.setattr(
        dashboard,
        "TerminalMenu",
        lambda *args, **kwargs: SimpleNamespace(show=lambda: selected),
    )

    saved_cfg: dict = {}

    def _save(cfg):
        saved_cfg.clear()
        saved_cfg.update(cfg)

    pruned: list[list[Tool]] = []
    monkeypatch.setattr("hawk_hooks.config.save_global_config", _save)
    monkeypatch.setattr(dashboard, "_prune_disabled_tools", lambda ds: pruned.append(ds))

    changed = dashboard._handle_tools_toggle(state)

    assert changed is True
    assert state["tools_status"][Tool.CLAUDE]["enabled"] is False
    assert saved_cfg["tools"]["claude"]["enabled"] is False
    assert pruned == [[Tool.CLAUDE]]


def test_handle_tools_toggle_no_prune_when_only_enabling(monkeypatch):
    state = _minimal_state()
    state["tools_status"][Tool.CLAUDE]["enabled"] = False
    state["cfg"]["tools"]["claude"] = {"enabled": False}
    selected = tuple(range(len(Tool.all())))

    monkeypatch.setattr(
        dashboard,
        "TerminalMenu",
        lambda *args, **kwargs: SimpleNamespace(show=lambda: selected),
    )

    pruned: list[list[Tool]] = []
    monkeypatch.setattr("hawk_hooks.config.save_global_config", lambda _cfg: None)
    monkeypatch.setattr(dashboard, "_prune_disabled_tools", lambda ds: pruned.append(ds))

    changed = dashboard._handle_tools_toggle(state)

    assert changed is True
    assert state["tools_status"][Tool.CLAUDE]["enabled"] is True
    assert pruned == []


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

    monkeypatch.setattr("hawk_hooks.config.save_global_config", _save)

    changed = dashboard._handle_codex_multi_agent_setup(state)
    assert changed is True
    codex_cfg = saved_cfg["tools"]["codex"]
    assert codex_cfg["multi_agent_consent"] == "granted"
    assert codex_cfg["allow_multi_agent"] is True


def test_auto_sync_after_change_returns_clean_on_success(monkeypatch):
    calls: list[tuple[str | None, bool]] = []

    def _fake_sync(scope_dir=None, force=False):
        calls.append((scope_dir, force))
        return {"global": [SyncResult(tool="claude")]}

    monkeypatch.setattr(
        dashboard,
        "_sync_all_with_preflight",
        _fake_sync,
    )
    monkeypatch.setattr(
        "hawk_hooks.sync.format_sync_results",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr(dashboard, "wait_for_continue", lambda *_args, **_kwargs: None)

    dirty_after = dashboard._apply_auto_sync_if_needed(True)
    assert calls == [(None, False)]
    assert dirty_after is False


def test_auto_sync_after_change_keeps_dirty_on_errors(monkeypatch):
    calls: list[tuple[str | None, bool]] = []

    def _fake_sync(scope_dir=None, force=False):
        calls.append((scope_dir, force))
        return {"global": [SyncResult(tool="codex", errors=["hooks: failed"])]}

    monkeypatch.setattr(
        dashboard,
        "_sync_all_with_preflight",
        _fake_sync,
    )
    monkeypatch.setattr(
        "hawk_hooks.sync.format_sync_results",
        lambda *_args, **_kwargs: "error summary",
    )
    monkeypatch.setattr(dashboard, "wait_for_continue", lambda *_args, **_kwargs: None)

    dirty_after = dashboard._apply_auto_sync_if_needed(True)
    assert calls == [(None, False)]
    assert dirty_after is True


def test_handle_sync_uses_force_true(monkeypatch):
    calls: list[tuple[str | None, bool]] = []

    def _fake_sync(scope_dir=None, force=False):
        calls.append((scope_dir, force))
        return {"global": [SyncResult(tool="claude")]}

    monkeypatch.setattr(dashboard, "_sync_all_with_preflight", _fake_sync)
    monkeypatch.setattr("hawk_hooks.sync.format_sync_results", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(dashboard, "wait_for_continue", lambda *_args, **_kwargs: None)

    dashboard._handle_sync({"scope_dir": "/tmp/demo"})
    assert calls == [("/tmp/demo", True)]


def test_run_dashboard_dispatches_sync_now(monkeypatch):
    first_state = _minimal_state()
    first_state["unsynced_targets"] = 2
    first_state["sync_targets_total"] = 3

    second_state = _minimal_state()
    second_state["unsynced_targets"] = 0
    second_state["sync_targets_total"] = 3

    states = [first_state, second_state]

    def _fake_load(_scope_dir=None):
        if states:
            return states.pop(0)
        return second_state

    calls: list[dict] = []

    def _fake_handle_sync(state):
        calls.append(state)

    selections = [9, None]  # Sync now row index for default menu layout

    monkeypatch.setattr(dashboard, "_load_state", _fake_load)
    monkeypatch.setattr(dashboard, "_handle_sync", _fake_handle_sync)
    monkeypatch.setattr(dashboard, "_run_main_menu", lambda *_args, **_kwargs: selections.pop(0))
    monkeypatch.setattr(dashboard, "set_project_theme", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard, "_prompt_sync_on_exit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard.console, "clear", lambda: None)

    dashboard.run_dashboard()

    assert len(calls) == 1
    assert calls[0]["unsynced_targets"] == 2


def test_delete_project_scope_unregisters_and_keeps_local_hawk(tmp_path, monkeypatch):
    project = tmp_path / "demo"
    project.mkdir()
    hawk_dir = project / ".hawk"
    hawk_dir.mkdir()
    (hawk_dir / "config.yaml").write_text("skills: {}\n")

    calls: list[Path] = []

    def _unregister(path: Path):
        calls.append(path)

    monkeypatch.setattr("hawk_hooks.config.unregister_directory", _unregister)

    ok, _msg = dashboard._delete_project_scope(project, delete_local_hawk=False)
    assert ok is True
    assert calls == [project.resolve()]
    assert (project / ".hawk" / "config.yaml").exists()


def test_delete_project_scope_can_remove_local_hawk_dir(tmp_path, monkeypatch):
    project = tmp_path / "demo"
    project.mkdir()
    hawk_dir = project / ".hawk"
    hawk_dir.mkdir()
    (hawk_dir / "config.yaml").write_text("skills: {}\n")

    monkeypatch.setattr("hawk_hooks.config.unregister_directory", lambda _path: None)

    ok, _msg = dashboard._delete_project_scope(project, delete_local_hawk=True)
    assert ok is True
    assert not hawk_dir.exists()
