"""Toggle list component with scope switching.

Renders a Rich Live panel with checkboxes for registry items.
Supports Tab to switch between Global and Local scopes.
"""

from __future__ import annotations

import os
from pathlib import Path

import readchar
from rich.console import Console
from rich.live import Live
from rich.text import Text

console = Console()

# Actions appended after the item list
ACTION_SELECT_ALL = "__select_all__"
ACTION_SELECT_NONE = "__select_none__"
ACTION_SWITCH_SCOPE = "__switch_scope__"
ACTION_DONE = "__done__"


def _get_terminal_height() -> int:
    try:
        return os.get_terminal_size().lines
    except OSError:
        return 24


def _calculate_visible_range(
    cursor: int, total: int, max_visible: int, scroll_offset: int
) -> tuple[int, int, int]:
    """Calculate visible range for scrolling list."""
    if total == 0:
        return 0, 0, 0
    cursor = max(0, min(cursor, total - 1))
    if cursor < scroll_offset:
        scroll_offset = cursor
    elif cursor >= scroll_offset + max_visible:
        scroll_offset = cursor - max_visible + 1
    scroll_offset = max(0, min(scroll_offset, total - 1))
    visible_end = min(scroll_offset + max_visible, total)
    return scroll_offset, scroll_offset, visible_end


def run_toggle_list(
    component_type: str,
    registry_names: list[str],
    global_enabled: list[str],
    local_enabled: list[str] | None,
    project_name: str | None,
    start_scope: str = "local",
) -> tuple[list[str], list[str] | None, bool]:
    """Run an interactive toggle list for a component type.

    Args:
        component_type: Display name (e.g. "Skills", "Hooks")
        registry_names: All items in registry for this type
        global_enabled: Currently globally enabled items
        local_enabled: Currently locally enabled items (None if no local scope)
        project_name: Short project name for display (None if no local scope)
        start_scope: "global" or "local"

    Returns:
        Tuple of (new_global_enabled, new_local_enabled, changed)
        new_local_enabled is None if no local scope.
    """
    if not registry_names:
        _show_empty(component_type, project_name, start_scope)
        return global_enabled, local_enabled, False

    # Mutable state
    global_checked = set(global_enabled)
    local_checked = set(local_enabled) if local_enabled is not None else None
    scope = start_scope if local_checked is not None else "global"
    cursor = 0
    scroll_offset = 0
    changed = False

    # Build the full list: items + separator + actions
    items = list(registry_names)
    has_local = local_checked is not None

    def _get_actions() -> list[tuple[str, str]]:
        actions = [
            ("Select All", ACTION_SELECT_ALL),
            ("Select None", ACTION_SELECT_NONE),
        ]
        if has_local:
            if scope == "local":
                actions.append((f"Switch to \U0001f310 Global", ACTION_SWITCH_SCOPE))
            else:
                label = f"Switch to \U0001f4cd Local: {project_name}"
                actions.append((label, ACTION_SWITCH_SCOPE))
        actions.append(("Done", ACTION_DONE))
        return actions

    def _total_rows() -> int:
        return len(items) + 1 + len(_get_actions())  # items + separator + actions

    def _is_separator(idx: int) -> bool:
        return idx == len(items)

    def _is_action(idx: int) -> bool:
        return idx > len(items)

    def _action_id(idx: int) -> str:
        action_idx = idx - len(items) - 1
        actions = _get_actions()
        if 0 <= action_idx < len(actions):
            return actions[action_idx][1]
        return ""

    def _checked_set() -> set[str]:
        return local_checked if scope == "local" and local_checked is not None else global_checked

    def _build_display() -> str:
        """Build the display string for Rich."""
        lines: list[str] = []

        # Header
        if scope == "local" and project_name:
            scope_label = f"\U0001f4cd Local: {project_name}"
            tab_hint = "[Tab: switch to \U0001f310 Global]"
        else:
            scope_label = "\U0001f310 Global"
            tab_hint = f"[Tab: switch to \U0001f4cd Local]" if has_local else ""

        lines.append(f"[bold]{component_type}[/bold] \u2014 {scope_label}    [dim]{tab_hint}[/dim]")
        lines.append("[dim]\u2500" * 50 + "[/dim]")

        total = _total_rows()
        max_visible = _get_terminal_height() - 6  # header + footer margins
        _, vis_start, vis_end = _calculate_visible_range(cursor, total, max_visible, scroll_offset)

        checked = _checked_set()

        # Scroll indicator (above)
        if vis_start > 0:
            lines.append(f"[dim]  \u2191 {vis_start} more[/dim]")

        for i in range(vis_start, vis_end):
            is_cur = i == cursor
            prefix = "[cyan]\u276f[/cyan] " if is_cur else "  "

            if i < len(items):
                # Item row
                name = items[i]
                mark = "[green]\u2714[/green]" if name in checked else "[dim]\u2610[/dim]"
                style = "[bold]" if is_cur else ""
                end_style = "[/bold]" if is_cur else ""
                lines.append(f"{prefix}{mark} {style}{name}{end_style}")
            elif _is_separator(i):
                lines.append("  [dim]\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500[/dim]")
            elif _is_action(i):
                action_idx = i - len(items) - 1
                actions = _get_actions()
                if 0 <= action_idx < len(actions):
                    label = actions[action_idx][0]
                    style = "[cyan bold]" if is_cur else "[dim]"
                    end = "[/cyan bold]" if is_cur else "[/dim]"
                    lines.append(f"{prefix}{style}{label}{end}")

        # Scroll indicator (below)
        if vis_end < total:
            remaining = total - vis_end
            lines.append(f"[dim]  \u2193 {remaining} more[/dim]")

        # Footer
        lines.append("")
        lines.append("[dim]Space: toggle  \u2191\u2193/jk: navigate  Enter: done  q: cancel[/dim]")

        return "\n".join(lines)

    # Main loop
    with Live("", console=console, refresh_per_second=15, transient=True) as live:
        live.update(Text.from_markup(_build_display()))
        while True:
            try:
                key = readchar.readkey()
            except (KeyboardInterrupt, EOFError):
                break

            total = _total_rows()

            # Navigation
            if key in (readchar.key.UP, "k"):
                cursor = (cursor - 1) % total
                # Skip separator
                if _is_separator(cursor):
                    cursor = (cursor - 1) % total
            elif key in (readchar.key.DOWN, "j"):
                cursor = (cursor + 1) % total
                if _is_separator(cursor):
                    cursor = (cursor + 1) % total

            # Toggle
            elif key == " ":
                if cursor < len(items):
                    name = items[cursor]
                    checked = _checked_set()
                    if name in checked:
                        checked.discard(name)
                    else:
                        checked.add(name)
                    changed = True
                elif _is_action(cursor):
                    aid = _action_id(cursor)
                    if aid == ACTION_SELECT_ALL:
                        _checked_set().update(items)
                        changed = True
                    elif aid == ACTION_SELECT_NONE:
                        _checked_set().clear()
                        changed = True
                    elif aid == ACTION_SWITCH_SCOPE:
                        scope = "local" if scope == "global" else "global"
                    elif aid == ACTION_DONE:
                        break

            # Enter on actions
            elif key in ("\r", "\n", readchar.key.ENTER):
                if _is_action(cursor):
                    aid = _action_id(cursor)
                    if aid == ACTION_SELECT_ALL:
                        _checked_set().update(items)
                        changed = True
                    elif aid == ACTION_SELECT_NONE:
                        _checked_set().clear()
                        changed = True
                    elif aid == ACTION_SWITCH_SCOPE:
                        scope = "local" if scope == "global" else "global"
                    elif aid == ACTION_DONE:
                        break
                else:
                    # Enter on item = done
                    break

            # Tab = switch scope
            elif key == "\t":
                if has_local:
                    scope = "local" if scope == "global" else "global"

            # Quit
            elif key in ("q", "\x1b"):
                break

            live.update(Text.from_markup(_build_display()))

    new_global = sorted(global_checked)
    new_local = sorted(local_checked) if local_checked is not None else None
    return new_global, new_local, changed


def _show_empty(component_type: str, project_name: str | None, scope: str) -> None:
    """Show empty state for a component type."""
    if scope == "local" and project_name:
        scope_label = f"\U0001f4cd Local: {project_name}"
    else:
        scope_label = "\U0001f310 Global"

    console.print(f"\n[bold]{component_type}[/bold] \u2014 {scope_label}")
    console.print("[dim]\u2500" * 40 + "[/dim]")
    console.print("  [dim](none in registry)[/dim]")
    console.print(f"\n  Run [cyan]hawk download <url>[/cyan] to add {component_type.lower()}.")
    console.print()
    console.input("[dim]Press Enter to continue...[/dim]")
