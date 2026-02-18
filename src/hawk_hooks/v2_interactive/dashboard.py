"""Main dashboard and menu for hawk v2 TUI."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from simple_term_menu import TerminalMenu

from .. import __version__, v2_config
from ..adapters import get_adapter
from ..registry import Registry
from ..resolver import resolve
from ..types import ComponentType, ToggleGroup, ToggleScope, Tool
from .toggle import run_toggle_list

console = Console()

# Component types shown in the menu, in order
COMPONENT_TYPES = [
    ("Skills", "skills", ComponentType.SKILL),
    ("Hooks", "hooks", ComponentType.HOOK),
    ("Commands", "commands", ComponentType.COMMAND),
    ("Agents", "agents", ComponentType.AGENT),
    ("MCP Servers", "mcp", ComponentType.MCP),
]


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

    # Also check if registered in global index
    dirs = v2_config.get_registered_directories()
    cwd_str = str(cwd)
    if cwd_str in dirs:
        return "local", cwd, cwd.name

    return "global", None, None


def _load_state(scope_dir: str | None = None) -> dict:
    """Load all state needed for the dashboard."""
    cfg = v2_config.load_global_config()
    registry = Registry(v2_config.get_registry_path(cfg))
    contents = registry.list()

    scope, project_dir, project_name = _detect_scope(scope_dir)

    # Load enabled lists
    global_cfg = cfg.get("global", {})

    local_cfg = None
    if project_dir:
        local_cfg = v2_config.load_dir_config(project_dir) or {}

    # Detect tools
    tools_status = {}
    for tool in Tool.all():
        adapter = get_adapter(tool)
        installed = adapter.detect_installed()
        tool_cfg = cfg.get("tools", {}).get(str(tool), {})
        enabled = tool_cfg.get("enabled", True)
        tools_status[tool] = {"installed": installed, "enabled": enabled}

    return {
        "cfg": cfg,
        "registry": registry,
        "contents": contents,
        "scope": scope,
        "project_dir": project_dir,
        "project_name": project_name,
        "global_cfg": global_cfg,
        "local_cfg": local_cfg,
        "tools_status": tools_status,
        "scope_dir": scope_dir,
    }


def _count_enabled(state: dict, field: str) -> str:
    """Count enabled items for a component field."""
    global_list = state["global_cfg"].get(field, [])
    g_count = len(global_list)

    if state["scope"] == "local" and state["local_cfg"] is not None:
        local_extra = state["local_cfg"].get(field, {})
        if isinstance(local_extra, dict):
            l_enabled = local_extra.get("enabled", [])
            l_disabled = local_extra.get("disabled", [])
            l_count = len(l_enabled)
            total = g_count + l_count - len(set(l_disabled) & set(global_list))
        else:
            l_count = 0
            total = g_count
        return f"{total} enabled ({g_count} global + {l_count} local)"
    return f"{g_count} enabled"


def _build_header(state: dict) -> str:
    """Build the dashboard header string."""
    total_components = sum(len(names) for names in state["contents"].values())
    tools_active = sum(1 for t in state["tools_status"].values() if t["installed"] and t["enabled"])

    header = f"\U0001f985 hawk v{__version__} \u2014 {total_components} components, {tools_active} tools"

    if state["scope"] == "local" and state["project_name"]:
        header += f"\n\U0001f4cd This project: {state['project_dir']}"
    else:
        header += f"\n\U0001f310 All projects"

    return header


def _build_menu_options(state: dict) -> list[tuple[str, str | None]]:
    """Build main menu options with counts."""
    options: list[tuple[str, str | None]] = []

    for display_name, field, ct in COMPONENT_TYPES:
        count_str = _count_enabled(state, field)
        reg_count = len(state["contents"].get(ct, []))
        label = f"{display_name:<14} {count_str}"
        if reg_count == 0:
            if ct == ComponentType.MCP:
                label = f"{display_name:<14} (empty \u2014 add with +)"
            else:
                label = f"{display_name:<14} (empty)"
        options.append((label, field))

    options.append(("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", None))
    options.append(("Download       Fetch from git URL", "download"))

    # Packages count
    packages = v2_config.load_packages()
    pkg_count = len(packages)
    if pkg_count > 0:
        options.append((f"Packages       {pkg_count} installed, manage & update", "packages"))
    else:
        options.append(("Packages       (none installed)", "packages"))

    options.append(("Registry       Browse installed items", "registry"))

    # Tools summary
    tool_parts = []
    for tool in Tool.all():
        ts = state["tools_status"][tool]
        if ts["installed"] and ts["enabled"]:
            tool_parts.append(f"{tool} \u2714")
        elif ts["installed"]:
            tool_parts.append(f"{tool} \u2716")
        else:
            tool_parts.append(str(tool))
    tools_str = "  ".join(tool_parts)
    options.append((f"Tools          {tools_str}", "tools"))
    options.append(("Projects       Manage registered directories", "projects"))

    options.append(("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", None))
    options.append(("Settings       Editor, paths, behavior", "settings"))
    options.append(("Sync           Apply changes to tools", "sync"))
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

        # Name
        name = console.input("\n[cyan]Server name[/cyan] (e.g. github, postgres): ").strip()
        if not name:
            console.print("[dim]Cancelled.[/dim]")
            return None

        # Validate name
        if "/" in name or ".." in name or name.startswith("."):
            console.print("[red]Invalid name.[/red]")
            console.input("[dim]Press Enter to continue...[/dim]")
            return None

        # Check clash
        if registry.has(ComponentType.MCP, name + ".yaml"):
            console.print(f"[red]Already exists: mcp/{name}.yaml[/red]")
            console.input("[dim]Press Enter to continue...[/dim]")
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
        menu_cursor="\u276f ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
        quit_keys=("q",),
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


def _handle_registry_browse(state: dict) -> None:
    """Interactive registry browser with sections, view, edit, remove."""
    import readchar
    from rich.live import Live
    from rich.text import Text

    from .toggle import (
        _get_terminal_height, _calculate_visible_range,
        _pick_file, _view_in_terminal, _open_in_finder, _open_in_editor,
    )

    registry = state["registry"]
    registry_path = v2_config.get_registry_path(state["cfg"])

    # Build flat list with section headers
    rows: list[tuple[str, str | None, ComponentType | None]] = []  # (label, name, ct)
    for ct, names in state["contents"].items():
        if names:
            rows.append((f"[bold]{ct.registry_dir}/[/bold]", None, None))  # section header
            for name in sorted(names):
                rows.append((name, name, ct))

    if not rows:
        console.print("\n[dim]Registry is empty. Run [cyan]hawk download <url>[/cyan] to add components.[/dim]\n")
        console.input("[dim]Press Enter to continue...[/dim]")
        return

    cursor = 0
    # Start on first non-header item
    if rows[0][1] is None and len(rows) > 1:
        cursor = 1
    status_msg = ""

    def _is_header(idx: int) -> bool:
        return rows[idx][1] is None

    def _build_display() -> str:
        lines: list[str] = []
        total = len(rows)
        total_items = sum(len(n) for n in state["contents"].values())
        lines.append(f"[bold]Registry[/bold] \u2014 {total_items} components")
        lines.append("[dim]\u2500" * 50 + "[/dim]")

        max_visible = _get_terminal_height() - 7
        _, vis_start, vis_end = _calculate_visible_range(cursor, total, max_visible, 0)

        if vis_start > 0:
            lines.append(f"[dim]  \u2191 {vis_start} more[/dim]")

        for i in range(vis_start, vis_end):
            is_cur = i == cursor
            label, name, ct = rows[i]

            if name is None:
                # Section header
                lines.append(f"\n  {label}")
            else:
                prefix = "[cyan]\u276f[/cyan] " if is_cur else "    "
                style = "[bold]" if is_cur else ""
                end = "[/bold]" if is_cur else ""
                lines.append(f"{prefix}{style}{name}{end}")

        if vis_end < total:
            lines.append(f"[dim]  \u2193 {total - vis_end} more[/dim]")

        if status_msg:
            lines.append(f"\n[dim]{status_msg}[/dim]")

        lines.append("")
        lines.append("[dim]\u2191\u2193/jk: navigate  v: view  e: edit  o: open  x: remove  q: done[/dim]")
        return "\n".join(lines)

    def _get_item_path(idx: int) -> Path | None:
        _, name, ct = rows[idx]
        if name and ct:
            p = registry_path / ct.registry_dir / name
            return p if p.exists() else None
        return None

    with Live("", console=console, refresh_per_second=15, transient=True) as live:
        live.update(Text.from_markup(_build_display()))
        while True:
            try:
                key = readchar.readkey()
            except (KeyboardInterrupt, EOFError):
                break

            status_msg = ""
            total = len(rows)

            if key in (readchar.key.UP, "k"):
                cursor = (cursor - 1) % total
                if _is_header(cursor):
                    cursor = (cursor - 1) % total
            elif key in (readchar.key.DOWN, "j"):
                cursor = (cursor + 1) % total
                if _is_header(cursor):
                    cursor = (cursor + 1) % total

            elif key == "v":
                path = _get_item_path(cursor)
                if path:
                    live.stop()
                    target = _pick_file(path)
                    if target:
                        _view_in_terminal(target)
                    live.start()

            elif key == "o":
                path = _get_item_path(cursor)
                if path:
                    live.stop()
                    _open_in_finder(path)
                    status_msg = f"Opened {rows[cursor][1]}"
                    live.start()

            elif key == "e":
                path = _get_item_path(cursor)
                if path:
                    live.stop()
                    _open_in_editor(path)
                    live.start()

            elif key == "x":
                _, name, ct = rows[cursor]
                if name and ct:
                    # Confirm removal
                    live.stop()
                    confirm_menu = TerminalMenu(
                        ["No", "Yes, remove"],
                        title=f"\nRemove {ct.value}/{name} from registry?",
                        cursor_index=0,
                        menu_cursor="\u276f ",
                        menu_cursor_style=("fg_cyan", "bold"),
                        menu_highlight_style=("fg_cyan", "bold"),
                    )
                    result = confirm_menu.show()
                    if result == 1:
                        if registry.remove(ct, name):
                            status_msg = f"Removed {ct.value}/{name}"
                            # Rebuild rows
                            state["contents"] = registry.list()
                            rows.clear()
                            for rct, rnames in state["contents"].items():
                                if rnames:
                                    rows.append((f"[bold]{rct.registry_dir}/[/bold]", None, None))
                                    for rn in sorted(rnames):
                                        rows.append((rn, rn, rct))
                            if not rows:
                                live.start()
                                break
                            cursor = min(cursor, len(rows) - 1)
                            if _is_header(cursor) and cursor + 1 < len(rows):
                                cursor += 1
                            elif _is_header(cursor) and cursor > 0:
                                cursor -= 1
                        else:
                            status_msg = f"Failed to remove {name}"
                    live.start()

            elif key in ("q", "\x1b"):
                break

            live.update(Text.from_markup(_build_display()))


def _handle_packages(state: dict) -> bool:
    """Interactive packages management. Returns True if changes were made."""
    packages = v2_config.load_packages()

    if not packages:
        console.print("\n[dim]No packages installed.[/dim]")
        console.print("[dim]Run [cyan]hawk download <url>[/cyan] to install a package.[/dim]\n")
        console.input("[dim]Press Enter to continue...[/dim]")
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
            style = "bold cyan" if i == cursor else ""
            lines.append(f"[{style}]{prefix}\U0001f4e6 {name:<30} {item_count} items[/{style}]")
            if i == cursor and url:
                lines.append(f"[dim]    {url}[/dim]")
        lines.append("")
        lines.append("[dim]Enter: toggle items  u: update  x: remove  U: update all  q: back[/dim]")
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
                console.input("[dim]Press Enter to continue...[/dim]")
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
                console.input("[dim]Press Enter to continue...[/dim]")
                packages = v2_config.load_packages()
                pkg_list = sorted(packages.items())
                if not pkg_list:
                    break
                cursor = min(cursor, len(pkg_list) - 1)
                live.start()

            elif key == "x":
                pkg_name = pkg_list[cursor][0]
                live.stop()
                console.print(f"\n[yellow]Remove package '{pkg_name}'?[/yellow]")
                confirm = console.input("[dim]Type 'yes' to confirm: [/dim]")
                if confirm.strip().lower() == "yes":
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
                console.input("[dim]Press Enter to continue...[/dim]")
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
    item_field_map: dict[str, str] = {}  # item name -> config field ("skills", "commands", etc.)
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
                item_field_map[name] = field
                all_pkg_items.add(name)

    if not toggle_groups:
        console.print(f"\n[dim]No items in package {pkg_name}.[/dim]")
        console.input("[dim]Press Enter to continue...[/dim]")
        return False

    # 2. Build scopes — collect enabled items across ALL types for this package
    scopes: list[ToggleScope] = []

    # Global scope
    global_cfg = state["global_cfg"]
    global_enabled = []
    for field in ["skills", "hooks", "commands", "agents", "mcp"]:
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
            for field in ["skills", "hooks", "commands", "agents", "mcp"]:
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
            for field in ["skills", "hooks", "commands", "agents", "mcp"]:
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

    hint = None
    if len(scopes) == 1 and state.get("local_cfg") is None:
        hint = "Run 'hawk init' in a project directory to add a local scope"

    enabled_lists, changed = run_toggle_list(
        f"\U0001f4e6 {pkg_name}",
        all_items,
        scopes=scopes,
        start_scope_index=len(scopes) - 1,
        registry_path=registry_path,
        groups=toggle_groups,
        footer_hint=hint,
    )

    # 4. Save changes — route per-type diffs to the correct config fields
    if changed:
        for i, scope in enumerate(scopes):
            new_enabled = set(enabled_lists[i])
            old_enabled = set(scope.enabled)

            if new_enabled == old_enabled:
                continue

            # Diff per field
            for field in ["skills", "hooks", "commands", "agents", "mcp"]:
                field_items = {name for name, f in item_field_map.items() if f == field}
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
        console.input("[dim]Press Enter to continue...[/dim]")
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
            for field in ["skills", "hooks", "commands", "agents", "mcp"]:
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
    for field in ["skills", "hooks", "commands", "agents", "mcp"]:
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
        quit_keys=("q",),
        status_bar="[Enter: edit]  [q: quit]",
    )

    while True:
        choice = menu.show()
        if choice is None:
            break

        selected_path = menu_paths[choice]
        if selected_path == "global":
            # Show global config editor or toggle
            console.print(f"\n[dim]Global config: {v2_config.get_global_config_path()}[/dim]")
            console.input("[dim]Press Enter to continue...[/dim]")
        else:
            # Open dashboard scoped to that directory
            from . import v2_interactive_menu
            v2_interactive_menu(scope_dir=selected_path)
            break


def _handle_sync(state: dict) -> None:
    """Run sync and show results."""
    from ..v2_sync import format_sync_results, sync_all

    console.print("\n[bold]Syncing...[/bold]")
    all_results = sync_all(force=True)
    formatted = format_sync_results(all_results)
    console.print(formatted or "  No changes.")
    console.print()
    console.input("[dim]Press Enter to continue...[/dim]")


def _handle_download() -> None:
    """Run download flow."""
    console.print("\n[bold]Download components from git[/bold]")
    url = console.input("[cyan]URL:[/cyan] ")
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
    console.input("[dim]Press Enter to continue...[/dim]")


def _prompt_sync_on_exit(dirty: bool) -> None:
    """If changes were made, prompt to sync."""
    if not dirty:
        return

    menu = TerminalMenu(
        ["Yes", "No"],
        title="\nChanges made. Sync to tools now?",
        cursor_index=0,
        menu_cursor="\u276f ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
    )
    result = menu.show()
    if result == 0:
        from ..v2_sync import format_sync_results, sync_all

        console.print("[bold]Syncing...[/bold]")
        all_results = sync_all(force=True)
        formatted = format_sync_results(all_results)
        console.print(formatted or "  No changes.")


def run_dashboard(scope_dir: str | None = None) -> None:
    """Run the main dashboard loop.

    Args:
        scope_dir: Optional directory to scope the TUI to.
    """
    dirty = False

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
            menu_cursor="\u276f ",
            menu_cursor_style=("fg_cyan", "bold"),
            menu_highlight_style=("fg_cyan", "bold"),
            quit_keys=("q",),
        )
        choice = menu.show()

        if choice is None:
            # q pressed
            _prompt_sync_on_exit(dirty)
            console.clear()
            break

        _, action = options[choice]

        if action is None:
            # Separator
            continue

        if action == "exit":
            _prompt_sync_on_exit(dirty)
            console.clear()
            break

        if action in ("skills", "hooks", "commands", "agents", "mcp"):
            if _handle_component_toggle(state, action):
                dirty = True

        elif action == "tools":
            if _handle_tools_toggle(state):
                dirty = True

        elif action == "packages":
            if _handle_packages(state):
                dirty = True

        elif action == "registry":
            _handle_registry_browse(state)

        elif action == "projects":
            _handle_projects(state)

        elif action == "sync":
            _handle_sync(state)
            dirty = False  # Just synced

        elif action == "settings":
            from .config_editor import run_config_editor
            run_config_editor()

        elif action == "download":
            _handle_download()
            # Reload state on next loop
