"""Interactive menu system using Rich.Live.

This module provides the core InteractiveList class and Item factory
for building flicker-free CLI menus with keyboard navigation.

Example:
    from rich_menu import InteractiveList, Item

    menu = InteractiveList(
        title="Settings",
        items=[
            Item.toggle("debug", "Debug mode", value=True),
            Item.text("api_key", "API Key", value=""),
            Item.action("Save", value="save"),
        ]
    )
    result = menu.show()
"""

from typing import Any

import readchar
from rich.console import Console
from rich.live import Live
from rich.panel import Panel

from .components import (
    ActionItem,
    CheckboxItem,
    MenuItem,
    SeparatorItem,
    TextItem,
    ToggleItem,
)
from .keys import is_backspace, is_down, is_enter, is_escape, is_exit, is_select, is_up
from .themes import DEFAULT_THEME, Theme


class Item:
    """Factory for creating menu items.

    Provides convenient static methods for creating different item types:
    - toggle(): Boolean checkbox/switch
    - checkbox(): Multi-select checkbox
    - text(): Text input field
    - action(): Clickable button
    - separator(): Visual divider
    """

    @staticmethod
    def toggle(key: str, label: str, value: bool = False) -> ToggleItem:
        """Create a boolean toggle item.

        Args:
            key: Identifier for tracking changes.
            label: Display text.
            value: Initial boolean state.

        Returns:
            ToggleItem that can be added to a menu.
        """
        return ToggleItem(key=key, label=label, value=value)

    @staticmethod
    def checkbox(key: str, label: str, checked: bool = False, value: Any = None) -> CheckboxItem:
        """Create a checkbox item for multi-select.

        Args:
            key: Unique identifier.
            label: Display text.
            checked: Initial checked state.
            value: Optional value (defaults to key).

        Returns:
            CheckboxItem instance.
        """
        return CheckboxItem(key=key, label=label, checked=checked, value=value)

    @staticmethod
    def text(key: str, label: str, value: str = "") -> TextItem:
        """Create a text input item.

        Args:
            key: Identifier for tracking changes.
            label: Display text.
            value: Initial text value.

        Returns:
            TextItem that can be added to a menu.
        """
        return TextItem(key=key, label=label, value=value)

    @staticmethod
    def action(label: str, value: Any = None) -> ActionItem:
        """Create an action/button item.

        Args:
            label: Display text for the button.
            value: Identifier returned in {"action": value} when triggered.

        Returns:
            ActionItem that exits the menu when activated.
        """
        return ActionItem(key=None, label=label, value=value)

    @staticmethod
    def separator(label: str) -> SeparatorItem:
        """Create a visual separator.

        Args:
            label: Text to display (typically blank or a category name).

        Returns:
            Non-interactive SeparatorItem for visual grouping.
        """
        return SeparatorItem(label=label)


class InteractiveList:
    """Interactive menu with keyboard navigation and live updates.

    Provides a flicker-free menu system using Rich.Live. Changes are tracked
    and returned as a dictionary when the user exits or triggers an action.

    Automatically remembers cursor position across menu instances with the same title.

    Keyboard controls:
        - Up/Down or j/k: Navigate
        - Enter/Space: Activate item (toggle, edit, or action)
        - Esc/q: Exit without saving changes
        - In text edit mode: Enter saves, Esc cancels

    Args:
        title: Menu title displayed in the panel header.
        items: List of MenuItem objects to display.
        console: Optional Rich Console for output (auto-created if not provided).
        theme: Optional Theme for customizing appearance.

    Raises:
        ValueError: If items list is empty or contains only separators.

    Example:
        menu = InteractiveList(
            title="Settings",
            items=[
                Item.toggle("debug", "Debug Mode", value=False),
                Item.text("name", "User Name", value="Alice"),
                Item.separator(""),
                Item.action("Save", value="save"),
            ]
        )
        result = menu.show()  # {"debug": True, "name": "Bob", "action": "save"}
    """

    _cursor_memory: dict[str, int] = {}

    def __init__(
        self,
        title: str,
        items: list[MenuItem],
        console: Console | None = None,
        theme: Theme | None = None,
        key_handlers: dict[str, callable] | None = None,
        footer: str | None = None,
    ):
        """Initialize the interactive menu.

        Args:
            title: Menu title displayed in the panel header.
            items: List of MenuItem objects to display.
            console: Rich Console instance (creates new one if None).
            theme: Visual theme for styling.
            key_handlers: Optional dict mapping key chars to callbacks.
                          Callback signature: (menu, item) -> bool
                          Return True to request exit after handling.
            footer: Optional custom footer text (overrides default hints).
        """
        if not items:
            raise ValueError("Menu must have at least one item")

        if all(isinstance(item, SeparatorItem) for item in items):
            raise ValueError("Menu must have at least one interactive item")

        self.title = title
        self.items = items
        self.console = console or Console()
        self.theme = theme or DEFAULT_THEME
        self.cursor_pos = 0
        self.editing_index: int | None = None
        self.changes: dict[str, Any] = {}
        self.should_exit = False
        self._live: Live | None = None
        self.window_offset = 0
        self.key_handlers = key_handlers or {}
        self._custom_footer = footer

        # Restore cursor position for this menu title
        if title in InteractiveList._cursor_memory:
            saved_pos = InteractiveList._cursor_memory[title]
            if 0 <= saved_pos < len(self.items):
                self.cursor_pos = saved_pos
                if isinstance(self.items[self.cursor_pos], SeparatorItem):
                    self._move_cursor(+1)
            else:
                self._find_first_interactive()
        else:
            self._find_first_interactive()

    def _find_first_interactive(self):
        """Find and set cursor to first non-separator item."""
        for i, item in enumerate(self.items):
            if not isinstance(item, SeparatorItem):
                self.cursor_pos = i
                break

    def _move_cursor(self, delta: int):
        """Move cursor up/down, skipping separators."""
        if not self.items:
            return

        new_pos = self.cursor_pos + delta
        attempts = 0
        max_attempts = len(self.items)

        # Wrap around
        if new_pos < 0:
            new_pos = len(self.items) - 1
        elif new_pos >= len(self.items):
            new_pos = 0

        # Skip separators
        while isinstance(self.items[new_pos], SeparatorItem):
            new_pos += delta
            if new_pos < 0:
                new_pos = len(self.items) - 1
            elif new_pos >= len(self.items):
                new_pos = 0

            attempts += 1
            if attempts >= max_attempts:
                return

        self.cursor_pos = new_pos

    def _update_window(self, max_visible: int):
        """Update window offset to keep cursor visible."""
        if len(self.items) <= max_visible:
            self.window_offset = 0
            return

        if self.cursor_pos < self.window_offset:
            self.window_offset = self.cursor_pos
        elif self.cursor_pos >= self.window_offset + max_visible:
            self.window_offset = self.cursor_pos - max_visible + 1

    def _edit_text_item(self, item: TextItem, live: Live):
        """Enter inline text editing mode."""
        self.editing_index = self.cursor_pos
        edit_buffer = item.value
        original_value = item.value

        try:
            while True:
                live.update(self.render())

                try:
                    key = readchar.readkey()
                except KeyboardInterrupt:
                    item.value = original_value
                    break

                if is_escape(key):
                    item.value = original_value
                    break
                elif is_enter(key):
                    if item.key is not None:
                        self.changes[item.key] = edit_buffer
                    break
                elif is_backspace(key):
                    if edit_buffer:
                        edit_buffer = edit_buffer[:-1]
                elif len(key) == 1 and key.isprintable():
                    if len(edit_buffer) < item.max_length:
                        edit_buffer += key

                item.value = edit_buffer
        finally:
            self.editing_index = None

    def _activate_current_item(self, live: Live | None = None):
        """Handle Enter/Space activation on the current menu item."""
        item = self.items[self.cursor_pos]

        if isinstance(item, SeparatorItem):
            return

        if isinstance(item, ToggleItem):
            item.value = not item.value
            if item.key is not None:
                self.changes[item.key] = item.value

        elif isinstance(item, CheckboxItem):
            item.checked = not item.checked

        elif isinstance(item, TextItem):
            if live:
                self._edit_text_item(item, live)

        elif isinstance(item, ActionItem):
            self.changes["action"] = item.value
            self.should_exit = True

    def _handle_key(self, key: str):
        """Handle keyboard input and update menu state."""
        # Check custom key handlers first
        if key in self.key_handlers:
            item = self.items[self.cursor_pos]
            should_exit = self.key_handlers[key](self, item)
            if should_exit:
                self.should_exit = True
            return

        if is_exit(key):
            self.should_exit = True
        elif is_down(key):
            self._move_cursor(+1)
        elif is_up(key):
            self._move_cursor(-1)
        elif is_select(key):
            self._activate_current_item(self._live)

    def get_checked_values(self) -> list[Any]:
        """Get values of all checked CheckboxItems."""
        return [
            item.value for item in self.items if isinstance(item, CheckboxItem) and item.checked
        ]

    def render(self) -> Panel:
        """Render the menu as a Rich Panel."""
        terminal_height = self.console.height
        calculated = terminal_height - self.theme.panel_padding
        # Cap at reasonable bounds: min 5, max from theme (default 20)
        max_visible = max(
            self.theme.min_visible_items, min(self.theme.max_visible_items, calculated)
        )

        self._update_window(max_visible)

        window_end = min(self.window_offset + max_visible, len(self.items))
        visible_items = self.items[self.window_offset : window_end]

        lines = []
        if self.window_offset > 0:
            lines.append(
                f"[{self.theme.dim_color}]  {self.theme.scroll_up_icon} "
                f"{self.window_offset} more above[/{self.theme.dim_color}]"
            )

        for i, item in enumerate(visible_items):
            actual_index = self.window_offset + i
            is_selected = actual_index == self.cursor_pos
            is_editing = actual_index == self.editing_index

            prefix = (
                f"[{self.theme.selected_color}]{self.theme.cursor_icon}[/{self.theme.selected_color}]"
                if is_selected
                else " "
            )
            line = f"{prefix} {item.render(is_selected, is_editing, self.theme)}"
            lines.append(line)

        items_below = len(self.items) - window_end
        if items_below > 0:
            lines.append(
                f"[{self.theme.dim_color}]  {self.theme.scroll_down_icon} "
                f"{items_below} more below[/{self.theme.dim_color}]"
            )

        content = "\n".join(lines)

        if self._custom_footer:
            footer = f"[{self.theme.dim_color}]{self._custom_footer}[/{self.theme.dim_color}]"
        elif any(isinstance(item, CheckboxItem) for item in self.items):
            footer = (
                f"[{self.theme.dim_color}]{self.theme.scroll_up_icon}{self.theme.scroll_down_icon}/jk navigate "
                f"• Space toggle • [{self.theme.warning_color}]{self.theme.change_icon}[/{self.theme.warning_color}] unsaved "
                f"• Enter save • q back[/{self.theme.dim_color}]"
            )
        else:
            footer = (
                f"[{self.theme.dim_color}]{self.theme.scroll_up_icon}{self.theme.scroll_down_icon}/jk navigate "
                f"• Enter/Space select • q back[/{self.theme.dim_color}]"
            )

        return Panel(
            f"{content}\n\n{footer}",
            title=f"[bold]{self.title}[/bold]",
            border_style=self.theme.border_color,
            width=self.theme.panel_width,
        )

    def show(self) -> dict[str, Any]:
        """Display the interactive menu and block until user exits.

        Returns:
            Dictionary of changes:
            - For toggles/text: {key: value} pairs for modified items
            - For actions: {"action": value} when an action is triggered
            - Empty dict if user exits without changes (Esc/q)
        """
        with Live(self.render(), console=self.console, refresh_per_second=20) as live:
            self._live = live

            while not self.should_exit:
                try:
                    key = readchar.readkey()
                    self._handle_key(key)
                    live.update(self.render())
                except KeyboardInterrupt:
                    self.should_exit = True

        InteractiveList._cursor_memory[self.title] = self.cursor_pos

        return self.changes

    @classmethod
    def clear_cursor_memory(cls):
        """Clear all saved cursor positions."""
        cls._cursor_memory.clear()
