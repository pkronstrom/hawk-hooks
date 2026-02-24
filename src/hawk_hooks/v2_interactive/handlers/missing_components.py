"""Missing component handlers for the dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ... import v2_config
from ...types import ComponentType
from .. import dashboard as _dashboard

console = _dashboard.console
_COMPONENT_TYPE_BY_FIELD = _dashboard._COMPONENT_TYPE_BY_FIELD


def wait_for_continue(*args, **kwargs):
    return _dashboard.wait_for_continue(*args, **kwargs)


def warning_style(*args, **kwargs):
    return _dashboard.warning_style(*args, **kwargs)


def TerminalMenu(*args, **kwargs):
    return _dashboard.TerminalMenu(*args, **kwargs)


def terminal_menu_style_kwargs(*args, **kwargs):
    return _dashboard.terminal_menu_style_kwargs(*args, **kwargs)


def _iter_lock_packages(*args, **kwargs):
    return _dashboard._iter_lock_packages(*args, **kwargs)


def _remove_names_from_section(*args, **kwargs):
    return _dashboard._remove_names_from_section(*args, **kwargs)


def _find_package_lock_path(*args, **kwargs):
    return _dashboard._find_package_lock_path(*args, **kwargs)


def _install_from_package_lock(*args, **kwargs):
    return _dashboard._install_from_package_lock(*args, **kwargs)


def _remove_missing_references(*args, **kwargs):
    return _dashboard._remove_missing_references(*args, **kwargs)

def compute_missing_components(
    resolved_active: Any,
    contents: dict[ComponentType, list[str]],
) -> dict[str, list[str]]:
    """Compute missing component references for the active scope."""
    missing: dict[str, list[str]] = {}

    for field, component_type in _COMPONENT_TYPE_BY_FIELD.items():
        configured = list(dict.fromkeys(getattr(resolved_active, field, []) or []))
        if not configured:
            continue

        existing = set(contents.get(component_type, []))
        missing_names: list[str] = []
        for name in configured:
            if field == "mcp":
                if name in existing or f"{name}.yaml" in existing:
                    continue
            elif name in existing:
                continue
            missing_names.append(name)

        if missing_names:
            missing[field] = missing_names

    return missing

def find_package_lock_path(state: dict) -> Path | None:
    """Find a package lock file for the current scope."""
    candidates: list[Path] = []
    project_dir = state.get("project_dir")
    if project_dir is not None:
        candidates.extend([
            project_dir / ".hawk" / "packages.lock.yaml",
            project_dir / ".hawk" / "packages.lock.yml",
        ])

    config_dir = v2_config.get_config_dir()
    candidates.extend([
        config_dir / "packages.lock.yaml",
        config_dir / "packages.lock.yml",
    ])

    for path in candidates:
        if path.exists():
            return path
    return None


def iter_lock_packages(lock_data: Any) -> list[tuple[str, str | None]]:
    """Return a normalized list of (url, name) entries from lock data."""
    if not isinstance(lock_data, dict):
        return []
    packages = lock_data.get("packages", [])
    if not isinstance(packages, list):
        return []

    normalized: list[tuple[str, str | None]] = []
    for item in packages:
        if isinstance(item, str):
            url = item.strip()
            if url:
                normalized.append((url, None))
            continue
        if isinstance(item, dict):
            url = str(item.get("url") or item.get("source") or "").strip()
            if not url:
                continue
            name_raw = str(item.get("name") or "").strip()
            normalized.append((url, name_raw or None))
    return normalized


def install_from_package_lock(state: dict, lock_path: Path | None) -> bool:
    """Install packages listed in package lock.

    Returns True when any install attempt was executed.
    """
    if lock_path is None:
        console.print("\n[yellow]No package lock found.[/yellow]")
        console.print("[dim]Expected .hawk/packages.lock.yaml in project scope.[/dim]\n")
        wait_for_continue()
        return False

    import yaml
    from ...download_service import download_and_install

    try:
        data = yaml.safe_load(lock_path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        console.print(f"\n[red]Could not read package lock:[/red] {lock_path}\n")
        wait_for_continue()
        return False

    packages = _iter_lock_packages(data)
    if not packages:
        console.print(f"\n[yellow]No packages found in lock:[/yellow] {lock_path}\n")
        wait_for_continue()
        return False

    console.print(f"\n[bold]Installing from lock[/bold] [dim]({lock_path})[/dim]")
    attempted = 0
    for url, name in packages:
        result = download_and_install(
            url,
            select_all=True,
            replace=False,
            name=name,
            log=lambda msg: console.print(msg),
        )
        if result.success:
            attempted += 1

    if attempted <= 0:
        console.print("\n[yellow]No packages were installed from lock.[/yellow]\n")
        wait_for_continue()
        return False

    console.print(f"\n[green]\u2714 Installed {attempted} package(s) from lock.[/green]\n")
    wait_for_continue()
    return True


def remove_names_from_section(section: Any, names_to_remove: set[str]) -> tuple[Any, int]:
    """Remove names from a list-or-dict section and return (updated, removed_count)."""
    if isinstance(section, list):
        updated = [name for name in section if name not in names_to_remove]
        return updated, len(section) - len(updated)
    if isinstance(section, dict):
        enabled = section.get("enabled")
        if isinstance(enabled, list):
            updated = [name for name in enabled if name not in names_to_remove]
            removed = len(enabled) - len(updated)
            if removed > 0:
                section = dict(section)
                section["enabled"] = updated
            return section, removed
    return section, 0


def remove_missing_references(state: dict) -> tuple[bool, int]:
    """Remove missing references from active config layers."""
    missing_map = state.get("missing_components", {})
    if not missing_map:
        return False, 0

    total_removed = 0
    changed_any = False

    cfg = v2_config.load_global_config()
    global_section = cfg.get("global", {})

    # Global layer
    for field, names in missing_map.items():
        cleaned, removed = _remove_names_from_section(global_section.get(field, []), set(names))
        if removed > 0:
            global_section[field] = cleaned
            total_removed += removed
            changed_any = True
        if field == "prompts":
            cleaned_cmds, removed_cmds = _remove_names_from_section(global_section.get("commands", []), set(names))
            if removed_cmds > 0:
                global_section["commands"] = cleaned_cmds
                total_removed += removed_cmds
                changed_any = True
    cfg["global"] = global_section

    # Directory layers in scope chain
    project_dir = state.get("project_dir")
    chain_dirs: list[Path] = []
    if project_dir is not None:
        chain_dirs = [chain_dir for chain_dir, _ in v2_config.get_config_chain(project_dir)]
        if not chain_dirs and state.get("local_cfg") is not None:
            chain_dirs = [project_dir.resolve()]

    profile_names: set[str] = set()
    for chain_dir in chain_dirs:
        dir_cfg = v2_config.load_dir_config(chain_dir)
        if not isinstance(dir_cfg, dict):
            continue

        dir_changed = False
        for field, names in missing_map.items():
            section = dir_cfg.get(field, {})
            cleaned, removed = _remove_names_from_section(section, set(names))
            if removed > 0:
                dir_cfg[field] = cleaned
                total_removed += removed
                dir_changed = True
                changed_any = True

            if field == "prompts":
                legacy = dir_cfg.get("commands", {})
                cleaned_legacy, removed_legacy = _remove_names_from_section(legacy, set(names))
                if removed_legacy > 0:
                    dir_cfg["commands"] = cleaned_legacy
                    total_removed += removed_legacy
                    dir_changed = True
                    changed_any = True

        if dir_changed:
            v2_config.save_dir_config(chain_dir, dir_cfg)

        profile_name = dir_cfg.get("profile")
        if not profile_name:
            entry = cfg.get("directories", {}).get(str(chain_dir.resolve()), {})
            profile_name = entry.get("profile")
        if profile_name:
            profile_names.add(str(profile_name))

    # Profile layers referenced by current chain
    for profile_name in profile_names:
        profile_cfg = v2_config.load_profile(profile_name)
        if not isinstance(profile_cfg, dict):
            continue

        profile_changed = False
        for field, names in missing_map.items():
            cleaned, removed = _remove_names_from_section(profile_cfg.get(field, []), set(names))
            if removed > 0:
                profile_cfg[field] = cleaned
                total_removed += removed
                profile_changed = True
                changed_any = True
            if field == "prompts":
                cleaned_cmds, removed_cmds = _remove_names_from_section(profile_cfg.get("commands", []), set(names))
                if removed_cmds > 0:
                    profile_cfg["commands"] = cleaned_cmds
                    total_removed += removed_cmds
                    profile_changed = True
                    changed_any = True

        if profile_changed:
            v2_config.save_profile(profile_name, profile_cfg)

    if changed_any:
        v2_config.save_global_config(cfg)

    return changed_any, total_removed


def handle_missing_components_setup(state: dict) -> bool:
    """Resolve missing component references via one-time setup flow."""
    missing_map = state.get("missing_components", {})
    missing_total = int(state.get("missing_components_total", 0))
    if not missing_map or missing_total <= 0:
        return False

    lock_path = _find_package_lock_path(state)
    lock_hint = str(lock_path) if lock_path else "(not found)"

    lines = [
        "[bold]Resolve missing components[/bold]",
        "",
        "These items are enabled in config but missing from your local registry.",
        f"Missing references: [yellow]{missing_total}[/yellow]",
        "",
        "[dim]A package lock is a file that lists package sources to reinstall on this machine.[/dim]",
        f"[dim]Package lock path: {lock_hint}[/dim]",
        "",
        "[cyan]Install from package lock[/cyan]: reinstall package components listed in the lock.",
        "[green]Remove missing references[/green]: clean stale names from active configs.",
        "[yellow]Ignore for now[/yellow]: keep current state.",
    ]
    if missing_map:
        lines.extend(["", "[bold]Missing item names:[/bold]"])
        field_labels = {
            "skills": "Skills",
            "hooks": "Hooks",
            "prompts": "Prompts",
            "agents": "Agents",
            "mcp": "MCP",
        }
        for field, label in field_labels.items():
            names = list(missing_map.get(field, []))
            if not names:
                continue
            lines.append(f"  - {label}: {', '.join(sorted(names))}")

    console.print()
    warn_start, warn_end = warning_style(True)
    console.print(f"{warn_start}One-time setup{warn_end}")
    console.print("[dim]" + ("\u2500" * 50) + "[/dim]")
    console.print("\n".join(lines))

    option_install = "Install from package lock"
    if lock_path is None:
        option_install = "Install from package lock (not found)"

    menu = TerminalMenu(
        [option_install, "Remove missing references", "Ignore for now"],
        title="\nChoose an option",
        cursor_index=1,
        menu_cursor="\u276f ",
        **terminal_menu_style_kwargs(),
        quit_keys=("q", "\x1b"),
    )
    choice = menu.show()
    if choice is None or choice == 2:
        return False

    if choice == 0:
        return _install_from_package_lock(state, lock_path)

    changed, removed = _remove_missing_references(state)
    if changed:
        console.print(f"\n[green]\u2714 Removed {removed} missing reference(s).[/green]\n")
    else:
        console.print("\n[yellow]No missing references were removed.[/yellow]\n")
    wait_for_continue()
    return changed
