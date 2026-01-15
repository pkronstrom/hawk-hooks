"""Interactive UI package for captain-hook CLI.

This package provides the interactive menu system and all UI components.
"""

from __future__ import annotations

import questionary

from .. import config
from .config_editor import interactive_config
from .core import console, custom_style, print_header, set_console
from .deps import install_deps
from .hooks import interactive_add_hook, interactive_toggle, show_status
from .prompts import _auto_sync_prompts, _handle_agents_menu, _handle_commands_menu
from .setup import interactive_install, interactive_uninstall, run_wizard
from .ui import simple_menu

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

    # Menu options with their handler functions
    options = [
        ("Status       Show hooks + enabled state", "status"),
        ("Hooks        Enable/disable/edit/delete hooks", "toggle"),
        ("Commands     Manage slash commands", "commands"),
        ("Agents       Manage AI agents", "agents"),
        ("Add...       Create new hook/command/agent", "add"),
        ("─────────", None),
        ("Config       Debug mode, notifications", "config"),
        ("Install      Register hooks in Claude settings", "install"),
        ("Uninstall    Remove hooks from Claude settings", "uninstall"),
        ("Install-deps Install Python dependencies", "deps"),
        ("─────────", None),
        ("Exit", "exit"),
    ]

    handlers = {
        "status": show_status,
        "toggle": interactive_toggle,
        "commands": _handle_commands_menu,
        "agents": _handle_agents_menu,
        "add": interactive_add_hook,
        "config": interactive_config,
        "install": interactive_install,
        "uninstall": interactive_uninstall,
        "deps": install_deps,
    }

    while True:
        console.clear()
        print_header()

        # Build menu options (simple-term-menu handles separators differently)
        menu_options = [label for label, _ in options]

        choice_idx = simple_menu.select(menu_options)

        if choice_idx is None:
            console.clear()
            break

        _, action = options[choice_idx]

        if action is None:
            # Separator selected, ignore
            continue

        if action == "exit":
            console.clear()
            break

        handler = handlers.get(action)
        if handler:
            handler()
