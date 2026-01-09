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
        marked_for_deletion: Whether item is marked for deletion (red strikethrough).
    """

    checked: bool = False
    value: Any = None
    original_checked: bool = None
    marked_for_deletion: bool = False

    def __post_init__(self):
        if self.value is None:
            self.value = self.key
        if self.original_checked is None:
            self.original_checked = self.checked

    def _get_checkbox_icon(self, theme: Theme) -> str:
        """Get the checkbox icon based on checked state."""
        if self.checked:
            return f"[{theme.checked_color}]{theme.checked_icon}[/{theme.checked_color}]"
        return f"[{theme.unchecked_color}]{theme.unchecked_icon}[/{theme.unchecked_color}]"

    def _get_change_indicator(self, theme: Theme) -> str:
        """Get change indicator if state differs from original."""
        if self.checked != self.original_checked:
            return f" [{theme.warning_color}]{theme.change_icon}[/{theme.warning_color}]"
        return ""

    def _style_name(self, name: str, theme: Theme) -> str:
        """Style the name part based on checked state."""
        change = self._get_change_indicator(theme)
        if self.marked_for_deletion:
            return f"[strike red]{name}[/strike red]"
        if self.checked:
            return f"[{theme.checked_color}]{name}[/{theme.checked_color}]{change}"
        return f"[{theme.dim_color}]{name}[/{theme.dim_color}]{change}"

    def _style_description(self, desc: str, theme: Theme) -> str:
        """Style description text (dimmed when unchecked)."""
        if self.checked:
            return desc
        return f"[{theme.dim_color}]{desc}[/{theme.dim_color}]"

    def _render_with_description(self, name: str, description: str, theme: Theme) -> str:
        """Render checkbox with name - description format."""
        checkbox = self._get_checkbox_icon(theme)
        name_part = self._style_name(name, theme)

        # Calculate indentation and wrapping
        indent_spaces = len(name) + 5
        desc_width = 95 - indent_spaces

        if len(description) <= desc_width:
            # Single line description
            desc_part = self._style_description(description, theme)
            return f"{checkbox} {name_part} - {desc_part}"

        # Multi-line wrapped description
        wrapped = textwrap.wrap(description, width=desc_width)
        indent = " " * (indent_spaces + 2)

        lines = [f"{checkbox} {name_part} - {self._style_description(wrapped[0], theme)}"]
        for line in wrapped[1:]:
            lines.append(f"{indent}{self._style_description(line, theme)}")

        return "\n".join(lines)

    def _render_simple(self, theme: Theme) -> str:
        """Render checkbox with simple label (no description)."""
        checkbox = self._get_checkbox_icon(theme)
        label = self._style_name(self.label, theme)
        return f"{checkbox} {label}"

    def render(self, is_selected: bool, is_editing: bool, theme: Theme = DEFAULT_THEME) -> str:
        if " - " in self.label:
            name, description = self.label.split(" - ", 1)
            return self._render_with_description(name, description, theme)
        return self._render_simple(theme)


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
