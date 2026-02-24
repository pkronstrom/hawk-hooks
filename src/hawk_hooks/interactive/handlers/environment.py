"""Environment handlers for the dashboard."""

from __future__ import annotations

import readchar
from rich.live import Live
from rich.text import Text

from ... import config
from ...types import Tool
from .. import dashboard as _dashboard
from ..pause import wait_for_continue
from ..theme import (
    action_style,
    cursor_prefix,
    dim_separator,
    keybinding_hint,
    warning_style,
)
from ..uninstall_flow import run_uninstall_wizard

console = _dashboard.console


# ---------------------------------------------------------------------------
# Tools toggle (multi-select with Rich Live)
# ---------------------------------------------------------------------------


def _handle_tools_toggle(state: dict) -> bool:
    """Toggle tool enable/disable with a Rich Live multi-select menu."""
    tool_list = Tool.all()
    selected: set[int] = {
        i for i, tool in enumerate(tool_list)
        if state["tools_status"][tool]["enabled"]
    }
    cursor = 0
    total = len(tool_list) + 2  # tools + separator + Done

    def _build_display() -> str:
        lines: list[str] = []
        lines.append("[bold]Tools[/bold] — toggle which tools hawk syncs to")
        lines.append(dim_separator())

        for i, tool in enumerate(tool_list):
            is_cur = i == cursor
            prefix = cursor_prefix(is_cur)
            ts = state["tools_status"][tool]
            installed = "installed" if ts["installed"] else "not found"
            check = "[green]●[/green]" if i in selected else "[dim]○[/dim]"
            name_style = "[bold]" if is_cur else ""
            name_end = "[/bold]" if is_cur else ""
            lines.append(f"{prefix}{check} {name_style}{tool:<12}{name_end} [dim]({installed})[/dim]")

        sep_idx = len(tool_list)
        done_idx = sep_idx + 1
        lines.append(f"  {dim_separator(9)}")
        is_done_cur = cursor == done_idx
        style, end = action_style(is_done_cur)
        lines.append(f"{cursor_prefix(is_done_cur)}{style}Done{end}")

        lines.append("")
        lines.append(keybinding_hint(["space toggle", "↵ confirm"]))
        return "\n".join(lines)

    sep_idx = len(tool_list)
    done_idx = sep_idx + 1

    with Live("", console=console, refresh_per_second=15, transient=True) as live:
        live.update(Text.from_markup(_build_display()))
        while True:
            try:
                key = readchar.readkey()
            except (KeyboardInterrupt, EOFError):
                return False

            if key in (readchar.key.UP, "k"):
                cursor = (cursor - 1) % total
                if cursor == sep_idx:
                    cursor = (cursor - 1) % total
            elif key in (readchar.key.DOWN, "j"):
                cursor = (cursor + 1) % total
                if cursor == sep_idx:
                    cursor = (cursor + 1) % total

            elif key == " ":
                if cursor < len(tool_list):
                    if cursor in selected:
                        selected.discard(cursor)
                    else:
                        selected.add(cursor)

            elif key in ("\r", "\n", readchar.key.ENTER):
                if cursor == done_idx:
                    break
                # On items, toggle
                if cursor < len(tool_list):
                    if cursor in selected:
                        selected.discard(cursor)
                    else:
                        selected.add(cursor)

            elif key in ("q", "\x1b"):
                return False

            live.update(Text.from_markup(_build_display()))

    # Apply changes
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
            _prune_disabled_tools(disabled_tools)

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


# ---------------------------------------------------------------------------
# Environment submenu (Rich Live)
# ---------------------------------------------------------------------------

_ENV_ACTIONS = ["tools", "projects", "preferences", "uninstall", "back"]


def _build_environment_entries(state: dict) -> list[tuple[str, str]]:
    """Build Environment submenu entries as (label, action) pairs."""
    tools_total = len(Tool.all())
    tools_enabled = sum(
        1
        for tool_state in state.get("tools_status", {}).values()
        if tool_state.get("enabled", True)
    )
    scopes_count = len(config.get_registered_directories())
    sync_pref = str((state.get("cfg") or {}).get("sync_on_exit", "ask"))

    entries: list[tuple[str, str]] = [
        (f"Tool Integrations  {tools_enabled}/{tools_total} enabled", "tools"),
        (f"Project Scopes     {scopes_count} registered", "projects"),
        (f"Preferences        sync on exit: {sync_pref}", "preferences"),
    ]
    return entries


def _build_environment_menu_entries(state: dict) -> tuple[list[str], str]:
    """Build Environment submenu entries + title (legacy compat for dashboard)."""
    entries = _build_environment_entries(state)
    labels = [e[0] for e in entries] + ["Unlink and uninstall  (destructive)", "Back"]

    pending: list[str] = []
    if state.get("codex_multi_agent_required", False):
        pending.append("codex setup")
    if state.get("missing_components_required", False):
        pending.append("missing components")

    title = "\nEnvironment\nManage tools, scopes, and preferences"
    if pending:
        title += f"\nPending one-time setup: {', '.join(pending)}"
    return labels, title


def handle_environment(state: dict) -> bool:
    """Environment submenu (tools, projects, preferences, uninstall)."""
    changed = False
    cursor = 0

    while True:
        entries = _build_environment_entries(state)
        # Full menu: entries + separator + uninstall + separator + Back
        total = len(entries) + 4  # entries... sep, uninstall, sep, Back
        sep1_idx = len(entries)
        uninstall_idx = sep1_idx + 1
        sep2_idx = uninstall_idx + 1
        back_idx = sep2_idx + 1

        def _build_display() -> str:
            lines: list[str] = []
            lines.append("[bold]Environment[/bold]")
            lines.append("[dim]Manage tools, scopes, and preferences[/dim]")
            lines.append(dim_separator())

            for i, (label, _action) in enumerate(entries):
                is_cur = i == cursor
                prefix = cursor_prefix(is_cur)
                style, end = action_style(is_cur)
                lines.append(f"{prefix}{style}{label}{end}")

            # Separator
            lines.append(f"  {dim_separator(9)}")

            # Uninstall (warning style)
            is_cur = cursor == uninstall_idx
            prefix = cursor_prefix(is_cur)
            style, end = warning_style(is_cur)
            lines.append(f"{prefix}{style}Unlink and uninstall{end}")

            # Separator
            lines.append(f"  {dim_separator(9)}")

            # Back
            is_cur = cursor == back_idx
            style, end = action_style(is_cur)
            lines.append(f"{cursor_prefix(is_cur)}{style}Back{end}")

            lines.append("")
            lines.append(keybinding_hint(["space/↵ select"], include_nav=True))
            return "\n".join(lines)

        skip_indices = {sep1_idx, sep2_idx}

        def _move(direction: int) -> None:
            nonlocal cursor
            for _ in range(total):
                cursor = (cursor + direction) % total
                if cursor not in skip_indices:
                    return

        with Live("", console=console, refresh_per_second=15, transient=True) as live:
            live.update(Text.from_markup(_build_display()))
            while True:
                try:
                    key = readchar.readkey()
                except (KeyboardInterrupt, EOFError):
                    return changed

                action = None

                if key in (readchar.key.UP, "k"):
                    _move(-1)
                elif key in (readchar.key.DOWN, "j"):
                    _move(1)
                elif key in (" ", "\r", "\n", readchar.key.ENTER):
                    if cursor < len(entries):
                        action = entries[cursor][1]
                    elif cursor == uninstall_idx:
                        action = "uninstall"
                    elif cursor == back_idx:
                        action = "back"
                elif key in ("q", "\x1b"):
                    action = "back"

                if action == "back":
                    return changed

                if action == "tools":
                    live.stop()
                    console.clear()
                    if _handle_tools_toggle(state):
                        changed = True
                    console.clear()
                    live.start()
                    break  # Re-render outer loop (counts may have changed)

                if action == "projects":
                    live.stop()
                    console.clear()
                    _dashboard._handle_projects(state)
                    console.clear()
                    live.start()
                    break

                if action == "preferences":
                    live.stop()
                    console.clear()
                    from ..config_editor import run_config_editor
                    if run_config_editor():
                        changed = True
                    console.clear()
                    live.start()
                    break

                if action == "uninstall":
                    live.stop()
                    console.clear()
                    if _handle_uninstall_from_environment():
                        changed = True
                    console.clear()
                    live.start()
                    break

                live.update(Text.from_markup(_build_display()))

    return changed


# Public API wrappers for backward compat with dashboard imports
handle_tools_toggle = _handle_tools_toggle
prune_disabled_tools = _prune_disabled_tools
handle_uninstall_from_environment = _handle_uninstall_from_environment
build_environment_menu_entries = _build_environment_menu_entries
