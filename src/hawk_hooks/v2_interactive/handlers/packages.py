"""Package management handlers for the dashboard."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import readchar
from rich.live import Live
from rich.text import Text

from ... import v2_config
from ...types import ComponentType
from .. import dashboard as _dashboard

console = _dashboard.console
_ORDERED_COMPONENT_FIELDS = _dashboard._ORDERED_COMPONENT_FIELDS


def TerminalMenu(*args, **kwargs):
    return _dashboard.TerminalMenu(*args, **kwargs)


def wait_for_continue(*args, **kwargs):
    return _dashboard.wait_for_continue(*args, **kwargs)


def terminal_menu_style_kwargs(*args, **kwargs):
    return _dashboard.terminal_menu_style_kwargs(*args, **kwargs)


def cursor_prefix(*args, **kwargs):
    return _dashboard.cursor_prefix(*args, **kwargs)


def scoped_header(*args, **kwargs):
    return _dashboard.scoped_header(*args, **kwargs)


def dim_separator(*args, **kwargs):
    return _dashboard.dim_separator(*args, **kwargs)


def warning_style(*args, **kwargs):
    return _dashboard.warning_style(*args, **kwargs)


def enabled_count_style(*args, **kwargs):
    return _dashboard.enabled_count_style(*args, **kwargs)


def row_style(*args, **kwargs):
    return _dashboard.row_style(*args, **kwargs)


def action_style(*args, **kwargs):
    return _dashboard.action_style(*args, **kwargs)


def _run_editor_command(*args, **kwargs):
    return _dashboard._run_editor_command(*args, **kwargs)


def _confirm_registry_item_delete(*args, **kwargs):
    return _dashboard._confirm_registry_item_delete(*args, **kwargs)


def confirm_registry_item_delete(ct: ComponentType, name: str) -> bool:
    """Ask for confirmation before deleting an item from registry."""
    console.print(
        f"\n[yellow]Delete {ct.registry_dir}/{name} from registry?[/yellow] [dim](y/N)[/dim] ",
        end="",
    )
    confirm = readchar.readkey()
    console.print()
    return confirm.lower() == "y"


# ---------------------------------------------------------------------------
# Row kind constants shared by run_three_tier_picker and handle_packages
# ---------------------------------------------------------------------------
ROW_PACKAGE = "package"
ROW_TYPE = "type"
ROW_ITEM = "item"
ROW_SEPARATOR = "separator"
ROW_ACTION = "action"
ACTION_DONE = "__done__"
UNGROUPED = "__ungrouped__"


# ---------------------------------------------------------------------------
# Reusable three-tier picker
# ---------------------------------------------------------------------------

def run_three_tier_picker(
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
) -> tuple[list[dict], bool]:
    """Three-tier picker: packages -> types -> items.

    Args:
        title: Header title (e.g. "Packages", "Components").
        package_tree: {pkg_name: {field: [item_names]}}.
        package_order: Display order of package names.
        field_labels: {field: "Human Label"} for type rows.
        scopes: [{key, label, enabled: set[(field, name)]}].
        start_scope_index: Which scope to start on.
        packages_meta: Package index data for URL display.
        collapsed_packages: Mutable dict of pkg->collapsed state (created if None).
        collapsed_types: Mutable dict of (pkg,field)->collapsed state (created if None).
        on_toggle: (scope_key, field, name, enabled) -> None. Called on item toggle.
        on_rebuild: () -> (package_order, package_tree, scopes). Called to refresh data.
        extra_key_handler: (key, row, scope, live) -> (handled, status_msg).
        extra_hints: (row_kind) -> str | None. Extra hint text per row kind.
        action_label: Label for the Done/Save action button.
        scope_hint: Shown when only 1 scope and no scope_hint provided.

    Returns:
        (final_scopes, changed) — the scopes list with updated enabled sets, and
        whether any toggle happened.
    """
    if collapsed_packages is None:
        collapsed_packages = {}
    if collapsed_types is None:
        collapsed_types = {}
    if packages_meta is None:
        packages_meta = {}

    # Ordered fields from field_labels (preserve insertion order)
    ordered_fields = list(field_labels.keys())

    cursor = 0
    scroll_offset = 0
    scope_index = start_scope_index
    status_msg = ""
    changed = False

    def _build_rows() -> list[dict]:
        rows: list[dict] = []
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

            for field in ordered_fields:
                names = field_map.get(field, [])
                if not names:
                    continue
                label = field_labels.get(field, field.title())
                rows.append({
                    "kind": ROW_TYPE,
                    "package": pkg_name,
                    "field": field,
                    "label": label,
                    "count": len(names),
                })

                if collapsed_types.get((pkg_name, field), True):
                    continue

                for name in names:
                    rows.append({
                        "kind": ROW_ITEM,
                        "package": pkg_name,
                        "field": field,
                        "name": name,
                    })

        rows.append({"kind": ROW_SEPARATOR})
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

    def _terminal_height() -> int:
        try:
            return os.get_terminal_size().lines
        except OSError:
            return 24

    def _update_scroll(total: int, idx: int, max_visible: int, offset: int) -> int:
        if total <= 0 or max_visible <= 0:
            return 0
        if idx < offset:
            offset = idx
        elif idx >= offset + max_visible:
            offset = idx - max_visible + 1
        max_offset = max(0, total - max_visible)
        return max(0, min(offset, max_offset))

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
        checked = scope["enabled"]
        next_scope = scopes_[(scope_index + 1) % len(scopes_)]["label"] if len(scopes_) > 1 else ""
        package_count = len([p for p in package_order if p != UNGROUPED])
        ungrouped_count = sum(len(names) for names in package_tree.get(UNGROUPED, {}).values())

        lines: list[str] = [scoped_header(title, scope["label"])]
        if len(scopes_) > 1:
            lines[0] += f"    [dim]\\[Tab: {next_scope}][/dim]"
        elif scope_hint:
            lines[0] += f" [dim]\u2014 {scope_hint}[/dim]"
        if ungrouped_count > 0:
            lines.append(f"[dim]Packages: {package_count}  |  Ungrouped items: {ungrouped_count}[/dim]")
        else:
            lines.append(f"[dim]Packages: {package_count}[/dim]")
        lines.append(dim_separator())

        total_rows = len(rows)
        max_visible = max(8, _terminal_height() - 10)
        scroll_offset = _update_scroll(total_rows, cursor, max_visible, scroll_offset)
        vis_start = scroll_offset
        vis_end = min(total_rows, vis_start + max_visible)

        if vis_start > 0:
            lines.append(f"[dim]  \u2191 {vis_start} more[/dim]")

        for i in range(vis_start, vis_end):
            row = rows[i]
            kind = row["kind"]
            is_cur = i == cursor
            prefix = cursor_prefix(is_cur)
            cols = _term_cols()

            if kind == ROW_PACKAGE:
                pkg_name = row["package"]
                is_ungrouped = row["is_ungrouped"]
                collapsed = collapsed_packages.get(pkg_name, False)
                arrow = "\u25b6" if collapsed else "\u25bc"
                icon = "\U0001f4c1" if is_ungrouped else "\U0001f4e6"
                label = "Ungrouped (not in package)" if is_ungrouped else pkg_name
                pkg_items = package_tree.get(pkg_name, {})
                enabled_count = sum(
                    1
                    for field, names in pkg_items.items()
                    for name in names
                    if (field, name) in checked
                )
                suffix = f" ({enabled_count}/{row['count']}) {arrow}"
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
                    f"[{count_style}]({enabled_count}/{row['count']})[/{count_style}] {arrow}{end}"
                )

                if not is_ungrouped and not collapsed:
                    url = str(packages_meta.get(pkg_name, {}).get("url", "")).strip()
                    if url:
                        lines.append(f"      [dim]{url}[/dim]")

            elif kind == ROW_TYPE:
                pkg_name = row["package"]
                field = row["field"]
                collapsed = collapsed_types.get((pkg_name, field), True)
                arrow = "\u25b6" if collapsed else "\u25bc"
                names = package_tree.get(pkg_name, {}).get(field, [])
                enabled_count = sum(1 for name in names if (field, name) in checked)
                total_count = len(names)
                suffix = f" ({enabled_count}/{total_count}) {arrow}"
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
                    f"{prefix}    {style}{label} "
                    f"[{count_style}]({enabled_count}/{total_count})[/{count_style}] {arrow}{end}"
                )

            elif kind == ROW_ITEM:
                field = row["field"]
                name = row["name"]
                enabled = (field, name) in checked
                if enabled:
                    mark = "\u25cf"
                else:
                    mark = "[dim]\u25cb[/dim]"
                if is_cur:
                    if enabled:
                        lines.append(f"{prefix}      {mark} [bold white]{name}[/bold white]")
                    else:
                        lines.append(f"{prefix}      {mark} [bold dim]{name}[/bold dim]")
                else:
                    if enabled:
                        lines.append(f"{prefix}      {mark} [white]{name}[/white]")
                    else:
                        lines.append(f"{prefix}      {mark} [dim]{name}[/dim]")

            elif kind == ROW_SEPARATOR:
                lines.append(f"  {dim_separator(9)}")

            elif kind == ROW_ACTION:
                style, end = action_style(is_cur)
                lines.append(f"{prefix}{style}{row['label']}{end}")

        if vis_end < total_rows:
            lines.append(f"[dim]  \u2193 {total_rows - vis_end} more[/dim]")

        if status_msg:
            lines.append(f"\n[dim]{status_msg}[/dim]")

        current_kind = rows[cursor]["kind"] if rows else ROW_ACTION
        lines.append("")
        if extra_hints:
            hints = extra_hints(current_kind)
        else:
            if current_kind == ROW_PACKAGE:
                hints = "space/\u21b5 expand · t toggle all"
            elif current_kind == ROW_TYPE:
                hints = "space/\u21b5 expand · t toggle all"
            elif current_kind == ROW_ITEM:
                hints = "space/\u21b5 toggle · t toggle group"
            else:
                hints = "space/\u21b5 select"
        if len(scopes_) > 1:
            hints += " · tab scope"
        hints += " · \u2191\u2193/jk nav · q/esc/^C back"
        lines.append(f"[dim]{hints}[/dim]")
        return "\n".join(lines)

    def _do_toggle(scope: dict, field: str, name: str, enable: bool) -> None:
        nonlocal changed
        if enable:
            scope["enabled"].add((field, name))
        else:
            scope["enabled"].discard((field, name))
        changed = True
        if on_toggle:
            on_toggle(scope["key"], field, name, enable)

    def _toggle_group_items(scope: dict, pairs: list[tuple[str, str]]) -> str:
        """Toggle a list of (field, name) pairs. Returns status message."""
        if not pairs:
            return ""
        all_enabled = all((f, n) in scope["enabled"] for f, n in pairs)
        for f, n in pairs:
            _do_toggle(scope, f, n, not all_enabled)
        return "Disabled" if all_enabled else "Enabled"

    with Live("", console=console, refresh_per_second=15, screen=True) as live:
        while True:
            # Allow caller to rebuild data (e.g. after external mutations)
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

            if kind == ROW_ACTION and primary:
                break

            if kind == ROW_PACKAGE:
                pkg_name = row["package"]
                if primary:
                    collapsed_packages[pkg_name] = not collapsed_packages.get(pkg_name, False)
                    continue

            if kind == ROW_TYPE and primary:
                pkg_name = row["package"]
                field = row["field"]
                key_id = (pkg_name, field)
                collapsed_types[key_id] = not collapsed_types.get(key_id, True)
                continue

            # Toggle all items in a package or type group
            if key == "t":
                if kind == ROW_PACKAGE:
                    pkg_name = row["package"]
                    pkg_items = package_tree.get(pkg_name, {})
                    all_pairs = [(f, n) for f, names in pkg_items.items() for n in names]
                    action = _toggle_group_items(scope, all_pairs)
                    if action:
                        label = "ungrouped" if row["is_ungrouped"] else pkg_name
                        status_msg = f"{action} all in {label}"
                    continue
                if kind == ROW_TYPE:
                    pkg_name = row["package"]
                    field = row["field"]
                    names = package_tree.get(pkg_name, {}).get(field, [])
                    pairs = [(field, n) for n in names]
                    action = _toggle_group_items(scope, pairs)
                    if action:
                        status_msg = f"{action} all {row['label']} in {pkg_name}"
                    continue
                if kind == ROW_ITEM:
                    pkg_name = row["package"]
                    field = row["field"]
                    names = package_tree.get(pkg_name, {}).get(field, [])
                    pairs = [(field, n) for n in names]
                    action = _toggle_group_items(scope, pairs)
                    if action:
                        status_msg = f"{action} all {field} in {pkg_name}"
                    continue

            if kind == ROW_ITEM and primary:
                field = row["field"]
                name = row["name"]
                enabled_now = (field, name) in scope["enabled"]
                _do_toggle(scope, field, name, not enabled_now)
                status_msg = (
                    f"{'Enabled' if not enabled_now else 'Disabled'} {name} in {scope['label']}"
                )
                continue

    return scopes, changed


# ---------------------------------------------------------------------------
# Dashboard packages handler
# ---------------------------------------------------------------------------

def handle_packages(state: dict) -> bool:
    """Unified package-first registry view with package/type/item accordions."""
    from ...package_service import (
        PackageNotFoundError,
        PackageServiceError,
        remove_ungrouped_items,
        update_packages,
        remove_package,
    )

    packages = v2_config.load_packages()
    registry = state["registry"]
    dirty = False

    ordered_types: list[tuple[str, str, ComponentType]] = list(_ORDERED_COMPONENT_FIELDS)
    fields = [f for f, _, _ in ordered_types]
    field_to_ct = {f: ct for f, _, ct in ordered_types}
    ct_to_field = {ct.value: f for f, _, ct in ordered_types}

    collapsed_packages: dict[str, bool] = {}
    collapsed_types: dict[tuple[str, str], bool] = {}

    def _reload_state_config() -> None:
        cfg = v2_config.load_global_config()
        state["cfg"] = cfg
        state["global_cfg"] = cfg.get("global", {})
        project_dir = state.get("project_dir")
        if project_dir:
            state["local_cfg"] = v2_config.load_dir_config(project_dir) or {}
        else:
            state["local_cfg"] = None

    def _refresh_contents() -> None:
        nonlocal packages
        packages = v2_config.load_packages()
        state["contents"] = registry.list()

    def _build_scope_entries() -> list[dict]:
        scopes: list[dict] = []

        global_enabled: set[tuple[str, str]] = set()
        for field in fields:
            for name in state["global_cfg"].get(field, []):
                global_enabled.add((field, name))
        scopes.append({
            "key": "global",
            "label": "\U0001f310 Global (default)",
            "enabled": global_enabled,
        })

        project_dir = state.get("project_dir") or Path.cwd().resolve()
        config_chain = v2_config.get_config_chain(project_dir)
        if config_chain:
            for chain_dir, chain_config in config_chain:
                enabled: set[tuple[str, str]] = set()
                for field in fields:
                    section = chain_config.get(field, {})
                    if isinstance(section, dict):
                        names = section.get("enabled", [])
                    elif isinstance(section, list):
                        names = section
                    else:
                        names = []
                    for name in names:
                        enabled.add((field, name))

                if chain_dir == project_dir.resolve():
                    label = f"\U0001f4cd This project: {chain_dir.name}"
                else:
                    label = f"\U0001f4c1 {chain_dir.name}"
                scopes.append({"key": str(chain_dir), "label": label, "enabled": enabled})
        else:
            local_cfg = state.get("local_cfg")
            if local_cfg is not None:
                enabled: set[tuple[str, str]] = set()
                for field in fields:
                    section = local_cfg.get(field, {})
                    if isinstance(section, dict):
                        names = section.get("enabled", [])
                    elif isinstance(section, list):
                        names = section
                    else:
                        names = []
                    for name in names:
                        enabled.add((field, name))

                project_name = state.get("project_name") or project_dir.name
                scopes.append({
                    "key": str(project_dir),
                    "label": f"\U0001f4cd This project: {project_name}",
                    "enabled": enabled,
                })

        return scopes

    def _set_item_enabled(scope_key: str, field: str, name: str, enabled: bool) -> None:
        if scope_key == "global":
            current = list(state["global_cfg"].get(field, []))
            if enabled and name not in current:
                current.append(name)
            elif not enabled:
                current = [n for n in current if n != name]
            state["global_cfg"][field] = current
            cfg = state["cfg"]
            cfg["global"] = state["global_cfg"]
            v2_config.save_global_config(cfg)
            state["cfg"] = cfg
            return

        dir_path = Path(scope_key)
        dir_cfg = v2_config.load_dir_config(dir_path) or {}
        section = dir_cfg.get(field, {})
        if not isinstance(section, dict):
            section = {"enabled": list(section) if isinstance(section, list) else []}

        current = list(section.get("enabled", []))
        if enabled and name not in current:
            current.append(name)
        elif not enabled:
            current = [n for n in current if n != name]

        section["enabled"] = current
        dir_cfg[field] = section
        v2_config.save_dir_config(dir_path, dir_cfg)

        project_dir = state.get("project_dir")
        if project_dir and dir_path.resolve() == Path(project_dir).resolve():
            state["local_cfg"] = dir_cfg

    def _build_package_tree() -> tuple[list[str], dict[str, dict[str, list[str]]]]:
        package_tree: dict[str, dict[str, list[str]]] = {
            pkg_name: {field: [] for field in fields}
            for pkg_name in sorted(packages.keys())
        }

        ownership: dict[tuple[str, str], str] = {}
        for pkg_name, pkg_data in packages.items():
            for item in pkg_data.get("items", []):
                comp_type = item.get("type")
                item_name = item.get("name")
                if not isinstance(comp_type, str) or not isinstance(item_name, str):
                    continue
                field = ct_to_field.get(comp_type)
                if field:
                    ownership[(field, item_name)] = pkg_name

        ungrouped_has_items = False
        for field, _, ct in ordered_types:
            for name in sorted(state["contents"].get(ct, [])):
                pkg_name = ownership.get((field, name), UNGROUPED)
                if pkg_name not in package_tree:
                    package_tree[pkg_name] = {f: [] for f in fields}
                package_tree[pkg_name][field].append(name)
                if pkg_name == UNGROUPED:
                    ungrouped_has_items = True

        package_order = [p for p in sorted(package_tree.keys()) if p != UNGROUPED]
        if UNGROUPED in package_tree and (ungrouped_has_items or any(package_tree[UNGROUPED].values())):
            package_order.append(UNGROUPED)

        return package_order, package_tree

    # ── Callbacks for run_three_tier_picker ──

    def _on_toggle(scope_key: str, field: str, name: str, enabled: bool) -> None:
        nonlocal dirty
        _set_item_enabled(scope_key, field, name, enabled)
        dirty = True
        _reload_state_config()

    def _on_rebuild():
        _refresh_contents()
        package_order, package_tree = _build_package_tree()
        scopes = _build_scope_entries()
        return package_order, package_tree, scopes

    def _extra_key_handler(key, row, scope, live):
        nonlocal dirty
        kind = row["kind"]

        if key == "U":
            live.stop()
            console.print("\n[bold]Updating all packages...[/bold]")
            try:
                update_packages(
                    package=None,
                    check=False,
                    force=False,
                    prune=False,
                    sync_on_change=True,
                    log=console.print,
                )
            except PackageServiceError:
                pass
            console.print()
            console.print("[dim]Press any key to continue...[/dim]")
            readchar.readkey()
            _reload_state_config()
            _refresh_contents()
            live.start()
            return True, ""

        if kind == ROW_PACKAGE:
            pkg_name = row["package"]
            is_ungrouped = row["is_ungrouped"]

            if key == "u":
                if is_ungrouped:
                    return True, "Ungrouped has no package source to update."

                live.stop()
                console.print(f"\n[bold]Updating {pkg_name}...[/bold]")
                try:
                    update_packages(
                        package=pkg_name,
                        check=False,
                        force=False,
                        prune=False,
                        sync_on_change=True,
                        log=console.print,
                    )
                except PackageNotFoundError:
                    console.print(f"[yellow]Package not found:[/yellow] {pkg_name}")
                except PackageServiceError:
                    pass
                console.print()
                console.print("[dim]Press any key to continue...[/dim]")
                readchar.readkey()
                _reload_state_config()
                _refresh_contents()
                live.start()
                return True, ""

            if key in ("x", "d"):
                live.stop()
                if is_ungrouped:
                    console.print(
                        "\n[yellow]Remove all ungrouped items?[/yellow] [dim](y/N)[/dim] ",
                        end="",
                    )
                else:
                    console.print(
                        f"\n[yellow]Remove package '{pkg_name}'?[/yellow] [dim](y/N)[/dim] ",
                        end="",
                    )
                confirm = readchar.readkey()
                console.print()
                if confirm.lower() == "y":
                    if is_ungrouped:
                        try:
                            remove_ungrouped_items(sync_after=True, log=console.print)
                        except PackageServiceError:
                            pass
                    else:
                        try:
                            remove_package(pkg_name, sync_after=True, log=console.print)
                        except PackageNotFoundError:
                            console.print(f"[yellow]Package not found:[/yellow] {pkg_name}")
                        except PackageServiceError:
                            pass
                    console.print()
                    console.print("[dim]Press any key to continue...[/dim]")
                    readchar.readkey()
                _reload_state_config()
                _refresh_contents()
                live.start()
                return True, ""

        if kind == ROW_ITEM:
            field = row["field"]
            name = row["name"]
            ct = field_to_ct[field]

            if key == "e":
                item_path = registry.get_path(ct, name)
                if item_path is not None:
                    live.stop()
                    if not _run_editor_command(item_path):
                        console.print(f"\n[red]Could not open {item_path} in $EDITOR[/red]")
                        wait_for_continue()
                    live.start()
                return True, ""

            if key == "d":
                live.stop()
                if not _confirm_registry_item_delete(ct, name):
                    live.start()
                    return True, f"Delete cancelled for {ct.registry_dir}/{name}."

                removed = registry.remove(ct, name)
                if removed:
                    dirty = True
                    state["contents"] = registry.list()
                    live.start()
                    return True, f"Removed {ct.registry_dir}/{name} from registry."
                else:
                    live.start()
                    return True, f"Could not remove {ct.registry_dir}/{name}."

        return False, ""

    def _extra_hints(current_kind):
        if current_kind == ROW_PACKAGE:
            return "space/\u21b5 expand · t toggle all · u update pkg · d/x remove pkg · U update all"
        elif current_kind == ROW_TYPE:
            return "space/\u21b5 expand · t toggle all"
        elif current_kind == ROW_ITEM:
            return "space/\u21b5 toggle · t toggle group · e open · d remove item · U update all"
        else:
            return "space/\u21b5 select · U update all"

    # ── Setup and run ──

    _reload_state_config()
    _refresh_contents()
    package_order, package_tree = _build_package_tree()
    has_registry_items = any(
        state["contents"].get(ct, [])
        for _field, _label, ct in ordered_types
    )
    if not packages and not has_registry_items:
        console.print("\n[dim]No packages or ungrouped registry items found.[/dim]")
        console.print("[dim]Run [cyan]hawk download <url>[/cyan] to install a package.[/dim]\n")
        wait_for_continue()
        return False

    field_labels = {f: label for f, label, _ in ordered_types}
    scopes = _build_scope_entries()

    show_scope_hint = len(scopes) == 1 and state.get("local_cfg") is None

    run_three_tier_picker(
        "Packages",
        package_tree,
        package_order,
        field_labels,
        scopes,
        start_scope_index=0,
        packages_meta=packages,
        collapsed_packages=collapsed_packages,
        collapsed_types=collapsed_types,
        on_toggle=_on_toggle,
        on_rebuild=_on_rebuild,
        extra_key_handler=_extra_key_handler,
        extra_hints=_extra_hints,
        action_label="Done",
        scope_hint="run 'hawk init' for local scope" if show_scope_hint else None,
    )

    return dirty
