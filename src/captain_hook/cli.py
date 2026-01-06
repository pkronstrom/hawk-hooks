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
from rich.table import Table

from . import __version__, config, generator, installer, scanner, templates

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
        instruction="(Esc cancel)",
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
    console.print("[bold]Discovered Hooks[/bold]  [dim]([green]✓[/green] enabled  [dim]✗[/dim] disabled)[/dim]")
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
        instruction="(Esc cancel)",
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
        instruction="(Esc cancel)",
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
    console.print("[dim]To fully remove captain-hook:[/dim]")
    console.print(f"  [cyan]rm -rf {config.get_config_dir()}[/cyan]  [dim](config + hooks)[/dim]")
    console.print("  [cyan]pipx uninstall captain-hook[/cyan]  [dim](program)[/dim]")
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
            instruction="(Esc cancel)",
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
            instruction="(Esc cancel)",
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
        instruction="(Space toggle • A all • I invert • Enter save • Esc cancel)",
    ).ask()

    if selected is None:
        return

    console.print()

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
                        console.print(f"  [green]✓[/green] Shell tools installed")
                    except subprocess.CalledProcessError as e:
                        console.print(f"  [red]✗[/red] Installation failed (exit {e.returncode})")
                        console.print(f"  [dim]Run manually: {install_cmd}[/dim]")
                    except subprocess.TimeoutExpired:
                        console.print(f"  [red]✗[/red] Installation timed out")
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
                        console.print(f"  [green]✓[/green] Node packages installed")
                    except subprocess.CalledProcessError as e:
                        console.print(f"  [red]✗[/red] Installation failed (exit {e.returncode})")
                    except subprocess.TimeoutExpired:
                        console.print(f"  [red]✗[/red] Installation timed out")
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

    console.print()
    console.print("[bold]Configuration[/bold]")
    console.print("─" * 50)

    while True:
        # Build choices with current values
        debug_status = "✓ on " if cfg.get("debug", False) else "  off"

        choices = [
            questionary.Choice(f"debug           {debug_status}   Log hook calls", value="debug"),
        ]

        # Add script-defined env vars (grouped by prefix = hook name)
        if script_env_vars:
            choices.append(questionary.Separator("── Hook Settings ──"))

            # Group env vars by hook prefix
            for var_name, default_value in sorted(script_env_vars.items()):
                # Get current value (from config or default)
                current_value = env_config.get(var_name, default_value)

                # Detect boolean values
                is_bool = current_value.lower() in ("true", "false", "1", "0", "yes", "no")

                if is_bool:
                    is_on = current_value.lower() in ("true", "1", "yes")
                    status = "✓ on " if is_on else "  off"
                    display = f"{var_name:<25} {status}"
                else:
                    display_val = current_value[:15] if current_value else "(not set)"
                    display = f"{var_name:<25} {display_val}"

                choices.append(questionary.Choice(display, value=("env", var_name, is_bool)))

        choices.append(questionary.Separator("─────────"))
        choices.append(questionary.Choice("Back", value="back"))

        console.print()
        choice = questionary.select(
            "Select to toggle/edit:",
            choices=choices,
            style=custom_style,
            instruction="(Enter select • Esc back)",
        ).ask()

        if choice is None or choice == "back":
            break

        # Handle selection
        if choice == "debug":
            cfg["debug"] = not cfg.get("debug", False)
            debug_changed = True
            config.save_config(cfg)
        elif isinstance(choice, tuple) and choice[0] == "env":
            _, var_name, is_bool = choice
            current_value = env_config.get(var_name, script_env_vars.get(var_name, ""))

            if is_bool:
                # Toggle boolean
                is_on = current_value.lower() in ("true", "1", "yes")
                new_value = "false" if is_on else "true"
            else:
                # Text input for string values
                new_value = questionary.text(
                    f"{var_name}:",
                    default=current_value,
                    style=custom_style,
                ).ask()

            if new_value is not None:
                env_config[var_name] = new_value
                cfg["env"] = env_config
                config.save_config(cfg)
                env_changed = True

    # Regenerate runners if debug or env changed
    if debug_changed or env_changed:
        console.print()
        console.print("[bold]Regenerating runners...[/bold]")
        runners = generator.generate_all_runners()
        for runner in runners:
            console.print(f"  [green]✓[/green] {runner.name}")
        if debug_changed:
            console.print(f"[dim]Log file: {config.get_log_path()}[/dim]")

    console.print()


def interactive_add_hook():
    """Interactive hook creation wizard."""
    console.print()
    console.print("[bold]Add Hook[/bold]")
    console.print("─" * 50)

    # Step 1: Select event
    event = questionary.select(
        "Select event:",
        choices=[questionary.Choice(e, value=e) for e in config.EVENTS],
        style=custom_style,
        instruction="(Esc cancel)",
    ).ask()

    if event is None:
        return

    # Step 2: Select hook type
    hook_type = questionary.select(
        "Hook type:",
        choices=[
            questionary.Choice("Link existing script (updates with original)", value="link"),
            questionary.Choice("Copy existing script (independent snapshot)", value="copy"),
            questionary.Choice("Create command script (.py/.sh/.js/.ts)", value="script"),
            questionary.Choice("Create stdout hook (.stdout.md)", value="stdout"),
            questionary.Choice("Create prompt hook (.prompt.json)", value="prompt"),
        ],
        style=custom_style,
        instruction="(Esc cancel)",
    ).ask()

    if hook_type is None:
        return

    hooks_dir = config.get_hooks_dir() / event
    hooks_dir.mkdir(parents=True, exist_ok=True)

    if hook_type in ("link", "copy"):
        _add_existing_hook(event, hooks_dir, copy=(hook_type == "copy"))
    elif hook_type == "script":
        _add_new_script(event, hooks_dir)
    elif hook_type == "stdout":
        _add_new_stdout(event, hooks_dir)
    elif hook_type == "prompt":
        _add_new_prompt(event, hooks_dir)


def _add_existing_hook(event: str, hooks_dir: Path, copy: bool = False):
    """Link or copy an existing script."""
    # Get path from user
    path_str = questionary.path(
        "Script path:",
        style=custom_style,
    ).ask()

    if path_str is None:
        return

    source_path = Path(path_str).expanduser().resolve()

    # Validate file exists
    if not source_path.exists():
        console.print(f"[red]File not found:[/red] {source_path}")
        return

    # Validate extension
    valid_exts = {".py", ".sh", ".js", ".ts"}
    if source_path.suffix.lower() not in valid_exts:
        console.print(f"[red]Unsupported extension.[/red] Use: {', '.join(valid_exts)}")
        return

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
            console.print(f"  [green]✓[/green] Made executable")

    dest_path = hooks_dir / source_path.name

    # Check if already exists
    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {dest_path.name}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return
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


def _add_new_script(event: str, hooks_dir: Path):
    """Create a new script from template."""
    # Select script type
    script_type = questionary.select(
        "Script type:",
        choices=[
            questionary.Choice("Python (.py)", value=".py"),
            questionary.Choice("Shell (.sh)", value=".sh"),
            questionary.Choice("Node (.js)", value=".js"),
            questionary.Choice("TypeScript (.ts)", value=".ts"),
        ],
        style=custom_style,
        instruction="(Esc cancel)",
    ).ask()

    if script_type is None:
        return

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
        return

    # Validate suffix
    if not filename.endswith(script_type):
        console.print(f"[red]Filename must end with {script_type}[/red]")
        return

    dest_path = hooks_dir / filename

    # Check if already exists
    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {filename}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return

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


def _add_new_stdout(event: str, hooks_dir: Path):
    """Create a new stdout hook."""
    # Get filename
    filename = questionary.text(
        "Filename (must end with .stdout.md or .stdout.txt):",
        style=custom_style,
    ).ask()

    if filename is None:
        return

    # Validate suffix
    if not (filename.endswith(".stdout.md") or filename.endswith(".stdout.txt")):
        console.print("[red]Filename must end with .stdout.md or .stdout.txt[/red]")
        return

    dest_path = hooks_dir / filename

    # Check if already exists
    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {filename}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return

    # Write template
    dest_path.write_text(templates.STDOUT_TEMPLATE)
    console.print(f"  [green]✓[/green] Created {dest_path}")

    # Offer to open in editor
    _open_in_editor(dest_path)

    # Get hook name (part before .stdout.)
    hook_name = filename.split(".stdout.")[0]
    _prompt_enable_hook(event, hook_name)


def _add_new_prompt(event: str, hooks_dir: Path):
    """Create a new prompt hook."""
    # Get filename
    filename = questionary.text(
        "Filename (must end with .prompt.json):",
        style=custom_style,
    ).ask()

    if filename is None:
        return

    # Validate suffix
    if not filename.endswith(".prompt.json"):
        console.print("[red]Filename must end with .prompt.json[/red]")
        return

    dest_path = hooks_dir / filename

    # Check if already exists
    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {filename}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return

    # Write template
    dest_path.write_text(templates.PROMPT_TEMPLATE)
    console.print(f"  [green]✓[/green] Created {dest_path}")

    # Offer to open in editor
    _open_in_editor(dest_path)

    # Get hook name (part before .prompt.json)
    hook_name = filename[:-len(".prompt.json")]
    _prompt_enable_hook(event, hook_name)


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
    console.print(f"[green]Hook enabled![/green]")
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
                questionary.Choice("Toggle       Enable/disable hooks + regenerate", value="toggle"),
                questionary.Choice("Config       Debug mode, notifications", value="config"),
                questionary.Separator("─────────"),
                questionary.Choice("Install      Register hooks in Claude settings", value="install"),
                questionary.Choice("Uninstall    Remove hooks from Claude settings", value="uninstall"),
                questionary.Choice("Install-deps Install Python dependencies", value="deps"),
                questionary.Separator("─────────"),
                questionary.Choice("Exit", value="exit"),
            ],
            style=custom_style,
            instruction="(↑↓ navigate • Enter select • Ctrl+C exit)",
        ).ask()

        if choice is None or choice == "exit":
            break

        if choice == "status":
            show_status()
        elif choice == "toggle":
            interactive_toggle()
        elif choice == "config":
            interactive_config()
        elif choice == "install":
            interactive_install()
        elif choice == "uninstall":
            interactive_uninstall()
            break  # Exit after uninstall
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
    print(f"\nTo fully remove captain-hook:")
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
