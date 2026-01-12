"""Commands and agents management.

Handles the Commands and Agents submenus, toggle functions, and add functions.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

import questionary
import readchar

from rich_menu import InteractiveList, Item
from rich_menu.keys import is_enter

from .. import config, templates
from .core import _with_paused_live, console, custom_style


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
    import shutil

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


def _make_prompt_handlers(prompts_list: list, item_type: str, delete_callback):
    """Create key handlers for prompts/agents menus.

    Args:
        prompts_list: List of PromptInfo objects (will be looked up by name from item.value)
        item_type: "command" or "agent" for display purposes
        delete_callback: Function to call to delete a prompt (takes name, returns True if deleted)
    """
    prompts_by_name = {p.name: p for p in prompts_list}

    def _handle_edit(menu, item) -> bool:
        """Open prompt file in editor."""
        from rich_menu.components import ActionItem

        if not isinstance(item, ActionItem) or item.value in (
            "back",
            "toggle_all_on",
            "toggle_all_off",
        ):
            return False

        prompt = prompts_by_name.get(item.value)
        if not prompt:
            return False

        editor = os.environ.get("EDITOR", "nano")

        def edit_action():
            subprocess.run([editor, str(prompt.path)], check=False)

        _with_paused_live(menu, edit_action)
        return False

    def _handle_show(menu, item) -> bool:
        """Show prompt file in system file manager."""
        from rich_menu.components import ActionItem

        if not isinstance(item, ActionItem) or item.value in (
            "back",
            "toggle_all_on",
            "toggle_all_off",
        ):
            return False

        prompt = prompts_by_name.get(item.value)
        if not prompt:
            return False

        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(prompt.path)], check=False)
        elif sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(prompt.path)], check=False)
        else:
            subprocess.run(["xdg-open", str(prompt.path.parent)], check=False)

        return False

    def _handle_delete(menu, item) -> bool:
        """Delete prompt with confirmation."""
        from rich_menu.components import ActionItem

        if not isinstance(item, ActionItem) or item.value in (
            "back",
            "toggle_all_on",
            "toggle_all_off",
        ):
            return False

        name = item.value
        prompt = prompts_by_name.get(name)
        if not prompt:
            return False

        def delete_action():
            menu.console.print()
            confirm = questionary.confirm(
                f"Delete {item_type} '{name}'?",
                default=False,
                style=custom_style,
            ).ask()

            if confirm:
                delete_callback(name, prompt)
                return True
            return False

        result = _with_paused_live(menu, delete_action)
        return result if result else False

    def _handle_add(menu, item) -> bool:
        """Add a new prompt/agent."""

        def add_action():
            menu.console.clear()
            if item_type == "command":
                _add_command()
            else:
                _add_agent()

        _with_paused_live(menu, add_action)
        return True  # Exit menu to refresh list

    return {
        "e": _handle_edit,
        "s": _handle_show,
        "d": _handle_delete,
        "a": _handle_add,
    }


def _handle_items_menu(
    item_type_name: str,
    scanner_fn: Callable,
    is_enabled_fn: Callable[[str], bool],
    set_enabled_fn: Callable[[str, bool, bool], None],
    is_hook_enabled_fn: Callable[[str], bool],
    dir_fn: Callable[[], Path],
    toggle_fn: Callable[[str], None],
) -> None:
    """Generic handler for commands/agents menu.

    Args:
        item_type_name: "command" or "agent" for display.
        scanner_fn: Function to scan for items.
        is_enabled_fn: Function to check if item is enabled.
        set_enabled_fn: Function to set item enabled state.
        is_hook_enabled_fn: Function to check if item's hook is enabled.
        dir_fn: Function to get directory path.
        toggle_fn: Function to toggle an item.
    """
    from .. import sync

    def delete_item(name: str, item) -> None:
        """Delete an item."""
        if is_enabled_fn(name):
            set_enabled_fn(name, False, False)
            sync.unsync_prompt(item)
        item.path.unlink()
        console.print(f"[red]Deleted {name}[/red]")

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

    while True:
        console.clear()
        # Build choices
        menu_items = []
        enabled_count = 0
        for item in items_list:
            enabled = is_enabled_fn(item.name)
            if enabled:
                enabled_count += 1
            status = "[green]ON[/green]" if enabled else "[dim]OFF[/dim]"
            hook_status = ""
            if item.has_hooks:
                hook_enabled = is_hook_enabled_fn(item.name)
                hook_status = " [cyan](hook)[/cyan]" if hook_enabled else " [dim](hook off)[/dim]"
            menu_items.append(Item.action(f"{status} {item.name}{hook_status}", value=item.name))

        menu_items.append(Item.separator("─────────"))
        # Toggle all option - show appropriate action based on current state
        all_enabled = enabled_count == len(items_list)
        if all_enabled:
            menu_items.append(
                Item.action("[yellow]Toggle All OFF[/yellow]", value="toggle_all_off")
            )
        else:
            menu_items.append(Item.action("[green]Toggle All ON[/green]", value="toggle_all_on"))
        menu_items.append(Item.action("Back", value="back"))

        key_handlers = _make_prompt_handlers(items_list, item_type_name, delete_item)
        footer = "↑↓ navigate • Enter toggle • e edit • s show • d delete • a add • Esc back"

        menu = InteractiveList(
            title=f"{item_type_name.capitalize()}s ({enabled_count}/{len(items_list)} enabled)",
            items=menu_items,
            console=console,
            key_handlers=key_handlers,
            footer=footer,
        )
        result = menu.show()
        selected = result.get("action")

        if selected == "back" or selected is None:
            return

        if selected == "toggle_all_on":
            for item in items_list:
                if not is_enabled_fn(item.name):
                    set_enabled_fn(item.name, True, is_hook_enabled_fn(item.name))
                    sync.sync_prompt(item)
            console.print(f"[green]Enabled all {len(items_list)} {item_type_name}s[/green]")
        elif selected == "toggle_all_off":
            for item in items_list:
                if is_enabled_fn(item.name):
                    set_enabled_fn(item.name, False, is_hook_enabled_fn(item.name))
                    sync.unsync_prompt(item)
            console.print(f"[yellow]Disabled all {len(items_list)} {item_type_name}s[/yellow]")
        else:
            # Toggle the selected item
            toggle_fn(selected)
        # Refresh the list
        items_list = scanner_fn()


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
