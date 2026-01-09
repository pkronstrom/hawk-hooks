"""Backwards compatibility shim - imports from rich_menu package.

This module exists for backwards compatibility. New code should import
directly from the rich_menu package:

    from rich_menu import InteractiveList, Item
"""

from rich_menu import (
    DEFAULT_THEME,
    ActionItem,
    CheckboxItem,
    InteractiveList,
    Item,
    MenuItem,
    SeparatorItem,
    TextItem,
    Theme,
    ToggleItem,
)

__all__ = [
    "InteractiveList",
    "Item",
    "MenuItem",
    "ToggleItem",
    "CheckboxItem",
    "TextItem",
    "ActionItem",
    "SeparatorItem",
    "Theme",
    "DEFAULT_THEME",
]
