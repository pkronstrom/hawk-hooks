"""CLI interface for captain-hook."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__, config, generator, installer, scanner

console = Console()

# Custom style for questionary
custom_style = Style([
    ("qmark", "fg:cyan bold"),
    ("question", "fg:white bold"),
    ("answer", "fg:cyan"),
    ("pointer", "fg:cyan bold"),
    ("highlighted", "fg:cyan bold"),
    ("selected", "fg:green"),
    ("separator", "fg:gray"),
    ("instruction", "fg:gray"),
])


def print_header():
    """Print the application header."""
    console.print(Panel(
        f"[bold cyan]captain-hook[/bold cyan] v{__version__}\n"
        "[dim]A modular Claude Code hooks manager[/dim]",
        border_style="cyan",
    ))
    console.print()


def run_wizard():
    """Run the first-time setup wizard."""
    console.print(Panel(
        "[bold cyan]Welcome to captain-hook![/bold cyan]\n"
        "[dim]A modular Claude Code hooks manager[/dim]",
        border_style="cyan",
    ))
    console.print()

    # Brief explanation
    console.print("[bold]How it works:[/bold]")
    console.print("  1. Hooks are scripts in [cyan]~/.config/captain-hook/hooks/{event}/[/cyan]")
    console.print("  2. Enable/disable hooks to control what runs")
    console.print("  3. Claude runs enabled hooks on matching events")
    console.print()
    console.print("[dim]Formats: .py .sh .js .ts (scripts) | .stdout.md (context) | .prompt.json (LLM)[/dim]")
    console.print()

    # Ensure directories exist
    config.ensure_dirs()

    # Step 1: Choose installation level
    level = questionary.select(
        "Install hooks to:",
        choices=[
            questionary.Choice("User settings   ~/.claude/settings.json (all projects)", value="user"),
            questionary.Choice("Project settings  .claude/settings.json (this project)", value="project"),
        ],
        style=custom_style,
    ).ask()

    if level is None:
        return
    console.print()

    # Step 2: Install to Claude
    results = installer.install_hooks(level=level)
    for event, success in results.items():
        if success:
            console.print(f"  [green]✓[/green] Registered {event}")
    console.print()

    # Step 3: Go to toggle view (automatic)
    hooks = scanner.scan_hooks()
    has_hooks = any(hooks.values())

    if not has_hooks:
        console.print("[dim]No hooks found yet.[/dim]")
        console.print()

        # Check if examples directory exists (development install)
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
                for event in config.EVENTS:
                    src = examples_dir / event
                    dst = hooks_dir / event
                    if src.exists():
                        for hook_file in src.iterdir():
                            if hook_file.is_file():
                                shutil.copy(hook_file, dst / hook_file.name)
                                console.print(f"  [green]✓[/green] Copied {event}/{hook_file.name}")
                console.print()
                # Rescan hooks after copying
                hooks = scanner.scan_hooks()
                has_hooks = any(hooks.values())
        else:
            console.print(f"[dim]Add scripts to: {config.get_hooks_dir()}/{{event}}/[/dim]")
            console.print()

    if has_hooks:
        console.print("[bold]Configure hooks:[/bold]")
        scope = "global" if level == "user" else "project"
        interactive_toggle(skip_scope=True, scope=scope)

    # Step 4: Install deps (only if hooks exist)
    if has_hooks:
        install_py_deps = questionary.confirm(
            "Install Python dependencies?",
            default=True,
            style=custom_style,
        ).ask()
        console.print()

        if install_py_deps:
            install_deps()

    # Save config to mark setup as complete
    cfg = config.load_config()
    config.save_config(cfg)

    # Done
    console.print()
    console.print(Panel(
        "[bold green]You're all set![/bold green]\n\n"
        f"[dim]Config:[/dim] {config.get_config_path()}\n"
        f"[dim]Hooks:[/dim]  {config.get_hooks_dir()}\n\n"
        "[dim]Run[/dim] [cyan]captain-hook[/cyan] [dim]to manage hooks[/dim]\n"
        "[dim]Run[/dim] [cyan]captain-hook status[/cyan] [dim]to verify[/dim]",
        border_style="green",
    ))


def show_status():
    """Show status of all installed hooks and enabled handlers."""
    console.print()

    # Claude settings status
    status = installer.get_status()

    console.print("[bold]Claude Settings[/bold]")
    console.print("─" * 50)

    # User level
    if status["user"]["installed"]:
        console.print(f"  User:    [green]✓ Installed[/green]")
        console.print(f"           [dim]{status['user']['path']}[/dim]")
    else:
        console.print(f"  User:    [dim]✗ Not installed[/dim]")
        console.print(f"           [dim]{status['user']['path']}[/dim]")

    # Project level
    if status["project"]["installed"]:
        console.print(f"  Project: [green]✓ Installed[/green]")
        console.print(f"           [dim]{status['project']['path']}[/dim]")
    else:
        console.print(f"  Project: [dim]✗ Not installed[/dim]")
        console.print(f"           [dim]{status['project']['path']}[/dim]")

    console.print()

    # Discovered hooks
    console.print("[bold]Discovered Hooks[/bold]")
    console.print("─" * 50)

    hooks = scanner.scan_hooks()
    cfg = config.load_config()

    for event in config.EVENTS:
        event_hooks = hooks.get(event, [])
        enabled = cfg.get("enabled", {}).get(event, [])

        if not event_hooks:
            continue

        console.print(f"\n  [cyan]{event}[/cyan]")
        for hook in event_hooks:
            is_enabled = hook.name in enabled
            icon = "[green]✓[/green]" if is_enabled else "[dim]✗[/dim]"
            if hook.is_native_prompt:
                hook_type = "[magenta]prompt[/magenta]"
            elif hook.is_stdout:
                hook_type = "[cyan]stdout[/cyan]"
            else:
                hook_type = f"[dim]{hook.extension}[/dim]"
            console.print(f"    {icon} {hook.name:20} {hook_type:15} {hook.description}")

    console.print()

    # Project config indicator
    project_config = config.load_project_config()
    if project_config:
        console.print("[dim]Project overrides active: .claude/captain-hook/config.json[/dim]")
    else:
        console.print("[dim]Using global config[/dim]")

    console.print()


def interactive_install():
    """Interactive installation wizard."""
    level = questionary.select(
        "Install captain-hook to:",
        choices=[
            questionary.Choice("User settings   ~/.claude/settings.json (all projects)", value="user"),
            questionary.Choice("Project settings  .claude/settings.json (this project)", value="project"),
        ],
        style=custom_style,
    ).ask()

    if level is None:
        return

    console.print()
    console.print("[bold]Installing captain-hook...[/bold]")
    console.print()

    results = installer.install_hooks(level=level)

    for event, success in results.items():
        if success:
            console.print(f"  [green]✓[/green] Registered {event}")
        else:
            console.print(f"  [red]✗[/red] Failed to register {event}")

    console.print()
    console.print("[green]Done![/green] Use [cyan]Toggle[/cyan] to enable/disable hooks.")
    console.print()


def interactive_uninstall():
    """Interactive uninstallation wizard."""
    level = questionary.select(
        "Uninstall captain-hook from:",
        choices=[
            questionary.Choice("User settings   ~/.claude/settings.json", value="user"),
            questionary.Choice("Project settings  .claude/settings.json", value="project"),
            questionary.Choice("Both", value="both"),
        ],
        style=custom_style,
    ).ask()

    if level is None:
        return

    confirm = questionary.confirm(
        f"Remove captain-hook from {level} settings?",
        default=False,
        style=custom_style,
    ).ask()

    if not confirm:
        return

    # Uninstall from Claude
    if level == "both":
        installer.uninstall_hooks(level="user")
        installer.uninstall_hooks(level="project")
    else:
        installer.uninstall_hooks(level=level)

    console.print()
    console.print("[green]✓[/green] Removed from Claude settings")

    # Offer to clean up project files
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
    console.print("[dim]To fully remove captain-hook config, run:[/dim]")
    console.print(f"  [cyan]rm -rf {config.get_config_dir()}[/cyan]")
    console.print()


def interactive_toggle(skip_scope: bool = False, scope: str | None = None):
    """Interactive handler toggle with checkbox multi-select."""
    # First, ask for scope (unless skipped for wizard)
    if not skip_scope:
        scope = questionary.select(
            "Toggle scope:",
            choices=[
                questionary.Choice(f"Global        {config.get_config_path()}", value="global"),
                questionary.Choice(f"This project  .claude/captain-hook/", value="project"),
            ],
            style=custom_style,
        ).ask()

        if scope is None:
            return

    # For project scope, ask about git exclude
    add_to_git_exclude = True
    if scope == "project":
        visibility = questionary.select(
            "Project config visibility:",
            choices=[
                questionary.Choice("Personal   (added to .git/info/exclude)", value="personal"),
                questionary.Choice("Shared     (committable, team can use)", value="shared"),
            ],
            style=custom_style,
        ).ask()

        if visibility is None:
            return

        add_to_git_exclude = (visibility == "personal")

    # Scan for hooks
    hooks = scanner.scan_hooks()

    # Get current enabled state
    if scope == "global":
        current_enabled = config.load_config().get("enabled", {})
    else:
        project_cfg = config.load_project_config() or {}
        current_enabled = project_cfg.get("enabled", {})
        # Fall back to global for display
        if not current_enabled:
            current_enabled = config.load_config().get("enabled", {})

    # Build checkbox choices grouped by event
    choices = []

    for event in config.EVENTS:
        event_hooks = hooks.get(event, [])
        if not event_hooks:
            continue

        # Add separator for event group
        choices.append(questionary.Separator(f"── {event} ──"))

        enabled_list = current_enabled.get(event, [])

        for hook in event_hooks:
            is_enabled = hook.name in enabled_list
            if hook.is_native_prompt:
                hook_type = "[prompt]"
            elif hook.is_stdout:
                hook_type = "[stdout]"
            else:
                hook_type = f"[{hook.extension}]"
            label = f"{hook.name:20} {hook_type:10} {hook.description}"

            choices.append(questionary.Choice(
                label,
                value=(event, hook.name),
                checked=is_enabled,
            ))

    if not choices:
        console.print("[yellow]No hooks found. Add scripts to:[/yellow]")
        console.print(f"  {config.get_hooks_dir()}/{{event}}/")
        return

    console.print()
    selected = questionary.checkbox(
        f"Toggle hooks ({scope}):",
        choices=choices,
        style=custom_style,
        instruction="(Space toggle • A all • I invert • Enter save)",
    ).ask()

    if selected is None:
        return

    # Group selected by event
    enabled_by_event: dict[str, list[str]] = {event: [] for event in config.EVENTS}
    for event, hook_name in selected:
        enabled_by_event[event].append(hook_name)

    # Save config
    for event, enabled_hooks in enabled_by_event.items():
        config.set_enabled_hooks(
            event, enabled_hooks,
            scope=scope,
            add_to_git_exclude=add_to_git_exclude,
        )

    # Regenerate runners and sync prompt hooks
    console.print()
    console.print("[bold]Updating hooks...[/bold]")

    if scope == "project":
        runners = generator.generate_all_runners(scope="project", project_dir=Path.cwd())
        prompt_results = installer.sync_prompt_hooks(level="project", project_dir=Path.cwd())
    else:
        runners = generator.generate_all_runners(scope="global")
        prompt_results = installer.sync_prompt_hooks(level="user")

    for runner in runners:
        console.print(f"  [green]✓[/green] {runner.name}")

    for hook_name, success in prompt_results.items():
        if success:
            console.print(f"  [green]✓[/green] {hook_name} [dim](prompt)[/dim]")

    console.print()
    console.print(f"[green]Hooks updated ({scope}).[/green]")
    console.print("[dim]Changes take effect immediately.[/dim]")
    console.print()


def install_deps():
    """Install Python dependencies for hooks."""
    console.print("[bold]Installing dependencies...[/bold]")
    console.print()

    venv_dir = config.get_venv_dir()
    venv_python = config.get_venv_python()

    # Create venv if needed
    if not venv_dir.exists():
        console.print(f"  Creating venv at {venv_dir}...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            timeout=120,  # 2 minutes for venv creation
        )
        console.print(f"  [green]✓[/green] Venv created")

    # Get Python deps
    python_deps = scanner.get_python_deps()

    if python_deps:
        all_deps = set()
        for deps in python_deps.values():
            all_deps.update(deps)

        if all_deps:
            console.print(f"  Installing: {', '.join(sorted(all_deps))}")
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "--quiet"] + list(all_deps),
                check=True,
                timeout=300,  # 5 minutes for pip install
            )
            console.print(f"  [green]✓[/green] Python deps installed")
    else:
        console.print("  [dim]No Python dependencies required[/dim]")

    # Show non-Python deps
    other_deps = scanner.get_non_python_deps()
    if other_deps:
        console.print()
        console.print("[bold]Manual installation needed:[/bold]")
        for lang, hooks_deps in other_deps.items():
            all_lang_deps = set()
            for deps in hooks_deps.values():
                all_lang_deps.update(deps)
            if lang == "node":
                console.print(f"  Node: [cyan]npm install -g {' '.join(sorted(all_lang_deps))}[/cyan]")
            elif lang == "bash":
                console.print(f"  Shell tools: [cyan]{', '.join(sorted(all_lang_deps))}[/cyan]")

    console.print()


def interactive_menu():
    """Main interactive menu."""
    # Check for first run
    if not config.config_exists():
        answer = questionary.confirm(
            "First time setup - run wizard?",
            default=True,
            style=custom_style,
        ).ask()
        if answer is None:
            return  # User cancelled
        if answer:
            run_wizard()
            return

    print_header()

    while True:
        choice = questionary.select(
            "What would you like to do?",
            choices=[
                questionary.Choice("Status       Show hooks + enabled state", value="status"),
                questionary.Choice("Install      Register hooks in Claude settings", value="install"),
                questionary.Choice("Uninstall    Remove hooks from Claude settings", value="uninstall"),
                questionary.Choice("Toggle       Enable/disable hooks + regenerate", value="toggle"),
                questionary.Choice("Install-deps Install Python dependencies", value="deps"),
                questionary.Separator("─────────"),
                questionary.Choice("Exit", value="exit"),
            ],
            style=custom_style,
            instruction="(↑↓ navigate • Enter select • ESC back)",
        ).ask()

        if choice is None or choice == "exit":
            break

        if choice == "status":
            show_status()
        elif choice == "install":
            interactive_install()
        elif choice == "uninstall":
            interactive_uninstall()
        elif choice == "toggle":
            interactive_toggle()
        elif choice == "deps":
            install_deps()


# CLI commands for non-interactive use

def cmd_status(args):
    """CLI: Show status."""
    show_status()


def cmd_install(args):
    """CLI: Install hooks."""
    results = installer.install_hooks(level=args.level)
    for event, success in results.items():
        icon = "✓" if success else "✗"
        print(f"  {icon} {event}")


def cmd_uninstall(args):
    """CLI: Uninstall hooks."""
    installer.uninstall_hooks(level=args.level)
    print("Hooks uninstalled.")
    print(f"\nTo fully remove config: rm -rf {config.get_config_dir()}")


def cmd_toggle(args):
    """CLI: Toggle (non-interactive just regenerates)."""
    generator.generate_all_runners()
    print("Runners regenerated.")


def cmd_deps(args):
    """CLI: Install dependencies."""
    install_deps()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="captain-hook: A modular Claude Code hooks manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"captain-hook {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show hooks status")
    status_parser.set_defaults(func=cmd_status)

    # Install command
    install_parser = subparsers.add_parser("install", help="Install hooks to Claude settings")
    install_parser.add_argument(
        "--level", choices=["user", "project"], default="user",
        help="Installation level (default: user)"
    )
    install_parser.set_defaults(func=cmd_install)

    # Uninstall command
    uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall hooks from Claude settings")
    uninstall_parser.add_argument(
        "--level", choices=["user", "project"], default="user",
        help="Uninstallation level (default: user)"
    )
    uninstall_parser.set_defaults(func=cmd_uninstall)

    # Toggle command
    toggle_parser = subparsers.add_parser("toggle", help="Regenerate runners")
    toggle_parser.set_defaults(func=cmd_toggle)

    # Install-deps command
    deps_parser = subparsers.add_parser("install-deps", help="Install Python dependencies")
    deps_parser.set_defaults(func=cmd_deps)

    args = parser.parse_args()

    if args.command is None:
        interactive_menu()
    else:
        args.func(args)


if __name__ == "__main__":
    main()
