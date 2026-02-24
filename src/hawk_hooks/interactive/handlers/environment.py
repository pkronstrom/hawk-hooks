"""Environment handlers for the dashboard."""

from __future__ import annotations

from ... import config
from ...types import Tool
from .. import dashboard as _dashboard

console = _dashboard.console


def TerminalMenu(*args, **kwargs):
    return _dashboard.TerminalMenu(*args, **kwargs)


def terminal_menu_style_kwargs(*args, **kwargs):
    return _dashboard.terminal_menu_style_kwargs(*args, **kwargs)


def wait_for_continue(*args, **kwargs):
    return _dashboard.wait_for_continue(*args, **kwargs)


def _handle_projects(*args, **kwargs):
    return _dashboard._handle_projects(*args, **kwargs)


def run_uninstall_wizard(*args, **kwargs):
    return _dashboard.run_uninstall_wizard(*args, **kwargs)

def _handle_tools_toggle(state: dict) -> bool:
    """Toggle tool enable/disable."""
    options = []
    tool_list = Tool.all()
    for tool in tool_list:
        ts = state["tools_status"][tool]
        installed = "installed" if ts["installed"] else "not found"
        options.append(f"{tool:<12} ({installed})")

    preselected = [
        i for i, tool in enumerate(tool_list)
        if state["tools_status"][tool]["enabled"]
    ]

    menu = TerminalMenu(
        options,
        title="\nTools \u2014 toggle which tools hawk syncs to:",
        multi_select=True,
        preselected_entries=preselected,
        multi_select_select_on_accept=False,
        multi_select_cursor="(\u25cf) ",
        multi_select_cursor_brackets_style=("fg_green",),
        multi_select_cursor_style=("fg_green",),
        menu_cursor="\u203a ",
        **terminal_menu_style_kwargs(include_status_bar=True),
        quit_keys=("q", "\x1b"),
        status_bar="space toggle · \u21b5 confirm · q/esc back",
    )
    result = menu.show()
    if result is None:
        return False

    selected = set(result) if isinstance(result, tuple) else {result}
    changed = False
    disabled_tools: list[Tool] = []
    cfg = state["cfg"]
    tools_cfg = cfg.get("tools", {})

    for i, tool in enumerate(tool_list):
        new_enabled = i in selected
        old_enabled = state["tools_status"][tool]["enabled"]
        if new_enabled != old_enabled:
            changed = True
            if old_enabled and not new_enabled:
                disabled_tools.append(tool)
            tool_key = str(tool)
            if tool_key not in tools_cfg:
                tools_cfg[tool_key] = {}
            tools_cfg[tool_key]["enabled"] = new_enabled
            state["tools_status"][tool]["enabled"] = new_enabled

    if changed:
        cfg["tools"] = tools_cfg
        config.save_global_config(cfg)
        if disabled_tools:
            _dashboard._prune_disabled_tools(disabled_tools)

    return changed


def _prune_disabled_tools(disabled_tools: list[Tool]) -> None:
    """Opinionated cleanup for disabled tools (no clean/prune choice in TUI)."""
    if not disabled_tools:
        return

    from ...sync import format_sync_results, purge_all

    tool_labels = ", ".join(str(tool) for tool in disabled_tools)
    console.print(f"\n[bold]Cleaning disabled tool integrations:[/bold] {tool_labels}")
    all_results = purge_all(tools=disabled_tools)
    formatted = format_sync_results(all_results, verbose=False)
    console.print(formatted or "  No changes.")
    console.print()
    wait_for_continue()


def _handle_uninstall_from_environment() -> bool:
    """Run unlink + uninstall flow from Environment menu."""
    return run_uninstall_wizard(console)


def _build_environment_menu_entries(state: dict) -> tuple[list[str], str]:
    """Build Environment submenu entries + title with lightweight status context."""
    tools_total = len(Tool.all())
    tools_enabled = sum(
        1
        for tool_state in state.get("tools_status", {}).values()
        if tool_state.get("enabled", True)
    )
    scopes_count = len(config.get_registered_directories())
    sync_pref = str((state.get("cfg") or {}).get("sync_on_exit", "ask"))

    entries = [
        f"Tool Integrations  {tools_enabled}/{tools_total} enabled",
        f"Project Scopes     {scopes_count} registered",
        f"Preferences        sync on exit: {sync_pref}",
        "Unlink and uninstall  (destructive)",
        "Back",
    ]

    pending: list[str] = []
    if state.get("codex_multi_agent_required", False):
        pending.append("codex setup")
    if state.get("missing_components_required", False):
        pending.append("missing components")

    title = "\nEnvironment\nManage tools, scopes, and preferences"
    if pending:
        title += f"\nPending one-time setup: {', '.join(pending)}"
    return entries, title


def handle_tools_toggle(state: dict) -> bool:
    """Toggle tool enable/disable."""
    return _handle_tools_toggle(state)


def prune_disabled_tools(disabled_tools: list[Tool]) -> None:
    """Opinionated cleanup for disabled tools (no clean/prune choice in TUI)."""
    _prune_disabled_tools(disabled_tools)


def handle_uninstall_from_environment() -> bool:
    """Run unlink + uninstall flow from Environment menu."""
    return _handle_uninstall_from_environment()


def build_environment_menu_entries(state: dict) -> tuple[list[str], str]:
    """Build Environment submenu entries + title with lightweight status context."""
    return _build_environment_menu_entries(state)


def handle_environment(state: dict) -> bool:
    """Environment submenu (tools, projects, preferences, uninstall)."""
    changed = False

    while True:
        # Clear transient output from submenu actions before re-rendering menu.
        console.clear()
        menu_entries, menu_title = _build_environment_menu_entries(state)
        menu = TerminalMenu(
            menu_entries,
            title=menu_title,
            cursor_index=0,
            menu_cursor="\u203a ",
            **terminal_menu_style_kwargs(include_status_bar=True),
            accept_keys=("enter", " "),
            quit_keys=("q", "\x1b"),
            status_bar="space/\u21b5 select · q/esc back",
        )
        choice = menu.show()
        if choice is None or choice == 4:
            break

        if choice == 0:
            if _handle_tools_toggle(state):
                changed = True
        elif choice == 1:
            _handle_projects(state)
        elif choice == 2:
            from ..config_editor import run_config_editor

            if run_config_editor():
                changed = True
        elif choice == 3:
            if _handle_uninstall_from_environment():
                changed = True

    return changed
