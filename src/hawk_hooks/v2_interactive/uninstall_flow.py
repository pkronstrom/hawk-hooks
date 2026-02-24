"""Shared uninstall/unlink wizard for interactive entry points."""

from __future__ import annotations

from rich.console import Console
from simple_term_menu import TerminalMenu

from .. import v2_config
from ..v2_sync import format_sync_results, purge_all, uninstall_all
from .pause import wait_for_continue
from .theme import get_theme, terminal_menu_style_kwargs
from .uninstall_hint import detect_uninstall_command


def run_uninstall_wizard(console: Console) -> bool:
    """Run a compact 3-step uninstall wizard.

    Returns:
        True when cleanup was executed, False when cancelled.
    """
    theme = get_theme()

    step1 = TerminalMenu(
        ["Unlink only", "Full uninstall", "Cancel"],
        title=(
            "\nStep 1/3: What do you want to remove?\n"
            "Unlink only keeps Hawk config/registry/packages.\n"
            "Full uninstall clears Hawk-managed state."
        ),
        cursor_index=0,
        menu_cursor="\u203a ",
        **terminal_menu_style_kwargs(),
        quit_keys=("q", "\x1b"),
    )
    choice1 = step1.show()
    if choice1 is None or choice1 == 2:
        return False

    full_uninstall = choice1 == 1
    remove_project_configs = False
    registered_count = len(v2_config.get_registered_directories())

    if full_uninstall:
        step2 = TerminalMenu(
            ["Keep local .hawk files", "Delete local .hawk files", "Cancel"],
            title=(
                "\nStep 2/3: Local project files\n"
                f"Registered projects: {registered_count}\n"
                "Choose whether full uninstall should remove local .hawk files."
            ),
            cursor_index=0,
            menu_cursor="\u203a ",
            **terminal_menu_style_kwargs(),
            quit_keys=("q", "\x1b"),
        )
        choice2 = step2.show()
        if choice2 is None or choice2 == 2:
            return False
        remove_project_configs = choice2 == 1

    effects: list[str] = []
    if full_uninstall:
        effects.append("- Unlink hawk-managed items from tool configs")
        effects.append("- Clear Hawk global config selections, registry, and packages")
        if remove_project_configs:
            effects.append(f"- Delete local .hawk files for {registered_count} registered project(s)")
        else:
            effects.append("- Keep local .hawk files in registered projects")
    else:
        effects.append("- Unlink/prune hawk-managed items from tool configs")
        effects.append("- Keep Hawk global config, registry, packages, and project .hawk files")

    step3 = TerminalMenu(
        ["Back", "Confirm"],
        title="\nStep 3/3: Confirm\n\n" + "\n".join(effects),
        cursor_index=1,
        menu_cursor="\u203a ",
        **terminal_menu_style_kwargs(),
        quit_keys=("q", "\x1b"),
    )
    choice3 = step3.show()
    if choice3 != 1:
        return False

    if full_uninstall:
        console.print(f"\n[bold {theme.error_rich}]Unlinking and uninstalling...[/bold {theme.error_rich}]")
        results = uninstall_all(remove_project_configs=remove_project_configs)
        formatted = format_sync_results(results, verbose=False)
        console.print(formatted or "  No changes.")
        console.print(
            f"\n[{theme.success_rich}]\u2714 Cleared hawk-managed config, packages, and registry state.[/{theme.success_rich}]\n"
        )
        uninstall_cmd = detect_uninstall_command()
        accent = theme.accent_rich
        console.print("[dim]To remove the hawk program itself, run:[/dim]")
        console.print(f"  [{accent}]{uninstall_cmd}[/{accent}]\n")
    else:
        console.print(f"\n[bold {theme.error_rich}]Unlinking hawk-managed items...[/bold {theme.error_rich}]")
        results = purge_all()
        formatted = format_sync_results(results, verbose=False)
        console.print(formatted or "  No changes.")
        console.print(
            f"\n[{theme.success_rich}]\u2714 Removed hawk-managed links from tool configs.[/{theme.success_rich}]\n"
        )

    wait_for_continue()
    return True
