"""Registry browser handler for the dashboard."""

from __future__ import annotations

from pathlib import Path

from ... import v2_config
from ...types import ComponentType
from .. import dashboard as _dashboard

console = _dashboard.console


def TerminalMenu(*args, **kwargs):
    return _dashboard.TerminalMenu(*args, **kwargs)


def terminal_menu_style_kwargs(*args, **kwargs):
    return _dashboard.terminal_menu_style_kwargs(*args, **kwargs)


def wait_for_continue(*args, **kwargs):
    return _dashboard.wait_for_continue(*args, **kwargs)


def _human_size(*args, **kwargs):
    return _dashboard._human_size(*args, **kwargs)


def _path_size(*args, **kwargs):
    return _dashboard._path_size(*args, **kwargs)


def _run_editor_command(*args, **kwargs):
    return _dashboard._run_editor_command(*args, **kwargs)

def handle_registry_browser(state: dict) -> None:
    """Read-only registry browser with grouped rows and open-in-editor."""
    registry = state["registry"]
    contents = state["contents"]
    item_types = [ComponentType.SKILL, ComponentType.HOOK, ComponentType.PROMPT, ComponentType.AGENT, ComponentType.MCP, ComponentType.COMMAND]

    if not any(contents.get(ct, []) for ct in item_types):
        console.print("\n[dim]Registry is empty.[/dim]")
        wait_for_continue()
        return

    rows: list[str | None] = []
    row_items: list[tuple[ComponentType, str, Path] | None] = []

    rows.append("name                         type      package            size")
    row_items.append(None)
    rows.append("────────────────────────────────────────────────────────────────")
    row_items.append(None)

    for ct in item_types:
        names = contents.get(ct, [])
        if not names:
            continue
        rows.append(f"{ct.registry_dir}/ ({len(names)})")
        row_items.append(None)

        for name in names:
            item_path = registry.get_path(ct, name)
            if item_path is None:
                continue
            pkg = v2_config.get_package_for_item(ct.value, name) or "-"
            size_label = _human_size(_path_size(item_path))
            pkg_short = pkg if len(pkg) <= 16 else (pkg[:13] + "...")
            name_short = name if len(name) <= 28 else (name[:25] + "...")
            rows.append(f"  {name_short:<28} {ct.value:<9} {pkg_short:<16} {size_label:>8}")
            row_items.append((ct, name, item_path))

    rows.append("────────────────────────────────────────────────────────────────")
    row_items.append(None)
    rows.append("Back")
    row_items.append(None)

    menu = TerminalMenu(
        rows,
        title="\nRegistry Browser\n────────────────────────────────────────",
        menu_cursor="\u203a ",
        **terminal_menu_style_kwargs(include_status_bar=True),
        quit_keys=("q", "\x1b"),
        status_bar="↵ open ($EDITOR) · q/esc back",
    )

    while True:
        choice = menu.show()
        if choice is None:
            break

        selected = rows[choice]
        if selected == "Back":
            break

        item = row_items[choice]
        if item is None:
            continue
        _, _, item_path = item
        if not _run_editor_command(item_path):
            console.print(f"\n[red]Could not open {item_path} in $EDITOR[/red]")
            wait_for_continue()

