"""CLI interface for captain-hook."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel

from . import __version__, config, generator, installer, scanner, templates
from .rich_menu import InteractiveList, Item

console = Console()

# Custom style for questionary
custom_style = Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "fg:white bold"),
        ("answer", "fg:cyan"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:green"),
        ("separator", "fg:gray"),
        ("instruction", "fg:gray"),
    ]
)


def print_header():
    """Print the application header."""
    console.print(
        Panel(
            f"[bold cyan]captain-hook[/bold cyan] v{__version__}\n"
            "[dim]A modular Claude Code hooks manager[/dim]",
            border_style="cyan",
            width=100,
        )
    )
    console.print()


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

    # Brief explanation
    console.print("[bold]How it works:[/bold]")
    console.print("  1. Hooks are scripts in [cyan]~/.config/captain-hook/hooks/{event}/[/cyan]")
    console.print("  2. Enable/disable hooks to control what runs")
    console.print("  3. Claude runs enabled hooks on matching events")
    console.print()
    console.print(
        "[dim]Formats: .py .sh .js .ts (scripts) | .stdout.md (context) | .prompt.json (LLM)[/dim]"
    )
    console.print()

    # Ensure directories exist
    config.ensure_dirs()

    # Step 1: Choose installation level
    menu = InteractiveList(
        title="Install hooks to:",
        items=[
            Item.action("User settings   ~/.claude/settings.json (all projects)", value="user"),
            Item.action("Project settings  .claude/settings.json (this project)", value="project"),
        ],
        console=console,
    )
    result = menu.show()
    level = result.get("action")

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
        venv_dir = config.get_venv_dir()
        install_py_deps = questionary.confirm(
            f"Install Python dependencies? ({venv_dir})",
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


def show_status():
    """Show status of all installed hooks and enabled handlers."""
    console.clear()
    console.print()

    # Claude settings status
    status = installer.get_status()

    console.print("[bold]Claude Settings[/bold]")
    console.print("─" * 50)

    # User level
    if status["user"]["installed"]:
        console.print("  User:    [green]✓ Installed[/green]")
        console.print(f"           [dim]{status['user']['path']}[/dim]")
    else:
        console.print("  User:    [dim]✗ Not installed[/dim]")
        console.print(f"           [dim]{status['user']['path']}[/dim]")

    # Project level
    if status["project"]["installed"]:
        console.print("  Project: [green]✓ Installed[/green]")
        console.print(f"           [dim]{status['project']['path']}[/dim]")
    else:
        console.print("  Project: [dim]✗ Not installed[/dim]")
        console.print(f"           [dim]{status['project']['path']}[/dim]")

    console.print()

    # Discovered hooks
    console.print(
        "[bold]Discovered Hooks[/bold]  [dim]([green]✓[/green] enabled  [dim]✗[/dim] disabled)[/dim]"
    )
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
    level = result.get("action")

    if level is None:
        return False

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
    return True


def interactive_uninstall():
    """Interactive uninstallation wizard."""
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
    level = result.get("action")

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
    console.print("[dim]To fully remove captain-hook:[/dim]")
    console.print(f"  [cyan]rm -rf {config.get_config_dir()}[/cyan]  [dim](config + hooks)[/dim]")
    console.print("  [cyan]pipx uninstall captain-hook[/cyan]  [dim](program)[/dim]")
    console.print()


def interactive_toggle(skip_scope: bool = False, scope: str | None = None) -> bool:
    """Interactive handler toggle with checkbox multi-select. Returns True on success, False on cancel."""
    console.clear()
    # First, ask for scope (unless skipped for wizard)
    if not skip_scope:
        menu = InteractiveList(
            title="Toggle scope:",
            items=[
                Item.action(f"Global        {config.get_config_path()}", value="global"),
                Item.action("This project  .claude/captain-hook/", value="project"),
            ],
            console=console,
        )
        result = menu.show()
        scope = result.get("action")

        if scope is None:
            return False

    # For project scope, ask about git exclude
    add_to_git_exclude = True
    if scope == "project":
        console.clear()
        menu = InteractiveList(
            title="Project config visibility:",
            items=[
                Item.action("Personal   (added to .git/info/exclude)", value="personal"),
                Item.action("Shared     (committable, team can use)", value="shared"),
            ],
            console=console,
        )
        result = menu.show()
        visibility = result.get("action")

        if visibility is None:
            return False

        add_to_git_exclude = visibility == "personal"

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

    # Event name mapping with descriptions
    EVENT_INFO = {
        "pre_tool_use": ("PreToolUse", "Before each tool is executed"),
        "post_tool_use": ("PostToolUse", "After each tool completes"),
        "user_prompt_submit": ("UserPromptSubmit", "When user sends a message"),
        "session_start": ("SessionStart", "At the start of a session"),
        "session_end": ("SessionEnd", "When a session ends"),
        "pre_compact": ("PreCompact", "Before conversation is summarized"),
        "notification": ("Notification", "On system notifications"),
        "stop": ("Stop", "Before completing a response"),
        "subagent_stop": ("SubagentStop", "When a subagent completes"),
    }

    # Build checkbox menu items
    items = []
    for event in config.EVENTS:
        event_hooks = hooks.get(event, [])
        if not event_hooks:
            continue

        # Add separator with formatted event name and description
        if event in EVENT_INFO:
            event_display, event_desc = EVENT_INFO[event]
            items.append(Item.separator(f"── {event_display} - {event_desc} ──"))
        else:
            event_display = event.replace("_", " ").title()
            items.append(Item.separator(f"── {event_display} ──"))

        enabled_list = current_enabled.get(event, [])

        for hook in event_hooks:
            is_checked = hook.name in enabled_list

            # Build display label
            label = hook.name
            if hook.description:  # If hook has description metadata
                label = f"{hook.name} - {hook.description}"

            items.append(
                Item.checkbox(
                    key=(event, hook.name),
                    label=label,
                    checked=is_checked,
                )
            )

    if not items:
        console.print("[yellow]No hooks found. Add scripts to:[/yellow]")
        console.print(f"  {config.get_hooks_dir()}/{{event}}/")
        return False

    # Add submit/cancel actions
    items.append(Item.separator("─────────"))
    items.append(Item.action("Save", value="save"))
    items.append(Item.action("Cancel", value="cancel"))

    # Show menu
    menu = InteractiveList(title=f"Toggle hooks ({scope})", items=items, console=console)
    result = menu.show()

    # Handle cancel
    if result.get("action") == "cancel" or not result:
        return False

    # Handle exit without action (Esc/q)
    if "action" not in result:
        return False

    # Get checked items
    selected = menu.get_checked_values()

    console.print()

    # Group selected by event
    enabled_by_event: dict[str, list[str]] = {event: [] for event in config.EVENTS}
    for event, hook_name in selected:
        enabled_by_event[event].append(hook_name)

    # Save config
    for event, enabled_hooks in enabled_by_event.items():
        config.set_enabled_hooks(
            event,
            enabled_hooks,
            scope=scope,
            add_to_git_exclude=add_to_git_exclude,
        )

    # Regenerate runners and sync prompt hooks
    if scope == "project":
        runners = generator.generate_all_runners(scope="project", project_dir=Path.cwd())
        prompt_results = installer.sync_prompt_hooks(level="project", project_dir=Path.cwd())
    else:
        runners = generator.generate_all_runners(scope="global")
        prompt_results = installer.sync_prompt_hooks(level="user")

    # Build result message
    lines = []
    for runner in runners:
        lines.append(f"[green]✓[/green] {runner.name}")

    for hook_name, success in prompt_results.items():
        if success:
            lines.append(f"[green]✓[/green] {hook_name} [dim](prompt)[/dim]")

    result_content = "\n".join(lines) if lines else "[dim]No changes[/dim]"

    console.print()
    console.print(
        Panel(
            f"{result_content}\n\n[green]Hooks updated ({scope}).[/green]\n[dim]Changes take effect immediately.[/dim]",
            title="[bold]✓ Success[/bold]",
            border_style="green",
        )
    )
    console.print()
    return True


def _detect_package_manager() -> str | None:
    """Detect available package manager."""
    managers = [
        ("brew", "brew"),
        ("apt", "apt-get"),
        ("dnf", "dnf"),
        ("yum", "yum"),
        ("pacman", "pacman"),
        ("apk", "apk"),
    ]
    for name, cmd in managers:
        if shutil.which(cmd):
            return name
    return None


def _get_install_command(pkg_manager: str, packages: set[str]) -> str:
    """Get install command for package manager."""
    pkg_list = " ".join(sorted(packages))
    commands = {
        "brew": f"brew install {pkg_list}",
        "apt": f"sudo apt-get install -y {pkg_list}",
        "dnf": f"sudo dnf install -y {pkg_list}",
        "yum": f"sudo yum install -y {pkg_list}",
        "pacman": f"sudo pacman -S --noconfirm {pkg_list}",
        "apk": f"sudo apk add {pkg_list}",
    }
    return commands.get(pkg_manager, f"# Install: {pkg_list}")


def install_deps():
    """Install Python dependencies for hooks."""
    venv_dir = config.get_venv_dir()
    venv_python = config.get_venv_python()

    console.print("[bold]Installing dependencies...[/bold]")
    console.print(f"[dim]Venv location: {venv_dir}[/dim]")
    console.print()

    # Create venv if needed
    if not venv_dir.exists():
        console.print(f"  Creating venv at {venv_dir}...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            timeout=120,  # 2 minutes for venv creation
        )
        console.print("  [green]✓[/green] Venv created")

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
            console.print("  [green]✓[/green] Python deps installed")
    else:
        console.print("  [dim]No Python dependencies required[/dim]")

    # Handle non-Python deps
    other_deps = scanner.get_non_python_deps()
    if other_deps:
        console.print()

        # Collect shell tools
        shell_tools = set()
        node_deps = set()
        for lang, hooks_deps in other_deps.items():
            for deps in hooks_deps.values():
                if lang == "bash":
                    shell_tools.update(deps)
                elif lang == "node":
                    node_deps.update(deps)

        # Install shell tools via package manager
        if shell_tools:
            pkg_manager = _detect_package_manager()
            if pkg_manager:
                install_cmd = _get_install_command(pkg_manager, shell_tools)
                console.print(f"[bold]Shell tools needed:[/bold] {', '.join(sorted(shell_tools))}")
                console.print(f"[dim]Command: {install_cmd}[/dim]")
                console.print()

                install_shell = questionary.confirm(
                    f"Install via {pkg_manager}?",
                    default=True,
                    style=custom_style,
                ).ask()
                console.print()

                if install_shell:
                    try:
                        subprocess.run(install_cmd, shell=True, check=True, timeout=300)
                        console.print("  [green]✓[/green] Shell tools installed")
                    except subprocess.CalledProcessError as e:
                        console.print(f"  [red]✗[/red] Installation failed (exit {e.returncode})")
                        console.print(f"  [dim]Run manually: {install_cmd}[/dim]")
                    except subprocess.TimeoutExpired:
                        console.print("  [red]✗[/red] Installation timed out")
            else:
                console.print("[bold]Shell tools needed (install manually):[/bold]")
                console.print(f"  {', '.join(sorted(shell_tools))}")

        # Node deps
        if node_deps:
            console.print()
            npm_cmd = f"npm install -g {' '.join(sorted(node_deps))}"
            console.print(f"[bold]Node packages needed:[/bold] {', '.join(sorted(node_deps))}")
            console.print(f"[dim]Command: {npm_cmd}[/dim]")
            console.print()

            if shutil.which("npm"):
                install_node = questionary.confirm(
                    "Install via npm?",
                    default=True,
                    style=custom_style,
                ).ask()
                console.print()

                if install_node:
                    try:
                        subprocess.run(npm_cmd, shell=True, check=True, timeout=300)
                        console.print("  [green]✓[/green] Node packages installed")
                    except subprocess.CalledProcessError as e:
                        console.print(f"  [red]✗[/red] Installation failed (exit {e.returncode})")
                    except subprocess.TimeoutExpired:
                        console.print("  [red]✗[/red] Installation timed out")
            else:
                console.print("[dim]npm not found - install Node.js first[/dim]")

    console.print()


def interactive_config():
    """Interactive config editor with persistent menu."""
    cfg = config.load_config()
    debug_changed = False
    env_changed = False

    # Get all env vars from scripts (with defaults)
    script_env_vars = scanner.get_all_env_vars()

    # Merge script defaults with stored config values
    env_config = cfg.get("env", {})

    while True:
        console.clear()
        # Build menu items
        items = [
            Item.toggle("debug", "Log hook calls", value=cfg.get("debug", False)),
        ]

        # Add env var items
        if script_env_vars:
            items.append(Item.separator("── Hook Settings ──"))

            for var_name, default_value in sorted(script_env_vars.items()):
                current_value = env_config.get(var_name, default_value)
                # Ensure it's a string to avoid AttributeError
                if not isinstance(current_value, str):
                    current_value = str(current_value) if current_value is not None else ""
                is_bool = current_value.lower() in ("true", "false", "1", "0", "yes", "no")

                if is_bool:
                    value = current_value.lower() in ("true", "1", "yes")
                    items.append(Item.toggle(var_name, var_name, value=value))
                else:
                    items.append(Item.text(var_name, var_name, value=current_value))

        items.append(Item.separator("─────────"))
        items.append(Item.action("Back", value="back"))

        # Show menu
        menu = InteractiveList(title="Configuration", items=items, console=console)
        result = menu.show()

        # Handle exit (either "Back" action or cancellation via Esc/q/Ctrl+C)
        if result.get("action") == "back" or not result:
            break

        # Apply changes (don't save yet)
        for key, value in result.items():
            if key == "debug":
                cfg["debug"] = value
                debug_changed = True
            elif key in script_env_vars:
                # Convert bool back to string for env vars
                if isinstance(value, bool):
                    env_config[key] = "true" if value else "false"
                else:
                    env_config[key] = value.strip() if isinstance(value, str) else value
                cfg["env"] = env_config
                env_changed = True

    # Save config after loop if any changes were made
    if debug_changed or env_changed:
        config.save_config(cfg)
        console.print()
        console.print("[bold]Regenerating runners...[/bold]")
        runners = generator.generate_all_runners()
        for runner in runners:
            console.print(f"  [green]✓[/green] {runner.name}")
        if debug_changed:
            console.print(f"[dim]Log file: {config.get_log_path()}[/dim]")

    console.print()


def interactive_add_hook() -> bool:
    """Interactive hook creation wizard. Returns True on success, False on cancel."""
    console.clear()
    console.print()
    console.print("[bold]Add Hook[/bold]")
    console.print("─" * 50)

    # Step 1: Select event
    menu = InteractiveList(
        title="Select event:",
        items=[Item.action(e, value=e) for e in config.EVENTS],
        console=console,
    )
    result = menu.show()
    event = result.get("action")

    if event is None:
        return False

    # Step 2: Select hook type
    console.clear()
    menu = InteractiveList(
        title="Hook type:",
        items=[
            Item.action("Link existing script (updates with original)", value="link"),
            Item.action("Copy existing script (independent snapshot)", value="copy"),
            Item.action("Create command script (.py/.sh/.js/.ts)", value="script"),
            Item.action("Create stdout hook (.stdout.md)", value="stdout"),
            Item.action("Create prompt hook (.prompt.json)", value="prompt"),
        ],
        console=console,
    )
    result = menu.show()
    hook_type = result.get("action")

    if hook_type is None:
        return False

    hooks_dir = config.get_hooks_dir() / event
    hooks_dir.mkdir(parents=True, exist_ok=True)

    if hook_type in ("link", "copy"):
        return _add_existing_hook(event, hooks_dir, copy=(hook_type == "copy"))
    elif hook_type == "script":
        return _add_new_script(event, hooks_dir)
    elif hook_type == "stdout":
        return _add_new_stdout(event, hooks_dir)
    elif hook_type == "prompt":
        return _add_new_prompt(event, hooks_dir)
    return False


def _add_existing_hook(event: str, hooks_dir: Path, copy: bool = False) -> bool:
    """Link or copy an existing script. Returns True on success, False on cancel."""
    # Get path from user
    path_str = questionary.path(
        "Script path:",
        style=custom_style,
    ).ask()

    if path_str is None:
        return False

    source_path = Path(path_str).expanduser().resolve()

    # Validate file exists
    if not source_path.exists():
        console.print(f"[red]File not found:[/red] {source_path}")
        return False

    # Validate extension
    valid_exts = {".py", ".sh", ".js", ".ts"}
    if source_path.suffix.lower() not in valid_exts:
        console.print(f"[red]Unsupported extension.[/red] Use: {', '.join(valid_exts)}")
        return False

    # Check if executable (for scripts)
    if not os.access(source_path, os.X_OK):
        make_exec = questionary.confirm(
            "File is not executable. Make executable?",
            default=True,
            style=custom_style,
        ).ask()
        if make_exec:
            import stat

            current = source_path.stat().st_mode
            source_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            console.print("  [green]✓[/green] Made executable")

    dest_path = hooks_dir / source_path.name

    # Check if already exists
    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {dest_path.name}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return False
        dest_path.unlink()

    if copy:
        shutil.copy2(source_path, dest_path)
        console.print(f"  [green]✓[/green] Copied to {dest_path}")
    else:
        dest_path.symlink_to(source_path)
        console.print(f"  [green]✓[/green] Linked to {dest_path}")

    # Show docs path
    docs_path = templates.ensure_docs(config.get_docs_dir())
    console.print(f"  [dim]Docs: {docs_path}[/dim]")

    _prompt_enable_hook(event, source_path.stem)
    return True


def _add_new_script(event: str, hooks_dir: Path) -> bool:
    """Create a new script from template. Returns True on success, False on cancel."""
    console.clear()
    # Select script type
    menu = InteractiveList(
        title="Script type:",
        items=[
            Item.action("Python (.py)", value=".py"),
            Item.action("Shell (.sh)", value=".sh"),
            Item.action("Node (.js)", value=".js"),
            Item.action("TypeScript (.ts)", value=".ts"),
        ],
        console=console,
    )
    result = menu.show()
    script_type = result.get("action")

    if script_type is None:
        return False

    # Warn about TypeScript runtime if needed
    if script_type == ".ts":
        ts_runtime = templates.get_ts_runtime()
        if ts_runtime is None:
            console.print("[yellow]Warning:[/yellow] No TypeScript runtime found.")
            console.print("[dim]Install bun or npm to run .ts hooks.[/dim]")
            console.print()

    # Get filename
    filename = questionary.text(
        f"Filename (must end with {script_type}):",
        style=custom_style,
    ).ask()

    if filename is None:
        return False

    # Validate suffix
    if not filename.endswith(script_type):
        console.print(f"[red]Filename must end with {script_type}[/red]")
        return False

    dest_path = hooks_dir / filename

    # Check if already exists
    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {filename}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return False

    # Write template
    template_content = templates.get_template(script_type)
    dest_path.write_text(template_content)

    # Make executable
    import stat

    current = dest_path.stat().st_mode
    dest_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    console.print(f"  [green]✓[/green] Created {dest_path}")

    # Show docs path
    docs_path = templates.ensure_docs(config.get_docs_dir())
    console.print(f"  [dim]Docs: {docs_path}[/dim]")

    # Offer to open in editor
    _open_in_editor(dest_path)

    # Get hook name (stem without extension)
    hook_name = dest_path.stem
    _prompt_enable_hook(event, hook_name)
    return True


def _add_new_stdout(event: str, hooks_dir: Path) -> bool:
    """Create a new stdout hook. Returns True on success, False on cancel."""
    # Get filename
    filename = questionary.text(
        "Filename (must end with .stdout.md or .stdout.txt):",
        style=custom_style,
    ).ask()

    if filename is None:
        return False

    # Validate suffix
    if not (filename.endswith(".stdout.md") or filename.endswith(".stdout.txt")):
        console.print("[red]Filename must end with .stdout.md or .stdout.txt[/red]")
        return False

    dest_path = hooks_dir / filename

    # Check if already exists
    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {filename}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return False

    # Write template
    dest_path.write_text(templates.STDOUT_TEMPLATE)
    console.print(f"  [green]✓[/green] Created {dest_path}")

    # Offer to open in editor
    _open_in_editor(dest_path)

    # Get hook name (part before .stdout.)
    hook_name = filename.split(".stdout.")[0]
    _prompt_enable_hook(event, hook_name)
    return True


def _add_new_prompt(event: str, hooks_dir: Path) -> bool:
    """Create a new prompt hook. Returns True on success, False on cancel."""
    # Get filename
    filename = questionary.text(
        "Filename (must end with .prompt.json):",
        style=custom_style,
    ).ask()

    if filename is None:
        return False

    # Validate suffix
    if not filename.endswith(".prompt.json"):
        console.print("[red]Filename must end with .prompt.json[/red]")
        return False

    dest_path = hooks_dir / filename

    # Check if already exists
    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {filename}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return False

    # Write template
    dest_path.write_text(templates.PROMPT_TEMPLATE)
    console.print(f"  [green]✓[/green] Created {dest_path}")

    # Offer to open in editor
    _open_in_editor(dest_path)

    # Get hook name (part before .prompt.json)
    hook_name = filename[: -len(".prompt.json")]
    _prompt_enable_hook(event, hook_name)
    return True


def _open_in_editor(path: Path):
    """Offer to open file in editor."""
    open_editor = questionary.confirm(
        "Open in editor?",
        default=True,
        style=custom_style,
    ).ask()

    if not open_editor:
        return

    editor = os.environ.get("EDITOR")
    if not editor:
        if shutil.which("nano"):
            editor = "nano"
        elif shutil.which("vi"):
            editor = "vi"
        else:
            console.print(f"[yellow]No editor found.[/yellow] Edit manually: {path}")
            return

    try:
        subprocess.run([editor, str(path)], check=False)
    except Exception as e:
        console.print(f"[red]Failed to open editor:[/red] {e}")


def _prompt_enable_hook(event: str, hook_name: str):
    """Ask to enable the hook."""
    console.print()
    enable = questionary.confirm(
        "Enable this hook now?",
        default=True,
        style=custom_style,
    ).ask()

    if not enable:
        console.print("[dim]Hook created but not enabled. Use Toggle to enable later.[/dim]")
        return

    # Add to enabled hooks
    cfg = config.load_config()
    enabled = cfg.get("enabled", {}).get(event, [])
    if hook_name not in enabled:
        enabled.append(hook_name)
        config.set_enabled_hooks(event, enabled)

    # Regenerate runners
    console.print()
    console.print("[bold]Updating hooks...[/bold]")
    runners = generator.generate_all_runners()
    for runner in runners:
        console.print(f"  [green]✓[/green] {runner.name}")

    # Sync prompt hooks if needed
    prompt_results = installer.sync_prompt_hooks(level="user")
    for name, success in prompt_results.items():
        if success:
            console.print(f"  [green]✓[/green] {name} [dim](prompt)[/dim]")

    console.print()
    console.print("[green]Hook enabled![/green]")
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
        console.clear()
        print_header()
        menu = InteractiveList(
            title="What would you like to do?",
            items=[
                Item.action("Status       Show hooks + enabled state", value="status"),
                Item.action("Toggle       Enable/disable hooks + regenerate", value="toggle"),
                Item.action("Add hook    Create or link a new hook", value="add"),
                Item.action("Config       Debug mode, notifications", value="config"),
                Item.separator("─────────"),
                Item.action("Install      Register hooks in Claude settings", value="install"),
                Item.action("Uninstall    Remove hooks from Claude settings", value="uninstall"),
                Item.action("Install-deps Install Python dependencies", value="deps"),
                Item.separator("─────────"),
                Item.action("Exit", value="exit"),
            ],
            console=console,
        )
        result = menu.show()
        choice = result.get("action")

        if choice is None or choice == "exit":
            break

        if choice == "status":
            show_status()
        elif choice == "toggle":
            if interactive_toggle():
                break  # Exit on successful completion
        elif choice == "add":
            if interactive_add_hook():
                break  # Exit on successful completion
        elif choice == "config":
            interactive_config()
        elif choice == "install":
            if interactive_install():
                break  # Exit on successful completion
        elif choice == "uninstall":
            interactive_uninstall()
            break  # Exit after uninstall
        elif choice == "deps":
            install_deps()


# CLI commands for non-interactive use


def find_hook(name: str) -> tuple[str, str] | None:
    """Find hook by name, return (event, hook_name) or None.

    Supports formats:
      - "file-guard" - auto-detect event by scanning all events
      - "pre_tool_use/file-guard" - explicit event/hook
    """
    hooks = scanner.scan_hooks()

    # Check for explicit event/hook format
    if "/" in name:
        event, hook_name = name.split("/", 1)
        if event in hooks and any(h.name == hook_name for h in hooks[event]):
            return (event, hook_name)
        return None

    # Auto-detect: search all events
    for event, event_hooks in hooks.items():
        if any(h.name == name for h in event_hooks):
            return (event, name)
    return None


def cmd_enable(args):
    """CLI: Enable hooks by name."""
    changed = False
    for name in args.hooks:
        result = find_hook(name)
        if not result:
            print(f"  ✗ Hook not found: {name}")
            continue
        event, hook_name = result
        enabled = config.get_enabled_hooks(event)
        if hook_name not in enabled:
            enabled.append(hook_name)
            config.set_enabled_hooks(event, enabled)
            print(f"  ✓ Enabled {event}/{hook_name}")
            changed = True
        else:
            print(f"  - Already enabled: {event}/{hook_name}")

    if changed:
        generator.generate_all_runners()
        installer.sync_prompt_hooks(level="user")
        print("Runners regenerated.")


def cmd_disable(args):
    """CLI: Disable hooks by name."""
    changed = False
    for name in args.hooks:
        result = find_hook(name)
        if not result:
            print(f"  ✗ Hook not found: {name}")
            continue
        event, hook_name = result
        enabled = config.get_enabled_hooks(event)
        if hook_name in enabled:
            enabled.remove(hook_name)
            config.set_enabled_hooks(event, enabled)
            print(f"  ✓ Disabled {event}/{hook_name}")
            changed = True
        else:
            print(f"  - Already disabled: {event}/{hook_name}")

    if changed:
        generator.generate_all_runners()
        installer.sync_prompt_hooks(level="user")
        print("Runners regenerated.")


def cmd_list(args):
    """CLI: List hooks (scriptable output)."""
    hooks = scanner.scan_hooks()
    cfg = config.load_config()

    for event in config.EVENTS:
        event_hooks = hooks.get(event, [])
        if not event_hooks:
            continue

        enabled_list = cfg.get("enabled", {}).get(event, [])

        for hook in event_hooks:
            is_enabled = hook.name in enabled_list

            # Filter by --enabled or --disabled
            if args.enabled and not is_enabled:
                continue
            if args.disabled and is_enabled:
                continue

            status = "enabled" if is_enabled else "disabled"
            print(f"{event}/{hook.name}\t{status}\t{hook.description}")


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
    print("\nTo fully remove captain-hook:")
    print(f"  rm -rf {config.get_config_dir()}  # config + hooks")
    print("  pipx uninstall captain-hook        # program")


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
        "--level",
        choices=["user", "project"],
        default="user",
        help="Installation level (default: user)",
    )
    install_parser.set_defaults(func=cmd_install)

    # Uninstall command
    uninstall_parser = subparsers.add_parser(
        "uninstall", help="Uninstall hooks from Claude settings"
    )
    uninstall_parser.add_argument(
        "--level",
        choices=["user", "project"],
        default="user",
        help="Uninstallation level (default: user)",
    )
    uninstall_parser.set_defaults(func=cmd_uninstall)

    # Toggle command
    toggle_parser = subparsers.add_parser("toggle", help="Regenerate runners")
    toggle_parser.set_defaults(func=cmd_toggle)

    # Install-deps command
    deps_parser = subparsers.add_parser("install-deps", help="Install Python dependencies")
    deps_parser.set_defaults(func=cmd_deps)

    # Enable command
    enable_parser = subparsers.add_parser("enable", help="Enable hooks by name")
    enable_parser.add_argument(
        "hooks",
        nargs="+",
        help="Hook names (e.g., file-guard or pre_tool_use/file-guard)",
    )
    enable_parser.set_defaults(func=cmd_enable)

    # Disable command
    disable_parser = subparsers.add_parser("disable", help="Disable hooks by name")
    disable_parser.add_argument(
        "hooks",
        nargs="+",
        help="Hook names (e.g., file-guard or pre_tool_use/file-guard)",
    )
    disable_parser.set_defaults(func=cmd_disable)

    # List command
    list_parser = subparsers.add_parser("list", help="List hooks (scriptable output)")
    list_parser.add_argument(
        "--enabled",
        action="store_true",
        help="Show only enabled hooks",
    )
    list_parser.add_argument(
        "--disabled",
        action="store_true",
        help="Show only disabled hooks",
    )
    list_parser.set_defaults(func=cmd_list)

    args = parser.parse_args()

    if args.command is None:
        interactive_menu()
    else:
        args.func(args)


if __name__ == "__main__":
    main()
