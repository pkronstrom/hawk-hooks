"""Commands and agents management.

Handles the Commands and Agents submenus, toggle functions, and add functions.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

import questionary
import readchar

from rich_menu.keys import is_enter

from .. import config, templates
from .core import console, custom_style


def _add_item(item_type_name: str, template: str, dir_fn: Callable[[], Path]) -> bool:
    """Add a new item from template.

    Args:
        item_type_name: "Command" or "Agent" for display.
        template: Template string with {name} and {description} placeholders.
        dir_fn: Function to get the directory path.

    Returns:
        True if item was created, False otherwise.
    """
    console.clear()
    console.print()
    console.print(f"[bold]Add {item_type_name}[/bold]")
    console.print("─" * 50)

    name = questionary.text(f"{item_type_name} name:", style=custom_style).ask()
    if not name:
        return False

    description = (
        questionary.text("Description:", style=custom_style).ask()
        or f"{name} {item_type_name.lower()}"
    )

    content = template.format(name=name, description=description)
    path = dir_fn() / f"{name}.md"

    if path.exists():
        console.print(f"[red]{item_type_name} {name} already exists![/red]")
        console.print("[dim]Press Enter to continue...[/dim]")
        input()
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    console.print(f"[green]Created {path}[/green]")
    console.print("[dim]Edit the file to customize, then toggle to enable.[/dim]")

    _open_in_editor(path)
    return True


def _add_command() -> bool:
    """Add a new command from template."""
    return _add_item("Command", templates.COMMAND_PROMPT_TEMPLATE, config.get_prompts_dir)


def _add_agent() -> bool:
    """Add a new agent from template."""
    return _add_item("Agent", templates.AGENT_TEMPLATE, config.get_agents_dir)


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


def _toggle_item(
    name: str,
    is_enabled_fn: Callable[[str], bool],
    set_enabled_fn: Callable[[str, bool, bool], None],
    is_hook_enabled_fn: Callable[[str], bool],
) -> None:
    """Toggle an item's enabled state.

    Args:
        name: Item name.
        is_enabled_fn: Function to check if item is enabled.
        set_enabled_fn: Function to set item enabled state.
        is_hook_enabled_fn: Function to check if item's hook is enabled.
    """
    from .. import prompt_scanner, sync

    item = prompt_scanner.get_prompt_by_name(name)
    if not item:
        return

    current = is_enabled_fn(name)
    new_state = not current

    hook_enabled = is_hook_enabled_fn(name)
    set_enabled_fn(name, new_state, hook_enabled)

    if new_state:
        sync.sync_prompt(item)
        console.print(f"[green]Enabled {name}[/green]")
    else:
        sync.unsync_prompt(item)
        console.print(f"[yellow]Disabled {name}[/yellow]")


def _toggle_prompt(name: str) -> None:
    """Toggle a prompt's enabled state."""
    _toggle_item(
        name,
        config.is_prompt_enabled,
        config.set_prompt_enabled,
        config.is_prompt_hook_enabled,
    )


def _toggle_agent(name: str) -> None:
    """Toggle an agent's enabled state."""
    _toggle_item(
        name,
        config.is_agent_enabled,
        config.set_agent_enabled,
        config.is_agent_hook_enabled,
    )


def _handle_items_menu(
    item_type_name: str,
    scanner_fn: Callable,
    is_enabled_fn: Callable[[str], bool],
    set_enabled_fn: Callable[[str, bool, bool], None],
    is_hook_enabled_fn: Callable[[str], bool],
    dir_fn: Callable[[], Path],
    toggle_fn: Callable[[str], None],
) -> None:
    """Generic handler for commands/agents menu using Rich Live for flicker-free updates."""
    from rich.text import Text

    from .. import sync

    items_list = scanner_fn()
    if not items_list:
        console.print(f"[yellow]No {item_type_name}s found in directory.[/yellow]")
        console.print(f"[dim]Add .md files to: {dir_fn()}[/dim]")
        console.print()
        console.print("[dim]Press Enter to continue...[/dim]")
        while True:
            if is_enter(readchar.readkey()):
                break
        return

    prompts_by_name = {p.name: p for p in items_list}
    cursor = 0
    scroll_offset = 0

    def get_enabled_count() -> int:
        return sum(1 for item in items_list if is_enabled_fn(item.name))

    def get_max_visible() -> int:
        """Calculate max visible items based on terminal height, capped at reasonable max."""
        try:
            term_height = console.size.height
        except Exception:
            term_height = 24
        # Reserve: title (1) + blank (1) + scroll indicators (2) + separator (1) + toggle_all (1) + blank (1) + legend (1) + buffer (2)
        calculated = term_height - 10
        # Cap at reasonable max (20 items), min 5
        return max(5, min(20, calculated))

    def build_display() -> Text:
        """Build the display as Rich Text."""
        nonlocal scroll_offset
        enabled_count = get_enabled_count()
        max_visible = get_max_visible()

        # Adjust scroll offset to keep cursor visible
        if cursor < scroll_offset:
            scroll_offset = cursor
        elif cursor >= scroll_offset + max_visible:
            scroll_offset = cursor - max_visible + 1

        # Handle toggle_all item (at index len(items_list))
        toggle_all_idx = len(items_list)
        if cursor == toggle_all_idx:
            scroll_offset = max(0, len(items_list) - max_visible + 1)

        lines = []

        # Title
        title = f"{item_type_name.capitalize()}s ({enabled_count}/{len(items_list)} enabled)"
        lines.append(f"[bold]{title}[/bold]")
        lines.append("")

        # Scroll indicator - above (only show if scrolling)
        hidden_above = scroll_offset
        if hidden_above > 0:
            lines.append(f"  [dim]↑ {hidden_above} more above[/dim]")

        # Visible items
        visible_end = min(scroll_offset + max_visible, len(items_list))
        for i in range(scroll_offset, visible_end):
            item = items_list[i]
            marker = "[cyan]>[/cyan]" if i == cursor else " "
            enabled = is_enabled_fn(item.name)
            check = "[bold blue]✓[/bold blue]" if enabled else " "
            hook_status = ""
            if item.has_hooks:
                hook_enabled = is_hook_enabled_fn(item.name)
                hook_status = " [cyan](hook)[/cyan]" if hook_enabled else " [dim](hook off)[/dim]"

            name_display = item.name if enabled else f"[dim]{item.name}[/dim]"
            lines.append(f" {marker} {check} {name_display}{hook_status}")

        # Scroll indicator - below (only show if more items)
        hidden_below = len(items_list) - visible_end
        if hidden_below > 0:
            lines.append(f"  [dim]↓ {hidden_below} more below[/dim]")

        # Separator and toggle all action
        lines.append("  [dim]─────────[/dim]")

        all_enabled = get_enabled_count() == len(items_list)
        if all_enabled:
            marker = "[cyan]>[/cyan]" if cursor == toggle_all_idx else " "
            lines.append(f" {marker} [yellow]Toggle All OFF[/yellow]")
        else:
            marker = "[cyan]>[/cyan]" if cursor == toggle_all_idx else " "
            lines.append(f" {marker} [green]Toggle All ON[/green]")

        # Legend at bottom
        lines.append("")
        lines.append(
            "[dim]↑↓/jk navigate · enter toggle · e edit · s show · d delete · a add · q back[/dim]"
        )

        return Text.from_markup("\n".join(lines))

    def delete_item(name: str) -> bool:
        """Delete an item with confirmation."""
        item = prompts_by_name.get(name)
        if not item:
            return False

        confirm = questionary.confirm(
            f"Delete {item_type_name} '{name}'?",
            default=False,
            style=custom_style,
        ).ask()

        if confirm:
            if is_enabled_fn(name):
                set_enabled_fn(name, False, False)
                sync.unsync_prompt(item)
            item.path.unlink()
            return True
        return False

    def edit_item(name: str) -> None:
        """Open item in editor."""
        item = prompts_by_name.get(name)
        if not item:
            return
        editor = os.environ.get("EDITOR")
        if not editor:
            if shutil.which("nano"):
                editor = "nano"
            elif shutil.which("vi"):
                editor = "vi"
            else:
                return
        subprocess.run([editor, str(item.path)], check=False)

    def show_item(name: str) -> None:
        """Show item in file manager."""
        item = prompts_by_name.get(name)
        if not item:
            return
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(item.path)], check=False)
        elif sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(item.path)], check=False)
        else:
            subprocess.run(["xdg-open", str(item.path.parent)], check=False)

    total_items = len(items_list) + 1  # items + toggle_all
    action_triggered = None

    from rich.live import Live

    while True:  # Outer loop for re-entry after editor/add
        console.clear()
        display = build_display()

        with Live(display, console=console, refresh_per_second=10) as live:
            while True:
                try:
                    key = readchar.readkey()
                except KeyboardInterrupt:
                    return

                if key in (readchar.key.UP, "k"):
                    cursor = (cursor - 1) % total_items
                elif key in (readchar.key.DOWN, "j", "\t"):
                    cursor = (cursor + 1) % total_items
                elif key == "q":
                    return
                elif key in (" ", "\r", "\n"):
                    if cursor < len(items_list):
                        # Toggle item
                        item = items_list[cursor]
                        toggle_fn(item.name)
                    else:
                        # Toggle all
                        all_enabled = get_enabled_count() == len(items_list)
                        if all_enabled:
                            for item in items_list:
                                if is_enabled_fn(item.name):
                                    set_enabled_fn(item.name, False, is_hook_enabled_fn(item.name))
                                    sync.unsync_prompt(item)
                        else:
                            for item in items_list:
                                if not is_enabled_fn(item.name):
                                    set_enabled_fn(item.name, True, is_hook_enabled_fn(item.name))
                                    sync.sync_prompt(item)
                elif key == "e" and cursor < len(items_list):
                    action_triggered = ("edit", items_list[cursor].name)
                    break
                elif key == "s" and cursor < len(items_list):
                    show_item(items_list[cursor].name)
                elif key == "d" and cursor < len(items_list):
                    action_triggered = ("delete", items_list[cursor].name)
                    break
                elif key == "a":
                    action_triggered = ("add", None)
                    break

                # Update display
                live.update(build_display())

        # Handle actions that need to exit Live context
        if action_triggered:
            action, name = action_triggered
            action_triggered = None

            if action == "edit":
                edit_item(name)
            elif action == "delete":
                if delete_item(name):
                    # Refresh list
                    items_list = scanner_fn()
                    prompts_by_name.clear()
                    prompts_by_name.update({p.name: p for p in items_list})
                    total_items = len(items_list) + 1
                    if cursor >= len(items_list):
                        cursor = max(0, len(items_list) - 1)
                    if not items_list:
                        return
            elif action == "add":
                console.clear()
                if item_type_name == "command":
                    _add_command()
                else:
                    _add_agent()
                # Refresh list
                items_list = scanner_fn()
                prompts_by_name.clear()
                prompts_by_name.update({p.name: p for p in items_list})
                total_items = len(items_list) + 1


def _handle_commands_menu() -> None:
    """Handle the Commands submenu."""
    from .. import prompt_scanner

    _handle_items_menu(
        item_type_name="command",
        scanner_fn=prompt_scanner.scan_prompts,
        is_enabled_fn=config.is_prompt_enabled,
        set_enabled_fn=config.set_prompt_enabled,
        is_hook_enabled_fn=config.is_prompt_hook_enabled,
        dir_fn=config.get_prompts_dir,
        toggle_fn=_toggle_prompt,
    )


def _handle_agents_menu() -> None:
    """Handle the Agents submenu."""
    from .. import prompt_scanner

    _handle_items_menu(
        item_type_name="agent",
        scanner_fn=prompt_scanner.scan_agents,
        is_enabled_fn=config.is_agent_enabled,
        set_enabled_fn=config.set_agent_enabled,
        is_hook_enabled_fn=config.is_agent_hook_enabled,
        dir_fn=config.get_agents_dir,
        toggle_fn=_toggle_agent,
    )


def _auto_sync_prompts() -> None:
    """Auto-sync: detect new/removed prompts, update config."""
    from .. import prompt_scanner
    from ..types import PromptType

    # Scan all prompts
    all_prompts = prompt_scanner.scan_all_prompts()
    prompt_names = {p.name for p in all_prompts if p.prompt_type == PromptType.COMMAND}
    agent_names = {p.name for p in all_prompts if p.prompt_type == PromptType.AGENT}

    # Get current config
    prompts_cfg = config.get_prompts_config()
    agents_cfg = config.get_agents_config()

    # Find new prompts (in files but not in config)
    new_prompts = prompt_names - set(prompts_cfg.keys())
    new_agents = agent_names - set(agents_cfg.keys())

    # Find removed prompts (in config but not in files)
    removed_prompts = set(prompts_cfg.keys()) - prompt_names
    removed_agents = set(agents_cfg.keys()) - agent_names

    # Add new (disabled by default)
    for name in new_prompts:
        config.set_prompt_enabled(name, False, False)
        console.print(f"[dim]Found new command: {name}[/dim]")

    for name in new_agents:
        config.set_agent_enabled(name, False, False)
        console.print(f"[dim]Found new agent: {name}[/dim]")

    # Clean up removed
    for name in removed_prompts:
        cfg = config.load_config()
        if "prompts" in cfg and name in cfg["prompts"]:
            del cfg["prompts"][name]
            config.save_config(cfg)
        console.print(f"[dim]Removed command: {name}[/dim]")

    for name in removed_agents:
        cfg = config.load_config()
        if "agents" in cfg and name in cfg["agents"]:
            del cfg["agents"][name]
            config.save_config(cfg)
        console.print(f"[dim]Removed agent: {name}[/dim]")
