# Rich.Live Interactive Menu System Design

**Date:** 2026-01-07
**Purpose:** Replace questionary with a flicker-free, Rich.Live-based interactive menu system

## Problem Statement

Current questionary-based menus have visual issues:
- Screen clearing causes flickering on each interaction
- Cursor position resets briefly during updates
- Not ideal for smooth, modern CLI UX

## Solution Overview

Build a single-file, reusable menu library using Rich.Live for flicker-free updates and manual keyboard handling for full control over interactions.

## Goals

- **Flicker-free**: Use Rich.Live for smooth in-place updates
- **Reusable**: Single `.py` file that can be copied to other projects (like pyafk)
- **Minimal**: Simple, focused feature set - no over-engineering
- **Beautiful**: Clean, intuitive UI with sensible defaults
- **DRY**: Modular component design

## Architecture

### File Structure

Single file: `src/hawk_hooks/rich_menu.py` (~400-500 lines)

### Core Components

#### 1. MenuItem Base Class

Dataclass representing a menu item:
```python
@dataclass
class MenuItem:
    key: str | None
    label: str
    enabled: bool = True

    def render(self, is_selected: bool, is_editing: bool) -> str:
        raise NotImplementedError
```

**Subclasses:**
- `ToggleItem` - Boolean on/off values (e.g., debug mode)
- `TextItem` - String input fields (e.g., API keys)
- `ActionItem` - Clickable actions (e.g., "Back", "Save")
- `SeparatorItem` - Visual dividers (e.g., "── Settings ──")

#### 2. InteractiveList Class

Main menu controller:
```python
class InteractiveList:
    def __init__(self, title: str, items: list[MenuItem]):
        self.title = title
        self.items = items
        self.cursor_pos = 0
        self.editing_index = None
        self.changes = {}
        self.should_exit = False

    def show(self) -> dict:
        """Display menu and return changed values"""
        with Live(self.render(), refresh_per_second=20) as live:
            while not self.should_exit:
                key = readchar.readkey()
                self.handle_key(key)
                live.update(self.render())

        return self.changes
```

#### 3. Item Factory Class

Declarative API for creating items:
```python
class Item:
    @staticmethod
    def toggle(key: str, label: str, value: bool = False) -> ToggleItem:
        return ToggleItem(key=key, label=label, value=value)

    @staticmethod
    def text(key: str, label: str, value: str = "", max_length: int = 50) -> TextItem:
        return TextItem(key=key, label=label, value=value, max_length=max_length)

    @staticmethod
    def action(label: str, value: Any = None) -> ActionItem:
        return ActionItem(key=None, label=label, value=value)

    @staticmethod
    def separator(label: str) -> SeparatorItem:
        return SeparatorItem(key=None, label=label)
```

## User Interface

### Visual Layout

```
Configuration
──────────────────────────────────────────────────

› debug             ✓ on    Log hook calls
  ── Settings ──
  API_KEY           secret  Enter API key
  NOTIFY_ENABLED      off   Desktop notifications
  ─────────
  Back

↑↓/jk navigate • Enter/Space select • Esc/q exit
```

### Rendering Rules

**Selection indicator:** `›` prefix (cyan) for selected item, space for others

**ToggleItem:** `"  {label:<20} {status:>6}  {description}"`
- Status: `✓ on` (green) or `  off` (dim)

**TextItem:** `"  {label:<20} {value:>15}  {description}"`
- When editing: `"  {label:<20} {value}█  {description}"` (cursor blink)

**ActionItem:** `"  {label}"`

**SeparatorItem:** `"  {label}"` (dim gray)

### Keyboard Controls

**Navigation:**
- `↑/k` - Move up
- `↓/j` - Move down
- Automatically skips separators

**Actions:**
- `Enter` or `Space` - Toggle boolean / Edit text / Execute action
- `Esc`, `q`, or `Ctrl+C` - Exit menu

**Text Editing (inline modal):**
- `Enter` - Commit changes
- `Esc` - Cancel editing
- `Backspace` - Delete character
- Printable chars - Append to value
- Live preview as you type

## Interaction Behavior

### State Management (Option A)

Changes happen immediately in the menu display. When user exits:
- Return dict of all changed values: `{"debug": True, "API_KEY": "new_value"}`
- Only includes items that were modified
- Caller is responsible for persisting changes

### Inline Text Editing

When Enter/Space pressed on TextItem:
1. Enter edit mode (set `editing_index`)
2. Copy current value to `edit_buffer`
3. Character-by-character input loop:
   - Live update display with cursor
   - Backspace removes chars
   - Printable chars append
   - Enter commits → save to `item.value` and `changes` dict
   - Esc cancels → discard buffer
4. Exit edit mode

### Toggle Behavior

When Enter/Space pressed on ToggleItem:
- Flip boolean value immediately
- Record in `changes` dict
- Menu stays open, cursor stays in place

### Action Behavior

When Enter/Space pressed on ActionItem:
- Set `selected_action = item.value`
- Exit menu immediately
- Return `{"action": item.value}`

## API Usage Example

```python
from rich_menu import InteractiveList, Item

menu = InteractiveList(
    title="Configuration",
    items=[
        Item.toggle("debug", "Log hook calls", value=True),
        Item.separator("── Hook Settings ──"),
        Item.text("NOTIFY_NTFY_TOPIC", "ntfy.sh topic", value=""),
        Item.toggle("NOTIFY_DESKTOP", "Desktop notifications", value=False),
        Item.separator("─────────"),
        Item.action("Back", value="back"),
    ]
)

result = menu.show()
# Returns: {"debug": False, "NOTIFY_NTFY_TOPIC": "my-topic"}
# or: {"action": "back"} if action selected
```

## Dependencies

**New:**
- `readchar` - Cross-platform keyboard input (handles arrow keys, special keys)

**Existing:**
- `rich` - Already in project for Live, Panel, styling

## Error Handling

- **Non-TTY detection:** Raise `RuntimeError` if not running in interactive terminal
- **Ctrl+C:** Exit gracefully, no traceback
- **Terminal resize:** Re-render on SIGWINCH (future enhancement)

## Testing Strategy

Manual testing initially (terminal UI is hard to unit test):
- Toggle items update correctly
- Text editing works (backspace, typing, cancel)
- Navigation skips separators
- Exit keys work (Esc, q, Ctrl+C)
- Cursor position preserved after edits

Document test cases in docstrings for future contributors.

## Implementation Plan

1. Create `src/hawk_hooks/rich_menu.py`
2. Implement MenuItem base + subclasses
3. Implement InteractiveList with basic rendering
4. Add keyboard handling (navigation, toggle, edit)
5. Add inline text editing logic
6. Polish styling and colors (hardcoded defaults)
7. Replace questionary in `interactive_config()`
8. Test thoroughly in real usage
9. Document API and usage patterns

## Future Enhancements (Not v1)

- CheckboxMenu for multi-select
- Search/filter with `/` key
- Custom color themes
- Password masking for sensitive text fields
- Validation for text inputs
- Scroll support for long lists

## Migration from Questionary

Replace this:
```python
choice = questionary.select(
    "Select to toggle/edit:",
    choices=[
        questionary.Choice(f"debug {status} ...", value="debug"),
        questionary.Separator("── Settings ──"),
        # ...
    ],
    default=last_choice,
).ask()
```

With this:
```python
menu = InteractiveList(
    title="Configuration",
    items=[
        Item.toggle("debug", "Log hook calls", value=cfg["debug"]),
        Item.separator("── Settings ──"),
        # ...
    ]
)
result = menu.show()
```

Clean, declarative, and flicker-free!
