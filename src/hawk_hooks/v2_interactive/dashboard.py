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

_CODEX_CONSENT_OPTIONS = {"ask", "granted", "denied"}

_COMPONENT_TYPE_BY_FIELD: dict[str, ComponentType] = {
    "skills": ComponentType.SKILL,
    "hooks": ComponentType.HOOK,
    "prompts": ComponentType.PROMPT,
    "agents": ComponentType.AGENT,
    "mcp": ComponentType.MCP,
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
        dir_chain: list[tuple[dict, dict | None]] = []
        for chain_dir, chain_config in v2_config.get_config_chain(project_dir):
            profile_name = chain_config.get("profile")
            if not profile_name:
                dir_entry = cfg.get("directories", {}).get(str(chain_dir.resolve()), {})
                profile_name = dir_entry.get("profile")
            profile = v2_config.load_profile(profile_name) if profile_name else None
            dir_chain.append((chain_config, profile))

        if not dir_chain and local_cfg is not None:
            profile_name = local_cfg.get("profile")
            profile = v2_config.load_profile(profile_name) if profile_name else None
            dir_chain.append((local_cfg, profile))

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
    codex_cfg = cfg.get("tools", {}).get("codex", {})
    consent = codex_cfg.get("multi_agent_consent")
    if consent in _CODEX_CONSENT_OPTIONS:
        return str(consent)

    # Backward compatibility with earlier boolean gate.
    if codex_cfg.get("allow_multi_agent") is True:
        return "granted"
    return "ask"


def _is_codex_multi_agent_setup_required(state: dict) -> bool:
    """Whether codex multi-agent consent should be surfaced to the user."""
    codex_status = state.get("tools_status", {}).get(Tool.CODEX, {})
    if not codex_status.get("enabled", True):
        return False
    active_agents = len(getattr(state.get("resolved_active"), "agents", []))
    if active_agents <= 0:
        return False
    return state.get("codex_multi_agent_consent", "ask") == "ask"


def _compute_missing_components(
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


def _handle_registry_browser(state: dict) -> None:
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
        menu_cursor="❯ ",
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
    options = []
    tool_list = Tool.all()
    for tool in tool_list:
        ts = state["tools_status"][tool]
        installed = "installed" if ts["installed"] else "not found"
        options.append(f"{tool:<12} ({installed})")

    preselected = [
        i for i, tool in enumerate(tool_list)
        if state["tools_status"][tool]["enabled"]
    ]

    menu = TerminalMenu(
        options,
        title="\nTools \u2014 toggle which tools hawk syncs to:",
        multi_select=True,
        preselected_entries=preselected,
        multi_select_select_on_accept=False,
        multi_select_cursor="(\u25cf) ",
        multi_select_cursor_brackets_style=("fg_green",),
        multi_select_cursor_style=("fg_green",),
        menu_cursor="\u276f ",
        **terminal_menu_style_kwargs(include_status_bar=True),
        quit_keys=("q", "\x1b"),
        status_bar="space toggle · \u21b5 confirm · q/esc back",
    )
    result = menu.show()
    if result is None:
        return False

    selected = set(result) if isinstance(result, tuple) else {result}
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
        v2_config.save_global_config(cfg)
        if disabled_tools:
            _prune_disabled_tools(disabled_tools)

    return changed


def _prune_disabled_tools(disabled_tools: list[Tool]) -> None:
    """Opinionated cleanup for disabled tools (no clean/prune choice in TUI)."""
    if not disabled_tools:
        return

    from ..v2_sync import format_sync_results, purge_all

    tool_labels = ", ".join(str(tool) for tool in disabled_tools)
    console.print(f"\n[bold]Cleaning disabled tool integrations:[/bold] {tool_labels}")
    all_results = purge_all(tools=disabled_tools)
    formatted = format_sync_results(all_results, verbose=False)
    console.print(formatted or "  No changes.")
    console.print()
    wait_for_continue()


def _handle_packages(state: dict) -> bool:
    """Unified package-first registry view with package/type/item accordions."""
    packages = v2_config.load_packages()
    registry = state["registry"]
    dirty = False

    # Row kinds
    ROW_PACKAGE = "package"
    ROW_TYPE = "type"
    ROW_ITEM = "item"
    ROW_SEPARATOR = "separator"
    ROW_ACTION = "action"
    ACTION_DONE = "__done__"
    UNGROUPED = "__ungrouped__"

    # Component ordering in this view
    ordered_types: list[tuple[str, str, ComponentType]] = [
        ("skills", "Skills", ComponentType.SKILL),
        ("hooks", "Hooks", ComponentType.HOOK),
        ("prompts", "Prompts", ComponentType.PROMPT),
        ("agents", "Agents", ComponentType.AGENT),
        ("mcp", "MCP Servers", ComponentType.MCP),
    ]
    fields = [f for f, _, _ in ordered_types]
    field_to_ct = {f: ct for f, _, ct in ordered_types}
    ct_to_field = {ct.value: f for f, _, ct in ordered_types}

    collapsed_packages: dict[str, bool] = {}
    collapsed_types: dict[tuple[str, str], bool] = {}
    cursor = 0
    scroll_offset = 0
    scope_index = 0
    status_msg = ""

    def _reload_state_config() -> None:
        """Reload config slices that can be changed by package actions."""
        cfg = v2_config.load_global_config()
        state["cfg"] = cfg
        state["global_cfg"] = cfg.get("global", {})

        project_dir = state.get("project_dir")
        if project_dir:
            state["local_cfg"] = v2_config.load_dir_config(project_dir) or {}
        else:
            state["local_cfg"] = None

    def _build_scope_entries() -> list[dict]:
        """Build scope layers with enabled (field,name) pairs."""
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
        """Set one component enabled/disabled in a specific scope."""
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

    def _refresh_contents() -> None:
        nonlocal packages
        packages = v2_config.load_packages()
        state["contents"] = registry.list()

    def _build_package_tree() -> tuple[list[str], dict[str, dict[str, list[str]]]]:
        """Return (package_order, package -> field -> names) from registry + package index."""
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

    def _build_rows(
        package_order: list[str], package_tree: dict[str, dict[str, list[str]]]
    ) -> list[dict]:
        rows: list[dict] = []
        for pkg_name in package_order:
            collapsed_packages.setdefault(pkg_name, True)
            field_map = package_tree.get(pkg_name, {f: [] for f in fields})
            item_count = sum(len(names) for names in field_map.values())
            rows.append({
                "kind": ROW_PACKAGE,
                "package": pkg_name,
                "count": item_count,
                "is_ungrouped": pkg_name == UNGROUPED,
            })

            if collapsed_packages.get(pkg_name, False):
                continue

            for field, label, _ct in ordered_types:
                names = field_map.get(field, [])
                if not names:
                    continue
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
        rows.append({"kind": ROW_ACTION, "action": ACTION_DONE, "label": "Done"})
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

    def _build_display(rows: list[dict], package_tree: dict[str, dict[str, list[str]]], scopes: list[dict]) -> str:
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

        scope = scopes[scope_index]
        checked = scope["enabled"]
        next_scope = scopes[(scope_index + 1) % len(scopes)]["label"] if len(scopes) > 1 else ""
        show_scope_hint = len(scopes) == 1 and state.get("local_cfg") is None
        package_count = len([p for p in package_tree.keys() if p != UNGROUPED])
        ungrouped_count = sum(len(names) for names in package_tree.get(UNGROUPED, {}).values())

        lines: list[str] = [scoped_header("Packages", scope["label"])]
        if len(scopes) > 1:
            lines[0] += f"    [dim]\\[Tab: {next_scope}][/dim]"
        elif show_scope_hint:
            lines[0] += " [dim]\u2014 run 'hawk init' for local scope[/dim]"
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
                    url = str(packages.get(pkg_name, {}).get("url", "")).strip()
                    if url:
                        lines.append(f"    [dim]{url}[/dim]")

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
                    f"{prefix}  {style}{label} "
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
                        lines.append(f"{prefix}    {mark} [bold white]{name}[/bold white]")
                    else:
                        lines.append(f"{prefix}    {mark} [bold dim]{name}[/bold dim]")
                else:
                    if enabled:
                        lines.append(f"{prefix}    {mark} [white]{name}[/white]")
                    else:
                        lines.append(f"{prefix}    {mark} [dim]{name}[/dim]")

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
        if current_kind == ROW_PACKAGE:
            hints = "space/\u21b5 expand · u update pkg · d/x remove pkg · U update all"
        elif current_kind == ROW_TYPE:
            hints = "space/\u21b5 expand"
        elif current_kind == ROW_ITEM:
            hints = "space/\u21b5 toggle · e open · d remove item · U update all"
        else:
            hints = "space/\u21b5 select · U update all"
        if len(scopes) > 1:
            hints += " · tab scope"
        hints += " · \u2191\u2193/jk nav · q/esc/^C back"
        lines.append(f"[dim]{hints}[/dim]")
        return "\n".join(lines)

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

    with Live("", console=console, refresh_per_second=15, screen=True) as live:
        while True:
            scopes = _build_scope_entries()
            scope_index = max(0, min(scope_index, len(scopes) - 1))
            package_order, package_tree = _build_package_tree()
            rows = _build_rows(package_order, package_tree)
            cursor = _normalize_cursor(rows, cursor)
            live.update(Text.from_markup(_build_display(rows, package_tree, scopes)))

            try:
                key = readchar.readkey()
            except (KeyboardInterrupt, EOFError):
                break

            status_msg = ""
            row = rows[cursor]
            kind = row["kind"]
            scope = scopes[scope_index]

            if key in (readchar.key.UP, "k"):
                cursor = _move_cursor(rows, cursor, -1)
                continue
            if key in (readchar.key.DOWN, "j"):
                cursor = _move_cursor(rows, cursor, 1)
                continue
            if key in (readchar.key.TAB, "\t") and len(scopes) > 1:
                scope_index = (scope_index + 1) % len(scopes)
                continue
            if key in ("q", "\x1b", getattr(readchar.key, "CTRL_C", "\x03"), "\x03"):
                break

            if key == "U":
                live.stop()
                console.print("\n[bold]Updating all packages...[/bold]")
                from ..cli import cmd_update

                class _ArgsAll:
                    package = None
                    check = False
                    force = False
                    prune = False

                try:
                    cmd_update(_ArgsAll())
                except SystemExit:
                    pass
                console.print()
                console.print("[dim]Press any key to continue...[/dim]")
                readchar.readkey()
                _reload_state_config()
                _refresh_contents()
                live.start()
                continue

            primary = key in (readchar.key.ENTER, "\r", "\n", " ")

            if kind == ROW_ACTION and primary:
                break

            if kind == ROW_PACKAGE:
                pkg_name = row["package"]
                is_ungrouped = row["is_ungrouped"]

                if primary:
                    collapsed_packages[pkg_name] = not collapsed_packages.get(pkg_name, False)
                    continue

                if key == "u":
                    if is_ungrouped:
                        status_msg = "Ungrouped has no package source to update."
                        continue

                    live.stop()
                    console.print(f"\n[bold]Updating {pkg_name}...[/bold]")
                    from ..cli import cmd_update

                    class _Args:
                        package = pkg_name
                        check = False
                        force = False
                        prune = False

                    try:
                        cmd_update(_Args())
                    except SystemExit:
                        pass
                    console.print()
                    console.print("[dim]Press any key to continue...[/dim]")
                    readchar.readkey()
                    _reload_state_config()
                    _refresh_contents()
                    live.start()
                    continue

                if key in ("x", "d"):
                    if is_ungrouped:
                        status_msg = "Cannot remove Ungrouped as a package."
                        continue

                    live.stop()
                    console.print(
                        f"\n[yellow]Remove package '{pkg_name}'?[/yellow] [dim](y/N)[/dim] ",
                        end="",
                    )
                    confirm = readchar.readkey()
                    console.print()
                    if confirm.lower() == "y":
                        from ..cli import cmd_remove_package

                        class _RmArgs:
                            name = pkg_name
                            yes = True

                        try:
                            cmd_remove_package(_RmArgs())
                        except SystemExit:
                            pass
                        console.print()
                        console.print("[dim]Press any key to continue...[/dim]")
                        readchar.readkey()
                    _reload_state_config()
                    _refresh_contents()
                    live.start()
                    continue

            if kind == ROW_TYPE and primary:
                pkg_name = row["package"]
                field = row["field"]
                key_id = (pkg_name, field)
                collapsed_types[key_id] = not collapsed_types.get(key_id, True)
                continue

            if kind == ROW_ITEM:
                field = row["field"]
                name = row["name"]
                ct = field_to_ct[field]

                if primary:
                    enabled_now = (field, name) in scope["enabled"]
                    _set_item_enabled(scope["key"], field, name, not enabled_now)
                    dirty = True
                    status_msg = (
                        f"{'Enabled' if not enabled_now else 'Disabled'} {name} in {scope['label']}"
                    )
                    continue

                if key == "e":
                    item_path = registry.get_path(ct, name)
                    if item_path is not None:
                        live.stop()
                        if not _run_editor_command(item_path):
                            console.print(f"\n[red]Could not open {item_path} in $EDITOR[/red]")
                            wait_for_continue()
                        live.start()
                    continue

                if key == "d":
                    removed = registry.remove(ct, name)
                    if removed:
                        dirty = True
                        state["contents"] = registry.list()
                        status_msg = f"Removed {ct.registry_dir}/{name} from registry."
                    else:
                        status_msg = f"Could not remove {ct.registry_dir}/{name}."
                    continue

    return dirty


def _handle_projects(state: dict) -> None:
    """Interactive projects tree view."""
    _run_projects_tree()


def _delete_project_scope(project_dir: Path, *, delete_local_hawk: bool) -> tuple[bool, str]:
    """Delete a registered project scope, optionally removing local .hawk files."""
    project_dir = project_dir.resolve()
    try:
        v2_config.unregister_directory(project_dir)
    except Exception as e:
        return False, f"Failed to remove scope: {e}"

    if delete_local_hawk:
        hawk_dir = project_dir / ".hawk"
        try:
            if hawk_dir.is_symlink() or hawk_dir.is_file():
                hawk_dir.unlink()
            elif hawk_dir.is_dir():
                shutil.rmtree(hawk_dir)
        except OSError as e:
            return False, f"Scope removed, but failed to delete .hawk: {e}"

    if delete_local_hawk:
        return True, f"Removed scope and local .hawk for: {project_dir}"
    return True, f"Removed scope registration for: {project_dir}"


def _prompt_delete_scope(project_dir: Path, *, prefer_delete_local: bool = False) -> bool | None:
    """Prompt user for scope deletion details.

    Returns:
        True  -> delete scope + local .hawk
        False -> delete scope registration only
        None  -> cancelled
    """
    step1 = TerminalMenu(
        ["Cancel", "Delete scope"],
        title=(
            "\nDelete local scope?\n"
            f"{project_dir}\n"
            "This removes the project from Hawk Project Scopes."
        ),
        cursor_index=0,
        menu_cursor="\u276f ",
        **terminal_menu_style_kwargs(),
        quit_keys=("q", "\x1b"),
    )
    choice1 = step1.show()
    if choice1 != 1:
        return None

    default_idx = 1 if prefer_delete_local else 0
    step2 = TerminalMenu(
        ["Keep local .hawk files", "Delete local .hawk files", "Cancel"],
        title=(
            "\nAlso delete local .hawk files?\n"
            "Use this if you want to fully remove local Hawk setup for this project."
        ),
        cursor_index=default_idx,
        menu_cursor="\u276f ",
        **terminal_menu_style_kwargs(),
        quit_keys=("q", "\x1b"),
    )
    choice2 = step2.show()
    if choice2 is None or choice2 == 2:
        return None
    return choice2 == 1


def _run_projects_tree() -> None:
    """Show interactive tree of all registered directories."""
    while True:
        dirs = v2_config.get_registered_directories()

        if not dirs:
            console.print("\n[dim]No directories registered.[/dim]")
            console.print("[dim]Run [cyan]hawk init[/cyan] in a project directory to register it.[/dim]\n")
            wait_for_continue()
            return

        # Build tree structure: group by parent-child relationships
        dir_paths = sorted(dirs.keys())
        tree_entries: list[tuple[str, int, str]] = []  # (path, indent, label)

        # Find root dirs (not children of any other registered dir)
        roots: list[str] = []
        for dp in dir_paths:
            dp_path = Path(dp)
            is_child = False
            for other in dir_paths:
                if other != dp:
                    try:
                        if dp_path.is_relative_to(Path(other)):
                            is_child = True
                            break
                    except (ValueError, TypeError):
                        continue
            if not is_child:
                roots.append(dp)

        def _add_tree(parent: str, indent: int) -> None:
            p = Path(parent)
            entry = dirs.get(parent, {})
            profile = entry.get("profile", "")

            # Count enabled items
            dir_config = v2_config.load_dir_config(p)
            parts: list[str] = []
            if profile:
                parts.append(f"profile: {profile}")
            if dir_config:
                for field in ["skills", "hooks", "prompts", "agents", "mcp"]:
                    section = dir_config.get(field, {})
                    if isinstance(section, dict):
                        count = len(section.get("enabled", []))
                    elif isinstance(section, list):
                        count = len(section)
                    else:
                        count = 0
                    if count:
                        parts.append(f"+{count} {field}")

            suffix = f"  {', '.join(parts)}" if parts else ""
            exists = p.exists()
            marker = " [missing]" if not exists else ""

            if indent == 0:
                label = f"\U0001f4c1 {parent}{suffix}{marker}"
            else:
                label = f"{'   ' * indent}\U0001f4c1 {p.name}{suffix}{marker}"

            tree_entries.append((parent, indent, label))

            # Find children
            children = [
                dp for dp in dir_paths
                if dp != parent and dp.startswith(parent + "/")
                and not any(
                    other != parent and other != dp
                    and dp.startswith(other + "/")
                    and other.startswith(parent + "/")
                    for other in dir_paths
                )
            ]
            for child in sorted(children):
                _add_tree(child, indent + 1)

        for root in sorted(roots):
            _add_tree(root, 0)

        # Add global entry at top
        cfg = v2_config.load_global_config()
        global_section = cfg.get("global", {})
        global_parts: list[str] = []
        for field in ["skills", "hooks", "prompts", "agents", "mcp"]:
            count = len(global_section.get(field, []))
            if count:
                global_parts.append(f"{count} {field}")
        global_suffix = f"  {', '.join(global_parts)}" if global_parts else ""

        menu_entries = [f"\U0001f30e Global{global_suffix}"] + [e[2] for e in tree_entries]
        menu_paths = ["global"] + [e[0] for e in tree_entries]

        menu = TerminalMenu(
            menu_entries,
            title="\nhawk projects\n" + "\u2500" * 40,
            menu_cursor="\u276f ",
            **terminal_menu_style_kwargs(include_status_bar=True),
            accept_keys=("enter", "d", "x"),
            quit_keys=("q", "\x1b"),
            status_bar="↵ open · d/x delete scope · q/esc back",
        )

        choice = menu.show()
        if choice is None:
            break

        selected_path = menu_paths[choice]
        accept_key = getattr(menu, "chosen_accept_key", "enter")
        if accept_key in ("d", "x"):
            if selected_path == "global":
                console.print("\n[yellow]Global scope cannot be deleted.[/yellow]\n")
                wait_for_continue()
                continue

            project_dir = Path(selected_path)
            remove_local = _prompt_delete_scope(
                project_dir,
                prefer_delete_local=(accept_key == "x"),
            )
            if remove_local is None:
                continue

            ok, msg = _delete_project_scope(project_dir, delete_local_hawk=remove_local)
            style = "green" if ok else "red"
            console.print(f"\n[{style}]{msg}[/{style}]\n")
            wait_for_continue()
            continue

        if selected_path == "global":
            # Open settings editor for global config
            from .config_editor import run_config_editor
            run_config_editor()
        else:
            # Open dashboard scoped to that directory
            from . import v2_interactive_menu
            v2_interactive_menu(scope_dir=selected_path)
            break


def _handle_codex_multi_agent_setup(state: dict, *, from_sync: bool = False) -> bool:
    """Prompt for codex multi-agent consent and persist the chosen state."""
    cfg = state.get("cfg") or v2_config.load_global_config()
    tools_cfg = cfg.setdefault("tools", {})
    codex_cfg = tools_cfg.setdefault("codex", {})
    consent = _get_codex_multi_agent_consent(cfg)

    body_lines = [
        "[bold]Enable Codex multi-agent support?[/bold]",
        "",
        "To sync Hawk agents into Codex, Codex must have multi-agent mode enabled.",
        "",
        "Hawk can manage this in [cyan].codex/config.toml[/cyan] by writing:",
        "[cyan]  [features][/cyan]",
        "[cyan]  multi_agent = true[/cyan]",
        "",
        "[green]Enable now[/green]: let Hawk manage it automatically.",
        "[yellow]Not now[/yellow]: skip for now (you will be asked again).",
        "[red]Never[/red]: do not manage this setting.",
    ]
    if from_sync:
        body_lines.extend(["", "[yellow]Sync is about to run.[/yellow]"])

    console.print()
    warn_start, warn_end = warning_style(True)
    console.print(f"{warn_start}Codex setup required{warn_end}")
    console.print("[dim]" + ("\u2500" * 50) + "[/dim]")
    console.print("\n".join(body_lines))

    menu = TerminalMenu(
        ["Enable now", "Not now", "Never"],
        title="\nChoose an option",
        cursor_index=0,
        menu_cursor="\u276f ",
        **terminal_menu_style_kwargs(),
        quit_keys=("q", "\x1b"),
    )
    choice = menu.show()
    if choice is None:
        return False

    if choice == 0:
        new_consent = "granted"
    elif choice == 1:
        new_consent = "ask"
    else:
        new_consent = "denied"

    changed = new_consent != consent or codex_cfg.get("allow_multi_agent") != (new_consent == "granted")
    codex_cfg["multi_agent_consent"] = new_consent
    # Backward-compatible mirror for older adapter code paths.
    codex_cfg["allow_multi_agent"] = new_consent == "granted"
    tools_cfg["codex"] = codex_cfg
    cfg["tools"] = tools_cfg
    v2_config.save_global_config(cfg)

    # Update in-memory state for immediate menu refresh.
    state["cfg"] = cfg
    state["codex_multi_agent_consent"] = new_consent
    state["codex_multi_agent_required"] = _is_codex_multi_agent_setup_required(state)

    return changed


def _find_package_lock_path(state: dict) -> Path | None:
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


def _iter_lock_packages(lock_data: Any) -> list[tuple[str, str | None]]:
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


def _install_from_package_lock(state: dict, lock_path: Path | None) -> bool:
    """Install packages listed in package lock.

    Returns True when any install attempt was executed.
    """
    if lock_path is None:
        console.print("\n[yellow]No package lock found.[/yellow]")
        console.print("[dim]Expected .hawk/packages.lock.yaml in project scope.[/dim]\n")
        wait_for_continue()
        return False

    import yaml
    from ..cli import cmd_download

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
        class Args:
            pass

        args = Args()
        args.url = url
        args.all = True
        args.replace = False
        args.name = name

        try:
            cmd_download(args)
            attempted += 1
        except SystemExit:
            continue

    if attempted <= 0:
        console.print("\n[yellow]No packages were installed from lock.[/yellow]\n")
        wait_for_continue()
        return False

    console.print(f"\n[green]\u2714 Installed {attempted} package(s) from lock.[/green]\n")
    wait_for_continue()
    return True


def _remove_names_from_section(section: Any, names_to_remove: set[str]) -> tuple[Any, int]:
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


def _remove_missing_references(state: dict) -> tuple[bool, int]:
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


def _handle_missing_components_setup(state: dict) -> bool:
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


def _sync_all_with_preflight(scope_dir: str | None = None):
    """Run sync with codex consent preflight prompt when required."""
    pre_state = _load_state(scope_dir)
    if pre_state.get("codex_multi_agent_required", _is_codex_multi_agent_setup_required(pre_state)):
        _handle_codex_multi_agent_setup(pre_state, from_sync=True)

    from ..v2_sync import sync_all

    return sync_all(force=True)


def _handle_sync(state: dict) -> None:
    """Run sync and show results."""
    from ..v2_sync import format_sync_results

    console.print("\n[bold]Syncing...[/bold]")
    all_results = _sync_all_with_preflight(state.get("scope_dir"))
    formatted = format_sync_results(all_results, verbose=False)
    console.print(formatted or "  No changes.")
    console.print()
    wait_for_continue()


def _apply_auto_sync_if_needed(dirty: bool, scope_dir: str | None = None) -> bool:
    """Auto-sync dirty config changes and keep dirty only for real errors."""
    if not dirty:
        return False

    from ..v2_sync import format_sync_results

    all_results = _sync_all_with_preflight(scope_dir)
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

    import sys
    from ..cli import cmd_download

    class Args:
        pass

    args = Args()
    args.url = url.strip()
    args.all = False
    args.replace = False

    try:
        cmd_download(args)
    except SystemExit:
        pass

    console.print()
    wait_for_continue()


def _handle_uninstall_from_environment() -> bool:
    """Run unlink + uninstall flow from Environment menu."""
    return run_uninstall_wizard(console)


def _build_environment_menu_entries(state: dict) -> tuple[list[str], str]:
    """Build Environment submenu entries + title with lightweight status context."""
    tools_total = len(Tool.all())
    tools_enabled = sum(
        1
        for tool_state in state.get("tools_status", {}).values()
        if tool_state.get("enabled", True)
    )
    scopes_count = len(v2_config.get_registered_directories())
    sync_pref = str((state.get("cfg") or {}).get("sync_on_exit", "ask"))

    entries = [
        f"Tool Integrations  {tools_enabled}/{tools_total} enabled",
        f"Project Scopes     {scopes_count} registered",
        f"Preferences        sync on exit: {sync_pref}",
        "Unlink and uninstall  (destructive)",
        "Back",
    ]

    pending: list[str] = []
    if state.get("codex_multi_agent_required", False):
        pending.append("codex setup")
    if state.get("missing_components_required", False):
        pending.append("missing components")

    title = "\nEnvironment\nManage tools, scopes, and preferences"
    if pending:
        title += f"\nPending one-time setup: {', '.join(pending)}"
    return entries, title


def _handle_environment(state: dict) -> bool:
    """Environment submenu (tools, projects, preferences, uninstall)."""
    changed = False

    while True:
        # Clear transient output from submenu actions before re-rendering menu.
        console.clear()
        menu_entries, menu_title = _build_environment_menu_entries(state)
        menu = TerminalMenu(
            menu_entries,
            title=menu_title,
            cursor_index=0,
            menu_cursor="\u276f ",
            **terminal_menu_style_kwargs(include_status_bar=True),
            accept_keys=("enter", " "),
            quit_keys=("q", "\x1b"),
            status_bar="space/\u21b5 select · q/esc back",
        )
        choice = menu.show()
        if choice is None or choice == 4:
            break

        if choice == 0:
            if _handle_tools_toggle(state):
                changed = True
        elif choice == 1:
            _handle_projects(state)
        elif choice == 2:
            from .config_editor import run_config_editor

            if run_config_editor():
                changed = True
        elif choice == 3:
            if _handle_uninstall_from_environment():
                changed = True

    return changed


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
