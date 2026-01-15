"""Configurable themes for rich_menu components.

This module provides theming support for menu styling. The Theme dataclass
holds all configurable visual elements (colors, icons, layout).
"""

from dataclasses import dataclass


@dataclass
class Theme:
    """Visual theme for menu components.

    All colors use Rich markup format (e.g., "green", "bold cyan", "dim").

    Attributes:
        selected_color: Color for cursor indicator.
        checked_color: Color for checked/enabled items.
        unchecked_color: Color for unchecked/disabled items.
        dim_color: Color for dimmed/secondary text.
        warning_color: Color for change indicators.
        border_color: Color for panel border.

        cursor_icon: Character shown next to selected item.
        checked_icon: Character for checked state.
        unchecked_icon: Character for unchecked state.
        change_icon: Character indicating unsaved changes.
        scroll_up_icon: Character indicating more items above.
        scroll_down_icon: Character indicating more items below.

        panel_width: Fixed width of the menu panel.
        min_visible_items: Minimum items to show before scrolling.
        max_visible_items: Maximum items to show (caps tall terminals).
        panel_padding: Lines reserved for borders/title/footer.
    """

    # Colors
    selected_color: str = "cyan"
    checked_color: str = "green"
    unchecked_color: str = "red"
    dim_color: str = "dim"
    warning_color: str = "yellow"
    border_color: str = "cyan"

    # Icons
    cursor_icon: str = "›"
    checked_icon: str = "✓"
    unchecked_icon: str = "✗"
    change_icon: str = "✱"
    scroll_up_icon: str = "↑"
    scroll_down_icon: str = "↓"

    # Layout
    panel_width: int = 100
    min_visible_items: int = 5
    max_visible_items: int = 20
    panel_padding: int = 8


# Default theme used when none is specified
DEFAULT_THEME = Theme()
