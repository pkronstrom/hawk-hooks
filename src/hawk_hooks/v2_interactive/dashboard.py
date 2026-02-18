"""Main dashboard and menu for hawk v2 TUI."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from simple_term_menu import TerminalMenu

from .. import __version__, v2_config
from ..adapters import get_adapter
from ..registry import Registry
from ..resolver import resolve
from ..types import ComponentType, Tool
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


def _detect_scope() -> tuple[str, Path | None, str | None]:
    """Detect whether cwd is a hawk-initialized directory.

    Returns:
        (scope, project_dir, project_name)
        scope is "local" or "global"
    """
    cwd = Path.cwd().resolve()
    dir_config = v2_config.load_dir_config(cwd)
    if dir_config is not None:
        return "local", cwd, cwd.name

    # Also check if registered in global index
    dirs = v2_config.get_registered_directories()
    cwd_str = str(cwd)
    if cwd_str in dirs:
        return "local", cwd, cwd.name

    return "global", None, None


def _load_state() -> dict:
    """Load all state needed for the dashboard."""
    cfg = v2_config.load_global_config()
    registry = Registry(v2_config.get_registry_path(cfg))
    contents = registry.list()

    scope, project_dir, project_name = _detect_scope()

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

    options.append(("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", None))
    options.append(("Settings       Editor, paths, behavior", "settings"))
    options.append(("Sync           Apply changes to tools", "sync"))
    options.append(("Exit", "exit"))

    return options


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
    registry_names = sorted(state["contents"].get(ct, []))

    # Get current enabled lists
    global_enabled = list(state["global_cfg"].get(field, []))

    # Always allow local scope — use cwd as project dir
    project_dir = state.get("project_dir") or Path.cwd().resolve()
    project_name = state.get("project_name") or project_dir.name
    local_is_new = state["local_cfg"] is None

    local_enabled: list[str] = []
    if state["local_cfg"] is not None:
        local_section = state["local_cfg"].get(field, {})
        if isinstance(local_section, dict):
            local_enabled = list(local_section.get("enabled", []))

    start_scope = state["scope"]

    # Registry path for open/edit
    registry_path = v2_config.get_registry_path(state["cfg"])
    registry_dir = ct.registry_dir if ct else ""

    # MCP gets an "Add" action
    on_add = None
    add_label = "Add new..."
    if ct == ComponentType.MCP:
        on_add = _make_mcp_add_callback(state)
        add_label = "Add MCP server..."

    new_global, new_local, changed = run_toggle_list(
        display_name,
        registry_names,
        global_enabled,
        local_enabled,
        project_name,
        start_scope,
        registry_path=registry_path,
        registry_dir=registry_dir,
        local_is_new=local_is_new,
        on_add=on_add,
        add_label=add_label,
    )

    if changed:
        # Update global config
        state["global_cfg"][field] = new_global
        cfg = state["cfg"]
        cfg["global"] = state["global_cfg"]
        v2_config.save_global_config(cfg)

        # Update local config (auto-create if new)
        if new_local is not None:
            if local_is_new:
                # Auto-create .hawk/config.yaml and register directory
                v2_config.save_dir_config(project_dir, {})
                v2_config.register_directory(project_dir)
                state["local_cfg"] = {}
                state["project_dir"] = project_dir
                state["project_name"] = project_name
                state["scope"] = "local"

            local_cfg = state["local_cfg"] or {}
            local_section = local_cfg.get(field, {})
            if not isinstance(local_section, dict):
                local_section = {}
            local_section["enabled"] = new_local
            local_cfg[field] = local_section
            state["local_cfg"] = local_cfg
            v2_config.save_dir_config(project_dir, local_cfg)

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


def run_dashboard() -> None:
    """Run the main dashboard loop."""
    dirty = False

    while True:
        state = _load_state()

        console.clear()
        header = _build_header(state)
        console.print(header)
        console.print("[dim]\u2500" * 50 + "[/dim]")

        options = _build_menu_options(state)
        menu_labels = [label for label, _ in options]

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

        elif action == "registry":
            _handle_registry_browse(state)

        elif action == "sync":
            _handle_sync(state)
            dirty = False  # Just synced

        elif action == "settings":
            from .config_editor import run_config_editor
            run_config_editor()

        elif action == "download":
            _handle_download()
            # Reload state on next loop
