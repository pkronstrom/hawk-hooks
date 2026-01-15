"""Simple terminal menu wrapper.

Uses simple-term-menu for clean, non-flickering selection menus.
Matches dodo's menu patterns for consistency.
"""

from __future__ import annotations

from simple_term_menu import TerminalMenu

from .core import console


class SimpleMenu:
    """Rich + simple-term-menu implementation.

    Use for simple selection menus. For complex menus with toggles,
    checkboxes, and text input, use InteractiveList instead.
    """

    def select(self, options: list[str], title: str = "") -> int | None:
        """Show single-selection menu, return index or None if cancelled.

        Args:
            options: List of option strings to display.
            title: Optional title displayed above the menu.

        Returns:
            Selected index (0-based), or None if user cancelled (q/Ctrl+C).
        """
        if not options:
            return None
        menu = TerminalMenu(
            options,
            title=title or None,
            menu_cursor="❯ ",
            menu_cursor_style=("fg_cyan", "bold"),
            menu_highlight_style=("fg_cyan", "bold"),
            quit_keys=("q",),
        )
        result = menu.show()
        return result

    def multi_select(
        self, options: list[str], selected: list[bool] | None = None, title: str = ""
    ) -> list[int]:
        """Show multi-selection menu with checkboxes.

        Args:
            options: List of option strings to display.
            selected: Optional list of booleans indicating pre-selected items.
            title: Optional title displayed above the menu.

        Returns:
            List of selected indices (0-based), or empty list if cancelled.
        """
        if not options:
            return []
        preselected = []
        if selected:
            preselected = [i for i, s in enumerate(selected) if s]
        menu = TerminalMenu(
            options,
            title=title or None,
            multi_select=True,
            preselected_entries=preselected,
            multi_select_select_on_accept=False,
            menu_cursor="❯ ",
            menu_cursor_style=("fg_cyan", "bold"),
            menu_highlight_style=("fg_cyan", "bold"),
            quit_keys=("q",),
        )
        result = menu.show()
        return list(result) if result else []

    def confirm(self, message: str, default: bool = True) -> bool:
        """Show yes/no confirmation prompt.

        Args:
            message: Question to display.
            default: Default selection (True=Yes, False=No).

        Returns:
            True if user selected Yes, False otherwise.
        """
        options = ["Yes", "No"]
        cursor_index = 0 if default else 1
        menu = TerminalMenu(
            options,
            title=message,
            cursor_index=cursor_index,
            menu_cursor="❯ ",
            menu_cursor_style=("fg_cyan", "bold"),
            menu_highlight_style=("fg_cyan", "bold"),
            quit_keys=("q",),
        )
        result = menu.show()
        return result == 0

    def input(self, prompt: str, default: str = "") -> str | None:
        """Show text input prompt.

        Args:
            prompt: Prompt text to display.
            default: Default value.

        Returns:
            User input string, or None if cancelled.
        """
        try:
            return console.input(f"[bold]{prompt}[/bold] ")
        except (KeyboardInterrupt, EOFError):
            return None


# Module-level instance for convenience
simple_menu = SimpleMenu()
