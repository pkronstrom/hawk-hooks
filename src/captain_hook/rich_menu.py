"""Rich.Live-based interactive menu system."""

from dataclasses import dataclass
from typing import Any


@dataclass
class MenuItem:
    """Base class for menu items."""

    key: str | None
    label: str
    enabled: bool = True

    def render(self, is_selected: bool, is_editing: bool) -> str:
        """Render this item as a string."""
        raise NotImplementedError


@dataclass
class ToggleItem(MenuItem):
    """Boolean toggle item."""

    value: bool = False

    def render(self, is_selected: bool, is_editing: bool) -> str:
        # is_selected not used - future enhancement for visual highlighting
        status = "[green]✓ on [/green]" if self.value else "[dim]  off[/dim]"
        return f"{self.label:<20} {status}  Toggle"


@dataclass
class TextItem(MenuItem):
    """Text input item."""

    value: str = ""

    def render(self, is_selected: bool, is_editing: bool) -> str:
        # is_selected not used - future enhancement for visual highlighting
        display_val = self.value[:15] if self.value else "[dim](not set)[/dim]"
        if is_editing:
            display_val = f"{self.value}█"  # Cursor
        return f"{self.label:<20} {display_val}  Edit text"


@dataclass
class ActionItem(MenuItem):
    """Action/button item."""

    value: Any = None

    def render(self, is_selected: bool, is_editing: bool) -> str:
        # is_selected not used - future enhancement for visual highlighting
        return self.label


@dataclass
class SeparatorItem(MenuItem):
    """Visual separator."""

    def __init__(self, label: str):
        super().__init__(key=None, label=label, enabled=False)

    def render(self, is_selected: bool, is_editing: bool) -> str:
        return f"[dim]{self.label}[/dim]"
