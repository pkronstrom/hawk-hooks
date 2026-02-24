"""Interactive TUI for hawk.

Provides the main interactive menu when `hawk` is run without subcommands.
"""

from __future__ import annotations


def interactive_menu(scope_dir: str | None = None) -> None:
    """Main entry point for the interactive TUI.

    Args:
        scope_dir: Optional directory to scope the TUI to.
    """
    from pathlib import Path

    from .. import config
    from .dashboard import run_dashboard
    from .theme import set_project_theme
    from .wizard import run_wizard

    cwd = Path(scope_dir).resolve() if scope_dir else Path.cwd().resolve()
    set_project_theme(cwd)

    # First-run: guided wizard
    if not config.get_global_config_path().exists():
        if not run_wizard():
            return

    # Auto-register cwd if it has .hawk/config.yaml
    config.auto_register_if_needed(cwd)
    config.prune_stale_directories()

    run_dashboard(scope_dir=scope_dir)
