"""Toggle list component with N-scope switching.

Renders a Rich Live panel with checkboxes for registry items.
Supports Tab to cycle through arbitrary number of scopes (global, parent dirs, local).
Shows change indicators (yellow) for items modified since the list opened.
Shows "(enabled in <parent>)" hints when viewing inner scopes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import readchar
from rich.console import Console
from rich.live import Live
from rich.text import Text

console = Console()

# Actions appended after the item list
ACTION_SELECT_ALL = "__select_all__"
ACTION_SELECT_NONE = "__select_none__"
ACTION_ADD = "__add__"
ACTION_DONE = "__done__"


@dataclass
class ToggleScope:
    """A scope layer for the toggle list."""

    key: str  # "global" or absolute dir path
    label: str  # "All projects" / "monorepo" / "This project: frontend"
    enabled: list[str]  # currently enabled items in this scope
    is_new: bool = False  # True if config doesn't exist yet (will be created on save)


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


def _resolve_item_path(registry_path: Path, registry_dir: str, name: str) -> Path | None:
    """Resolve the filesystem path of a registry item."""
    item_path = registry_path / registry_dir / name
    if item_path.exists():
        return item_path
    return None


SYNTAX_LEXERS = {
    ".py": "python",
    ".sh": "bash",
    ".js": "javascript",
    ".ts": "typescript",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".html": "html",
    ".css": "css",
    ".mdc": "markdown",
}


def _pick_file(path: Path) -> Path | None:
    """Pick a file from a directory. Returns selected file or None.

    For single files or non-directories, returns the path directly.
    For directories with one file, returns that file.
    For directories with multiple files, shows a picker menu.
    """
    if path.is_file():
        return path

    if not path.is_dir():
        return None

    files = sorted(
        f for f in path.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )

    if not files:
        return None
    if len(files) == 1:
        return files[0]

    # Multiple files — show picker
    from simple_term_menu import TerminalMenu

    labels = [f.name for f in files]
    menu = TerminalMenu(
        labels,
        title=f"\n{path.name}/ \u2014 {len(files)} files",
        menu_cursor="\u276f ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
        quit_keys=("q",),
    )
    choice = menu.show()
    if choice is None:
        return None
    return files[choice]


def _view_in_terminal(path: Path) -> None:
    """View a file in the terminal with syntax highlighting, piped through less."""
    from io import StringIO

    from rich.console import Console as RichConsole
    from rich.markdown import Markdown
    from rich.syntax import Syntax

    try:
        content = path.read_text()
    except OSError:
        console.print(f"[red]Cannot read: {path}[/red]")
        console.input("[dim]Press Enter to go back...[/dim]")
        return

    # Render to string with ANSI codes
    buf = StringIO()
    render_console = RichConsole(file=buf, force_terminal=True)
    render_console.print(f"[bold]{path.name}[/bold]")
    render_console.print("[dim]\u2500" * 50 + "[/dim]\n")

    if path.suffix in (".md", ".mdc"):
        render_console.print(Markdown(content))
    else:
        lexer = SYNTAX_LEXERS.get(path.suffix, "text")
        render_console.print(Syntax(content, lexer, theme="monokai", line_numbers=True))

    rendered = buf.getvalue()

    # Pipe through less -R (interprets ANSI colors)
    try:
        subprocess.run(["less", "-R"], input=rendered, text=True, check=False)
    except FileNotFoundError:
        # No less available — fall back to print + wait
        console.print(rendered)
        console.input("[dim]Press Enter to go back...[/dim]")


def _open_in_finder(path: Path) -> None:
    """Open a path in the system file manager."""
    if sys.platform == "darwin":
        if path.is_dir():
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["open", "-R", str(path)], check=False)
    elif sys.platform == "linux":
        subprocess.run(["xdg-open", str(path.parent if path.is_file() else path)], check=False)


def _open_in_editor(path: Path) -> None:
    """Open a path in $EDITOR. Shows file picker for directories."""
    editor = os.environ.get("EDITOR", "vim")
    target = _pick_file(path)
    if target is None:
        return
    subprocess.run([editor, str(target)], check=False)


def run_toggle_list(
    component_type: str,
    registry_names: list[str],
    global_enabled: list[str] | None = None,
    local_enabled: list[str] | None = None,
    project_name: str | None = None,
    start_scope: str = "local",
    registry_path: Path | None = None,
    registry_dir: str = "",
    local_is_new: bool = False,
    on_add: Callable[[], str | None] | None = None,
    add_label: str = "Add new...",
    # N-scope API — when provided, the old 2-scope params are ignored
    scopes: list[ToggleScope] | None = None,
    start_scope_index: int = -1,
    # Optional: set of names that actually exist in registry (for missing hints)
    registry_items: set[str] | None = None,
) -> tuple[list[list[str]], bool]:
    """Run an interactive toggle list for a component type.

    Supports two calling conventions:

    **N-scope (new)**: Pass `scopes` list of ToggleScope objects.
        Returns (list of enabled lists per scope, changed).

    **2-scope (backward compat)**: Pass global_enabled + local_enabled.
        Returns (list of enabled lists per scope, changed) where
        scopes[0] = global, scopes[1] = local (if provided).

    Tab cycles through scopes. Shows parent-scope hints.
    """
    # Convert old API to N-scope API
    if scopes is None:
        scopes = [ToggleScope(
            key="global",
            label="\U0001f310 All projects",
            enabled=list(global_enabled or []),
        )]
        if local_enabled is not None:
            scopes.append(ToggleScope(
                key="local",
                label=f"\U0001f4cd This project: {project_name or 'local'}",
                enabled=list(local_enabled),
                is_new=local_is_new,
            ))
            if start_scope == "local":
                start_scope_index = len(scopes) - 1
            else:
                start_scope_index = 0
        else:
            start_scope_index = 0

    # Handle empty state — but if on_add is provided, still show the list
    if not registry_names and on_add is None:
        scope_idx = start_scope_index if start_scope_index >= 0 else len(scopes) - 1
        _show_empty(component_type, scopes[scope_idx].label)
        return [list(s.enabled) for s in scopes], False

    # Mutable state: one checked set per scope
    checked_sets: list[set[str]] = [set(s.enabled) for s in scopes]
    initial_sets: list[set[str]] = [set(s.enabled) for s in scopes]

    scope_index = start_scope_index if start_scope_index >= 0 else len(scopes) - 1
    cursor = 0
    scroll_offset = 0
    changed = False
    status_msg = ""

    items = list(registry_names)
    num_scopes = len(scopes)

    def _get_actions() -> list[tuple[str, str]]:
        actions = [
            ("Select All", ACTION_SELECT_ALL),
            ("Select None", ACTION_SELECT_NONE),
        ]
        if on_add is not None:
            actions.append((add_label, ACTION_ADD))
        actions.append(("Done", ACTION_DONE))
        return actions

    def _total_rows() -> int:
        if not items:
            return len(_get_actions())
        return len(items) + 1 + len(_get_actions())

    def _is_separator(idx: int) -> bool:
        if not items:
            return False
        return idx == len(items)

    def _is_action(idx: int) -> bool:
        if not items:
            return idx >= 0
        return idx > len(items)

    def _action_id(idx: int) -> str:
        if not items:
            action_idx = idx
        else:
            action_idx = idx - len(items) - 1
        actions = _get_actions()
        if 0 <= action_idx < len(actions):
            return actions[action_idx][1]
        return ""

    def _checked_set() -> set[str]:
        return checked_sets[scope_index]

    def _initial_set() -> set[str]:
        return initial_sets[scope_index]

    def _find_parent_hint(name: str) -> str | None:
        """Walk up from current scope to find nearest parent that enables an item."""
        for i in range(scope_index - 1, -1, -1):
            if name in checked_sets[i]:
                return scopes[i].label
        return None

    def _handle_action(aid: str) -> bool:
        """Handle an action. Returns True if should break loop."""
        nonlocal changed
        if aid == ACTION_SELECT_ALL:
            _checked_set().update(items)
            changed = True
        elif aid == ACTION_SELECT_NONE:
            _checked_set().clear()
            changed = True
        elif aid == ACTION_ADD:
            return False  # Handled separately in the main loop
        elif aid == ACTION_DONE:
            return True
        return False

    def _toggle_item() -> None:
        """Toggle the item at cursor position."""
        nonlocal changed
        if cursor < len(items):
            name = items[cursor]
            checked = _checked_set()
            if name in checked:
                checked.discard(name)
            else:
                checked.add(name)
            changed = True

    def _build_display() -> str:
        """Build the display string for Rich."""
        lines: list[str] = []

        # Header with scope label + Tab hint
        current_scope = scopes[scope_index]
        scope_label = current_scope.label
        if current_scope.is_new:
            scope_label += " [yellow](new)[/yellow]"

        if num_scopes > 1:
            next_idx = (scope_index + 1) % num_scopes
            next_label = scopes[next_idx].label
            tab_hint = f"[Tab: {next_label}]"
        else:
            tab_hint = ""

        lines.append(f"[bold]{component_type}[/bold] \u2014 {scope_label}    [dim]{tab_hint}[/dim]")
        lines.append("[dim]\u2500" * 50 + "[/dim]")

        total = _total_rows()
        max_visible = _get_terminal_height() - 7
        _, vis_start, vis_end = _calculate_visible_range(cursor, total, max_visible, scroll_offset)

        checked = _checked_set()
        initial = _initial_set()

        # Scroll indicator (above)
        if vis_start > 0:
            lines.append(f"[dim]  \u2191 {vis_start} more[/dim]")

        # Empty state within the list
        if not items:
            lines.append("  [dim](none in registry)[/dim]")
            lines.append("")

        for i in range(vis_start, vis_end):
            is_cur = i == cursor
            prefix = "[cyan]\u276f[/cyan] " if is_cur else "  "

            if i < len(items):
                # Item row with change tracking
                name = items[i]
                is_checked = name in checked
                was_checked = name in initial
                is_changed = is_checked != was_checked

                if is_checked and is_changed:
                    mark = "[yellow]\u2714[/yellow]"
                elif is_checked:
                    mark = "[green]\u2714[/green]"
                elif is_changed:
                    mark = "[yellow]\u2610[/yellow]"
                else:
                    mark = "[dim]\u2610[/dim]"

                style = "[bold]" if is_cur else ""
                end_style = "[/bold]" if is_cur else ""

                # Hints: show where item is enabled in parent scopes
                hint = ""
                if registry_items is not None and name not in registry_items:
                    hint = "  [dim](not in registry)[/dim]"
                elif scope_index > 0 and not is_checked:
                    parent_label = _find_parent_hint(name)
                    if parent_label:
                        hint = f"  [dim](enabled in {parent_label})[/dim]"
                if not hint and is_changed:
                    hint = "  [yellow]\u2022[/yellow]"

                lines.append(f"{prefix}{mark} {style}{name}{end_style}{hint}")
            elif _is_separator(i):
                lines.append("  [dim]\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500[/dim]")
            elif _is_action(i):
                if not items:
                    action_idx = i
                else:
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

        # Status message
        if status_msg:
            lines.append(f"\n[dim]{status_msg}[/dim]")

        # Footer
        lines.append("")
        hints = "Space/Enter: toggle  \u2191\u2193/jk: navigate  q: done"
        if num_scopes > 1:
            hints += "  Tab: scope"
        if registry_path:
            hints += "  v: view  e: edit  o: open"
        lines.append(f"[dim]{hints}[/dim]")

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
            status_msg = ""

            # Navigation
            if key in (readchar.key.UP, "k"):
                cursor = (cursor - 1) % total
                if _is_separator(cursor):
                    cursor = (cursor - 1) % total
            elif key in (readchar.key.DOWN, "j"):
                cursor = (cursor + 1) % total
                if _is_separator(cursor):
                    cursor = (cursor + 1) % total

            # Toggle (Space)
            elif key == " ":
                if cursor < len(items):
                    _toggle_item()
                elif _is_action(cursor):
                    aid = _action_id(cursor)
                    if aid == ACTION_ADD and on_add:
                        live.stop()
                        new_name = on_add()
                        if new_name:
                            items.append(new_name)
                            items.sort()
                            _checked_set().add(new_name)
                            changed = True
                            status_msg = f"Added {new_name}"
                        live.start()
                    elif _handle_action(aid):
                        break

            # Enter — toggle item, or activate action
            elif key in ("\r", "\n", readchar.key.ENTER):
                if cursor < len(items):
                    _toggle_item()
                elif _is_action(cursor):
                    aid = _action_id(cursor)
                    if aid == ACTION_ADD and on_add:
                        live.stop()
                        new_name = on_add()
                        if new_name:
                            items.append(new_name)
                            items.sort()
                            _checked_set().add(new_name)
                            changed = True
                            status_msg = f"Added {new_name}"
                        live.start()
                    elif _handle_action(aid):
                        break

            # Tab = cycle scope
            elif key == "\t":
                if num_scopes > 1:
                    scope_index = (scope_index + 1) % num_scopes

            # View in terminal
            elif key == "v":
                if cursor < len(items) and registry_path and registry_dir:
                    name = items[cursor]
                    item_path = _resolve_item_path(registry_path, registry_dir, name)
                    if item_path:
                        live.stop()
                        target = _pick_file(item_path)
                        if target:
                            _view_in_terminal(target)
                        live.start()
                    else:
                        status_msg = f"Not found: {registry_dir}/{name}"

            # Open in Finder / file manager
            elif key == "o":
                if cursor < len(items) and registry_path and registry_dir:
                    name = items[cursor]
                    item_path = _resolve_item_path(registry_path, registry_dir, name)
                    if item_path:
                        live.stop()
                        _open_in_finder(item_path)
                        status_msg = f"Opened {name} in file manager"
                        live.start()
                    else:
                        status_msg = f"Not found: {registry_dir}/{name}"

            # Edit in $EDITOR
            elif key == "e":
                if cursor < len(items) and registry_path and registry_dir:
                    name = items[cursor]
                    item_path = _resolve_item_path(registry_path, registry_dir, name)
                    if item_path:
                        live.stop()
                        _open_in_editor(item_path)
                        live.start()
                    else:
                        status_msg = f"Not found: {registry_dir}/{name}"

            # Quit / done
            elif key in ("q", "\x1b"):
                break

            live.update(Text.from_markup(_build_display()))

    return [sorted(cs) for cs in checked_sets], changed


def _show_empty(component_type: str, scope_label: str) -> None:
    """Show empty state for a component type."""
    console.print(f"\n[bold]{component_type}[/bold] \u2014 {scope_label}")
    console.print("[dim]\u2500" * 40 + "[/dim]")
    console.print("  [dim](none in registry)[/dim]")
    console.print(f"\n  Run [cyan]hawk download <url>[/cyan] to add {component_type.lower()}.")
    console.print()
    console.input("[dim]Press Enter to continue...[/dim]")
