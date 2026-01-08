"""Rich.Live-based interactive menu system."""

from dataclasses import dataclass
from typing import Any

import readchar
from rich.console import Console
from rich.live import Live
from rich.panel import Panel


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


class Item:
    """Factory for creating menu items."""

    @staticmethod
    def toggle(key: str, label: str, value: bool = False) -> ToggleItem:
        """Create a boolean toggle item."""
        return ToggleItem(key=key, label=label, value=value)

    @staticmethod
    def text(key: str, label: str, value: str = "") -> TextItem:
        """Create a text input item."""
        return TextItem(key=key, label=label, value=value)

    @staticmethod
    def action(label: str, value: Any = None) -> ActionItem:
        """Create an action/button item."""
        return ActionItem(key=None, label=label, value=value)

    @staticmethod
    def separator(label: str) -> SeparatorItem:
        """Create a visual separator."""
        return SeparatorItem(label=label)


class InteractiveList:
    """Interactive menu with keyboard navigation."""

    def __init__(self, title: str, items: list[MenuItem], console: Console | None = None):
        if not items:
            raise ValueError("Menu must have at least one item")

        self.title = title
        self.items = items
        self.console = console or Console()
        self.cursor_pos = 0
        self.editing_index: int | None = None
        self.changes: dict[str, Any] = {}
        self.should_exit = False

        # Move to first non-separator item
        if isinstance(self.items[0], SeparatorItem):
            self._move_cursor(1)

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

    def _activate_current_item(self):
        """Handle Enter/Space on current item."""
        item = self.items[self.cursor_pos]

        # Defensive check - should never happen but be safe
        if isinstance(item, SeparatorItem):
            return

        if isinstance(item, ToggleItem):
            # Toggle boolean
            item.value = not item.value
            if item.key is not None:
                self.changes[item.key] = item.value

        elif isinstance(item, TextItem):
            # Will implement text editing next
            pass

        elif isinstance(item, ActionItem):
            # Exit with action (preserve other changes)
            self.changes["action"] = item.value
            self.should_exit = True

    def _handle_key(self, key: str):
        """Handle keyboard input."""
        # Exit keys
        if key in ["q", readchar.key.ESC]:
            self.should_exit = True
        # Navigation
        elif key in ["j", readchar.key.DOWN]:
            self._move_cursor(+1)
        elif key in ["k", readchar.key.UP]:
            self._move_cursor(-1)
        # Action
        elif key in [readchar.key.ENTER, " "]:
            self._activate_current_item()

    def render(self) -> Panel:
        """Render the menu as a Rich Panel."""
        lines = []
        for i, item in enumerate(self.items):
            is_selected = i == self.cursor_pos
            is_editing = i == self.editing_index

            # Selection indicator
            prefix = "[cyan]›[/cyan]" if is_selected else " "
            line = f"{prefix} {item.render(is_selected, is_editing)}"
            lines.append(line)

        content = "\n".join(lines)
        footer = "[dim]↑↓/jk navigate • Enter/Space select • Esc/q exit[/dim]"

        return Panel(
            f"{content}\n\n{footer}",
            title=f"[bold]{self.title}[/bold]",
            border_style="cyan",
        )

    def show(self) -> dict[str, Any]:
        """Display menu and return changes."""
        with Live(self.render(), console=self.console, refresh_per_second=20) as live:
            while not self.should_exit:
                try:
                    key = readchar.readkey()
                    self._handle_key(key)
                    live.update(self.render())
                except KeyboardInterrupt:
                    self.should_exit = True

        return self.changes
