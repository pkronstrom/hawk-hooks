"""Installation and setup wizards.

Install, uninstall, and first-run wizard functionality.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import questionary
from rich.panel import Panel

from rich_menu import InteractiveList, Item

from .. import config, installer, scanner
from ..events import EVENTS
from .core import console, custom_style
from .deps import install_deps
from .hooks import interactive_toggle


def interactive_install() -> bool:
    """Interactive installation wizard. Returns True on success, False on cancel."""
    console.clear()
    menu = InteractiveList(
        title="Install captain-hook to:",
        items=[
            Item.action("User settings   ~/.claude/settings.json (all projects)", value="user"),
            Item.action("Project settings  .claude/settings.json (this project)", value="project"),
        ],
        console=console,
    )
    result = menu.show()
    scope = result.get("action")

    if scope is None:
        return False

    console.print()
    console.print("[bold]Installing captain-hook...[/bold]")
    console.print()

    results = installer.install_hooks(scope=scope)

    for event, success in results.items():
        if success:
            console.print(f"  [green]✓[/green] Registered {event}")
        else:
            console.print(f"  [red]✗[/red] Failed to register {event}")

    console.print()
    console.print("[green]Done![/green] Use [cyan]Toggle[/cyan] to enable/disable hooks.")
    console.print()
    return True


def interactive_uninstall() -> bool:
    """Interactive uninstallation wizard. Returns True on success, False on cancel."""
    console.clear()
    menu = InteractiveList(
        title="Uninstall captain-hook from:",
        items=[
            Item.action("User settings   ~/.claude/settings.json", value="user"),
            Item.action("Project settings  .claude/settings.json", value="project"),
            Item.action("Both", value="both"),
        ],
        console=console,
    )
    result = menu.show()
    scope = result.get("action")

    if scope is None:
        return False

    confirm = questionary.confirm(
        f"Remove captain-hook from {scope} settings?",
        default=False,
        style=custom_style,
    ).ask()

    if not confirm:
        return False

    if scope == "both":
        installer.uninstall_hooks(scope="user")
        installer.uninstall_hooks(scope="project")
    else:
        installer.uninstall_hooks(scope=scope)

    console.print()
    console.print("[green]✓[/green] Removed from Claude settings")

    projects = config.get_tracked_projects()
    if projects:
        console.print()
        console.print(f"[bold]Tracked projects ({len(projects)}):[/bold]")
        for p in projects:
            console.print(f"  [dim]{p}[/dim]")

        if questionary.confirm(
            "Clean up project-specific files?",
            default=False,
            style=custom_style,
        ).ask():
            for project_path in projects:
                project_dir = Path(project_path)
                captain_hook_dir = project_dir / ".claude" / "captain-hook"
                if captain_hook_dir.exists():
                    shutil.rmtree(captain_hook_dir)
                    console.print(f"  [green]✓[/green] Removed {captain_hook_dir}")
                config.remove_tracked_project(project_path)

    console.print()
    console.print("[dim]To fully remove captain-hook:[/dim]")
    console.print(f"  [cyan]rm -rf {config.get_config_dir()}[/cyan]  [dim](config + hooks)[/dim]")
    console.print("  [cyan]pipx uninstall captain-hook[/cyan]  [dim](program)[/dim]")
    console.print()
    return True


def run_wizard():
    """Run the first-time setup wizard."""
    console.clear()
    console.print(
        Panel(
            "[bold cyan]Welcome to captain-hook![/bold cyan]\n"
            "[dim]A modular Claude Code hooks manager[/dim]",
            border_style="cyan",
        )
    )
    console.print()

    console.print("[bold]How it works:[/bold]")
    console.print("  1. Hooks are scripts in [cyan]~/.config/captain-hook/hooks/{event}/[/cyan]")
    console.print("  2. Enable/disable hooks to control what runs")
    console.print("  3. Claude runs enabled hooks on matching events")
    console.print()
    console.print(
        "[dim]Formats: .py .sh .js .ts (scripts) | .stdout.md (context) | .prompt.json (LLM)[/dim]"
    )
    console.print()

    config.ensure_dirs()

    menu = InteractiveList(
        title="Install hooks to:",
        items=[
            Item.action("User settings   ~/.claude/settings.json (all projects)", value="user"),
            Item.action("Project settings  .claude/settings.json (this project)", value="project"),
        ],
        console=console,
    )
    result = menu.show()
    scope = result.get("action")

    if scope is None:
        return
    console.print()

    results = installer.install_hooks(scope=scope)
    for event, success in results.items():
        if success:
            console.print(f"  [green]✓[/green] Registered {event}")
    console.print()

    hooks = scanner.scan_hooks()
    has_hooks = any(hooks.values())

    if not has_hooks:
        console.print("[dim]No hooks found yet.[/dim]")
        console.print()

        examples_dir = Path(__file__).parent.parent.parent / "examples" / "hooks"
        if examples_dir.exists():
            copy_examples = questionary.confirm(
                "Copy example hooks to config directory?",
                default=True,
                style=custom_style,
            ).ask()
            console.print()

            if copy_examples:
                hooks_dir = config.get_hooks_dir()
                for event in EVENTS:
                    src = examples_dir / event
                    dst = hooks_dir / event
                    if src.exists():
                        for hook_file in src.iterdir():
                            if hook_file.is_file():
                                shutil.copy(hook_file, dst / hook_file.name)
                                console.print(f"  [green]✓[/green] Copied {event}/{hook_file.name}")
                console.print()
                hooks = scanner.scan_hooks()
                has_hooks = any(hooks.values())
        else:
            console.print(f"[dim]Add scripts to: {config.get_hooks_dir()}/{{event}}/[/dim]")
            console.print()

    if has_hooks:
        console.print("[bold]Configure hooks:[/bold]")
        # Map install scope to toggle scope: "user" -> "global" (for display), "project" -> "project"
        toggle_scope = "global" if scope == "user" else "project"
        interactive_toggle(skip_scope=True, scope=toggle_scope)  # Uses string for UI display

    if has_hooks:
        venv_dir = config.get_venv_dir()
        install_py_deps = questionary.confirm(
            f"Install Python dependencies? ({venv_dir})",
            default=True,
            style=custom_style,
        ).ask()
        console.print()

        if install_py_deps:
            install_deps()

    cfg = config.load_config()
    config.save_config(cfg)

    console.print()
    console.print(
        Panel(
            "[bold green]You're all set![/bold green]\n\n"
            f"[dim]Config:[/dim] {config.get_config_path()}\n"
            f"[dim]Hooks:[/dim]  {config.get_hooks_dir()}\n\n"
            "[dim]Run[/dim] [cyan]captain-hook[/cyan] [dim]to manage hooks[/dim]\n"
            "[dim]Run[/dim] [cyan]captain-hook status[/cyan] [dim]to verify[/dim]",
            border_style="green",
        )
    )
