"""Interactive UI package for captain-hook CLI.

This package provides the interactive menu system and all UI components.
"""

from __future__ import annotations

import questionary

from rich_menu import InteractiveList, Item

from .. import config
from .config_editor import interactive_config
from .core import console, custom_style, print_header, set_console
from .deps import install_deps
from .hooks import interactive_add_hook, interactive_toggle, show_status
from .prompts import _auto_sync_prompts, _handle_agents_menu, _handle_commands_menu
from .setup import interactive_install, interactive_uninstall, run_wizard

__all__ = [
    # Core
    "console",
    "custom_style",
    "print_header",
    "set_console",
    # Status
    "show_status",
    # Hooks
    "interactive_toggle",
    "interactive_add_hook",
    # Prompts
    "_handle_commands_menu",
    "_handle_agents_menu",
    "_auto_sync_prompts",
    # Config
    "interactive_config",
    # Setup
    "interactive_install",
    "interactive_uninstall",
    "run_wizard",
    # Deps
    "install_deps",
    # Main menu
    "interactive_menu",
]


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

    # Auto-sync prompts/agents on startup
    _auto_sync_prompts()

    while True:
        console.clear()
        print_header()
        menu = InteractiveList(
            title="What would you like to do?",
            items=[
                Item.action("Status       Show hooks + enabled state", value="status"),
                Item.action("Hooks        Enable/disable/edit/delete hooks", value="toggle"),
                Item.action("Commands     Manage slash commands", value="commands"),
                Item.action("Agents       Manage AI agents", value="agents"),
                Item.action("Add...       Create new hook/command/agent", value="add"),
                Item.separator("─────────"),
                Item.action("Config       Debug mode, notifications", value="config"),
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
            interactive_toggle()
        elif choice == "commands":
            _handle_commands_menu()
        elif choice == "agents":
            _handle_agents_menu()
        elif choice == "add":
            interactive_add_hook()
        elif choice == "config":
            interactive_config()
        elif choice == "install":
            interactive_install()
        elif choice == "uninstall":
            interactive_uninstall()
        elif choice == "deps":
            install_deps()
