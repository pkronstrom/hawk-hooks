"""Main dashboard and menu for hawk v2 TUI."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

import readchar
from rich.console import Console
from rich.live import Live
from rich.text import Text
from simple_term_menu import TerminalMenu

from .. import __version__, v2_config
from ..adapters import get_adapter
from ..registry import Registry
from ..resolver import resolve
from ..scope_resolution import build_resolver_dir_chain
from ..types import ComponentType, ToggleGroup, ToggleScope, Tool
from .pause import wait_for_continue
from .theme import (
    action_style,
    cursor_prefix,
    dim_separator,
    enabled_count_style,
    row_style,
    scoped_header,
    set_project_theme,
    terminal_menu_style_kwargs,
    warning_style,
)
from .toggle import _open_in_editor, run_toggle_list
from .uninstall_flow import run_uninstall_wizard

console = Console(highlight=False)

# Component types shown in the menu, in order
COMPONENT_TYPES = [
    ("Skills", "skills", ComponentType.SKILL),
    ("Hooks", "hooks", ComponentType.HOOK),
    ("Prompts", "prompts", ComponentType.PROMPT),
    ("Agents", "agents", ComponentType.AGENT),
    ("MCP Servers", "mcp", ComponentType.MCP),
]
_ORDERED_COMPONENT_FIELDS: list[tuple[str, str, ComponentType]] = [
    (field, label, ct) for label, field, ct in COMPONENT_TYPES
]

_CODEX_CONSENT_OPTIONS = {"ask", "granted", "denied"}

_COMPONENT_TYPE_BY_FIELD: dict[str, ComponentType] = {
    field: ct for field, _label, ct in _ORDERED_COMPONENT_FIELDS
}


def _detect_scope(scope_dir: str | None = None) -> tuple[str, Path | None, str | None]:
    """Detect whether cwd is a hawk-initialized directory.

    Returns:
        (scope, project_dir, project_name)
        scope is "local" or "global"
    """
    cwd = Path(scope_dir).resolve() if scope_dir else Path.cwd().resolve()
    dir_config = v2_config.load_dir_config(cwd)
    if dir_config is not None:
        return "local", cwd, cwd.name

    nearest = v2_config.get_nearest_registered_directory(cwd)
    if nearest is not None:
        return "local", nearest, nearest.name

    return "global", None, None


def _load_state(scope_dir: str | None = None) -> dict:
    """Load all state needed for the dashboard."""
    from ..v2_sync import count_unsynced_targets

    cfg = v2_config.load_global_config()
    registry = Registry(v2_config.get_registry_path(cfg))
    contents = registry.list()

    scope, project_dir, project_name = _detect_scope(scope_dir)

    # Load enabled lists
    global_cfg = cfg.get("global", {})

    local_cfg = None
    if project_dir:
        local_cfg = v2_config.load_dir_config(project_dir) or {}

    resolved_global = resolve(cfg)
    resolved_active = resolved_global
    if project_dir:
        dir_chain = build_resolver_dir_chain(project_dir, cfg=cfg)
        if dir_chain:
            resolved_active = resolve(cfg, dir_chain=dir_chain)

    # Detect tools
    tools_status = {}
    for tool in Tool.all():
        adapter = get_adapter(tool)
        installed = adapter.detect_installed()
        tool_cfg = cfg.get("tools", {}).get(str(tool), {})
        enabled = tool_cfg.get("enabled", True)
        tools_status[tool] = {"installed": installed, "enabled": enabled}

    unsynced_targets, sync_targets_total = count_unsynced_targets(
        project_dir=project_dir if scope == "local" else None,
        include_global=True,
        only_installed=True,
    )

    codex_consent = _get_codex_multi_agent_consent(cfg)
    missing_components = _compute_missing_components(resolved_active, contents)
    missing_components_total = sum(len(names) for names in missing_components.values())

    return {
        "cfg": cfg,
        "registry": registry,
        "contents": contents,
        "scope": scope,
        "project_dir": project_dir,
        "project_name": project_name,
        "global_cfg": global_cfg,
        "local_cfg": local_cfg,
        "resolved_global": resolved_global,
        "resolved_active": resolved_active,
        "tools_status": tools_status,
        "unsynced_targets": unsynced_targets,
        "sync_targets_total": sync_targets_total,
        "scope_dir": scope_dir,
        "codex_multi_agent_consent": codex_consent,
        "codex_multi_agent_required": (
            tools_status.get(Tool.CODEX, {}).get("enabled", True)
            and len(getattr(resolved_active, "agents", [])) > 0
            and codex_consent == "ask"
        ),
        "missing_components": missing_components,
        "missing_components_total": missing_components_total,
        "missing_components_required": missing_components_total > 0,
    }


def _count_enabled(state: dict, field: str) -> str:
    """Count configured items for a component field."""
    g_count = len(getattr(state["resolved_global"], field, []))

    if state["scope"] == "local" and state["project_dir"] is not None:
        total = len(getattr(state["resolved_active"], field, []))
        delta = total - g_count
        if delta > 0:
            return f"{total} configured ({g_count} global + {delta} local)"
        if delta < 0:
            return f"{total} configured ({g_count} global - {abs(delta)} local)"
        return f"{total} configured ({g_count} global)"
    return f"{g_count} configured"


def _get_codex_multi_agent_consent(cfg: dict) -> str:
    """Return codex multi-agent consent state with backward compatibility."""
    from .handlers.codex_consent import get_codex_multi_agent_consent

    return get_codex_multi_agent_consent(cfg)


def _is_codex_multi_agent_setup_required(state: dict) -> bool:
    """Whether codex multi-agent consent should be surfaced to the user."""
    from .handlers.codex_consent import is_codex_multi_agent_setup_required

    return is_codex_multi_agent_setup_required(state)


def _compute_missing_components(
    resolved_active: Any,
    contents: dict[ComponentType, list[str]],
) -> dict[str, list[str]]:
    """Compute missing component references for the active scope."""
    from .handlers.missing_components import compute_missing_components

    return compute_missing_components(resolved_active, contents)


def _human_size(size_bytes: int) -> str:
    """Format bytes into a short human-readable size string."""
    units = ["B", "KB", "MB", "GB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)}{unit}"
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{int(size_bytes)}B"


def _path_size(path: Path) -> int:
    """Compute total bytes for a file or directory."""
    try:
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            total = 0
            for child in path.rglob("*"):
                if child.is_file():
                    try:
                        total += child.stat().st_size
                    except OSError:
                        continue
            return total
    except OSError:
        return 0
    return 0


def _run_editor_command(path: Path) -> bool:
    """Open a path in $EDITOR (or fallback to default editor flow)."""
    editor = os.environ.get("EDITOR", "").strip()
    if not editor:
        _open_in_editor(path)
        return True

    try:
        cmd = shlex.split(editor)
        if not cmd:
            _open_in_editor(path)
            return True
        subprocess.run(cmd + [str(path)], check=False)
        return True
    except (OSError, ValueError):
        return False


def _confirm_registry_item_delete(ct: ComponentType, name: str) -> bool:
    """Ask for confirmation before deleting an item from registry."""
    from .handlers.packages import confirm_registry_item_delete

    return confirm_registry_item_delete(ct, name)


def _handle_registry_browser(state: dict) -> None:
    """Read-only registry browser with grouped rows and open-in-editor."""
    from .handlers.registry_browser import handle_registry_browser

    handle_registry_browser(state)


def _build_header(state: dict) -> str:
    """Build the dashboard header string."""
    header = f"\U0001f985 [bold]hawk {__version__}[/bold]"

    if state["scope"] == "local" and state["project_name"]:
        header += f"\n[dim]\U0001f4cd {state['project_dir']}[/dim]"
    else:
        header += (
            "\n[dim]\U0001f310 Global \u2014 run 'hawk init' for local scope[/dim]"
        )

    unsynced = state.get("unsynced_targets", 0)
    total_targets = state.get("sync_targets_total", 0)
    if unsynced > 0:
        warn_start, warn_end = warning_style(False)
        header += f"\n{warn_start}Sync status: {unsynced} unsynced target(s) of {total_targets}{warn_end}"
    return header


def _build_menu_options(state: dict) -> list[tuple[str, str | None]]:
    """Build main menu options with counts."""
    options: list[tuple[str, str | None]] = []

    for display_name, field, ct in COMPONENT_TYPES:
        count_str = _count_enabled(state, field)
        label = f"{display_name:<14} {count_str}"
        options.append((label, field))

    one_time_items: list[tuple[str, str]] = []
    if state.get("codex_multi_agent_required", _is_codex_multi_agent_setup_required(state)):
        one_time_items.append(("Codex setup required (one-time)", "codex_multi_agent_setup"))
    if state.get("missing_components_required", False):
        missing_total = int(state.get("missing_components_total", 0))
        one_time_items.append((f"Resolve missing components ({missing_total})", "resolve_missing_components"))

    if one_time_items:
        options.append(("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", None))
        options.append(("One-time setup", None))
        options.extend(one_time_items)
        options.append(("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", None))
    else:
        options.append(("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", None))

    options.append(("Download       Fetch from git URL", "download"))

    # Packages count
    packages = v2_config.load_packages()
    pkg_count = len(packages)
    if pkg_count > 0:
        options.append((f"Packages       {pkg_count} installed, manage & update", "packages"))
    else:
        options.append(("Packages       (none installed)", "packages"))

    unsynced = int(state.get("unsynced_targets", 0) or 0)
    total_targets = int(state.get("sync_targets_total", 0) or 0)
    if unsynced > 0:
        options.append((f"Sync now       {unsynced} pending of {total_targets}", "sync_now"))
    options.append(("Registry       Browse installed items", "registry"))

    options.append(("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", None))

    options.append(("Environment", "environment"))
    options.append(("Exit", "exit"))

    return options


def _normalize_main_menu_cursor(options: list[tuple[str, str | None]], cursor_index: int) -> int:
    """Clamp cursor to the first selectable row when needed."""
    if not options:
        return 0
    cursor = max(0, min(cursor_index, len(options) - 1))
    if options[cursor][1] is not None:
        return cursor
    for i, (_label, action) in enumerate(options):
        if action is not None:
            return i
    return 0


def _move_main_menu_cursor(
    options: list[tuple[str, str | None]],
    cursor: int,
    *,
    direction: int,
) -> int:
    """Move cursor up/down, skipping non-selectable separators."""
    total = len(options)
    if total == 0:
        return 0
    cursor = max(0, min(cursor, total - 1))
    for _ in range(total):
        cursor = (cursor + direction) % total
        if options[cursor][1] is not None:
            return cursor
    return cursor


def _build_main_menu_display(
    state: dict,
    options: list[tuple[str, str | None]],
    cursor: int,
) -> str:
    """Render the main dashboard menu with Rich markup."""
    lines: list[str] = []
    lines.append(_build_header(state))
    lines.append(dim_separator())

    for i, (label, action) in enumerate(options):
        if action is None:
            if label.strip("\u2500"):
                warn_start, warn_end = warning_style(False)
                lines.append(f"  {warn_start}{label}{warn_end}")
            else:
                lines.append(f"  {dim_separator(9)}")
            continue

        is_current = i == cursor
        prefix = cursor_prefix(is_current)

        if action in {"codex_multi_agent_setup", "resolve_missing_components"}:
            style, end_style = warning_style(is_current)
            lines.append(f"{prefix}{style}{label}{end_style}")
            continue

        style, end = action_style(is_current)
        lines.append(f"{prefix}{style}{label}{end}")

    lines.append("")
    lines.append("[dim]\u2191\u2193/jk nav · space/\u21b5 select · q/esc quit[/dim]")
    return "\n".join(lines)


def _run_main_menu(
    state: dict,
    options: list[tuple[str, str | None]],
    *,
    cursor_index: int,
) -> int | None:
    """Show the main dashboard menu and return selected row index."""
    if not options:
        return None

    cursor = _normalize_main_menu_cursor(options, cursor_index)

    with Live("", console=console, refresh_per_second=15, transient=True, screen=True) as live:
        live.update(Text.from_markup(_build_main_menu_display(state, options, cursor)))
        while True:
            try:
                key = readchar.readkey()
            except (KeyboardInterrupt, EOFError):
                return None

            if key in (readchar.key.UP, "k"):
                cursor = _move_main_menu_cursor(options, cursor, direction=-1)
            elif key in (readchar.key.DOWN, "j"):
                cursor = _move_main_menu_cursor(options, cursor, direction=1)
            elif key in (" ", "\r", "\n", readchar.key.ENTER):
                if options[cursor][1] is not None:
                    return cursor
            elif key in ("q", "\x1b", getattr(readchar.key, "CTRL_C", "\x03"), "\x03"):
                return None

            live.update(Text.from_markup(_build_main_menu_display(state, options, cursor)))


def _build_toggle_scopes(state: dict, field: str) -> list[ToggleScope]:
    """Build the list of ToggleScope objects for a component type.

    Uses get_config_chain to find all parent configs between global and cwd.
    """
    scopes: list[ToggleScope] = []

    # Global scope is always first
    global_enabled = list(state["global_cfg"].get(field, []))
    scopes.append(ToggleScope(
        key="global",
        label="\U0001f310 Global (default)",
        enabled=global_enabled,
    ))

    # Get config chain for current project dir
    project_dir = state.get("project_dir") or Path.cwd().resolve()
    config_chain = v2_config.get_config_chain(project_dir)

    if config_chain:
        for chain_dir, chain_config in config_chain:
            section = chain_config.get(field, {})
            if isinstance(section, dict):
                enabled = list(section.get("enabled", []))
            elif isinstance(section, list):
                enabled = list(section)
            else:
                enabled = []

            # Label: innermost = "This project: name", parents = dir name
            if chain_dir == project_dir.resolve():
                label = f"\U0001f4cd This project: {chain_dir.name}"
            else:
                label = f"\U0001f4c1 {chain_dir.name}"

            scopes.append(ToggleScope(
                key=str(chain_dir),
                label=label,
                enabled=enabled,
            ))
    else:
        # No config chain — only add local scope if config already exists
        local_cfg = state.get("local_cfg")
        if local_cfg is not None:
            local_enabled: list[str] = []
            local_section = local_cfg.get(field, {})
            if isinstance(local_section, dict):
                local_enabled = list(local_section.get("enabled", []))

            project_name = state.get("project_name") or project_dir.name
            scopes.append(ToggleScope(
                key=str(project_dir),
                label=f"\U0001f4cd This project: {project_name}",
                enabled=local_enabled,
            ))

    return scopes


def _handle_component_toggle(state: dict, field: str) -> bool:
    """Handle toggling a component type. Returns True if changes made."""
    # Find component type info
    ct = None
    display_name = field.title()
    for dn, f, c in COMPONENT_TYPES:
        if f == field:
            ct = c
            display_name = dn
            break
    if ct is None:
        return False

    # Get registry items for this type
    registry_names_set = set(state["contents"].get(ct, []))

    # Build N-scope list
    scopes = _build_toggle_scopes(state, field)

    # Include enabled items that aren't in the registry (orphaned references)
    all_enabled = set()
    for scope in scopes:
        all_enabled.update(scope.enabled)
    registry_names = sorted(registry_names_set | all_enabled)

    # Registry path for open/edit
    registry_path = v2_config.get_registry_path(state["cfg"])
    registry_dir = ct.registry_dir if ct else ""

    # Build groups from packages
    packages = v2_config.load_packages()
    toggle_groups: list[ToggleGroup] | None = None

    if packages:
        toggle_groups = []
        grouped_names: set[str] = set()
        # field is e.g. "skills" -> item type is "skill"
        item_type = field.rstrip("s") if field != "mcp" else "mcp"
        all_names = set(registry_names)

        for pkg_name, pkg_data in sorted(packages.items()):
            pkg_items = [
                item["name"] for item in pkg_data.get("items", [])
                if item.get("type") == item_type
                and item["name"] in all_names
            ]
            if pkg_items:
                toggle_groups.append(ToggleGroup(
                    key=pkg_name,
                    label=f"\U0001f4e6 {pkg_name}",
                    items=sorted(pkg_items),
                    collapsed=True,
                ))
                grouped_names.update(pkg_items)

        ungrouped = sorted(all_names - grouped_names)
        if ungrouped:
            toggle_groups.append(ToggleGroup(
                key="__ungrouped__",
                label="\u2500\u2500 ungrouped \u2500\u2500",
                items=ungrouped,
            ))

        if not toggle_groups:
            toggle_groups = None  # No packages for this type, flat list

    # MCP gets an "Add" action
    on_add = None
    add_label = "Add new..."
    if ct == ComponentType.MCP:
        on_add = _make_mcp_add_callback(state)
        add_label = "Add MCP server..."

    # Hint when no local config exists
    hint = None
    if len(scopes) == 1 and state.get("local_cfg") is None:
        hint = "run 'hawk init' for local scope"

    # Delete callback
    registry = state["registry"]

    def _delete_item(name: str) -> bool:
        if ct and registry.remove(ct, name):
            state["contents"] = registry.list()
            return True
        return False

    # Start on innermost scope
    enabled_lists, changed = run_toggle_list(
        display_name,
        registry_names,
        scopes=scopes,
        start_scope_index=len(scopes) - 1,
        registry_path=registry_path,
        registry_dir=registry_dir,
        on_add=on_add,
        add_label=add_label,
        registry_items=registry_names_set,
        groups=toggle_groups,
        footer_hint=hint,
        on_delete=_delete_item,
    )

    if changed:
        # Save each scope that changed
        for i, scope in enumerate(scopes):
            new_enabled = enabled_lists[i]
            old_enabled = scope.enabled

            if sorted(new_enabled) == sorted(old_enabled):
                continue

            if scope.key == "global":
                state["global_cfg"][field] = new_enabled
                cfg = state["cfg"]
                cfg["global"] = state["global_cfg"]
                v2_config.save_global_config(cfg)
            else:
                dir_path = Path(scope.key)
                dir_cfg = v2_config.load_dir_config(dir_path) or {}
                section = dir_cfg.get(field, {})
                if not isinstance(section, dict):
                    section = {}
                section["enabled"] = new_enabled
                dir_cfg[field] = section
                v2_config.save_dir_config(dir_path, dir_cfg)

                # Update local_cfg in state if this is cwd
                project_dir = state.get("project_dir")
                if project_dir and dir_path == project_dir.resolve() if isinstance(project_dir, Path) else dir_path == Path(str(project_dir)):
                    state["local_cfg"] = dir_cfg

    return changed


def _make_mcp_add_callback(state: dict):
    """Create a callback for adding MCP servers from the toggle list."""
    import yaml

    registry = state["registry"]
    registry_path = v2_config.get_registry_path(state["cfg"])

    def _add_mcp_server() -> str | None:
        """Interactive MCP server creation. Returns name or None."""
        try:
            return _add_mcp_server_inner()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Cancelled.[/dim]")
            return None

    def _add_mcp_server_inner() -> str | None:
        console.print("\n[bold]Add MCP Server[/bold]")
        console.print("[dim]" + "\u2500" * 40 + "[/dim]")

        try:
            # Name
            name = console.input("\n[cyan]Server name[/cyan] (e.g. github, postgres): ").strip()
            if not name:
                console.print("[dim]Cancelled.[/dim]")
                return None

            # Validate name
            if "/" in name or ".." in name or name.startswith("."):
                console.print("[red]Invalid name.[/red]")
                wait_for_continue()
                return None

            # Check clash
            if registry.has(ComponentType.MCP, name + ".yaml"):
                console.print(f"[red]Already exists: mcp/{name}.yaml[/red]")
                wait_for_continue()
                return None

            # Command
            command = console.input("[cyan]Command[/cyan] (e.g. npx, uvx, node, docker): ").strip()
            if not command:
                console.print("[dim]Cancelled.[/dim]")
                return None

            # Args
            args_str = console.input("[cyan]Arguments[/cyan] (space-separated, e.g. -y @modelcontextprotocol/server-github): ").strip()
            args = args_str.split() if args_str else []

            # Env vars (optional)
            console.print("[dim]Environment variables (one per line, KEY=VALUE, empty line to finish):[/dim]")
            env: dict[str, str] = {}
            while True:
                line = console.input("  ").strip()
                if not line:
                    break
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
                else:
                    console.print(f"  [dim]Skipping (no '='): {line}[/dim]")
        except KeyboardInterrupt:
            return None

        # Build config
        mcp_config: dict = {"command": command}
        if args:
            mcp_config["args"] = args
        if env:
            mcp_config["env"] = env

        # Preview
        console.print(f"\n[bold]Preview:[/bold]")
        console.print(f"  [cyan]{name}[/cyan]: {command} {' '.join(args)}")
        if env:
            for k, v in env.items():
                display_v = v if len(v) < 20 else v[:17] + "..."
                console.print(f"    {k}={display_v}")

        # Confirm
        confirm_menu = TerminalMenu(
            ["Yes, add to registry", "Cancel"],
            title="\nAdd this MCP server?",
            cursor_index=0,
            menu_cursor="\u276f ",
            **terminal_menu_style_kwargs(),
        )
        result = confirm_menu.show()
        if result != 0:
            console.print("[dim]Cancelled.[/dim]")
            return None

        # Write YAML to registry
        mcp_dir = registry_path / "mcp"
        mcp_dir.mkdir(parents=True, exist_ok=True)
        mcp_file = mcp_dir / f"{name}.yaml"
        mcp_file.write_text(yaml.dump(mcp_config, default_flow_style=False, sort_keys=False))

        # Refresh registry contents in state
        state["contents"] = registry.list()

        console.print(f"[green]\u2714[/green] Added mcp/{name}.yaml")
        console.print()
        return f"{name}.yaml"

    return _add_mcp_server


def _handle_tools_toggle(state: dict) -> bool:
    """Toggle tool enable/disable."""
    from .handlers.environment import handle_tools_toggle

    return handle_tools_toggle(state)


def _prune_disabled_tools(disabled_tools: list[Tool]) -> None:
    """Opinionated cleanup for disabled tools (no clean/prune choice in TUI)."""
    from .handlers.environment import prune_disabled_tools

    prune_disabled_tools(disabled_tools)


def _handle_packages(state: dict) -> bool:
    """Unified package-first registry view with package/type/item accordions."""
    from .handlers.packages import handle_packages

    return handle_packages(state)


def _handle_projects(state: dict) -> None:
    """Interactive projects tree view."""
    from .handlers.projects import handle_projects

    handle_projects(state)


def _delete_project_scope(project_dir: Path, *, delete_local_hawk: bool) -> tuple[bool, str]:
    """Delete a registered project scope, optionally removing local .hawk files."""
    from .handlers.projects import delete_project_scope

    return delete_project_scope(project_dir, delete_local_hawk=delete_local_hawk)


def _prompt_delete_scope(project_dir: Path, *, prefer_delete_local: bool = False) -> bool | None:
    """Prompt user for scope deletion details.

    Returns:
        True  -> delete scope + local .hawk
        False -> delete scope registration only
        None  -> cancelled
    """
    from .handlers.projects import prompt_delete_scope

    return prompt_delete_scope(project_dir, prefer_delete_local=prefer_delete_local)


def _run_projects_tree() -> None:
    """Show interactive tree of all registered directories."""
    from .handlers.projects import run_projects_tree

    run_projects_tree()


def _handle_codex_multi_agent_setup(state: dict, *, from_sync: bool = False) -> bool:
    """Prompt for codex multi-agent consent and persist the chosen state."""
    from .handlers.codex_consent import handle_codex_multi_agent_setup

    return handle_codex_multi_agent_setup(state, from_sync=from_sync)


def _find_package_lock_path(state: dict) -> Path | None:
    """Find a package lock file for the current scope."""
    from .handlers.missing_components import find_package_lock_path

    return find_package_lock_path(state)


def _iter_lock_packages(lock_data: Any) -> list[tuple[str, str | None]]:
    """Return a normalized list of (url, name) entries from lock data."""
    from .handlers.missing_components import iter_lock_packages

    return iter_lock_packages(lock_data)


def _install_from_package_lock(state: dict, lock_path: Path | None) -> bool:
    """Install packages listed in package lock.

    Returns True when any install attempt was executed.
    """
    from .handlers.missing_components import install_from_package_lock

    return install_from_package_lock(state, lock_path)


def _remove_names_from_section(section: Any, names_to_remove: set[str]) -> tuple[Any, int]:
    """Remove names from a list-or-dict section and return (updated, removed_count)."""
    from .handlers.missing_components import remove_names_from_section

    return remove_names_from_section(section, names_to_remove)


def _remove_missing_references(state: dict) -> tuple[bool, int]:
    """Remove missing references from active config layers."""
    from .handlers.missing_components import remove_missing_references

    return remove_missing_references(state)


def _handle_missing_components_setup(state: dict) -> bool:
    """Resolve missing component references via one-time setup flow."""
    from .handlers.missing_components import handle_missing_components_setup

    return handle_missing_components_setup(state)


def _sync_all_with_preflight(scope_dir: str | None = None, *, force: bool = False):
    """Run sync with codex consent preflight prompt when required."""
    pre_state = _load_state(scope_dir)
    if pre_state.get("codex_multi_agent_required", _is_codex_multi_agent_setup_required(pre_state)):
        _handle_codex_multi_agent_setup(pre_state, from_sync=True)

    from ..v2_sync import sync_all

    return sync_all(force=force)


def _handle_sync(state: dict) -> None:
    """Run sync and show results."""
    from ..v2_sync import format_sync_results

    console.print("\n[bold]Syncing...[/bold]")
    all_results = _sync_all_with_preflight(state.get("scope_dir"), force=True)
    formatted = format_sync_results(all_results, verbose=False)
    console.print(formatted or "  No changes.")
    console.print()
    wait_for_continue()


def _apply_auto_sync_if_needed(dirty: bool, scope_dir: str | None = None) -> bool:
    """Auto-sync dirty config changes and keep dirty only for real errors."""
    if not dirty:
        return False

    from ..v2_sync import format_sync_results

    all_results = _sync_all_with_preflight(scope_dir, force=False)
    has_errors = any(result.errors for scope in all_results.values() for result in scope)
    if has_errors:
        console.print("\n[bold red]Auto-sync encountered errors.[/bold red]")
        formatted = format_sync_results(all_results, verbose=False)
        console.print(formatted or "  No changes.")
        console.print()
        wait_for_continue()
        return True

    return False


def _handle_download() -> None:
    """Run download flow."""
    console.print("\n[bold]Download components from git[/bold]")
    try:
        url = console.input("[cyan]URL:[/cyan] ")
    except KeyboardInterrupt:
        return
    if not url or not url.strip():
        return

    from ..download_service import download_and_install, get_interactive_select_fn

    download_and_install(
        url.strip(),
        select_all=False,
        replace=False,
        select_fn=get_interactive_select_fn(),
        log=lambda msg: console.print(msg),
    )

    console.print()
    wait_for_continue()


def _handle_uninstall_from_environment() -> bool:
    """Run unlink + uninstall flow from Environment menu."""
    from .handlers.environment import handle_uninstall_from_environment

    return handle_uninstall_from_environment()


def _build_environment_menu_entries(state: dict) -> tuple[list[str], str]:
    """Build Environment submenu entries + title with lightweight status context."""
    from .handlers.environment import build_environment_menu_entries

    return build_environment_menu_entries(state)


def _handle_environment(state: dict) -> bool:
    """Environment submenu (tools, projects, preferences, uninstall)."""
    from .handlers.environment import handle_environment

    return handle_environment(state)


def _prompt_sync_on_exit(dirty: bool, scope_dir: str | None = None) -> None:
    """If changes were made, sync based on sync_on_exit setting."""
    if not dirty:
        return

    cfg = v2_config.load_global_config()
    preference = cfg.get("sync_on_exit", "ask")

    if preference == "never":
        return

    if preference == "always":
        from ..v2_sync import format_sync_results

        console.print("\n[bold]Syncing...[/bold]")
        all_results = _sync_all_with_preflight(scope_dir)
        formatted = format_sync_results(all_results, verbose=False)
        console.print(formatted or "  No changes.")
        return

    # "ask" (default)
    menu = TerminalMenu(
        ["Yes", "No"],
        title="\nChanges made. Sync to tools now?",
        cursor_index=0,
        menu_cursor="\u276f ",
        **terminal_menu_style_kwargs(),
        quit_keys=("q", "\x1b"),
    )
    result = menu.show()
    if result == 0:
        from ..v2_sync import format_sync_results

        console.print("[bold]Syncing...[/bold]")
        all_results = _sync_all_with_preflight(scope_dir)
        formatted = format_sync_results(all_results, verbose=False)
        console.print(formatted or "  No changes.")


def run_dashboard(scope_dir: str | None = None) -> None:
    """Run the main dashboard loop.

    Args:
        scope_dir: Optional directory to scope the TUI to.
    """
    dirty = False
    last_cursor = 0

    while True:
        state = _load_state(scope_dir)
        set_project_theme(state.get("project_dir") or Path.cwd().resolve())

        options = _build_menu_options(state)
        choice = _run_main_menu(state, options, cursor_index=last_cursor)
        if choice is not None:
            last_cursor = choice

        if choice is None:
            # q pressed
            _prompt_sync_on_exit(dirty, scope_dir=state.get("scope_dir"))
            console.clear()
            break

        _, action = options[choice]

        if action is None:
            # Separator
            continue

        if action == "exit":
            _prompt_sync_on_exit(dirty, scope_dir=state.get("scope_dir"))
            console.clear()
            break

        # Main menu uses a transient Rich live view; clear before entering
        # non-main flows so previous shell buffer lines are not shown above submenus.
        console.clear()

        if action in ("skills", "hooks", "prompts", "agents", "mcp"):
            if _handle_component_toggle(state, action):
                dirty = True
                dirty = _apply_auto_sync_if_needed(dirty, scope_dir=state.get("scope_dir"))

        elif action == "sync_now":
            _handle_sync(state)

        elif action == "registry":
            _handle_registry_browser(state)

        elif action == "codex_multi_agent_setup":
            if _handle_codex_multi_agent_setup(state):
                dirty = True
                dirty = _apply_auto_sync_if_needed(dirty, scope_dir=state.get("scope_dir"))

        elif action == "resolve_missing_components":
            if _handle_missing_components_setup(state):
                dirty = True
                dirty = _apply_auto_sync_if_needed(dirty, scope_dir=state.get("scope_dir"))

        elif action == "packages":
            if _handle_packages(state):
                dirty = True
                dirty = _apply_auto_sync_if_needed(dirty, scope_dir=state.get("scope_dir"))

        elif action == "environment":
            if _handle_environment(state):
                dirty = True
                dirty = _apply_auto_sync_if_needed(dirty, scope_dir=state.get("scope_dir"))

        elif action == "download":
            _handle_download()
            # Reload state on next loop
