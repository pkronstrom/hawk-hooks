"""Main dashboard and menu for hawk v2 TUI."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from rich.console import Console
from simple_term_menu import TerminalMenu

from .. import __version__, v2_config
from ..adapters import get_adapter
from ..registry import Registry
from ..resolver import resolve
from ..types import ComponentType, ToggleGroup, ToggleScope, Tool
from .pause import wait_for_continue
from .toggle import _open_in_editor, run_toggle_list

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
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
        quit_keys=("q", "\x1b"),
        status_bar="Enter: open in $EDITOR  q/Esc: back",
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
    total_components = sum(len(names) for names in state["contents"].values())
    tools_active = sum(1 for t in state["tools_status"].values() if t["installed"] and t["enabled"])

    header = f"\U0001f985 [bold]hawk[/bold] v{__version__} [dim]\u2014 {total_components} components, {tools_active} tools[/dim]"

    if state["scope"] == "local" and state["project_name"]:
        header += f"\n[dim]\U0001f4cd {state['project_dir']}[/dim]"
    else:
        header += f"\n[dim]\U0001f310 Global[/dim]"

    unsynced = state.get("unsynced_targets", 0)
    total_targets = state.get("sync_targets_total", 0)
    if unsynced > 0:
        header += f"\n[yellow]Sync status: {unsynced} unsynced target(s) of {total_targets}[/yellow]"

    return header


def _build_menu_options(state: dict) -> list[tuple[str, str | None]]:
    """Build main menu options with counts."""
    options: list[tuple[str, str | None]] = []

    for display_name, field, ct in COMPONENT_TYPES:
        count_str = _count_enabled(state, field)
        label = f"{display_name:<14} {count_str}"
        options.append((label, field))

    if state.get("codex_multi_agent_required", _is_codex_multi_agent_setup_required(state)):
        options.append(("⚠ Codex setup  multi-agent consent required", "codex_multi_agent_setup"))

    options.append(("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", None))
    options.append(("Download       Fetch from git URL", "download"))

    # Packages count
    packages = v2_config.load_packages()
    pkg_count = len(packages)
    if pkg_count > 0:
        options.append((f"Packages       {pkg_count} installed, manage & update", "packages"))
    else:
        options.append(("Packages       (none installed)", "packages"))
    options.append(("Registry       Browse installed components", "registry"))

    options.append(("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", None))

    options.append(("Env", "environment"))
    options.append(("Exit", "exit"))

    return options


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
        hint = "Run 'hawk init' in a project directory to add a local scope"

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
            menu_cursor_style=("fg_cyan", "bold"),
            menu_highlight_style=("fg_cyan", "bold"),
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
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
        quit_keys=("q", "\x1b"),
        status_bar="Space: toggle  Enter: confirm  q/Esc: back",
    )
    result = menu.show()
    if result is None:
        return False

    selected = set(result) if isinstance(result, tuple) else {result}
    changed = False
    cfg = state["cfg"]
    tools_cfg = cfg.get("tools", {})

    for i, tool in enumerate(tool_list):
        new_enabled = i in selected
        old_enabled = state["tools_status"][tool]["enabled"]
        if new_enabled != old_enabled:
            changed = True
            tool_key = str(tool)
            if tool_key not in tools_cfg:
                tools_cfg[tool_key] = {}
            tools_cfg[tool_key]["enabled"] = new_enabled
            state["tools_status"][tool]["enabled"] = new_enabled

    if changed:
        cfg["tools"] = tools_cfg
        v2_config.save_global_config(cfg)

    return changed


def _handle_packages(state: dict) -> bool:
    """Interactive packages management. Returns True if changes were made."""
    packages = v2_config.load_packages()

    if not packages:
        console.print("\n[dim]No packages installed.[/dim]")
        console.print("[dim]Run [cyan]hawk download <url>[/cyan] to install a package.[/dim]\n")
        wait_for_continue()
        return False

    dirty = False

    import readchar
    from rich.live import Live
    from rich.text import Text

    pkg_list = sorted(packages.items())
    cursor = 0

    def _build_pkg_menu() -> str:
        lines = ["[bold]hawk packages[/bold]"]
        lines.append("[dim]" + "\u2500" * 40 + "[/dim]")
        for i, (name, data) in enumerate(pkg_list):
            item_count = len(data.get("items", []))
            url = data.get("url", "")
            prefix = "\u276f " if i == cursor else "  "
            if i == cursor:
                lines.append(f"[bold cyan]{prefix}\U0001f4e6 {name:<30} {item_count} items[/bold cyan]")
            else:
                lines.append(f"{prefix}\U0001f4e6 {name:<30} {item_count} items")
            if i == cursor and url:
                lines.append(f"[dim]    {url}[/dim]")
        lines.append("")
        lines.append("[dim]Enter: toggle items  u: update  d/x: remove  U: update all  q: back[/dim]")
        return "\n".join(lines)

    with Live(Text.from_markup(_build_pkg_menu()), refresh_per_second=30, screen=True) as live:
        while True:
            key = readchar.readkey()

            if key in ("q", "\x1b"):
                break

            elif key in (readchar.key.UP, "k"):
                cursor = max(0, cursor - 1)

            elif key in (readchar.key.DOWN, "j"):
                cursor = min(len(pkg_list) - 1, cursor + 1)

            elif key in (readchar.key.ENTER, "\r", "\n"):
                pkg_name, pkg_data = pkg_list[cursor]
                live.stop()
                if _handle_package_toggle(state, pkg_name, pkg_data):
                    dirty = True
                # Reload packages in case toggle changed things
                packages = v2_config.load_packages()
                pkg_list = sorted(packages.items())
                if not pkg_list:
                    break
                cursor = min(cursor, len(pkg_list) - 1)
                live.start()

            elif key == "u":
                pkg_name = pkg_list[cursor][0]
                live.stop()
                console.print(f"\n[bold]Updating {pkg_name}...[/bold]")
                from ..v2_cli import cmd_update

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
                # Reload
                packages = v2_config.load_packages()
                pkg_list = sorted(packages.items())
                if not pkg_list:
                    break
                cursor = min(cursor, len(pkg_list) - 1)
                live.start()

            elif key == "U":
                live.stop()
                console.print("\n[bold]Updating all packages...[/bold]")
                from ..v2_cli import cmd_update

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
                packages = v2_config.load_packages()
                pkg_list = sorted(packages.items())
                if not pkg_list:
                    break
                cursor = min(cursor, len(pkg_list) - 1)
                live.start()

            elif key in ("x", "d"):
                pkg_name = pkg_list[cursor][0]
                live.stop()
                console.print(f"\n[yellow]Remove package '{pkg_name}'?[/yellow] [dim](y/N)[/dim] ", end="")
                confirm = readchar.readkey()
                console.print()
                if confirm.lower() == "y":
                    from ..v2_cli import cmd_remove_package

                    class _RmArgs:
                        name = pkg_name
                        yes = True
                    try:
                        cmd_remove_package(_RmArgs())
                    except SystemExit:
                        pass
                    dirty = True
                    console.print()
                    console.print("[dim]Press any key to continue...[/dim]")
                    readchar.readkey()
                packages = v2_config.load_packages()
                pkg_list = sorted(packages.items())
                if not pkg_list:
                    break
                cursor = min(cursor, len(pkg_list) - 1)
                live.start()

            live.update(Text.from_markup(_build_pkg_menu()))

    return dirty


def _handle_package_toggle(state: dict, pkg_name: str, pkg_data: dict) -> bool:
    """Toggle items within a single package, grouped by component type.

    Shows all component types from the package in one toggle view.
    Routes saves to the correct config field per type.
    Returns True if changes were made.
    """
    from pathlib import Path

    # 1. Build groups by component type + track item->field mapping
    toggle_groups: list[ToggleGroup] = []
    # Map item name -> set of config fields (handles same name across types)
    item_field_map: dict[str, set[str]] = {}
    all_pkg_items: set[str] = set()

    for display_name, field, ct in COMPONENT_TYPES:
        type_items = [
            item["name"] for item in pkg_data.get("items", [])
            if item.get("type") == ct.value
        ]
        if type_items:
            toggle_groups.append(ToggleGroup(
                key=field,
                label=display_name,
                items=sorted(type_items),
            ))
            for name in type_items:
                item_field_map.setdefault(name, set()).add(field)
                all_pkg_items.add(name)

    if not toggle_groups:
        console.print(f"\n[dim]No items in package {pkg_name}.[/dim]")
        wait_for_continue()
        return False

    # 2. Build scopes — collect enabled items across ALL types for this package
    scopes: list[ToggleScope] = []

    # Global scope
    global_cfg = state["global_cfg"]
    global_enabled = []
    for field in ["skills", "hooks", "prompts", "agents", "mcp"]:
        for name in global_cfg.get(field, []):
            if name in all_pkg_items:
                global_enabled.append(name)
    scopes.append(ToggleScope(
        key="global",
        label="\U0001f310 Global (default)",
        enabled=global_enabled,
    ))

    # Dir scopes from config chain
    project_dir = state.get("project_dir") or Path.cwd().resolve()
    config_chain = v2_config.get_config_chain(project_dir)

    if config_chain:
        for chain_dir, chain_config in config_chain:
            enabled = []
            for field in ["skills", "hooks", "prompts", "agents", "mcp"]:
                section = chain_config.get(field, {})
                if isinstance(section, dict):
                    for name in section.get("enabled", []):
                        if name in all_pkg_items:
                            enabled.append(name)
                elif isinstance(section, list):
                    for name in section:
                        if name in all_pkg_items:
                            enabled.append(name)

            if chain_dir == project_dir.resolve():
                label = f"\U0001f4cd This project: {chain_dir.name}"
            else:
                label = f"\U0001f4c1 {chain_dir.name}"

            scopes.append(ToggleScope(key=str(chain_dir), label=label, enabled=enabled))
    else:
        # No chain — only add local scope if config already exists
        local_cfg = state.get("local_cfg")
        if local_cfg is not None:
            local_enabled = []
            for field in ["skills", "hooks", "prompts", "agents", "mcp"]:
                section = local_cfg.get(field, {})
                if isinstance(section, dict):
                    for name in section.get("enabled", []):
                        if name in all_pkg_items:
                            local_enabled.append(name)

            project_name = state.get("project_name") or project_dir.name
            scopes.append(ToggleScope(
                key=str(project_dir),
                label=f"\U0001f4cd This project: {project_name}",
                enabled=local_enabled,
            ))

    # 3. Run toggle
    all_items = sorted(all_pkg_items)
    registry_path = v2_config.get_registry_path(state["cfg"])
    registry = state["registry"]

    hint = None
    if len(scopes) == 1 and state.get("local_cfg") is None:
        hint = "Run 'hawk init' in a project directory to add a local scope"

    # Delete callback — route to correct component type via item_field_map
    field_to_ct = {f: c for _, f, c in COMPONENT_TYPES}

    def _delete_pkg_item(name: str) -> bool:
        fields = item_field_map.get(name)
        if not fields:
            return False
        removed = False
        for field in fields:
            ct = field_to_ct.get(field)
            if ct and registry.remove(ct, name):
                removed = True
        if removed:
            state["contents"] = registry.list()
        return removed

    enabled_lists, changed = run_toggle_list(
        f"\U0001f4e6 {pkg_name}",
        all_items,
        scopes=scopes,
        start_scope_index=len(scopes) - 1,
        registry_path=registry_path,
        groups=toggle_groups,
        footer_hint=hint,
        on_delete=_delete_pkg_item,
    )

    # 4. Save changes — route per-type diffs to the correct config fields
    if changed:
        for i, scope in enumerate(scopes):
            new_enabled = set(enabled_lists[i])
            old_enabled = set(scope.enabled)

            if new_enabled == old_enabled:
                continue

            # Diff per field
            for field in ["skills", "hooks", "prompts", "agents", "mcp"]:
                field_items = {name for name, fields in item_field_map.items() if field in fields}
                if not field_items:
                    continue

                old_field = old_enabled & field_items
                new_field = new_enabled & field_items
                if old_field == new_field:
                    continue

                added = new_field - old_field
                removed = old_field - new_field

                if scope.key == "global":
                    current = list(state["global_cfg"].get(field, []))
                    updated = [n for n in current if n not in removed]
                    updated.extend(sorted(added - set(current)))
                    state["global_cfg"][field] = updated
                    cfg = state["cfg"]
                    cfg["global"] = state["global_cfg"]
                    v2_config.save_global_config(cfg)
                else:
                    dir_path = Path(scope.key)
                    dir_cfg = v2_config.load_dir_config(dir_path) or {}
                    section = dir_cfg.get(field, {})
                    if not isinstance(section, dict):
                        section = {"enabled": list(section) if isinstance(section, list) else []}
                    current = list(section.get("enabled", []))
                    updated = [n for n in current if n not in removed]
                    updated.extend(sorted(added - set(current)))
                    section["enabled"] = updated
                    dir_cfg[field] = section
                    v2_config.save_dir_config(dir_path, dir_cfg)

    return changed


def _handle_projects(state: dict) -> None:
    """Interactive projects tree view."""
    _run_projects_tree()


def _run_projects_tree() -> None:
    """Show interactive tree of all registered directories."""
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
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
        quit_keys=("q", "\x1b"),
        status_bar="Enter: open  q/Esc: back",
    )

    while True:
        choice = menu.show()
        if choice is None:
            break

        selected_path = menu_paths[choice]
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

    title = (
        "\nCodex agents need multi-agent mode\n\n"
        "Hawk can manage Codex multi-agent by writing:\n"
        "  [features]\n"
        "  multi_agent = true\n"
        "in .codex/config.toml with hawk-managed blocks."
    )
    if from_sync:
        title += "\n\nSync is about to run."

    menu = TerminalMenu(
        ["Enable now", "Not now", "Never"],
        title=title,
        cursor_index=0,
        menu_cursor="\u276f ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
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
    from ..v2_cli import cmd_download

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
    from ..v2_sync import format_sync_results, uninstall_all

    menu = TerminalMenu(
        ["No", "Yes, unlink + uninstall"],
        title=(
            "\nUnlink and uninstall hawk-managed state?\n"
            "This will purge tool links and clear registry/packages/config selections."
        ),
        cursor_index=0,
        menu_cursor="\u276f ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
        quit_keys=("q", "\x1b"),
    )
    choice = menu.show()
    if choice != 1:
        return False

    console.print("\n[bold red]Unlinking and uninstalling...[/bold red]")
    results = uninstall_all()
    formatted = format_sync_results(results, verbose=False)
    console.print(formatted or "  No changes.")
    console.print("\n[green]\u2714 Cleared hawk-managed config, packages, and registry state.[/green]\n")
    wait_for_continue()
    return True


def _handle_environment(state: dict) -> bool:
    """Environment submenu (tools, projects, preferences, uninstall)."""
    changed = False

    while True:
        menu = TerminalMenu(
            [
                "Tool Integrations",
                "Project Scopes",
                "Preferences",
                "Unlink and uninstall",
                "Back",
            ],
            title="\nEnvironment",
            cursor_index=0,
            menu_cursor="\u276f ",
            menu_cursor_style=("fg_cyan", "bold"),
            menu_highlight_style=("fg_cyan", "bold"),
            quit_keys=("q", "\x1b"),
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
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
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

        console.clear()
        header = _build_header(state)
        console.print(header)
        console.print("[dim]\u2500" * 50 + "[/dim]")

        options = _build_menu_options(state)
        menu_labels = [label if action is not None else None for label, action in options]

        menu = TerminalMenu(
            menu_labels,
            cursor_index=last_cursor,
            menu_cursor="\u276f ",
            menu_cursor_style=("fg_cyan", "bold"),
            menu_highlight_style=("fg_cyan", "bold"),
            accept_keys=("enter", " "),
            quit_keys=("q", "\x1b"),
            status_bar="\u2191\u2193: navigate  Space/Enter: select  q/Esc: quit",
        )
        choice = menu.show()
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

        if action in ("skills", "hooks", "prompts", "agents", "mcp"):
            if _handle_component_toggle(state, action):
                dirty = True
                dirty = _apply_auto_sync_if_needed(dirty, scope_dir=state.get("scope_dir"))

        elif action == "codex_multi_agent_setup":
            if _handle_codex_multi_agent_setup(state):
                dirty = True
                dirty = _apply_auto_sync_if_needed(dirty, scope_dir=state.get("scope_dir"))

        elif action == "packages":
            if _handle_packages(state):
                dirty = True
                dirty = _apply_auto_sync_if_needed(dirty, scope_dir=state.get("scope_dir"))

        elif action == "registry":
            _handle_registry_browser(state)

        elif action == "environment":
            if _handle_environment(state):
                dirty = True
                dirty = _apply_auto_sync_if_needed(dirty, scope_dir=state.get("scope_dir"))

        elif action == "download":
            _handle_download()
            # Reload state on next loop
