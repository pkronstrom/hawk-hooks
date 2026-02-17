"""First-run wizard for hawk v2."""

from __future__ import annotations

from rich.console import Console
from simple_term_menu import TerminalMenu

from .. import __version__, v2_config
from ..adapters import get_adapter
from ..types import Tool

console = Console()


def run_wizard() -> None:
    """Guided first-time setup."""
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
    )
    result = menu.show()
    if result != 0:
        console.print("[dim]Setup cancelled.[/dim]")
        return

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

    # Step 3: Bootstrap - offer to download
    console.print()
    menu = TerminalMenu(
        ["Yes, download components", "No, I'll add them later"],
        title="Your registry is empty. Download starter components?",
        cursor_index=1,
        menu_cursor="\u276f ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
    )
    result = menu.show()
    if result == 0:
        url = console.input("\n[cyan]Git URL:[/cyan] ")
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
