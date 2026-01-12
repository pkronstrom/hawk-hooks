"""Interactive UI components for captain-hook CLI.

This module is a backwards-compatibility shim. All functionality has been
moved to the captain_hook.interactive package.
"""

from __future__ import annotations

# Re-export everything from the interactive package
from .interactive import (
    _auto_sync_prompts,
    _handle_agents_menu,
    _handle_commands_menu,
    console,
    custom_style,
    install_deps,
    interactive_add_hook,
    interactive_config,
    interactive_install,
    interactive_menu,
    interactive_toggle,
    interactive_uninstall,
    print_header,
    run_wizard,
    set_console,
    show_status,
)

__all__ = [
    "console",
    "custom_style",
    "print_header",
    "set_console",
    "show_status",
    "interactive_toggle",
    "interactive_add_hook",
    "_handle_commands_menu",
    "_handle_agents_menu",
    "_auto_sync_prompts",
    "interactive_config",
    "interactive_install",
    "interactive_uninstall",
    "run_wizard",
    "install_deps",
    "interactive_menu",
]
