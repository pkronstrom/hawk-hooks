"""Menu item components for rich_menu.

This module provides the building blocks for interactive menus:
- MenuItem: Base class for all items
- ToggleItem: Boolean on/off switch
- CheckboxItem: Multi-select checkbox
- TextItem: Editable text field
- ActionItem: Clickable button
- SeparatorItem: Visual divider
"""

import textwrap
from dataclasses import dataclass
from typing import Any

from .themes import DEFAULT_THEME, Theme


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

    def render(self, is_selected: bool, is_editing: bool, theme: Theme = DEFAULT_THEME) -> str:
        """Render this item as a Rich markup string.

        Args:
            is_selected: Whether the cursor is on this item.
            is_editing: Whether this item is in edit mode.
            theme: Visual theme for styling.

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

    def render(self, is_selected: bool, is_editing: bool, theme: Theme = DEFAULT_THEME) -> str:
        if self.value:
            status = f"[{theme.checked_color}]{theme.checked_icon} on [/{theme.checked_color}]"
        else:
            status = f"[{theme.dim_color}]  off[/{theme.dim_color}]"
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
    original_checked: bool = None

    def __post_init__(self):
        if self.value is None:
            self.value = self.key
        if self.original_checked is None:
            self.original_checked = self.checked

    def render(self, is_selected: bool, is_editing: bool, theme: Theme = DEFAULT_THEME) -> str:
        # Check if state has changed
        if self.checked != self.original_checked:
            change_indicator = (
                f" [{theme.warning_color}]{theme.change_icon}[/{theme.warning_color}]"
            )
        else:
            change_indicator = ""

        # Split label into name and description (if present)
        if " - " in self.label:
            name, description = self.label.split(" - ", 1)

            # Build the name part with indicator
            if self.checked:
                checkbox = f"[{theme.checked_color}]{theme.checked_icon}[/{theme.checked_color}]"
                name_part = (
                    f"[{theme.checked_color}]{name}[/{theme.checked_color}]{change_indicator}"
                )
            else:
                checkbox = (
                    f"[{theme.unchecked_color}]{theme.unchecked_icon}[/{theme.unchecked_color}]"
                )
                name_part = (
                    f"[strike {theme.unchecked_color} {theme.dim_color}]{name}[/]{change_indicator}"
                )

            # Calculate indentation for wrapped lines
            indent_spaces = len(name) + 5

            # Wrap description to fit (assume ~100 char total width)
            desc_width = 95 - indent_spaces

            if len(description) > desc_width:
                wrapped_lines = textwrap.wrap(description, width=desc_width)
                first_line = wrapped_lines[0]
                remaining_lines = wrapped_lines[1:]

                if not self.checked:
                    first_line = f"[{theme.dim_color}]{first_line}[/{theme.dim_color}]"
                    result = f"{checkbox} {name_part} - {first_line}"
                    for line in remaining_lines:
                        result += f"\n{' ' * (indent_spaces + 2)}[{theme.dim_color}]{line}[/{theme.dim_color}]"
                else:
                    result = f"{checkbox} {name_part} - {first_line}"
                    for line in remaining_lines:
                        result += f"\n{' ' * (indent_spaces + 2)}{line}"
                return result
            else:
                if self.checked:
                    label = f"{name_part} - {description}"
                else:
                    label = f"{name_part} - [{theme.dim_color}]{description}[/{theme.dim_color}]"
        else:
            if self.checked:
                checkbox = f"[{theme.checked_color}]{theme.checked_icon}[/{theme.checked_color}]"
                label = (
                    f"[{theme.checked_color}]{self.label}[/{theme.checked_color}]{change_indicator}"
                )
            else:
                checkbox = (
                    f"[{theme.unchecked_color}]{theme.unchecked_icon}[/{theme.unchecked_color}]"
                )
                label = f"[strike {theme.unchecked_color} {theme.dim_color}]{self.label}[/]{change_indicator}"

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

    def render(self, is_selected: bool, is_editing: bool, theme: Theme = DEFAULT_THEME) -> str:
        if self.value:
            display_val = self.value[:15]
        else:
            display_val = f"[{theme.dim_color}](not set)[/{theme.dim_color}]"

        if is_editing:
            display_val = f"{self.value}█"

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

    def render(self, is_selected: bool, is_editing: bool, theme: Theme = DEFAULT_THEME) -> str:
        return self.label


@dataclass
class SeparatorItem(MenuItem):
    """Visual separator/divider.

    Non-interactive item used for grouping or spacing. Cursor skips over it.
    """

    def __init__(self, label: str):
        super().__init__(key=None, label=label, enabled=False)

    def render(self, is_selected: bool, is_editing: bool, theme: Theme = DEFAULT_THEME) -> str:
        return f"[{theme.dim_color}]{self.label}[/{theme.dim_color}]"
