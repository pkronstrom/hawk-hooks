"""Toggle list component with N-scope switching.

Renders a Rich Live panel with checkboxes for registry items.
Supports Tab to cycle through arbitrary number of scopes (global, parent dirs, local).
Shows change indicators (yellow) for items modified since the list opened.
Shows "(enabled in <parent>)" hints when viewing inner scopes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import readchar
import yaml
from rich.console import Console
from rich.live import Live
from rich.text import Text

from ..hook_meta import parse_hook_meta
from ..types import ToggleGroup, ToggleScope  # noqa: F401 — re-exported
from .pause import wait_for_continue
from .theme import (
    action_style,
    cursor_prefix,
    dim_separator,
    enabled_count_style,
    get_theme,
    keybinding_hint,
    row_style,
    scoped_header,
    terminal_menu_style_kwargs,
)

console = Console(highlight=False)

# Actions appended after the item list
ACTION_SELECT_ALL = "__select_all__"
ACTION_SELECT_NONE = "__select_none__"
ACTION_ADD = "__add__"
ACTION_DONE = "__done__"
DEFAULT_VIEW_WIDTH = 100
MIN_VIEW_WIDTH = 40
DEFAULT_DESC_WIDTH = 96
MIN_DESC_WIDTH = 32


def _get_terminal_height() -> int:
    try:
        return os.get_terminal_size().lines
    except OSError:
        return 24


def _get_terminal_width(default: int = 120) -> int:
    """Return terminal columns with a safe fallback."""
    try:
        cols = os.get_terminal_size().columns
        return cols if cols > 0 else default
    except OSError:
        return default


def _get_view_wrap_width() -> int:
    """Return viewer wrap width from env + terminal bounds.

    Uses HAWK_VIEW_WIDTH when valid, otherwise DEFAULT_VIEW_WIDTH.
    Final width is clamped to terminal width - 2 and MIN_VIEW_WIDTH.
    """
    raw = (os.environ.get("HAWK_VIEW_WIDTH") or "").strip()
    target = DEFAULT_VIEW_WIDTH
    if raw:
        try:
            target = int(raw)
        except ValueError:
            target = DEFAULT_VIEW_WIDTH

    terminal_cap = max(MIN_VIEW_WIDTH, _get_terminal_width() - 2)
    target = max(MIN_VIEW_WIDTH, target)
    return min(target, terminal_cap)


def _get_description_wrap_width() -> int:
    """Return description wrap width from env + terminal bounds.

    Uses HAWK_TUI_DESC_WIDTH when valid, otherwise DEFAULT_DESC_WIDTH.
    Final width is clamped to terminal width - 6 and MIN_DESC_WIDTH.
    """
    raw = (os.environ.get("HAWK_TUI_DESC_WIDTH") or "").strip()
    target = DEFAULT_DESC_WIDTH
    if raw:
        try:
            target = int(raw)
        except ValueError:
            target = DEFAULT_DESC_WIDTH

    terminal_cap = max(MIN_DESC_WIDTH, _get_terminal_width() - 6)
    target = max(MIN_DESC_WIDTH, target)
    return min(target, terminal_cap)


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


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n?---\s*\n?", re.DOTALL)


def _extract_markdown_description(content: str) -> str:
    """Extract a readable summary from markdown-like content."""
    if not content.strip():
        return ""

    # Prefer explicit frontmatter description when available.
    fm_match = _FRONTMATTER_RE.match(content)
    if fm_match:
        try:
            frontmatter = yaml.safe_load(fm_match.group(1))
        except Exception:
            frontmatter = None
        if isinstance(frontmatter, dict):
            desc = str(frontmatter.get("description", "")).strip()
            if desc:
                return desc
        content = content[fm_match.end():]

    # Fall back to the first useful paragraph line(s).
    for paragraph in re.split(r"\n\s*\n", content):
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].startswith("```"):
            continue
        if all(line.startswith("#") for line in lines):
            continue
        stripped = [re.sub(r"^#+\s*", "", line).strip() for line in lines]
        text = " ".join(part for part in stripped if part)
        if text:
            return text

    return ""


def _extract_mcp_description(content: str) -> str:
    """Extract a short MCP server summary from YAML."""
    try:
        data = yaml.safe_load(content)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""

    command = str(data.get("command", "")).strip()
    args_raw = data.get("args", [])
    args = [str(arg) for arg in args_raw] if isinstance(args_raw, list) else []
    env_raw = data.get("env", {})
    env_count = len(env_raw) if isinstance(env_raw, dict) else 0

    if command:
        snippet = " ".join(([command] + args)[:8]).strip()
        extra = "..." if len(([command] + args)) > 8 else ""
        if env_count > 0:
            return f"MCP command: {snippet}{extra}. Env vars: {env_count}."
        return f"MCP command: {snippet}{extra}."
    if env_count > 0:
        return f"MCP server with {env_count} environment variable(s)."
    return ""


def _extract_hook_fallback_description(path: Path, content: str) -> str:
    """Extract hook description from common non-hawk-hook metadata patterns."""
    suffix = path.suffix.lower()

    if suffix == ".json":
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError, TypeError):
            data = None
        if isinstance(data, dict):
            hawk = data.get("hawk-hook")
            if isinstance(hawk, dict):
                desc = str(hawk.get("description", "")).strip()
                if desc:
                    return desc

            top_desc = str(data.get("description", "")).strip()
            if top_desc:
                return top_desc

            prompt = str(data.get("prompt", "")).strip()
            if prompt:
                return prompt[:160]

    # Common wrapper metadata style from downloader-generated scripts.
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("# Description:"):
            return line.split(":", 1)[1].strip()
        if line.startswith("// Description:"):
            return line.split(":", 1)[1].strip()

    return ""


def _get_item_description(item_path: Path, registry_dir: str) -> str:
    """Return a short description string for a registry item path."""
    source = item_path
    try:
        if source.is_symlink():
            source = source.resolve()
    except OSError:
        source = item_path

    if registry_dir == "hooks" and source.is_file():
        try:
            meta = parse_hook_meta(source)
        except Exception:
            meta = None
        try:
            raw_content = source.read_text(errors="replace")
        except OSError:
            raw_content = ""
        if meta:
            if meta.description.strip():
                return meta.description.strip()
            fallback = _extract_hook_fallback_description(source, raw_content)
            if fallback:
                return fallback
            if meta.events:
                return f"Hook events: {', '.join(meta.events)}."
        else:
            fallback = _extract_hook_fallback_description(source, raw_content)
            if fallback:
                return fallback

    if source.is_file():
        try:
            content = source.read_text(errors="replace")
        except OSError:
            return ""
        suffix = source.suffix.lower()
        if suffix in (".md", ".mdc", ".txt"):
            return _extract_markdown_description(content)
        if registry_dir == "mcp" and suffix in (".yaml", ".yml"):
            return _extract_mcp_description(content)
        return ""

    if source.is_dir():
        for candidate in ("SKILL.md", "skill.md", "README.md", "readme.md"):
            candidate_path = source / candidate
            if not candidate_path.exists():
                continue
            try:
                content = candidate_path.read_text(errors="replace")
            except OSError:
                continue
            desc = _extract_markdown_description(content)
            if desc:
                return desc
        return ""

    return ""


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
        **terminal_menu_style_kwargs(),
        quit_keys=("q", "\x1b"),
    )
    choice = menu.show()
    if choice is None:
        return None
    return files[choice]


def _browse_files(path: Path, initial_action: str = "view") -> None:
    """Browse files in a directory with view/edit/open support.

    For single files, performs the initial_action directly.
    For directories with multiple files, shows a persistent file picker
    with v/e/o keys that loops until the user presses q.
    """
    def _do_action(target: Path, action: str = initial_action) -> None:
        if action == "edit":
            editor = os.environ.get("EDITOR", "vim")
            subprocess.run([editor, str(target)], check=False)
        else:
            _view_in_terminal(target)

    if path.is_file():
        _do_action(path)
        return

    if not path.is_dir():
        return

    files = sorted(
        f for f in path.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )

    if not files:
        return
    if len(files) == 1:
        _do_action(files[0])
        return

    # Multiple files — interactive loop with readchar
    from rich.live import Live as FileLive
    from rich.text import Text as FileText

    cursor = 0

    def _build() -> str:
        accent = get_theme().accent_rich
        lines = [f"[bold]{path.name}/[/bold] \u2014 {len(files)} files"]
        lines.append("[dim]\u2500" * 40 + "[/dim]")
        for i, f in enumerate(files):
            prefix = "\u276f " if i == cursor else "  "
            if i == cursor:
                lines.append(f"[bold {accent}]{prefix}{f.name}[/bold {accent}]")
            else:
                lines.append(f"{prefix}{f.name}")
        lines.append("")
        lines.append(
            keybinding_hint(
                ["v/\u21b5 view", "e edit", "o open in finder"],
                include_nav=True,
            )
        )
        return "\n".join(lines)

    with FileLive(FileText.from_markup(_build()), refresh_per_second=30, screen=True) as live:
        while True:
            key = readchar.readkey()

            if key in ("q", "\x1b"):
                break

            elif key in (readchar.key.UP, "k"):
                cursor = max(0, cursor - 1)

            elif key in (readchar.key.DOWN, "j"):
                cursor = min(len(files) - 1, cursor + 1)

            elif key in ("v", readchar.key.ENTER, "\r", "\n"):
                live.stop()
                _view_in_terminal(files[cursor])
                live.start()

            elif key == "e":
                live.stop()
                editor = os.environ.get("EDITOR", "vim")
                subprocess.run([editor, str(files[cursor])], check=False)
                live.start()

            elif key == "o":
                _open_in_finder(files[cursor])

            live.update(FileText.from_markup(_build()))


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
        wait_for_continue("[dim]Press Enter/q/Ctrl+C to go back...[/dim]")
        return

    # Render to string with ANSI codes
    buf = StringIO()
    render_console = RichConsole(file=buf, force_terminal=True, width=_get_view_wrap_width())
    render_console.print(f"[bold]{path.name}[/bold]")
    render_console.print("[dim]\u2500" * 50 + "[/dim]\n")

    if path.suffix in (".md", ".mdc"):
        render_console.print(Markdown(content))
    else:
        lexer = SYNTAX_LEXERS.get(path.suffix, "text")
        render_console.print(
            Syntax(content, lexer, theme="monokai", line_numbers=True, word_wrap=True)
        )

    rendered = buf.getvalue()

    # Pipe through less -R (interprets ANSI colors)
    try:
        subprocess.run(["less", "-R"], input=rendered, text=True, check=False)
    except FileNotFoundError:
        # No less available — fall back to print + wait
        console.print(rendered)
        wait_for_continue("[dim]Press Enter/q/Ctrl+C to go back...[/dim]")


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
    # Package grouping — when provided, items are shown under collapsible headers
    groups: list[ToggleGroup] | None = None,
    # Optional hint shown above keybinding footer
    footer_hint: str | None = None,
    # Delete callback — called with item name, returns True if deleted
    on_delete: Callable[[str], bool] | None = None,
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
            label="\U0001f310 Global (default)",
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
    description_cache: dict[str, str] = {}

    items = list(registry_names)
    num_scopes = len(scopes)

    # Row kinds for the virtual row model
    ROW_GROUP_HEADER = "group_header"
    ROW_ITEM = "item"
    ROW_SEPARATOR = "separator"
    ROW_ACTION = "action"

    def _get_actions() -> list[tuple[str, str]]:
        actions = [
            ("Select All", ACTION_SELECT_ALL),
            ("Select None", ACTION_SELECT_NONE),
        ]
        if on_add is not None:
            actions.append((add_label, ACTION_ADD))
        actions.append(("Done", ACTION_DONE))
        return actions

    def _build_rows() -> list[tuple[str, str, int]]:
        """Build the virtual row list: (kind, value, group_idx).

        value: item name for items, group key for headers, action id for actions.
        group_idx: index into groups list, -1 for non-grouped rows.
        """
        rows: list[tuple[str, str, int]] = []

        if groups:
            for gi, group in enumerate(groups):
                rows.append((ROW_GROUP_HEADER, group.key, gi))
                if not group.collapsed:
                    for name in group.items:
                        rows.append((ROW_ITEM, name, gi))
        else:
            for name in items:
                rows.append((ROW_ITEM, name, -1))

        if not items and not groups:
            pass  # empty state handled in display
        else:
            rows.append((ROW_SEPARATOR, "", -1))

        for _, aid in _get_actions():
            rows.append((ROW_ACTION, aid, -1))

        return rows

    row_list = _build_rows()

    def _rebuild_rows() -> None:
        nonlocal row_list
        row_list = _build_rows()

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
            changed = True  # Signal that user explicitly saved
            return True
        return False

    def _toggle_item_by_name(name: str) -> None:
        """Toggle an item by name."""
        nonlocal changed
        checked = _checked_set()
        if name in checked:
            checked.discard(name)
        else:
            checked.add(name)
        changed = True

    def _group_enabled_count(group: ToggleGroup) -> tuple[int, int]:
        """Count (enabled, total) for a group in current scope."""
        checked = _checked_set()
        enabled = sum(1 for name in group.items if name in checked)
        return enabled, len(group.items)

    def _action_label(aid: str) -> str:
        for label, a in _get_actions():
            if a == aid:
                return label
        return ""

    def _build_display() -> str:
        """Build the display string for Rich."""
        lines: list[str] = []

        # Header with scope label + Tab hint
        current_scope = scopes[scope_index]
        scope_label = current_scope.label
        theme = get_theme()
        warning = theme.warning_rich
        if current_scope.is_new:
            scope_label += f" [{warning}](new)[/{warning}]"
        if footer_hint and num_scopes == 1:
            scope_label += f" [dim]\u2014 {footer_hint}[/dim]"

        if num_scopes > 1:
            next_idx = (scope_index + 1) % num_scopes
            next_label = scopes[next_idx].label
            tab_hint = f"\\[Tab: {next_label}]"
        else:
            tab_hint = ""

        lines.append(scoped_header(component_type, scope_label, tab_hint))
        lines.append(dim_separator())

        def _description_panel_lines() -> list[str]:
            if not row_list or not registry_path or not registry_dir:
                return []
            current_kind, current_value, _ = row_list[cursor]
            if current_kind != ROW_ITEM:
                return []

            item_name = current_value
            description = description_cache.get(item_name)
            if description is None:
                item_path = _resolve_item_path(registry_path, registry_dir, item_name)
                description = (
                    _get_item_description(item_path, registry_dir)
                    if item_path is not None
                    else ""
                )
                description_cache[item_name] = description

            width = _get_description_wrap_width()
            wrapped = textwrap.wrap(
                description or "No description metadata found for this item.",
                width=width,
                break_long_words=False,
                replace_whitespace=False,
            )
            wrapped = wrapped[:3] if wrapped else ["No description metadata found for this item."]
            info_style = get_theme().info_rich
            return [f"[{info_style}]{line}[/{info_style}]" for line in wrapped]

        description_lines = _description_panel_lines()
        total = len(row_list)
        reserved_lines = 2  # header + separator
        reserved_lines += 2  # footer spacer + key hints
        reserved_lines += 2  # potential up/down scroll indicators
        if status_msg:
            reserved_lines += 2
        if description_lines:
            reserved_lines += 1 + len(description_lines)  # spacer + panel

        max_visible = max(3, _get_terminal_height() - reserved_lines)
        _, vis_start, vis_end = _calculate_visible_range(cursor, total, max_visible, scroll_offset)

        checked = _checked_set()
        initial = _initial_set()

        # Scroll indicator (above)
        if vis_start > 0:
            lines.append(f"[dim]  \u2191 {vis_start} more[/dim]")

        # Empty state
        if not items and not groups:
            lines.append("  [dim](none in registry)[/dim]")
            lines.append("")

        for i in range(vis_start, vis_end):
            kind, value, gi = row_list[i]
            is_cur = i == cursor
            prefix = cursor_prefix(is_cur)

            if kind == ROW_GROUP_HEADER:
                group = groups[gi]
                en, tot = _group_enabled_count(group)
                arrow = "\u25b6" if group.collapsed else "\u25bc"
                if is_cur:
                    style, end_style = row_style(True)
                elif en == 0:
                    style, end_style = "[dim]", "[/dim]"
                else:
                    style, end_style = "", ""
                count_style = enabled_count_style(en)
                lines.append(f"{prefix}{style}{group.label}  [{count_style}]({en}/{tot})[/{count_style}]  {arrow}{end_style}")

            elif kind == ROW_ITEM:
                name = value
                is_checked = name in checked
                was_checked = name in initial
                is_changed = is_checked != was_checked

                if is_checked and is_changed:
                    mark = f"[{warning}]\u25cf[/{warning}]"
                elif is_checked:
                    mark = "\u25cf"
                elif is_changed:
                    mark = f"[{warning}]\u25cb[/{warning}]"
                else:
                    mark = "[dim]\u25cb[/dim]"

                if is_cur:
                    if is_checked:
                        style, end_style = "[bold white]", "[/bold white]"
                    else:
                        style, end_style = "[bold dim]", "[/bold dim]"
                elif is_checked:
                    style, end_style = "[white]", "[/white]"
                else:
                    style, end_style = "[dim]", "[/dim]"

                # Indent items under groups
                indent = "  " if groups else ""

                # Hints
                hint = ""
                if registry_items is not None and name not in registry_items:
                    hint = "  [dim italic](not in registry)[/dim italic]"
                elif scope_index > 0 and not is_checked:
                    parent_label = _find_parent_hint(name)
                    if parent_label:
                        hint = f"  [dim](enabled in {parent_label})[/dim]"
                if not hint and is_changed:
                    hint = f"[bold {warning}]*[/bold {warning}]"

                lines.append(f"{prefix}{indent}{mark} {style}{name}{end_style}{hint}")

            elif kind == ROW_SEPARATOR:
                lines.append("  [dim]\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500[/dim]")

            elif kind == ROW_ACTION:
                label = _action_label(value)
                style, end = action_style(is_cur)
                lines.append(f"{prefix}{style}{label}{end}")

        # Scroll indicator (below)
        if vis_end < total:
            remaining = total - vis_end
            lines.append(f"[dim]  \u2193 {remaining} more[/dim]")

        # Status message
        if status_msg:
            lines.append("")
            lines.append(f"[dim]{status_msg}[/dim]")

        if description_lines:
            lines.append("")
            lines.extend(description_lines)

        # Footer
        lines.append("")
        hints = "space/\u21b5 toggle · \u2191\u2193/jk nav · q done"
        if num_scopes > 1:
            hints += " · tab scope"
        if registry_path:
            hints += " · v view · e edit · o open"
        if on_delete:
            hints += " · d delete"
        if footer_hint and num_scopes > 1:
            hints += f" · {footer_hint}"
        lines.append(f"[dim]{hints}[/dim]")

        return "\n".join(lines)

    def _get_item_name_at_cursor() -> str | None:
        """Get the item name at the current cursor position, or None."""
        if cursor < len(row_list):
            kind, value, _ = row_list[cursor]
            if kind == ROW_ITEM:
                return value
        return None

    # Main loop
    with Live("", console=console, refresh_per_second=15, transient=True) as live:
        live.update(Text.from_markup(_build_display()))
        while True:
            try:
                key = readchar.readkey()
            except (KeyboardInterrupt, EOFError):
                break

            total = len(row_list)
            status_msg = ""

            # Navigation — skip separators but land on everything else
            if key in (readchar.key.UP, "k"):
                cursor = (cursor - 1) % total
                if row_list[cursor][0] == ROW_SEPARATOR:
                    cursor = (cursor - 1) % total
            elif key in (readchar.key.DOWN, "j"):
                cursor = (cursor + 1) % total
                if row_list[cursor][0] == ROW_SEPARATOR:
                    cursor = (cursor + 1) % total

            # Toggle (Space) or collapse/expand
            elif key == " ":
                kind, value, gi = row_list[cursor]
                if kind == ROW_GROUP_HEADER and groups:
                    groups[gi].collapsed = not groups[gi].collapsed
                    _rebuild_rows()
                    # Keep cursor on the header
                    cursor = min(cursor, len(row_list) - 1)
                elif kind == ROW_ITEM:
                    _toggle_item_by_name(value)
                elif kind == ROW_ACTION:
                    if value == ACTION_ADD and on_add:
                        live.stop()
                        new_name = on_add()
                        if new_name:
                            items.append(new_name)
                            items.sort()
                            # Add to ungrouped group if groups exist
                            if groups:
                                ungrouped = next((g for g in groups if g.key == "__ungrouped__"), None)
                                if ungrouped:
                                    ungrouped.items.append(new_name)
                                    ungrouped.items.sort()
                                else:
                                    groups.append(ToggleGroup(
                                        key="__ungrouped__",
                                        label="\u2500\u2500 ungrouped \u2500\u2500",
                                        items=[new_name],
                                    ))
                            _checked_set().add(new_name)
                            changed = True
                            status_msg = f"Added {new_name}"
                            _rebuild_rows()
                        live.start()
                    elif _handle_action(value):
                        break

            # Enter — same as Space
            elif key in ("\r", "\n", readchar.key.ENTER):
                kind, value, gi = row_list[cursor]
                if kind == ROW_GROUP_HEADER and groups:
                    groups[gi].collapsed = not groups[gi].collapsed
                    _rebuild_rows()
                    cursor = min(cursor, len(row_list) - 1)
                elif kind == ROW_ITEM:
                    _toggle_item_by_name(value)
                elif kind == ROW_ACTION:
                    if value == ACTION_ADD and on_add:
                        live.stop()
                        new_name = on_add()
                        if new_name:
                            items.append(new_name)
                            items.sort()
                            if groups:
                                ungrouped = next((g for g in groups if g.key == "__ungrouped__"), None)
                                if ungrouped:
                                    ungrouped.items.append(new_name)
                                    ungrouped.items.sort()
                                else:
                                    groups.append(ToggleGroup(
                                        key="__ungrouped__",
                                        label="\u2500\u2500 ungrouped \u2500\u2500",
                                        items=[new_name],
                                    ))
                            _checked_set().add(new_name)
                            changed = True
                            status_msg = f"Added {new_name}"
                            _rebuild_rows()
                        live.start()
                    elif _handle_action(value):
                        break

            # Tab = cycle scope
            elif key == "\t":
                if num_scopes > 1:
                    scope_index = (scope_index + 1) % num_scopes

            # View in terminal (browse files for directories)
            elif key == "v":
                name = _get_item_name_at_cursor()
                if name and registry_path and registry_dir:
                    item_path = _resolve_item_path(registry_path, registry_dir, name)
                    if item_path:
                        live.stop()
                        _browse_files(item_path, initial_action="view")
                        live.start()
                    else:
                        status_msg = f"Not found: {registry_dir}/{name}"

            # Open in Finder / file manager
            elif key == "o":
                name = _get_item_name_at_cursor()
                if name and registry_path and registry_dir:
                    item_path = _resolve_item_path(registry_path, registry_dir, name)
                    if item_path:
                        live.stop()
                        _open_in_finder(item_path)
                        status_msg = f"Opened {name} in file manager"
                        live.start()
                    else:
                        status_msg = f"Not found: {registry_dir}/{name}"

            # Edit in $EDITOR (browse files for directories)
            elif key == "e":
                name = _get_item_name_at_cursor()
                if name and registry_path and registry_dir:
                    item_path = _resolve_item_path(registry_path, registry_dir, name)
                    if item_path:
                        live.stop()
                        _browse_files(item_path, initial_action="edit")
                        live.start()
                    else:
                        status_msg = f"Not found: {registry_dir}/{name}"

            # Delete item from registry (or remove orphaned reference)
            elif key == "d":
                name = _get_item_name_at_cursor()
                if name:
                    is_orphan = registry_items is not None and name not in registry_items
                    if is_orphan:
                        # Orphaned config reference — just remove from lists
                        live.stop()
                        console.print(f"\n[yellow]Remove [bold]{name}[/bold] (not in registry) from config?[/yellow] [dim](y/N)[/dim] ", end="")
                        confirm = readchar.readkey()
                        console.print()
                        if confirm.lower() == "y":
                            if name in items:
                                items.remove(name)
                            for cs in checked_sets:
                                cs.discard(name)
                            for ins in initial_sets:
                                ins.discard(name)
                            if groups:
                                for g in groups:
                                    if name in g.items:
                                        g.items.remove(name)
                                groups[:] = [g for g in groups if g.items]
                            status_msg = f"Removed {name}"
                            _rebuild_rows()
                            if row_list:
                                cursor = min(cursor, len(row_list) - 1)
                                if row_list[cursor][0] == ROW_SEPARATOR and cursor > 0:
                                    cursor -= 1
                            changed = True
                        live.start()
                    elif on_delete:
                        # Real registry item — delete from registry
                        live.stop()
                        console.print(f"\n[yellow]Delete [bold]{name}[/bold] from registry?[/yellow] [dim](y/N)[/dim] ", end="")
                        confirm = readchar.readkey()
                        console.print()
                        if confirm.lower() == "y":
                            if on_delete(name):
                                if name in items:
                                    items.remove(name)
                                for cs in checked_sets:
                                    cs.discard(name)
                                for ins in initial_sets:
                                    ins.discard(name)
                                if groups:
                                    for g in groups:
                                        if name in g.items:
                                            g.items.remove(name)
                                    groups[:] = [g for g in groups if g.items]
                                status_msg = f"Deleted {name}"
                                _rebuild_rows()
                                if row_list:
                                    cursor = min(cursor, len(row_list) - 1)
                                    if row_list[cursor][0] == ROW_SEPARATOR and cursor > 0:
                                        cursor -= 1
                                changed = True
                            else:
                                status_msg = f"Failed to delete {name}"
                        live.start()

            # Quit / done
            elif key in ("q", "\x1b"):
                break

            _rebuild_rows()
            live.update(Text.from_markup(_build_display()))

    return [sorted(cs) for cs in checked_sets], changed


def _show_empty(component_type: str, scope_label: str) -> None:
    """Show empty state for a component type."""
    console.print(f"\n{scoped_header(component_type, scope_label)}")
    console.print(dim_separator(40))
    console.print("  [dim](none in registry)[/dim]")
    console.print(f"\n  Run [cyan]hawk download <url>[/cyan] to add {component_type.lower()}.")
    console.print()
    wait_for_continue()
