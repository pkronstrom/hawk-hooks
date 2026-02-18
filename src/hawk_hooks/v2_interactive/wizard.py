"""First-run wizard for hawk v2."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from simple_term_menu import TerminalMenu

from .. import __version__, v2_config
from ..adapters import get_adapter
from ..types import Tool

console = Console()


def _get_builtins_path() -> Path | None:
    """Find the bundled builtins directory."""
    # Installed wheel location (src/hawk_hooks/builtins)
    p = Path(__file__).parent.parent / "builtins"
    if p.exists():
        return p
    # Editable install (repo root/builtins)
    p = Path(__file__).parent.parent.parent.parent / "builtins"
    if p.exists():
        return p
    return None


def run_wizard() -> bool:
    """Guided first-time setup. Returns True if completed, False if cancelled."""
    console.clear()
    console.print(f"\n[bold]\U0001f985 Welcome to hawk v{__version__}[/bold]")
    console.print("[dim]Multi-agent CLI package manager for AI tools[/dim]\n")
    console.print("Let's set up hawk for the first time.\n")

    # Step 1: Detect tools
    console.print("[bold]Detecting installed tools...[/bold]")
    found = {}
    for tool in Tool.all():
        adapter = get_adapter(tool)
        installed = adapter.detect_installed()
        found[tool] = installed
        icon = "[green]\u2714[/green]" if installed else "[dim]\u2716[/dim]"
        console.print(f"  {icon} {tool}")

    found_count = sum(1 for v in found.values() if v)
    console.print(f"\n  Found {found_count} tool(s).\n")

    # Step 2: Confirm and create config
    menu = TerminalMenu(
        ["Yes, create config", "Cancel"],
        title="Create hawk config with detected tools?",
        cursor_index=0,
        menu_cursor="\u276f ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
        quit_keys=("q", "\x1b"),
    )
    result = menu.show()
    if result != 0:
        console.print("[dim]Setup cancelled.[/dim]")
        return False

    # Create config
    v2_config.ensure_v2_dirs()
    cfg = v2_config.load_global_config()

    # Enable found tools, disable missing ones
    tools_cfg = cfg.get("tools", {})
    for tool in Tool.all():
        tool_key = str(tool)
        if tool_key not in tools_cfg:
            tools_cfg[tool_key] = {}
        tools_cfg[tool_key]["enabled"] = found[tool]
    cfg["tools"] = tools_cfg
    v2_config.save_global_config(cfg)

    console.print(f"\n[green]\u2714[/green] Config created at [cyan]{v2_config.get_global_config_path()}[/cyan]")

    # Step 3a: Install bundled builtins
    _offer_builtins_install(cfg)

    # Step 3b: Offer git download
    console.print()
    menu = TerminalMenu(
        ["Yes, download more", "No, I'm done"],
        title="Download additional components from git?",
        cursor_index=1,
        menu_cursor="\u276f ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
        quit_keys=("q", "\x1b"),
    )
    result = menu.show()
    if result == 0:
        try:
            url = console.input("\n[cyan]Git URL:[/cyan] ")
        except KeyboardInterrupt:
            return
        if url and url.strip():
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

    # Done
    console.print(f"\n[green]\u2714[/green] [bold]Setup complete![/bold]")
    console.print()
    console.print("[dim]Next steps:[/dim]")
    console.print("  [cyan]hawk download <url>[/cyan]   Add components from git")
    console.print("  [cyan]hawk add <type> <path>[/cyan] Add a local component")
    console.print("  [cyan]hawk sync[/cyan]              Sync to tool configs")
    console.print("  [cyan]hawk[/cyan]                   Open interactive menu")
    console.print()
    console.input("[dim]Press Enter to continue to the menu...[/dim]")
    return True


def _offer_builtins_install(cfg: dict) -> None:
    """Offer to install bundled agents, commands & hooks."""
    from ..downloader import add_items_to_registry, classify
    from ..registry import Registry
    from ..types import ComponentType

    builtins_path = _get_builtins_path()
    if not builtins_path:
        return

    content = classify(builtins_path)
    if not content.items:
        return

    agent_count = sum(1 for i in content.items if i.component_type == ComponentType.AGENT)
    command_count = sum(1 for i in content.items if i.component_type == ComponentType.COMMAND)
    hook_count = sum(1 for i in content.items if i.component_type == ComponentType.HOOK)
    parts = []
    if agent_count:
        parts.append(f"{agent_count} agents")
    if command_count:
        parts.append(f"{command_count} commands")
    if hook_count:
        parts.append(f"{hook_count} hook groups")
    desc = ", ".join(parts) if parts else f"{len(content.items)} components"

    console.print()
    menu = TerminalMenu(
        [f"Yes, install starter components ({desc})", "No, start empty"],
        title="Install bundled components?",
        cursor_index=0,
        menu_cursor="\u276f ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
        quit_keys=("q", "\x1b"),
    )
    result = menu.show()
    if result != 0:
        return

    registry = Registry(v2_config.get_registry_path(cfg))
    registry.ensure_dirs()
    added, skipped = add_items_to_registry(content.items, registry, replace=False)

    # Enable in global config
    if added:
        global_section = cfg.get("global", {})
        for item_str in added:
            ct_str, name = item_str.split("/", 1)
            field = ct_str + "s" if ct_str != "mcp" else "mcp"
            existing = global_section.get(field, [])
            if name not in existing:
                existing.append(name)
            global_section[field] = existing
        cfg["global"] = global_section
        v2_config.save_global_config(cfg)
        console.print(f"  [green]\u2714[/green] Installed {len(added)} components")
    if skipped:
        console.print(f"  [dim]Skipped {len(skipped)} (already in registry)[/dim]")
