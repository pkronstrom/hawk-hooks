"""Rich.Live-based interactive menu system.

A reusable menu library for building flicker-free CLI menus.

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
    result = menu.show()  # Returns: {"debug": False, "api_key": "newkey"}
"""

from .components import (
    ActionItem,
    CheckboxItem,
    MenuItem,
    SeparatorItem,
    TextItem,
    ToggleItem,
)
from .menu import InteractiveList, Item
from .themes import DEFAULT_THEME, Theme

__all__ = [
    # Main classes
    "InteractiveList",
    "Item",
    # Components
    "MenuItem",
    "ToggleItem",
    "CheckboxItem",
    "TextItem",
    "ActionItem",
    "SeparatorItem",
    # Theming
    "Theme",
    "DEFAULT_THEME",
]
