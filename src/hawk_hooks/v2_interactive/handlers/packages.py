"""Package management handlers for the dashboard."""

from __future__ import annotations

from pathlib import Path

import readchar

from ... import v2_config
from ...types import ComponentType
from .. import dashboard as _dashboard
from ..toggle import _browse_files, _open_in_finder

console = _dashboard.console
_ORDERED_COMPONENT_FIELDS = _dashboard._ORDERED_COMPONENT_FIELDS


def wait_for_continue(*args, **kwargs):
    return _dashboard.wait_for_continue(*args, **kwargs)


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


from ..toggle import (  # noqa: F401 — re-exported for backward compat
    ROW_ITEM,
    ROW_PACKAGE,
    ROW_SEPARATOR,
    ROW_TYPE,
    UNGROUPED,
    run_picker,
)


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
            "label": "Global (default)",
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
                    label = f"This project: {chain_dir.name}"
                else:
                    label = f"{chain_dir.name}"
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
                    "label": f"This project: {project_name}",
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

    # ── Callbacks for run_picker ──

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

            if key == "v":
                item_path = registry.get_path(ct, name)
                if item_path is not None:
                    live.stop()
                    _browse_files(item_path, initial_action="view")
                    live.start()
                return True, ""

            if key == "e":
                item_path = registry.get_path(ct, name)
                if item_path is not None:
                    live.stop()
                    if not _run_editor_command(item_path):
                        console.print(f"\n[red]Could not open {item_path} in $EDITOR[/red]")
                        wait_for_continue()
                    live.start()
                return True, ""

            if key == "o":
                item_path = registry.get_path(ct, name)
                if item_path is not None:
                    live.stop()
                    _open_in_finder(item_path)
                    live.start()
                    return True, f"Opened {name} in file manager"
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
            return "\u21b5 expand · t toggle · u update · d/x remove · U upd all"
        elif current_kind == ROW_TYPE:
            return "\u21b5 expand · t toggle all"
        elif current_kind == ROW_ITEM:
            return "\u21b5 toggle · t group · v view · e edit · o open · d del · U upd all"
        else:
            return "\u21b5 select · U upd all"

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

    run_picker(
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
