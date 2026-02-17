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
        header += f"\n\U0001f4cd Local: {state['project_dir']}"
    else:
        header += f"\n\U0001f310 Global"

    return header


def _build_menu_options(state: dict) -> list[tuple[str, str | None]]:
    """Build main menu options with counts."""
    options: list[tuple[str, str | None]] = []

    for display_name, field, ct in COMPONENT_TYPES:
        count_str = _count_enabled(state, field)
        reg_count = len(state["contents"].get(ct, []))
        label = f"{display_name:<14} {count_str}"
        if reg_count == 0:
            label = f"{display_name:<14} [dim](empty)[/dim]"
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
            tool_parts.append(f"[dim]{tool}[/dim]")
    tools_str = "  ".join(tool_parts)
    options.append((f"Tools          {tools_str}", "tools"))

    options.append(("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", None))
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

    local_enabled = None
    if state["local_cfg"] is not None:
        local_section = state["local_cfg"].get(field, {})
        if isinstance(local_section, dict):
            local_enabled = list(local_section.get("enabled", []))
        else:
            local_enabled = []

    start_scope = state["scope"]

    new_global, new_local, changed = run_toggle_list(
        display_name,
        registry_names,
        global_enabled,
        local_enabled,
        state["project_name"],
        start_scope,
    )

    if changed:
        # Update global config
        state["global_cfg"][field] = new_global
        cfg = state["cfg"]
        cfg["global"] = state["global_cfg"]
        v2_config.save_global_config(cfg)

        # Update local config
        if new_local is not None and state["project_dir"]:
            local_cfg = state["local_cfg"] or {}
            local_section = local_cfg.get(field, {})
            if not isinstance(local_section, dict):
                local_section = {}
            local_section["enabled"] = new_local
            local_cfg[field] = local_section
            state["local_cfg"] = local_cfg
            v2_config.save_dir_config(state["project_dir"], local_cfg)

    return changed


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
    """Show read-only registry browser."""
    lines = []
    for ct, names in state["contents"].items():
        if names:
            lines.append(f"  {ct.registry_dir}/")
            for name in sorted(names):
                lines.append(f"    {name}")

    if not lines:
        console.print("\n[dim]Registry is empty. Run [cyan]hawk download <url>[/cyan] to add components.[/dim]\n")
    else:
        console.print(f"\n[bold]Registry[/bold] \u2014 {sum(len(n) for n in state['contents'].values())} components")
        console.print("[dim]\u2500" * 40 + "[/dim]")
        for line in lines:
            console.print(line)
        console.print()

    console.input("[dim]Press Enter to continue...[/dim]")


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

        elif action == "download":
            _handle_download()
            # Reload state on next loop
