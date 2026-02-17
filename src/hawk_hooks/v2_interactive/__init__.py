"""v2 Interactive TUI for hawk.

Provides the main interactive menu when `hawk` is run without subcommands.
Operates entirely on the v2 backend (registry, resolver, multi-tool adapters).
"""

from __future__ import annotations


def v2_interactive_menu() -> None:
    """Main entry point for the v2 interactive TUI."""
    from .. import v2_config
    from .dashboard import run_dashboard
    from .wizard import run_wizard

    # First-run: guided wizard
    if not v2_config.get_global_config_path().exists():
        run_wizard()

    run_dashboard()
