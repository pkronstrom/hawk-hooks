"""First-run wizard for hawk v2."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from simple_term_menu import TerminalMenu

from .. import __version__, v2_config
from ..adapters import get_adapter
from ..types import Tool
from .pause import wait_for_continue
from .theme import get_theme, terminal_menu_style_kwargs

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
        **terminal_menu_style_kwargs(),
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

    accent = get_theme().accent_rich
    console.print(f"\n[green]\u2714[/green] Config created at [{accent}]{v2_config.get_global_config_path()}[/{accent}]")

    # Step 3a: Install bundled builtins
    _offer_builtins_install()

    # Done
    console.print(f"\n[green]\u2714[/green] [bold]Setup complete![/bold]")
    console.print()
    console.print("[dim]Next steps:[/dim]")
    console.print(f"  [{accent}]hawk download <url>[/{accent}]   Add components from git")
    console.print(f"  [{accent}]hawk add <type> <path>[/{accent}] Add a local component")
    console.print(f"  [{accent}]hawk[/{accent}]                   Open interactive menu")
    console.print()
    wait_for_continue("[dim]Press Enter/q/Ctrl+C to continue to the menu...[/dim]")
    return True


def _offer_builtins_install() -> None:
    """Offer to install bundled starter components as a local package."""
    from ..downloader import classify
    from ..types import ComponentType
    from ..cli import cmd_scan

    builtins_path = _get_builtins_path()
    if not builtins_path:
        return

    content = classify(builtins_path)
    if not content.items:
        return

    agent_count = sum(1 for i in content.items if i.component_type == ComponentType.AGENT)
    prompt_count = sum(1 for i in content.items if i.component_type == ComponentType.PROMPT)
    hook_count = sum(1 for i in content.items if i.component_type == ComponentType.HOOK)
    parts = []
    if agent_count:
        parts.append(f"{agent_count} agents")
    if prompt_count:
        parts.append(f"{prompt_count} prompts")
    if hook_count:
        parts.append(f"{hook_count} hook groups")
    desc = ", ".join(parts) if parts else f"{len(content.items)} components"

    console.print()
    menu = TerminalMenu(
        [f"Yes, install starter components ({desc})", "No, start empty"],
        title="Install bundled components?",
        cursor_index=0,
        menu_cursor="\u276f ",
        **terminal_menu_style_kwargs(),
        quit_keys=("q", "\x1b"),
    )
    result = menu.show()
    if result != 0:
        return

    class Args:
        pass

    args = Args()
    args.path = str(builtins_path)
    args.all = True
    args.replace = False
    args.depth = 5
    args.no_enable = False

    try:
        cmd_scan(args)
    except SystemExit:
        # cmd_scan reports conflicts/summary; wizard should continue either way
        pass
