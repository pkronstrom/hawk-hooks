"""v2 Interactive TUI for hawk.

Provides the main interactive menu when `hawk` is run without subcommands.
Operates entirely on the v2 backend (registry, resolver, multi-tool adapters).
"""

from __future__ import annotations


def v2_interactive_menu(scope_dir: str | None = None) -> None:
    """Main entry point for the v2 interactive TUI.

    Args:
        scope_dir: Optional directory to scope the TUI to.
    """
    from pathlib import Path

    from .. import v2_config
    from .dashboard import run_dashboard
    from .wizard import run_wizard

    # First-run: guided wizard
    if not v2_config.get_global_config_path().exists():
        run_wizard()

    # Auto-register cwd if it has .hawk/config.yaml
    cwd = Path(scope_dir).resolve() if scope_dir else Path.cwd().resolve()
    v2_config.auto_register_if_needed(cwd)
    v2_config.prune_stale_directories()

    run_dashboard(scope_dir=scope_dir)
