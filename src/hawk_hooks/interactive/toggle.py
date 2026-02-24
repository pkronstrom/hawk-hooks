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
from dataclasses import field
from pathlib import Path
from typing import Callable

import readchar
import yaml
from rich.console import Console
from rich.live import Live
from rich.text import Text

from ..hook_meta import parse_hook_meta
from ..types import TieredMenuItem, ToggleScope  # noqa: F401 — re-exported
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
    warning_style,
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
        menu_cursor="\u203a ",
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
            prefix = "\u203a " if i == cursor else "  "
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


# ---------------------------------------------------------------------------
# Row kind constants shared across the unified picker
# ---------------------------------------------------------------------------
ROW_PACKAGE = "package"
ROW_TYPE = "type"
ROW_ITEM = "item"
ROW_SEPARATOR = "separator"
ROW_ACTION = "action"
UNGROUPED = "__ungrouped__"


# ---------------------------------------------------------------------------
# Helpers for building picker data from flat item lists
# ---------------------------------------------------------------------------


def build_picker_tree(
    items: list[TieredMenuItem],
    field_labels: dict[str, str] | None = None,
) -> tuple[list[str], dict[str, dict[str, list[str]]], dict[str, str]]:
    """Build (package_order, package_tree, field_labels) from flat item list.

    Returns the triple expected by ``run_picker``.
    """
    if field_labels is None:
        field_labels = {}

    package_tree: dict[str, dict[str, list[str]]] = {}
    for mi in items:
        group = mi.group or UNGROUPED
        fld = mi.field or "__default__"
        package_tree.setdefault(group, {}).setdefault(fld, []).append(mi.name)
        if fld not in field_labels:
            field_labels[fld] = fld.title()

    package_order = [p for p in sorted(package_tree.keys()) if p != UNGROUPED]
    if UNGROUPED in package_tree:
        package_order.append(UNGROUPED)

    return package_order, package_tree, field_labels


def scopes_from_toggle_scopes(
    toggle_scopes: list[ToggleScope],
    field: str,
) -> list[dict]:
    """Convert ToggleScope (name-only enabled) to picker scope format (field, name tuples)."""
    result: list[dict] = []
    for ts in toggle_scopes:
        result.append({
            "key": ts.key,
            "label": ts.label,
            "enabled": {(field, name) for name in ts.enabled},
            "is_new": ts.is_new,
        })
    return result


def _detect_tiers(
    package_tree: dict[str, dict[str, list[str]]],
    package_order: list[str],
) -> int:
    """Auto-detect tier depth from data shape.

    Returns 1, 2, or 3.
    """
    real_packages = [p for p in package_order if p != UNGROUPED]
    all_fields: set[str] = set()
    for pkg in package_order:
        for fld in package_tree.get(pkg, {}):
            all_fields.add(fld)

    num_groups = len(real_packages) + (1 if UNGROUPED in package_tree else 0)

    if num_groups <= 1 and len(all_fields) <= 1:
        return 1  # flat list
    if len(all_fields) <= 1:
        return 2  # groups -> items (type tier hidden)
    return 3  # full 3-tier


# ---------------------------------------------------------------------------
# Unified picker
# ---------------------------------------------------------------------------


def run_picker(
    title: str,
    package_tree: dict[str, dict[str, list[str]]],
    package_order: list[str],
    field_labels: dict[str, str],
    scopes: list[dict],
    *,
    start_scope_index: int = 0,
    packages_meta: dict | None = None,
    collapsed_packages: dict[str, bool] | None = None,
    collapsed_types: dict[tuple[str, str], bool] | None = None,
    on_toggle: Callable | None = None,
    on_rebuild: Callable | None = None,
    extra_key_handler: Callable | None = None,
    extra_hints: Callable | None = None,
    action_label: str = "Done",
    scope_hint: str | None = None,
    # --- Features from run_toggle_list ---
    get_description: Callable[[str, str], str] | None = None,
    registry_path: Path | None = None,
    registry_dir: str = "",
    show_change_indicators: bool = False,
    show_select_all: bool = False,
    on_add: Callable[[], str | None] | None = None,
    add_label: str = "Add new...",
    registry_items: set[str] | None = None,
    on_delete: Callable[[str, str], bool] | None = None,
    parent_hint_fn: Callable[[int, str, str], str | None] | None = None,
) -> tuple[list[dict], bool]:
    """Unified picker supporting 1, 2, and 3 tier layouts.

    Auto-detects tier depth from data shape:
    - 1-tier: flat item list (no group/type headers)
    - 2-tier: group headers + items (type tier hidden)
    - 3-tier: package -> type -> items

    Args:
        title: Header title.
        package_tree: {pkg_name: {field: [item_names]}}.
        package_order: Display order of package names.
        field_labels: {field: "Human Label"} for type rows.
        scopes: [{key, label, enabled: set[(field, name)]}].
        start_scope_index: Which scope to start on.
        packages_meta: Package index data for URL display.
        collapsed_packages: Mutable dict of pkg->collapsed state.
        collapsed_types: Mutable dict of (pkg,field)->collapsed state.
        on_toggle: (scope_key, field, name, enabled) -> None.
        on_rebuild: () -> (package_order, package_tree, scopes).
        extra_key_handler: (key, row, scope, live) -> (handled, status_msg).
        extra_hints: (row_kind) -> str | None.
        action_label: Label for the Done/Save action button.
        scope_hint: Shown when only 1 scope.
        get_description: (field, name) -> str. For description panel.
        registry_path: Registry path for v/e/o file browsing.
        registry_dir: Registry subdir for file browsing (when single-field).
        show_change_indicators: Yellow marks for modified items.
        show_select_all: Add Select All / Select None actions.
        on_add: Callback for "Add new..." action.
        add_label: Label for the add action.
        registry_items: Set of names in registry (for "not in registry" hints).
        on_delete: (field, name) -> bool. Delete callback.
        parent_hint_fn: (scope_index, field, name) -> hint | None.

    Returns:
        (final_scopes, changed)
    """
    if collapsed_packages is None:
        collapsed_packages = {}
    if collapsed_types is None:
        collapsed_types = {}
    if packages_meta is None:
        packages_meta = {}

    tiers = _detect_tiers(package_tree, package_order)
    ordered_fields = list(field_labels.keys())

    cursor = 0
    scroll_offset = 0
    scope_index = start_scope_index
    status_msg = ""
    changed = False
    description_cache: dict[tuple[str, str], str] = {}

    # Track initial state for change indicators
    initial_sets: list[set[tuple[str, str]]] = [set(s["enabled"]) for s in scopes]

    # --- Auto default description function from registry_path ---
    if get_description is None and registry_path and registry_dir:
        def get_description(field: str, name: str) -> str:
            item_path = _resolve_item_path(registry_path, registry_dir, name)
            if item_path is not None:
                return _get_item_description(item_path, registry_dir)
            return ""

    # --- Auto default parent hint function ---
    if parent_hint_fn is None and len(scopes) > 1:
        def parent_hint_fn(si: int, field: str, name: str) -> str | None:
            for i in range(si - 1, -1, -1):
                if (field, name) in scopes[i]["enabled"]:
                    return scopes[i]["label"]
            return None

    def _build_rows() -> list[dict]:
        rows: list[dict] = []

        if tiers == 1:
            # Flat: just items from any package/field
            for pkg_name in package_order:
                field_map = package_tree.get(pkg_name, {})
                for fld in ordered_fields:
                    for name in field_map.get(fld, []):
                        rows.append({
                            "kind": ROW_ITEM,
                            "package": pkg_name,
                            "field": fld,
                            "name": name,
                        })

        elif tiers == 2:
            # Groups -> items (type tier hidden, single field)
            the_field = ordered_fields[0] if ordered_fields else ""
            for pkg_name in package_order:
                collapsed_packages.setdefault(pkg_name, True)
                field_map = package_tree.get(pkg_name, {})
                item_count = sum(len(names) for names in field_map.values())

                # Only show group header if there are multiple groups
                num_groups = len(package_order)
                if num_groups > 1:
                    rows.append({
                        "kind": ROW_PACKAGE,
                        "package": pkg_name,
                        "count": item_count,
                        "is_ungrouped": pkg_name == UNGROUPED,
                    })
                    if collapsed_packages.get(pkg_name, False):
                        continue

                for name in field_map.get(the_field, []):
                    rows.append({
                        "kind": ROW_ITEM,
                        "package": pkg_name,
                        "field": the_field,
                        "name": name,
                    })

        else:
            # Full 3-tier
            for pkg_name in package_order:
                collapsed_packages.setdefault(pkg_name, True)
                field_map = package_tree.get(pkg_name, {})
                item_count = sum(len(names) for f, names in field_map.items())
                rows.append({
                    "kind": ROW_PACKAGE,
                    "package": pkg_name,
                    "count": item_count,
                    "is_ungrouped": pkg_name == UNGROUPED,
                })

                if collapsed_packages.get(pkg_name, False):
                    continue

                for fld in ordered_fields:
                    names = field_map.get(fld, [])
                    if not names:
                        continue
                    label = field_labels.get(fld, fld.title())
                    rows.append({
                        "kind": ROW_TYPE,
                        "package": pkg_name,
                        "field": fld,
                        "label": label,
                        "count": len(names),
                    })

                    if collapsed_types.get((pkg_name, fld), True):
                        continue

                    for name in names:
                        rows.append({
                            "kind": ROW_ITEM,
                            "package": pkg_name,
                            "field": fld,
                            "name": name,
                        })

        rows.append({"kind": ROW_SEPARATOR})

        if show_select_all:
            rows.append({"kind": ROW_ACTION, "action": ACTION_SELECT_ALL, "label": "Select All"})
            rows.append({"kind": ROW_ACTION, "action": ACTION_SELECT_NONE, "label": "Select None"})
        if on_add is not None:
            rows.append({"kind": ROW_ACTION, "action": ACTION_ADD, "label": add_label})
        rows.append({"kind": ROW_ACTION, "action": ACTION_DONE, "label": action_label})
        return rows

    def _is_selectable(row: dict) -> bool:
        return row.get("kind") != ROW_SEPARATOR

    def _normalize_cursor(rows: list[dict], idx: int) -> int:
        if not rows:
            return 0
        idx = max(0, min(idx, len(rows) - 1))
        if _is_selectable(rows[idx]):
            return idx
        for i, row in enumerate(rows):
            if _is_selectable(row):
                return i
        return 0

    def _move_cursor(rows: list[dict], idx: int, direction: int) -> int:
        total = len(rows)
        if total == 0:
            return 0
        idx = max(0, min(idx, total - 1))
        for _ in range(total):
            idx = (idx + direction) % total
            if _is_selectable(rows[idx]):
                return idx
        return idx

    def _update_scroll(total: int, idx: int, max_visible: int, offset: int) -> int:
        if total <= 0 or max_visible <= 0:
            return 0
        if idx < offset:
            offset = idx
        elif idx >= offset + max_visible:
            offset = idx - max_visible + 1
        max_offset = max(0, total - max_visible)
        return max(0, min(offset, max_offset))

    def _get_all_item_pairs() -> list[tuple[str, str]]:
        """Get all (field, name) pairs from current tree."""
        pairs: list[tuple[str, str]] = []
        for pkg in package_order:
            fm = package_tree.get(pkg, {})
            for fld, names in fm.items():
                for name in names:
                    pairs.append((fld, name))
        return pairs

    def _build_display(rows: list[dict], scopes_: list[dict]) -> str:
        nonlocal scroll_offset

        def _term_cols() -> int:
            try:
                return os.get_terminal_size().columns
            except OSError:
                return 80

        def _truncate(text: str, max_len: int) -> str:
            if max_len <= 1:
                return text[:max_len]
            if len(text) <= max_len:
                return text
            return text[: max_len - 1] + "\u2026"

        scope = scopes_[scope_index]
        checked: set[tuple[str, str]] = scope["enabled"]
        initial = initial_sets[scope_index] if show_change_indicators else set()
        next_scope = scopes_[(scope_index + 1) % len(scopes_)]["label"] if len(scopes_) > 1 else ""

        theme = get_theme()
        warning = theme.warning_rich

        lines: list[str] = []

        # Header
        scope_label = scope["label"]
        if scope.get("is_new"):
            scope_label += f" [{warning}](new)[/{warning}]"

        lines.append(scoped_header(title, scope_label))
        if len(scopes_) > 1:
            lines[-1] += f"    [dim]\\[Tab: {next_scope}][/dim]"
        elif scope_hint:
            lines[-1] += f" [dim]\u2014 {scope_hint}[/dim]"

        # Sub-header for 3-tier
        if tiers == 3:
            package_count = len([p for p in package_order if p != UNGROUPED])
            ungrouped_count = sum(len(names) for names in package_tree.get(UNGROUPED, {}).values())
            if ungrouped_count > 0:
                lines.append(f"[dim]Packages: {package_count}  |  Ungrouped items: {ungrouped_count}[/dim]")
            else:
                lines.append(f"[dim]Packages: {package_count}[/dim]")

        lines.append(dim_separator())

        # Description panel
        desc_lines: list[str] = []
        if get_description and rows:
            cur_row = rows[cursor] if cursor < len(rows) else {}
            if cur_row.get("kind") == ROW_ITEM:
                cache_key = (cur_row["field"], cur_row["name"])
                desc = description_cache.get(cache_key)
                if desc is None:
                    desc = get_description(cur_row["field"], cur_row["name"])
                    description_cache[cache_key] = desc
                width = _get_description_wrap_width()
                wrapped = textwrap.wrap(
                    desc or "No description metadata found for this item.",
                    width=width,
                    break_long_words=False,
                    replace_whitespace=False,
                )
                wrapped = wrapped[:3] if wrapped else ["No description metadata found for this item."]
                info_style = get_theme().info_rich
                desc_lines = [f"[{info_style}]{line}[/{info_style}]" for line in wrapped]

        total_rows = len(rows)
        reserved = 4  # header + separator + footer spacer + hints
        if tiers == 3:
            reserved += 1  # sub-header
        if status_msg:
            reserved += 2
        if desc_lines:
            reserved += 1 + len(desc_lines)
        reserved += 2  # scroll indicators

        max_visible = max(8, _get_terminal_height() - reserved)
        scroll_offset = _update_scroll(total_rows, cursor, max_visible, scroll_offset)
        vis_start = scroll_offset
        vis_end = min(total_rows, vis_start + max_visible)

        if vis_start > 0:
            lines.append(f"[dim]  \u2191 {vis_start} more[/dim]")

        # Empty state — check actual data, not collapsed rows
        has_any_items = any(
            names
            for pkg in package_order
            for names in package_tree.get(pkg, {}).values()
        )
        if not has_any_items:
            lines.append("  [dim](none in registry)[/dim]")
            lines.append("")

        cols = _term_cols()

        for i in range(vis_start, vis_end):
            row = rows[i]
            kind = row["kind"]
            is_cur = i == cursor
            prefix = cursor_prefix(is_cur)

            if kind == ROW_PACKAGE:
                pkg_name = row["package"]
                is_ungrouped = row["is_ungrouped"]
                collapsed = collapsed_packages.get(pkg_name, False)
                icon = "+" if collapsed else "-"
                label = "Ungrouped (not in package)" if is_ungrouped else pkg_name
                pkg_items = package_tree.get(pkg_name, {})
                enabled_count = sum(
                    1
                    for fld, names in pkg_items.items()
                    for name in names
                    if (fld, name) in checked
                )
                suffix = f" ({enabled_count}/{row['count']})"
                max_label = max(10, cols - 8 - len(suffix))
                label = _truncate(label, max_label)
                if is_cur:
                    style, end = row_style(True)
                elif is_ungrouped:
                    style, end = warning_style(False)
                elif enabled_count == 0:
                    style, end = "[dim]", "[/dim]"
                else:
                    style, end = "", ""
                count_style = enabled_count_style(enabled_count)
                lines.append(
                    f"{prefix}{style}{icon} {label} "
                    f"[{count_style}]({enabled_count}/{row['count']})[/{count_style}]{end}"
                )

                # Show URL for non-ungrouped expanded packages in 3-tier
                if tiers == 3 and not is_ungrouped and not collapsed:
                    url = str(packages_meta.get(pkg_name, {}).get("url", "")).strip()
                    if url:
                        lines.append(f"      [dim]{url}[/dim]")

            elif kind == ROW_TYPE:
                pkg_name = row["package"]
                fld = row["field"]
                collapsed = collapsed_types.get((pkg_name, fld), True)
                icon = "+" if collapsed else "-"
                names = package_tree.get(pkg_name, {}).get(fld, [])
                enabled_count = sum(1 for name in names if (fld, name) in checked)
                total_count = len(names)
                suffix = f" ({enabled_count}/{total_count})"
                max_label = max(8, cols - 18 - len(suffix))
                label = _truncate(row["label"], max_label)
                if is_cur:
                    style, end = row_style(True)
                elif enabled_count == 0:
                    style, end = "[dim]", "[/dim]"
                else:
                    style, end = "", ""
                count_style = enabled_count_style(enabled_count)
                lines.append(
                    f"{prefix}  {style}{icon} {label} "
                    f"[{count_style}]({enabled_count}/{total_count})[/{count_style}]{end}"
                )

            elif kind == ROW_ITEM:
                fld = row["field"]
                name = row["name"]
                enabled = (fld, name) in checked
                was_enabled = (fld, name) in initial if show_change_indicators else enabled
                is_changed = show_change_indicators and enabled != was_enabled

                # Check mark with change indicators
                if enabled and is_changed:
                    mark = f"[{warning}]\u25cf[/{warning}]"
                elif enabled:
                    mark = "\u25cf"
                elif is_changed:
                    mark = f"[{warning}]\u25cb[/{warning}]"
                else:
                    mark = "[dim]\u25cb[/dim]"

                if is_cur:
                    if enabled:
                        style, end = "[bold white]", "[/bold white]"
                    else:
                        style, end = "[bold dim]", "[/bold dim]"
                elif enabled:
                    style, end = "[white]", "[/white]"
                else:
                    style, end = "[dim]", "[/dim]"

                # Indentation depends on tier mode
                if tiers == 1:
                    indent = ""
                elif tiers == 2:
                    indent = "  " if len(package_order) > 1 else ""
                else:
                    indent = "    "

                # Hints
                hint = ""
                if registry_items is not None and name not in registry_items:
                    hint = "  [dim italic](not in registry)[/dim italic]"
                elif parent_hint_fn and scope_index > 0 and not enabled:
                    parent_label = parent_hint_fn(scope_index, fld, name)
                    if parent_label:
                        hint = f"  [dim](enabled in {parent_label})[/dim]"
                if not hint and is_changed:
                    hint = f"[bold {warning}]*[/bold {warning}]"

                lines.append(f"{prefix}{indent}{mark} {style}{name}{end}{hint}")

            elif kind == ROW_SEPARATOR:
                lines.append(f"  {dim_separator(9)}")

            elif kind == ROW_ACTION:
                style, end = action_style(is_cur)
                lines.append(f"{prefix}{style}{row['label']}{end}")

        if vis_end < total_rows:
            lines.append(f"[dim]  \u2193 {total_rows - vis_end} more[/dim]")

        if status_msg:
            lines.append(f"\n[dim]{status_msg}[/dim]")

        if desc_lines:
            lines.append("")
            lines.extend(desc_lines)

        # Footer hints
        lines.append("")
        current_kind = rows[cursor]["kind"] if rows else ROW_ACTION
        if extra_hints:
            hints = extra_hints(current_kind)
        else:
            if current_kind == ROW_PACKAGE:
                hints = "\u21b5 expand · t toggle all"
            elif current_kind == ROW_TYPE:
                hints = "\u21b5 expand · t toggle all"
            elif current_kind == ROW_ITEM:
                hints = "\u21b5 toggle · t group"
            else:
                hints = "\u21b5 select"
        if len(scopes_) > 1:
            hints += " · tab scope"
        if registry_path and registry_dir:
            hints += " · v view · e edit · o open"
        if on_delete:
            hints += " · d del"
        hints += " · jk nav · q back"

        # Wrap long hint lines to terminal width
        cols = _term_cols()
        if len(hints) > cols - 2:
            parts = hints.split(" \u00b7 ")
            hint_lines: list[str] = []
            current_line = ""
            for part in parts:
                candidate = f"{current_line} \u00b7 {part}" if current_line else part
                if len(candidate) > cols - 2 and current_line:
                    hint_lines.append(current_line)
                    current_line = part
                else:
                    current_line = candidate
            if current_line:
                hint_lines.append(current_line)
            for hl in hint_lines:
                lines.append(f"[dim]{hl}[/dim]")
        else:
            lines.append(f"[dim]{hints}[/dim]")
        return "\n".join(lines)

    def _do_toggle(scope: dict, fld: str, name: str, enable: bool) -> None:
        nonlocal changed
        if enable:
            scope["enabled"].add((fld, name))
        else:
            scope["enabled"].discard((fld, name))
        changed = True
        if on_toggle:
            on_toggle(scope["key"], fld, name, enable)

    def _toggle_group_items(scope: dict, pairs: list[tuple[str, str]]) -> str:
        if not pairs:
            return ""
        all_enabled = all((f, n) in scope["enabled"] for f, n in pairs)
        for f, n in pairs:
            _do_toggle(scope, f, n, not all_enabled)
        return "Disabled" if all_enabled else "Enabled"

    def _handle_select_all(scope: dict) -> None:
        nonlocal changed
        for f, n in _get_all_item_pairs():
            scope["enabled"].add((f, n))
        changed = True

    def _handle_select_none(scope: dict) -> None:
        nonlocal changed
        scope["enabled"].clear()
        changed = True

    def _handle_add(live: Live) -> str:
        nonlocal changed
        if not on_add:
            return ""
        live.stop()
        new_name = on_add()
        if new_name:
            # Add to the first field in the ungrouped package
            fld = ordered_fields[0] if ordered_fields else "__default__"
            package_tree.setdefault(UNGROUPED, {}).setdefault(fld, []).append(new_name)
            if UNGROUPED not in package_order:
                package_order.append(UNGROUPED)
            scopes[scope_index]["enabled"].add((fld, new_name))
            changed = True
            live.start()
            return f"Added {new_name}"
        live.start()
        return ""

    with Live("", console=console, refresh_per_second=15, screen=True) as live:
        while True:
            if on_rebuild:
                new_order, new_tree, new_scopes = on_rebuild()
                package_order[:] = new_order
                package_tree.clear()
                package_tree.update(new_tree)
                scopes[:] = new_scopes

            scope_index = max(0, min(scope_index, len(scopes) - 1))
            rows = _build_rows()
            cursor = _normalize_cursor(rows, cursor)
            live.update(Text.from_markup(_build_display(rows, scopes)))

            try:
                key = readchar.readkey()
            except (KeyboardInterrupt, EOFError):
                break

            status_msg = ""
            row = rows[cursor]
            kind = row["kind"]
            scope = scopes[scope_index]

            # Navigation
            if key in (readchar.key.UP, "k"):
                cursor = _move_cursor(rows, cursor, -1)
                continue
            if key in (readchar.key.DOWN, "j"):
                cursor = _move_cursor(rows, cursor, 1)
                continue
            if key == readchar.key.LEFT:
                for i in range(len(rows)):
                    if _is_selectable(rows[i]):
                        cursor = i
                        break
                continue
            if key == readchar.key.RIGHT:
                for i in range(len(rows) - 1, -1, -1):
                    if _is_selectable(rows[i]):
                        cursor = i
                        break
                continue
            if key in (readchar.key.TAB, "\t") and len(scopes) > 1:
                scope_index = (scope_index + 1) % len(scopes)
                continue
            if key in ("q", "\x1b", getattr(readchar.key, "CTRL_C", "\x03"), "\x03"):
                break

            # Let caller handle extra keys first
            if extra_key_handler:
                handled, extra_status = extra_key_handler(key, row, scope, live)
                if handled:
                    if extra_status:
                        status_msg = extra_status
                    changed = True
                    continue

            primary = key in (readchar.key.ENTER, "\r", "\n", " ")

            # Actions
            if kind == ROW_ACTION and primary:
                action = row.get("action", "")
                if action == ACTION_DONE:
                    changed = True
                    break
                if action == ACTION_SELECT_ALL:
                    _handle_select_all(scope)
                    continue
                if action == ACTION_SELECT_NONE:
                    _handle_select_none(scope)
                    continue
                if action == ACTION_ADD:
                    status_msg = _handle_add(live)
                    continue

            # Package collapse/expand
            if kind == ROW_PACKAGE:
                pkg_name = row["package"]
                if primary:
                    collapsed_packages[pkg_name] = not collapsed_packages.get(pkg_name, False)
                    continue

            # Type collapse/expand
            if kind == ROW_TYPE and primary:
                pkg_name = row["package"]
                fld = row["field"]
                key_id = (pkg_name, fld)
                collapsed_types[key_id] = not collapsed_types.get(key_id, True)
                continue

            # Toggle group (t key)
            if key == "t":
                if kind == ROW_PACKAGE:
                    pkg_name = row["package"]
                    pkg_items = package_tree.get(pkg_name, {})
                    all_pairs = [(f, n) for f, names in pkg_items.items() for n in names]
                    action = _toggle_group_items(scope, all_pairs)
                    if action:
                        label = "ungrouped" if row.get("is_ungrouped") else pkg_name
                        status_msg = f"{action} all in {label}"
                    continue
                if kind == ROW_TYPE:
                    pkg_name = row["package"]
                    fld = row["field"]
                    names = package_tree.get(pkg_name, {}).get(fld, [])
                    pairs = [(fld, n) for n in names]
                    action = _toggle_group_items(scope, pairs)
                    if action:
                        status_msg = f"{action} all {row['label']} in {pkg_name}"
                    continue
                if kind == ROW_ITEM:
                    pkg_name = row["package"]
                    fld = row["field"]
                    names = package_tree.get(pkg_name, {}).get(fld, [])
                    pairs = [(fld, n) for n in names]
                    action = _toggle_group_items(scope, pairs)
                    if action:
                        status_msg = f"{action} all {fld} in {pkg_name}"
                    continue

            # Item toggle
            if kind == ROW_ITEM and primary:
                fld = row["field"]
                name = row["name"]
                enabled_now = (fld, name) in scope["enabled"]
                _do_toggle(scope, fld, name, not enabled_now)
                status_msg = (
                    f"{'Enabled' if not enabled_now else 'Disabled'} {name} in {scope['label']}"
                )
                continue

            # File browsing (v/e/o)
            if kind == ROW_ITEM and registry_path and registry_dir:
                name = row["name"]
                if key == "v":
                    item_path = _resolve_item_path(registry_path, registry_dir, name)
                    if item_path:
                        live.stop()
                        _browse_files(item_path, initial_action="view")
                        live.start()
                    else:
                        status_msg = f"Not found: {registry_dir}/{name}"
                    continue
                if key == "e":
                    item_path = _resolve_item_path(registry_path, registry_dir, name)
                    if item_path:
                        live.stop()
                        _browse_files(item_path, initial_action="edit")
                        live.start()
                    else:
                        status_msg = f"Not found: {registry_dir}/{name}"
                    continue
                if key == "o":
                    item_path = _resolve_item_path(registry_path, registry_dir, name)
                    if item_path:
                        live.stop()
                        _open_in_finder(item_path)
                        status_msg = f"Opened {name} in file manager"
                        live.start()
                    else:
                        status_msg = f"Not found: {registry_dir}/{name}"
                    continue

            # Delete (d key on items — only when on_delete is provided and
            # extra_key_handler didn't handle it)
            if key == "d" and kind == ROW_ITEM and on_delete:
                fld = row["field"]
                name = row["name"]
                is_orphan = registry_items is not None and name not in registry_items
                live.stop()
                if is_orphan:
                    console.print(
                        f"\n[yellow]Remove [bold]{name}[/bold] (not in registry) from config?[/yellow] [dim](y/N)[/dim] ",
                        end="",
                    )
                else:
                    console.print(
                        f"\n[yellow]Delete [bold]{name}[/bold] from registry?[/yellow] [dim](y/N)[/dim] ",
                        end="",
                    )
                confirm = readchar.readkey()
                console.print()
                if confirm.lower() == "y":
                    if is_orphan or on_delete(fld, name):
                        # Remove from tree
                        for pkg in list(package_tree.keys()):
                            fm = package_tree[pkg]
                            if fld in fm and name in fm[fld]:
                                fm[fld].remove(name)
                        # Remove from all scopes
                        for s in scopes:
                            s["enabled"].discard((fld, name))
                        for ins in initial_sets:
                            ins.discard((fld, name))
                        status_msg = f"{'Removed' if is_orphan else 'Deleted'} {name}"
                        changed = True
                    else:
                        status_msg = f"Failed to delete {name}"
                live.start()
                continue

    return scopes, changed
