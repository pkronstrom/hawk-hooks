"""Interactive UI components for captain-hook CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path

import questionary
import readchar
from questionary import Style
from rich.console import Console
from rich.console import Console as RichConsole
from rich.panel import Panel

from . import __version__, config, generator, installer, scanner, templates
from .events import EVENTS, get_event_display
from .hook_manager import HookManager
from .rich_menu import InteractiveList, Item
from .types import Scope

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


def show_status():
    """Show status of all installed hooks and enabled handlers."""
    console.clear()

    buffer = StringIO()
    temp_console = RichConsole(
        file=buffer, width=console.width, legacy_windows=False, force_terminal=True
    )

    temp_console.print()

    # Claude settings status
    status = installer.get_status()

    temp_console.print("[bold]Claude Settings[/bold]")
    temp_console.print("─" * 50)

    if status["user"]["installed"]:
        temp_console.print("  User:    [green]✓ Installed[/green]")
        temp_console.print(f"           [dim]{status['user']['path']}[/dim]")
    else:
        temp_console.print("  User:    [dim]✗ Not installed[/dim]")
        temp_console.print(f"           [dim]{status['user']['path']}[/dim]")

    if status["project"]["installed"]:
        temp_console.print("  Project: [green]✓ Installed[/green]")
        temp_console.print(f"           [dim]{status['project']['path']}[/dim]")
    else:
        temp_console.print("  Project: [dim]✗ Not installed[/dim]")
        temp_console.print(f"           [dim]{status['project']['path']}[/dim]")

    temp_console.print()

    # Load configs
    hooks = scanner.scan_hooks()
    global_cfg = config.load_config()
    project_cfg = config.load_project_config()
    has_project = project_cfg is not None and project_cfg.get("enabled")

    # Header
    if has_project:
        temp_console.print(
            "[bold]Enabled Hooks[/bold]  [dim]([yellow](P)[/yellow] project  [dim](G)[/dim] global)[/dim]"
        )
    else:
        temp_console.print("[bold]Enabled Hooks[/bold]")
    temp_console.print("─" * 50)

    any_enabled = False
    for event in EVENTS:
        event_hooks = hooks.get(event, [])
        if not event_hooks:
            continue

        global_enabled = global_cfg.get("enabled", {}).get(event, [])
        project_enabled = project_cfg.get("enabled", {}).get(event, []) if project_cfg else []

        enabled_hooks = []
        for hook in event_hooks:
            in_global = hook.name in global_enabled
            in_project = hook.name in project_enabled

            if has_project:
                if in_project:
                    enabled_hooks.append((hook, "project"))
                elif in_global:
                    enabled_hooks.append((hook, "global"))
            else:
                if in_global:
                    enabled_hooks.append((hook, "global"))

        if not enabled_hooks:
            continue

        event_display, event_desc = get_event_display(event)
        if event_desc:
            temp_console.print(f"\n  [cyan]{event_display}[/cyan] [dim]- {event_desc}[/dim]")
        else:
            temp_console.print(f"\n  [cyan]{event_display}[/cyan]")

        any_enabled = True

        for hook, scope in enabled_hooks:
            if hook.is_native_prompt:
                hook_type = "[magenta]prompt[/magenta]"
            elif hook.is_stdout:
                hook_type = "[cyan]stdout[/cyan]"
            else:
                hook_type = f"[dim]{hook.extension}[/dim]"

            scope_badge = ""
            if has_project:
                if scope == "project":
                    scope_badge = " [yellow](P)[/yellow]"
                else:
                    scope_badge = " [dim](G)[/dim]"

            temp_console.print(f"    [green]✓[/green] {hook.name} {hook_type}{scope_badge}")
            if hook.description:
                temp_console.print(f"       [dim]{hook.description}[/dim]")

    if not any_enabled:
        temp_console.print("\n  [dim]No hooks enabled[/dim]")

    temp_console.print()

    if has_project:
        temp_console.print("[dim]Project overrides active: .claude/captain-hook/config.json[/dim]")
    else:
        temp_console.print("[dim]Using global config[/dim]")

    temp_console.print()

    content = buffer.getvalue()
    lines = content.rstrip("\n").split("\n")
    terminal_height = console.height

    max_lines_per_page = terminal_height - 3

    if len(lines) <= max_lines_per_page:
        print(content, end="")
        console.print("[dim]Press Enter or q to exit...[/dim]")

        while True:
            key = readchar.readkey()
            if is_enter(key):
                break
            if is_exit(key):
                break
    else:
        window_offset = 0

        while True:
            console.clear()
            print()

            window_end = min(window_offset + max_lines_per_page, len(lines))
            visible_lines = lines[window_offset:window_end]

            for line in visible_lines:
                print(line)

            hint_parts = []
            lines_above = window_offset
            lines_below = len(lines) - window_end

            if lines_above > 0:
                hint_parts.append(f"[dim]↑ {lines_above} more above[/dim]")
            if lines_below > 0:
                hint_parts.append(f"[dim]↓ {lines_below} more below[/dim]")

            hint_parts.append(f"[dim]Line {window_offset + 1}-{window_end}/{len(lines)}[/dim]")
            hint_parts.append("[dim]↑/↓ scroll  Enter/q exit[/dim]")

            console.print("\n" + "  ".join(hint_parts))

            key = readchar.readkey()

            if is_down(key):
                if window_end < len(lines):
                    window_offset += 1
            elif is_up(key):
                if window_offset > 0:
                    window_offset -= 1
            elif is_enter(key):
                break
            elif is_exit(key):
                break


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


def interactive_toggle(skip_scope: bool = False, scope: str | None = None) -> bool:
    """Interactive handler toggle with checkbox multi-select."""
    console.clear()

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

    hooks = scanner.scan_hooks()

    global_enabled = config.load_config().get("enabled", {})
    project_enabled = {}

    if scope == "global":
        current_enabled = global_enabled
    else:
        project_cfg = config.load_project_config() or {}
        project_enabled = project_cfg.get("enabled", {})
        if project_enabled:
            current_enabled = project_enabled
        else:
            current_enabled = global_enabled

    original_enabled = {event: list(hooks_list) for event, hooks_list in current_enabled.items()}

    items = []
    for event in EVENTS:
        event_hooks = hooks.get(event, [])
        if not event_hooks:
            continue

        event_display, event_desc = get_event_display(event)
        if event_desc:
            items.append(Item.separator(f"── {event_display} - {event_desc} ──"))
        else:
            items.append(Item.separator(f"── {event_display} ──"))

        enabled_list = current_enabled.get(event, [])

        for hook in event_hooks:
            is_checked = hook.name in enabled_list

            label = hook.name
            if hook.description:
                label = f"{hook.name} - {hook.description}"

            if scope == "project":
                in_global = hook.name in global_enabled.get(event, [])
                in_project = hook.name in project_enabled.get(event, [])

                if in_global and in_project:
                    label = f"{label} [cyan](both)[/cyan]"
                elif in_project:
                    label = f"{label} [yellow](project)[/yellow]"
                elif in_global:
                    label = f"{label} [dim](global)[/dim]"

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

    items.append(Item.separator("─────────"))
    items.append(Item.action("Save", value="save"))
    items.append(Item.action("Cancel", value="cancel"))

    menu = InteractiveList(title=f"Toggle hooks ({scope})", items=items, console=console)
    result = menu.show()

    if result.get("action") == "cancel" or not result:
        return False

    if "action" not in result:
        return False

    selected = menu.get_checked_values()

    console.print()

    enabled_by_event: dict[str, list[str]] = {event: [] for event in EVENTS}
    for event, hook_name in selected:
        enabled_by_event[event].append(hook_name)

    manager = HookManager(scope=scope, project_dir=Path.cwd() if scope == "project" else None)

    for event, enabled_hooks in enabled_by_event.items():
        manager.set_enabled_hooks(event, enabled_hooks, add_to_git_exclude=add_to_git_exclude)

    manager.sync()

    lines = []
    for event in EVENTS:
        original = set(original_enabled.get(event, []))
        new = set(enabled_by_event.get(event, []))

        enabled = new - original
        disabled = original - new

        for hook_name in sorted(enabled):
            lines.append(f"[green]✓[/green] Enabled:  {event}/{hook_name}")

        for hook_name in sorted(disabled):
            lines.append(f"[red]✗[/red] Disabled: {event}/{hook_name}")

    result_content = "\n".join(lines) if lines else "[dim]No changes[/dim]"

    console.clear()
    console.print()
    console.print(
        Panel(
            f"{result_content}\n\n[dim]Changes take effect immediately.[/dim]\n\n[dim]Press Enter to continue...[/dim]",
            title=f"[bold green]Updated hooks ({scope})[/bold green]",
            border_style="green",
        )
    )

    while True:
        key = readchar.readkey()
        if is_enter(key):
            break

    return False


def interactive_config():
    """Interactive config editor with Save/Cancel menu."""
    cfg = config.load_config()

    script_env_vars = scanner.get_all_env_vars()
    env_config = cfg.get("env", {})

    original_debug = cfg.get("debug", False)
    original_env = dict(env_config)

    console.clear()
    items = [
        Item.toggle("debug", "Log hook calls", value=cfg.get("debug", False)),
    ]

    if script_env_vars:
        items.append(Item.separator("── Hook Settings ──"))

        for var_name, default_value in sorted(script_env_vars.items()):
            current_value = env_config.get(var_name, default_value)
            if not isinstance(current_value, str):
                current_value = str(current_value) if current_value is not None else ""
            is_bool = current_value.lower() in ("true", "false", "1", "0", "yes", "no")

            if is_bool:
                value = current_value.lower() in ("true", "1", "yes")
                items.append(Item.toggle(var_name, var_name, value=value))
            else:
                items.append(Item.text(var_name, var_name, value=current_value))

    items.append(Item.separator("─────────"))
    items.append(Item.action("Save", value="save"))
    items.append(Item.action("Cancel", value="cancel"))

    menu = InteractiveList(title="Configuration", items=items, console=console)
    result = menu.show()

    if result.get("action") == "cancel" or not result:
        return

    if "action" not in result:
        return

    debug_changed = False
    env_changed = False

    for key, value in result.items():
        if key == "action":
            continue
        if key == "debug":
            cfg["debug"] = value
            if value != original_debug:
                debug_changed = True
        elif key in script_env_vars:
            if isinstance(value, bool):
                env_config[key] = "true" if value else "false"
            else:
                env_config[key] = value.strip() if isinstance(value, str) else value
            cfg["env"] = env_config
            if env_config.get(key) != original_env.get(key):
                env_changed = True

    if debug_changed or env_changed:
        config.save_config(cfg)
        generator.generate_all_runners()

        lines = []
        if debug_changed:
            new_val = cfg.get("debug", False)
            lines.append(f"[cyan]debug:[/cyan] {original_debug} → {new_val}")

        for key in sorted(env_config.keys()):
            if env_config.get(key) != original_env.get(key):
                old_val = original_env.get(key, "")
                new_val = env_config.get(key, "")
                lines.append(f"[cyan]{key}:[/cyan] {old_val} → {new_val}")

        result_content = "\n".join(lines) if lines else "[dim]No changes[/dim]"

        console.clear()
        console.print()
        console.print(
            Panel(
                f"{result_content}\n\n[dim]Changes take effect immediately.[/dim]"
                + (f"\n[dim]Log file: {config.get_log_path()}[/dim]" if debug_changed else "")
                + "\n\n[dim]Press Enter to continue...[/dim]",
                title="[bold green]Configuration updated[/bold green]",
                border_style="green",
            )
        )

        while True:
            key = readchar.readkey()
            if is_enter(key):
                break
    else:
        console.clear()
        console.print()
        console.print(Panel("[dim]No changes[/dim]", title="Configuration", border_style="dim"))
        console.print()
        console.print("[dim]Press Enter to continue...[/dim]")

        while True:
            key = readchar.readkey()
            if is_enter(key):
                break


def interactive_add_hook() -> bool:
    """Interactive hook creation wizard."""
    console.clear()
    console.print()
    console.print("[bold]Add Hook[/bold]")
    console.print("─" * 50)

    menu = InteractiveList(
        title="Select event:",
        items=[Item.action(e, value=e) for e in EVENTS],
        console=console,
    )
    result = menu.show()
    event = result.get("action")

    if event is None:
        return False

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
    """Link or copy an existing script."""
    path_str = questionary.path("Script path:", style=custom_style).ask()

    if path_str is None:
        return False

    source_path = Path(path_str).expanduser().resolve()

    if not source_path.exists():
        console.print(f"[red]File not found:[/red] {source_path}")
        return False

    valid_exts = {".py", ".sh", ".js", ".ts"}
    if source_path.suffix.lower() not in valid_exts:
        console.print(f"[red]Unsupported extension.[/red] Use: {', '.join(valid_exts)}")
        return False

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

    docs_path = templates.ensure_docs(config.get_docs_dir())
    console.print(f"  [dim]Docs: {docs_path}[/dim]")

    _prompt_enable_hook(event, source_path.stem)
    return True


def _add_new_script(event: str, hooks_dir: Path) -> bool:
    """Create a new script from template."""
    console.clear()
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

    if script_type == ".ts":
        ts_runtime = templates.get_ts_runtime()
        if ts_runtime is None:
            console.print("[yellow]Warning:[/yellow] No TypeScript runtime found.")
            console.print("[dim]Install bun or npm to run .ts hooks.[/dim]")
            console.print()

    filename = questionary.text(
        f"Filename (must end with {script_type}):",
        style=custom_style,
    ).ask()

    if filename is None:
        return False

    if not filename.endswith(script_type):
        console.print(f"[red]Filename must end with {script_type}[/red]")
        console.print("[dim]Press Enter to continue...[/dim]")
        input()
        return False

    dest_path = hooks_dir / filename

    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {filename}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return False

    template_content = templates.get_template(script_type)
    dest_path.write_text(template_content)

    import stat

    current = dest_path.stat().st_mode
    dest_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    console.print(f"  [green]✓[/green] Created {dest_path}")

    docs_path = templates.ensure_docs(config.get_docs_dir())
    console.print(f"  [dim]Docs: {docs_path}[/dim]")

    _open_in_editor(dest_path)

    hook_name = dest_path.stem
    _prompt_enable_hook(event, hook_name)
    return True


def _add_new_stdout(event: str, hooks_dir: Path) -> bool:
    """Create a new stdout hook."""
    filename = questionary.text(
        "Filename (must end with .stdout.md or .stdout.txt):",
        style=custom_style,
    ).ask()

    if filename is None:
        return False

    if not (filename.endswith(".stdout.md") or filename.endswith(".stdout.txt")):
        console.print("[red]Filename must end with .stdout.md or .stdout.txt[/red]")
        console.print("[dim]Press Enter to continue...[/dim]")
        input()
        return False

    dest_path = hooks_dir / filename

    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {filename}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return False

    dest_path.write_text(templates.STDOUT_TEMPLATE)
    console.print(f"  [green]✓[/green] Created {dest_path}")

    _open_in_editor(dest_path)

    hook_name = filename.split(".stdout.")[0]
    _prompt_enable_hook(event, hook_name)
    return True


def _add_new_prompt(event: str, hooks_dir: Path) -> bool:
    """Create a new prompt hook."""
    filename = questionary.text(
        "Filename (must end with .prompt.json):",
        style=custom_style,
    ).ask()

    if filename is None:
        return False

    if not filename.endswith(".prompt.json"):
        console.print("[red]Filename must end with .prompt.json[/red]")
        console.print("[dim]Press Enter to continue...[/dim]")
        input()
        return False

    dest_path = hooks_dir / filename

    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {filename}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return False

    dest_path.write_text(templates.PROMPT_TEMPLATE)
    console.print(f"  [green]✓[/green] Created {dest_path}")

    _open_in_editor(dest_path)

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

    manager = HookManager(scope=Scope.USER)
    manager.enable_hook(event, hook_name)

    console.print()
    console.print("[green]Hook enabled![/green]")
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
    """Get install command for package manager (display only)."""
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


def _get_install_command_list(pkg_manager: str, packages: set[str]) -> list[str]:
    """Get install command as a list for subprocess."""
    pkg_list = sorted(packages)
    commands: dict[str, list[str]] = {
        "brew": ["brew", "install", *pkg_list],
        "apt": ["sudo", "apt-get", "install", "-y", *pkg_list],
        "dnf": ["sudo", "dnf", "install", "-y", *pkg_list],
        "yum": ["sudo", "yum", "install", "-y", *pkg_list],
        "pacman": ["sudo", "pacman", "-S", "--noconfirm", *pkg_list],
        "apk": ["sudo", "apk", "add", *pkg_list],
    }
    return commands.get(pkg_manager, [])


def install_deps():
    """Install Python dependencies for hooks."""
    venv_dir = config.get_venv_dir()
    venv_python = config.get_venv_python()

    console.print("[bold]Installing dependencies...[/bold]")
    console.print(f"[dim]Venv location: {venv_dir}[/dim]")
    console.print()

    if not venv_dir.exists():
        console.print(f"  Creating venv at {venv_dir}...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            timeout=120,
        )
        console.print("  [green]✓[/green] Venv created")

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
                timeout=300,
            )
            console.print("  [green]✓[/green] Python deps installed")
    else:
        console.print("  [dim]No Python dependencies required[/dim]")

    other_deps = scanner.get_non_python_deps()
    if other_deps:
        console.print()

        shell_tools = set()
        node_deps = set()
        for lang, hooks_deps in other_deps.items():
            for deps in hooks_deps.values():
                if lang == "bash":
                    shell_tools.update(deps)
                elif lang == "node":
                    node_deps.update(deps)

        if shell_tools:
            pkg_manager = _detect_package_manager()
            if pkg_manager:
                install_cmd_display = _get_install_command(pkg_manager, shell_tools)
                install_cmd_list = _get_install_command_list(pkg_manager, shell_tools)
                console.print(f"[bold]Shell tools needed:[/bold] {', '.join(sorted(shell_tools))}")
                console.print(f"[dim]Command: {install_cmd_display}[/dim]")
                console.print()

                install_shell = questionary.confirm(
                    f"Install via {pkg_manager}?",
                    default=True,
                    style=custom_style,
                ).ask()
                console.print()

                if install_shell and install_cmd_list:
                    try:
                        subprocess.run(install_cmd_list, check=True, timeout=300)
                        console.print("  [green]✓[/green] Shell tools installed")
                    except subprocess.CalledProcessError as e:
                        console.print(f"  [red]✗[/red] Installation failed (exit {e.returncode})")
                        console.print(f"  [dim]Run manually: {install_cmd_display}[/dim]")
                    except subprocess.TimeoutExpired:
                        console.print("  [red]✗[/red] Installation timed out")
            else:
                console.print("[bold]Shell tools needed (install manually):[/bold]")
                console.print(f"  {', '.join(sorted(shell_tools))}")

        if node_deps:
            console.print()
            npm_cmd_display = f"npm install -g {' '.join(sorted(node_deps))}"
            npm_cmd_list = ["npm", "install", "-g", *sorted(node_deps)]
            console.print(f"[bold]Node packages needed:[/bold] {', '.join(sorted(node_deps))}")
            console.print(f"[dim]Command: {npm_cmd_display}[/dim]")
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
                        subprocess.run(npm_cmd_list, check=True, timeout=300)
                        console.print("  [green]✓[/green] Node packages installed")
                    except subprocess.CalledProcessError as e:
                        console.print(f"  [red]✗[/red] Installation failed (exit {e.returncode})")
                    except subprocess.TimeoutExpired:
                        console.print("  [red]✗[/red] Installation timed out")
            else:
                console.print("[dim]npm not found - install Node.js first[/dim]")

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


def interactive_menu():
    """Main interactive menu."""
    if not config.config_exists():
        answer = questionary.confirm(
            "First time setup - run wizard?",
            default=True,
            style=custom_style,
        ).ask()
        if answer is None:
            return
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
            console.clear()
            break

        if choice == "status":
            show_status()
        elif choice == "toggle":
            if interactive_toggle():
                break
        elif choice == "add":
            if interactive_add_hook():
                break
        elif choice == "config":
            interactive_config()
        elif choice == "install":
            if interactive_install():
                break
        elif choice == "uninstall":
            if interactive_uninstall():
                break
        elif choice == "deps":
            install_deps()
