"""Rich.Live-based interactive menu system.

A single-file, reusable menu library for building flicker-free CLI menus.

Example:
    from captain_hook.rich_menu import InteractiveList, Item

    menu = InteractiveList(
        title="Settings",
        items=[
            Item.toggle("debug", "Debug mode", value=True),
            Item.text("api_key", "API Key", value=""),
            Item.action("Save", value="save"),
        ]
    )

    result = menu.show()  # Returns: {"debug": False, "api_key": "newkey"}
"""

from dataclasses import dataclass
from typing import Any

import readchar
from rich.console import Console
from rich.live import Live
from rich.panel import Panel


@dataclass
class MenuItem:
    """Base class for menu items.

    Attributes:
        key: Optional identifier for storing changes (None for non-interactive items).
        label: Display text for this item.
        enabled: Whether this item can be interacted with.
    """

    key: str | None
    label: str
    enabled: bool = True

    def render(self, is_selected: bool, is_editing: bool) -> str:
        """Render this item as a Rich markup string.

        Args:
            is_selected: Whether the cursor is on this item.
            is_editing: Whether this item is in edit mode.

        Returns:
            Rich markup string to display in the menu.
        """
        raise NotImplementedError


@dataclass
class ToggleItem(MenuItem):
    """Boolean toggle item (checkbox/switch).

    Toggle between True/False by pressing Enter or Space.

    Attributes:
        value: Current boolean state.
    """

    value: bool = False

    def render(self, is_selected: bool, is_editing: bool) -> str:
        # is_selected not used - future enhancement for visual highlighting
        status = "[green]✓ on [/green]" if self.value else "[dim]  off[/dim]"
        return f"{self.label:<20} {status}  Toggle"


@dataclass
class CheckboxItem(MenuItem):
    """Menu item with checkbox for multi-select.

    Attributes:
        key: Unique identifier for this item (required).
        label: Display text for the item.
        checked: Whether the checkbox is checked.
        value: Optional value to return (defaults to key).
        original_checked: Original state for tracking changes.
    """

    checked: bool = False
    value: Any = None
    original_checked: bool = None  # Track original state

    def __post_init__(self):
        if self.value is None:
            self.value = self.key
        if self.original_checked is None:
            self.original_checked = self.checked

    def render(self, is_selected: bool, is_editing: bool) -> str:
        import textwrap

        # Check if state has changed
        change_indicator = " [yellow]✱[/yellow]" if self.checked != self.original_checked else ""

        # Split label into name and description (if present)
        if " - " in self.label:
            name, description = self.label.split(" - ", 1)

            # Build the name part with indicator
            if self.checked:
                checkbox = "[green]✓[/green]"
                name_part = f"[green]{name}[/green]{change_indicator}"
            else:
                checkbox = "[red]✗[/red]"
                name_part = f"[strike red dim]{name}[/]{change_indicator}"

            # Calculate indentation for wrapped lines
            # Checkbox (1) + space (1) + max name length (~30) + " - " (3) = ~35
            indent_spaces = len(name) + 5  # checkbox + space + " - " + indicator space

            # Wrap description to fit in remaining space (assume 100 char total width)
            desc_width = 95 - indent_spaces  # Leave some margin

            if len(description) > desc_width:
                # Wrap the description
                wrapped_lines = textwrap.wrap(description, width=desc_width)
                first_line = wrapped_lines[0]
                remaining_lines = wrapped_lines[1:]

                # Dim descriptions for unchecked items
                if not self.checked:
                    first_line = f"[dim]{first_line}[/]"
                    result = f"{checkbox} {name_part} - {first_line}"

                    # Add wrapped lines with proper indentation
                    for line in remaining_lines:
                        result += f"\n{' ' * (indent_spaces + 2)}[dim]{line}[/]"
                else:
                    result = f"{checkbox} {name_part} - {first_line}"

                    # Add wrapped lines with proper indentation
                    for line in remaining_lines:
                        result += f"\n{' ' * (indent_spaces + 2)}{line}"

                return result
            else:
                # No wrapping needed
                if self.checked:
                    label = f"{name_part} - {description}"
                else:
                    label = f"{name_part} - [dim]{description}[/]"
        else:
            # No description, color entire label
            if self.checked:
                checkbox = "[green]✓[/green]"
                label = f"[green]{self.label}[/green]{change_indicator}"
            else:
                checkbox = "[red]✗[/red]"
                label = f"[strike red dim]{self.label}[/]{change_indicator}"

        return f"{checkbox} {label}"


@dataclass
class TextItem(MenuItem):
    """Text input field.

    Press Enter to edit, type normally, Enter to save, Esc to cancel.

    Attributes:
        value: Current text value.
        max_length: Maximum allowed characters.
    """

    value: str = ""
    max_length: int = 100

    def render(self, is_selected: bool, is_editing: bool) -> str:
        # is_selected not used - future enhancement for visual highlighting
        display_val = self.value[:15] if self.value else "[dim](not set)[/dim]"
        if is_editing:
            display_val = f"{self.value}█"  # Cursor
        return f"{self.label:<20} {display_val}  Edit text"


@dataclass
class ActionItem(MenuItem):
    """Clickable action/button.

    Pressing Enter triggers the action and exits the menu with
    {"action": value} in the result dictionary.

    Attributes:
        value: Identifier returned when this action is triggered.
    """

    value: Any = None

    def render(self, is_selected: bool, is_editing: bool) -> str:
        # is_selected not used - future enhancement for visual highlighting
        return self.label


@dataclass
class SeparatorItem(MenuItem):
    """Visual separator/divider.

    Non-interactive item used for grouping or spacing. Cursor skips over it.
    """

    def __init__(self, label: str):
        super().__init__(key=None, label=label, enabled=False)

    def render(self, is_selected: bool, is_editing: bool) -> str:
        return f"[dim]{self.label}[/dim]"


class Item:
    """Factory for creating menu items.

    Provides convenient static methods for creating different item types:
    - toggle(): Boolean checkbox/switch
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

    Keyboard controls:
        - Up/Down or j/k: Navigate
        - Enter/Space: Activate item (toggle, edit, or action)
        - Esc/q: Exit without saving changes
        - In text edit mode: Enter saves, Esc cancels

    Args:
        title: Menu title displayed in the panel header.
        items: List of MenuItem objects to display.
        console: Optional Rich Console for output (auto-created if not provided).

    Raises:
        ValueError: If items list is empty.

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

    def __init__(self, title: str, items: list[MenuItem], console: Console | None = None):
        if not items:
            raise ValueError("Menu must have at least one item")

        # Validate at least one non-separator item exists
        if all(isinstance(item, SeparatorItem) for item in items):
            raise ValueError("Menu must have at least one interactive item")

        self.title = title
        self.items = items
        self.console = console or Console()
        self.cursor_pos = 0
        self.editing_index: int | None = None
        self.changes: dict[str, Any] = {}
        self.should_exit = False
        self._live: Live | None = None
        self.window_offset = 0  # For scrolling

        # Find first non-separator item
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

        # Skip separators with infinite loop protection
        # Continue in the same direction as delta
        while isinstance(self.items[new_pos], SeparatorItem):
            new_pos += delta
            if new_pos < 0:
                new_pos = len(self.items) - 1
            elif new_pos >= len(self.items):
                new_pos = 0

            attempts += 1
            if attempts >= max_attempts:
                # All items are separators - stay at current position
                return

        self.cursor_pos = new_pos

    def _update_window(self, max_visible: int):
        """Update window offset to keep cursor visible.

        Args:
            max_visible: Maximum number of items that can be displayed.
        """
        # If all items fit, no scrolling needed
        if len(self.items) <= max_visible:
            self.window_offset = 0
            return

        # Keep cursor in view
        if self.cursor_pos < self.window_offset:
            # Cursor moved above window, scroll up
            self.window_offset = self.cursor_pos
        elif self.cursor_pos >= self.window_offset + max_visible:
            # Cursor moved below window, scroll down
            self.window_offset = self.cursor_pos - max_visible + 1

    def _edit_text_item(self, item: TextItem, live: Live):
        """Enter inline text editing mode for a TextItem.

        Displays a cursor and allows character input, backspace, Enter to save,
        and Esc to cancel. The live display updates in real-time as the user types.

        Args:
            item: The TextItem to edit.
            live: The Rich Live context for updating the display.
        """
        self.editing_index = self.cursor_pos
        edit_buffer = item.value
        original_value = item.value  # Store for cancel restoration

        try:
            while True:
                # Update display with cursor
                live.update(self.render())

                try:
                    key = readchar.readkey()
                except KeyboardInterrupt:
                    item.value = original_value  # Restore on interrupt
                    break

                # Cancel editing
                if key == readchar.key.ESC:
                    item.value = original_value  # Restore original value
                    break

                # Commit changes
                elif key == readchar.key.ENTER:
                    # Save to changes dict if item has a key
                    if item.key is not None:
                        self.changes[item.key] = edit_buffer
                    break

                # Backspace
                elif key == readchar.key.BACKSPACE:
                    if edit_buffer:
                        edit_buffer = edit_buffer[:-1]

                # Regular character input
                elif len(key) == 1 and key.isprintable():
                    if len(edit_buffer) < item.max_length:
                        edit_buffer += key

                # Update item value for live preview
                item.value = edit_buffer
        finally:
            self.editing_index = None

    def _activate_current_item(self, live: Live | None = None):
        """Handle Enter/Space activation on the current menu item.

        Behavior depends on item type:
        - ToggleItem: Flip boolean value and track change
        - CheckboxItem: Toggle checked state (no exit, allows multi-select)
        - TextItem: Enter text editing mode
        - ActionItem: Set action and exit menu
        - SeparatorItem: No effect (defensive check)

        Args:
            live: Optional Live context (required for TextItem editing).
        """
        item = self.items[self.cursor_pos]

        # Defensive check - should never happen but be safe
        if isinstance(item, SeparatorItem):
            return

        if isinstance(item, ToggleItem):
            item.value = not item.value
            if item.key is not None:
                self.changes[item.key] = item.value

        elif isinstance(item, CheckboxItem):
            item.checked = not item.checked
            # Don't exit on checkbox toggle - allow multi-select
            # Checkboxes are collected when user presses a submit action

        elif isinstance(item, TextItem):
            if live:
                self._edit_text_item(item, live)

        elif isinstance(item, ActionItem):
            self.changes["action"] = item.value
            self.should_exit = True

    def _handle_key(self, key: str):
        """Handle keyboard input and update menu state.

        Key mappings:
            - q/Esc: Exit menu
            - j/Down: Move cursor down
            - k/Up: Move cursor up
            - Enter/Space: Activate current item

        Args:
            key: Key string from readchar.readkey().
        """
        # Exit keys - use \x1b as fallback for ESC on macOS
        if key.lower() == "q" or key == readchar.key.ESC or key == "\x1b":
            self.should_exit = True
        # Navigation
        elif key.lower() == "j" or key == readchar.key.DOWN:
            self._move_cursor(+1)
        elif key.lower() == "k" or key == readchar.key.UP:
            self._move_cursor(-1)
        # Action
        elif key in [readchar.key.ENTER, " "]:
            self._activate_current_item(self._live)

    def get_checked_values(self) -> list[Any]:
        """Get values of all checked CheckboxItems.

        Returns:
            List of values from checked items.
        """
        return [
            item.value for item in self.items if isinstance(item, CheckboxItem) and item.checked
        ]

    def render(self) -> Panel:
        """Render the menu as a Rich Panel with cursor and help text.

        Returns:
            Rich Panel containing the menu items and keyboard help footer.
        """
        # Calculate available height (terminal height - panel borders - title - footer)
        terminal_height = self.console.height
        max_visible = max(5, terminal_height - 8)  # Reserve space for borders, title, footer

        # Update window to keep cursor visible
        self._update_window(max_visible)

        # Determine visible slice
        window_end = min(self.window_offset + max_visible, len(self.items))
        visible_items = self.items[self.window_offset : window_end]

        # Add scroll indicators
        lines = []
        if self.window_offset > 0:
            lines.append(f"[dim]  ↑ {self.window_offset} more above[/dim]")

        # Render visible items
        for i, item in enumerate(visible_items):
            actual_index = self.window_offset + i
            is_selected = actual_index == self.cursor_pos
            is_editing = actual_index == self.editing_index

            # Selection indicator
            prefix = "[cyan]›[/cyan]" if is_selected else " "
            line = f"{prefix} {item.render(is_selected, is_editing)}"
            lines.append(line)

        # Add more below indicator
        items_below = len(self.items) - window_end
        if items_below > 0:
            lines.append(f"[dim]  ↓ {items_below} more below[/dim]")

        content = "\n".join(lines)

        # Check if menu has checkboxes
        has_checkboxes = any(isinstance(item, CheckboxItem) for item in self.items)
        if has_checkboxes:
            footer = "[dim]↑↓/jk navigate • Space toggle • [yellow]✱[/yellow] unsaved • Enter save • Esc/q cancel[/dim]"
        else:
            footer = "[dim]↑↓/jk navigate • Enter/Space select • Esc/q exit[/dim]"

        return Panel(
            f"{content}\n\n{footer}",
            title=f"[bold]{self.title}[/bold]",
            border_style="cyan",
            width=100,
        )

    def show(self) -> dict[str, Any]:
        """Display the interactive menu and block until user exits.

        The menu runs in a Rich.Live context for flicker-free updates.
        All changes to toggle and text items are tracked in real-time.

        Returns:
            Dictionary of changes:
            - For toggles/text: {key: value} pairs for modified items
            - For actions: {"action": value} when an action is triggered
            - Empty dict if user exits without changes (Esc/q)

        Example:
            result = menu.show()
            # User toggled "debug" and clicked "Save"
            # Returns: {"debug": True, "action": "save"}
        """
        with Live(self.render(), console=self.console, refresh_per_second=20) as live:
            self._live = live  # Store for activation

            while not self.should_exit:
                try:
                    key = readchar.readkey()
                    self._handle_key(key)
                    live.update(self.render())
                except KeyboardInterrupt:
                    self.should_exit = True

        return self.changes
