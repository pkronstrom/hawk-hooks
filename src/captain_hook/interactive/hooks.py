"""Hook management UI.

Status display, toggle, add, edit, delete functionality for hooks.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path

import questionary
import readchar
from rich.console import Console as RichConsole
from rich.panel import Panel

from rich_menu import InteractiveList, Item
from rich_menu.keys import is_enter

from .. import config, installer, scanner, templates
from ..events import EVENTS, get_event_display
from ..hook_manager import HookManager
from ..types import Scope
from .core import _paginate_output, _with_paused_live, console, custom_style
from .prompts import _add_agent, _add_command


def _render_install_status(temp_console: RichConsole, status) -> None:
    """Render Claude settings installation status."""
    temp_console.print("[bold]Claude Settings[/bold]")
    temp_console.print("─" * 50)

    if status.user.installed:
        temp_console.print("  User:    [green]✓ Installed[/green]")
    else:
        temp_console.print("  User:    [dim]✗ Not installed[/dim]")
    temp_console.print(f"           [dim]{status.user.path}[/dim]")

    if status.project.installed:
        temp_console.print("  Project: [green]✓ Installed[/green]")
    else:
        temp_console.print("  Project: [dim]✗ Not installed[/dim]")
    temp_console.print(f"           [dim]{status.project.path}[/dim]")

    temp_console.print()


def _render_enabled_hooks(
    temp_console: RichConsole, hooks: dict, global_cfg: dict, project_cfg: dict | None
) -> None:
    """Render enabled hooks section."""
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
    _render_install_status(temp_console, status)

    # Load configs and render enabled hooks
    hooks = scanner.scan_hooks()
    global_cfg = config.load_config()
    project_cfg = config.load_project_config()
    _render_enabled_hooks(temp_console, hooks, global_cfg, project_cfg)

    # Paginate and display
    content = buffer.getvalue()
    lines = content.rstrip("\n").split("\n")
    max_lines_per_page = console.height - 3

    _paginate_output(lines, max_lines_per_page)


def _build_toggle_items(
    hooks: dict, scope: str, current_enabled: dict, global_enabled: dict, project_enabled: dict
) -> list:
    """Build menu items for hook toggle selection."""
    items = []
    events_with_hooks = [e for e in EVENTS if hooks.get(e)]

    for idx, event in enumerate(events_with_hooks):
        event_hooks = hooks.get(event, [])

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
                    value=(event, hook),  # Store hook object for key handlers
                )
            )

        # Add spacing between event blocks (except after the last one)
        if idx < len(events_with_hooks) - 1:
            items.append(Item.separator(""))

    return items


def _handle_edit_hook(menu, item) -> bool:
    """Open hook file in editor."""
    from rich_menu.components import CheckboxItem

    if not isinstance(item, CheckboxItem):
        return False

    event, hook = item.value
    editor = os.environ.get("EDITOR", "nano")

    def edit_action():
        subprocess.run([editor, str(hook.path)], check=False)

    _with_paused_live(menu, edit_action)
    return False  # Don't exit menu


def _handle_show_hook(menu, item) -> bool:
    """Show hook file in system file manager."""
    from rich_menu.components import CheckboxItem

    if not isinstance(item, CheckboxItem):
        return False

    event, hook = item.value

    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(hook.path)], check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", "/select,", str(hook.path)], check=False)
    else:
        subprocess.run(["xdg-open", str(hook.path.parent)], check=False)

    return False  # Don't exit menu


def _make_delete_handler(marked_for_deletion: set):
    """Create a delete handler with access to the deletion set."""

    def _handle_delete_hook(menu, item) -> bool:
        """Toggle mark for deletion on hook."""
        from rich_menu.components import CheckboxItem

        if not isinstance(item, CheckboxItem):
            return False

        event, hook = item.value
        key = (event, hook.name)

        if key in marked_for_deletion:
            # Unmark
            marked_for_deletion.discard(key)
            item.marked_for_deletion = False
        else:
            # Mark for deletion
            marked_for_deletion.add(key)
            item.marked_for_deletion = True

        return False  # Don't exit menu

    return _handle_delete_hook


def _apply_toggle_changes(
    selected: list, scope: str, add_to_git_exclude: bool, original_enabled: dict
) -> None:
    """Apply hook toggle changes and display result."""
    enabled_by_event: dict[str, list[str]] = {event: [] for event in EVENTS}
    for event, hook in selected:
        enabled_by_event[event].append(hook.name)

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
        current_enabled = project_enabled if project_enabled else global_enabled

    original_enabled = {event: list(hooks_list) for event, hooks_list in current_enabled.items()}

    items = _build_toggle_items(hooks, scope, current_enabled, global_enabled, project_enabled)

    if not items:
        console.print("[yellow]No hooks found. Add scripts to:[/yellow]")
        console.print(f"  {config.get_hooks_dir()}/{{event}}/")
        return False

    items.append(Item.separator("─────────"))
    items.append(Item.action("Save", value="save"))
    items.append(Item.action("Cancel", value="cancel"))

    marked_for_deletion: set[tuple[str, str]] = set()

    key_handlers = {
        "e": _handle_edit_hook,
        "s": _handle_show_hook,
        "d": _make_delete_handler(marked_for_deletion),
    }
    footer = "↑↓/jk navigate • Space toggle • e edit • s show • d delete • Enter save • Esc cancel"

    menu = InteractiveList(
        title=f"Toggle hooks ({scope})",
        items=items,
        console=console,
        key_handlers=key_handlers,
        footer=footer,
    )
    result = menu.show()

    if result.get("action") == "cancel" or not result or "action" not in result:
        return False

    # Calculate changes
    selected = menu.get_checked_values()
    enabled_by_event: dict[str, list[str]] = {event: [] for event in EVENTS}
    for event, hook in selected:
        enabled_by_event[event].append(hook.name)

    to_enable = []
    to_disable = []
    for event in EVENTS:
        original = set(original_enabled.get(event, []))
        new = set(enabled_by_event.get(event, []))
        for name in sorted(new - original):
            to_enable.append(f"{event}/{name}")
        for name in sorted(original - new):
            to_disable.append(f"{event}/{name}")

    to_delete = [f"{event}/{name}" for event, name in sorted(marked_for_deletion)]

    # Check if there are any changes
    if not to_enable and not to_disable and not to_delete:
        console.clear()
        console.print()
        console.print(Panel("[dim]No changes[/dim]", title="Toggle hooks", border_style="dim"))
        console.print("[dim]Press Enter to continue...[/dim]")
        while True:
            if is_enter(readchar.readkey()):
                break
        return False

    # Show confirmation
    console.clear()
    console.print()
    lines = []
    if to_enable:
        lines.append("[green]Enable:[/green]")
        for name in to_enable:
            lines.append(f"  [green]✓[/green] {name}")
    if to_disable:
        lines.append("[yellow]Disable:[/yellow]")
        for name in to_disable:
            lines.append(f"  [yellow]✗[/yellow] {name}")
    if to_delete:
        lines.append("[red]Delete:[/red]")
        for name in to_delete:
            lines.append(f"  [red]✗[/red] {name}")

    console.print(
        Panel("\n".join(lines), title="[bold]Confirm changes[/bold]", border_style="cyan")
    )
    console.print()

    confirm = questionary.confirm(
        "Apply these changes?",
        default=True,
        style=custom_style,
    ).ask()

    if not confirm:
        return False

    # Apply deletions
    for event, hook_name in marked_for_deletion:
        for hook in hooks.get(event, []):
            if hook.name == hook_name:
                manager = HookManager(scope=Scope.USER)
                manager.disable_hook(event, hook_name)
                hook.path.unlink()
                break

    # Apply toggle changes
    _apply_toggle_changes(selected, scope, add_to_git_exclude, original_enabled)

    return False


def interactive_add_hook() -> bool:
    """Interactive hook/command/agent creation wizard."""
    console.clear()

    # First ask what type of thing to add
    menu = InteractiveList(
        title="Add new:",
        items=[
            Item.action("Hook (script for events)", value="hook"),
            Item.action("Command (slash command)", value="command"),
            Item.action("Agent (AI persona)", value="agent"),
        ],
        console=console,
    )
    result = menu.show()
    item_type = result.get("action")

    if item_type is None:
        return False

    if item_type == "command":
        return _add_command()
    elif item_type == "agent":
        return _add_agent()

    # Continue with hook creation
    console.clear()
    console.print()
    console.print("[bold]Add Hook[/bold]")
    console.print("─" * 50)

    event_items = []
    for e in EVENTS:
        display_name, description = get_event_display(e)
        label = f"{display_name:<20} {description}" if description else display_name
        event_items.append(Item.action(label, value=e))

    menu = InteractiveList(
        title="Select event:",
        items=event_items,
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
