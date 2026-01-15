# Rich.Live Interactive Menu System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a single-file, flicker-free interactive menu library using Rich.Live to replace questionary in hawk-hooks.

**Architecture:** Create `src/hawk_hooks/rich_menu.py` with MenuItem base class + subclasses (Toggle, Text, Action, Separator), InteractiveList controller using Rich.Live for rendering, and Item factory for clean API. Manual keyboard handling with readchar library for full control.

**Tech Stack:** Rich (Live, Panel), readchar (keyboard input), Python 3.10+ dataclasses

---

## Task 1: Add readchar dependency

**Files:**
- Modify: `pyproject.toml:26-29`

**Step 1: Add readchar to dependencies**

Edit `pyproject.toml`:
```toml
dependencies = [
    "questionary>=2.0.0",
    "rich>=13.0.0",
    "readchar>=4.0.0",
]
```

**Step 2: Verify dependency syntax**

Run: `python -m pip check`
Expected: No errors

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add readchar for keyboard input"
```

---

## Task 2: Create MenuItem base classes

**Files:**
- Create: `src/hawk_hooks/rich_menu.py`

**Step 1: Create module with MenuItem dataclasses**

Create `src/hawk_hooks/rich_menu.py`:
```python
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
        status = "[green]✓ on [/green]" if self.value else "[dim]  off[/dim]"
        return f"{self.label:<20} {status:>10}  Toggle"


@dataclass
class TextItem(MenuItem):
    """Text input item."""
    value: str = ""
    max_length: int = 50

    def render(self, is_selected: bool, is_editing: bool) -> str:
        display_val = self.value[:15] if self.value else "[dim](not set)[/dim]"
        if is_editing:
            display_val = f"{self.value}█"  # Cursor
        return f"{self.label:<20} {display_val:>15}  Edit text"


@dataclass
class ActionItem(MenuItem):
    """Action/button item."""
    value: Any = None

    def render(self, is_selected: bool, is_editing: bool) -> str:
        return self.label


@dataclass
class SeparatorItem(MenuItem):
    """Visual separator."""

    def __init__(self, label: str):
        super().__init__(key=None, label=label, enabled=False)

    def render(self, is_selected: bool, is_editing: bool) -> str:
        return f"[dim]{self.label}[/dim]"
```

**Step 2: Verify imports work**

Run: `python -c "from src.hawk_hooks.rich_menu import MenuItem, ToggleItem"`
Expected: No errors

**Step 3: Commit**

```bash
git add src/hawk_hooks/rich_menu.py
git commit -m "feat: add MenuItem base classes"
```

---

## Task 3: Add Item factory class

**Files:**
- Modify: `src/hawk_hooks/rich_menu.py` (append at end)

**Step 1: Add Item factory**

Append to `src/hawk_hooks/rich_menu.py`:
```python


class Item:
    """Factory for creating menu items."""

    @staticmethod
    def toggle(key: str, label: str, value: bool = False) -> ToggleItem:
        """Create a boolean toggle item."""
        return ToggleItem(key=key, label=label, value=value)

    @staticmethod
    def text(key: str, label: str, value: str = "", max_length: int = 50) -> TextItem:
        """Create a text input item."""
        return TextItem(key=key, label=label, value=value, max_length=max_length)

    @staticmethod
    def action(label: str, value: Any = None) -> ActionItem:
        """Create an action/button item."""
        return ActionItem(key=None, label=label, value=value)

    @staticmethod
    def separator(label: str) -> SeparatorItem:
        """Create a visual separator."""
        return SeparatorItem(label=label)
```

**Step 2: Verify factory works**

Run:
```bash
python -c "from src.hawk_hooks.rich_menu import Item; print(Item.toggle('test', 'Test', True))"
```
Expected: Prints `ToggleItem(key='test', label='Test', enabled=True, value=True)`

**Step 3: Commit**

```bash
git add src/hawk_hooks/rich_menu.py
git commit -m "feat: add Item factory class"
```

---

## Task 4: Create InteractiveList skeleton

**Files:**
- Modify: `src/hawk_hooks/rich_menu.py` (append at end)

**Step 1: Add InteractiveList class**

Append to `src/hawk_hooks/rich_menu.py`:
```python
from rich.console import Console
from rich.panel import Panel


class InteractiveList:
    """Interactive menu with keyboard navigation."""

    def __init__(self, title: str, items: list[MenuItem], console: Console | None = None):
        self.title = title
        self.items = items
        self.console = console or Console()
        self.cursor_pos = 0
        self.editing_index: int | None = None
        self.changes: dict[str, Any] = {}
        self.should_exit = False

    def render(self) -> Panel:
        """Render the menu as a Rich Panel."""
        lines = []
        for i, item in enumerate(self.items):
            is_selected = (i == self.cursor_pos)
            is_editing = (i == self.editing_index)

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
        # Placeholder - will add Live loop next
        self.console.print(self.render())
        return self.changes
```

**Step 2: Test rendering**

Create test script `test_menu.py`:
```python
from src.hawk_hooks.rich_menu import InteractiveList, Item

menu = InteractiveList(
    title="Test Menu",
    items=[
        Item.toggle("debug", "Debug mode", value=True),
        Item.separator("── Settings ──"),
        Item.text("api_key", "API Key", value="secret"),
        Item.action("Back", value="back"),
    ]
)
menu.show()
```

Run: `python test_menu.py`
Expected: Displays menu with 4 items, cursor on first item

**Step 3: Commit**

```bash
git add src/hawk_hooks/rich_menu.py
git commit -m "feat: add InteractiveList skeleton with rendering"
```

---

## Task 5: Add keyboard navigation

**Files:**
- Modify: `src/hawk_hooks/rich_menu.py` (InteractiveList class)

**Step 1: Add imports**

Add at top of file:
```python
import readchar
from rich.live import Live
```

**Step 2: Add navigation methods**

Add to `InteractiveList` class:
```python
    def _move_cursor(self, delta: int):
        """Move cursor up/down, skipping separators."""
        new_pos = self.cursor_pos + delta

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

        self.cursor_pos = new_pos

    def _handle_key(self, key: str):
        """Handle keyboard input."""
        # Exit keys
        if key in ['q', readchar.key.ESC]:
            self.should_exit = True
        # Navigation
        elif key in ['j', readchar.key.DOWN]:
            self._move_cursor(+1)
        elif key in ['k', readchar.key.UP]:
            self._move_cursor(-1)
        # Action (placeholder for now)
        elif key in [readchar.key.ENTER, ' ']:
            pass  # Will implement in next task
```

**Step 3: Update show() method**

Replace `show()` method:
```python
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
```

**Step 4: Test navigation**

Run: `python test_menu.py`
Expected:
- Arrow keys / j/k move cursor
- Cursor skips separator
- q/Esc exits

**Step 5: Commit**

```bash
git add src/hawk_hooks/rich_menu.py
git commit -m "feat: add keyboard navigation"
```

---

## Task 6: Add toggle functionality

**Files:**
- Modify: `src/hawk_hooks/rich_menu.py` (InteractiveList._handle_key)

**Step 1: Implement toggle activation**

Add method to `InteractiveList`:
```python
    def _activate_current_item(self):
        """Handle Enter/Space on current item."""
        item = self.items[self.cursor_pos]

        if isinstance(item, ToggleItem):
            # Toggle boolean
            item.value = not item.value
            self.changes[item.key] = item.value

        elif isinstance(item, TextItem):
            # Will implement text editing next
            pass

        elif isinstance(item, ActionItem):
            # Exit with action
            self.changes = {"action": item.value}
            self.should_exit = True
```

**Step 2: Wire up to key handler**

Update `_handle_key()` method, replace the placeholder:
```python
        # Action
        elif key in [readchar.key.ENTER, ' ']:
            self._activate_current_item()
```

**Step 3: Test toggle**

Run: `python test_menu.py`
Expected:
- Press Enter on "Debug mode" toggles ✓ on/off
- Press Enter on "Back" exits and returns `{"action": "back"}`

**Step 4: Commit**

```bash
git add src/hawk_hooks/rich_menu.py
git commit -m "feat: add toggle and action functionality"
```

---

## Task 7: Add inline text editing

**Files:**
- Modify: `src/hawk_hooks/rich_menu.py` (InteractiveList class)

**Step 1: Add text editing method**

Add to `InteractiveList` class:
```python
    def _edit_text_item(self, item: TextItem, live: Live):
        """Enter inline text editing mode."""
        self.editing_index = self.cursor_pos
        edit_buffer = item.value

        while True:
            # Update display with cursor
            live.update(self.render())

            try:
                key = readchar.readkey()
            except KeyboardInterrupt:
                break

            # Commit changes
            if key == readchar.key.ENTER:
                item.value = edit_buffer
                self.changes[item.key] = edit_buffer
                break

            # Cancel editing
            elif key == readchar.key.ESC:
                break

            # Delete character
            elif key == readchar.key.BACKSPACE:
                if edit_buffer:
                    edit_buffer = edit_buffer[:-1]

            # Add printable characters
            elif len(key) == 1 and key.isprintable():
                if len(edit_buffer) < item.max_length:
                    edit_buffer += key

            # Update item value for live preview
            item.value = edit_buffer

        self.editing_index = None
```

**Step 2: Wire up to activation**

Update `_activate_current_item()` method to pass live context:
```python
    def _activate_current_item(self, live: Live | None = None):
        """Handle Enter/Space on current item."""
        item = self.items[self.cursor_pos]

        if isinstance(item, ToggleItem):
            item.value = not item.value
            self.changes[item.key] = item.value

        elif isinstance(item, TextItem):
            if live:
                self._edit_text_item(item, live)

        elif isinstance(item, ActionItem):
            self.changes = {"action": item.value}
            self.should_exit = True
```

**Step 3: Update show() to pass live**

Modify `show()` method to pass live context:
```python
    def show(self) -> dict[str, Any]:
        """Display menu and return changes."""
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
```

**Step 4: Update activation call**

In `_handle_key()`:
```python
        # Action
        elif key in [readchar.key.ENTER, ' ']:
            self._activate_current_item(self._live)
```

**Step 5: Test text editing**

Run: `python test_menu.py`
Expected:
- Navigate to "API Key"
- Press Enter
- Type new value, see cursor update
- Press Enter to commit
- Value updates in menu

**Step 6: Commit**

```bash
git add src/hawk_hooks/rich_menu.py
git commit -m "feat: add inline text editing"
```

---

## Task 8: Add initialization cursor skip

**Files:**
- Modify: `src/hawk_hooks/rich_menu.py` (InteractiveList.__init__)

**Step 1: Skip separators on init**

Update `__init__` method:
```python
    def __init__(self, title: str, items: list[MenuItem], console: Console | None = None):
        self.title = title
        self.items = items
        self.console = console or Console()
        self.cursor_pos = 0
        self.editing_index: int | None = None
        self.changes: dict[str, Any] = {}
        self.should_exit = False
        self._live: Live | None = None

        # Skip separators on initial position
        while self.cursor_pos < len(self.items) and isinstance(self.items[self.cursor_pos], SeparatorItem):
            self.cursor_pos += 1
```

**Step 2: Test**

Run: `python test_menu.py`
Expected: Cursor starts on "Debug mode", not separator

**Step 3: Commit**

```bash
git add src/hawk_hooks/rich_menu.py
git commit -m "fix: skip separators on initialization"
```

---

## Task 9: Replace questionary in interactive_config()

**Files:**
- Modify: `src/hawk_hooks/cli.py:638-735`

**Step 1: Add import**

At top of `cli.py`, add:
```python
from .rich_menu import InteractiveList, Item
```

**Step 2: Rewrite interactive_config()**

Replace entire `interactive_config()` function:
```python
def interactive_config():
    """Interactive config editor with persistent menu."""
    cfg = config.load_config()
    debug_changed = False
    env_changed = False

    # Get all env vars from scripts (with defaults)
    script_env_vars = scanner.get_all_env_vars()

    # Merge script defaults with stored config values
    env_config = cfg.get("env", {})

    while True:
        # Build menu items
        items = [
            Item.toggle("debug", "Log hook calls", value=cfg.get("debug", False)),
        ]

        # Add env var items
        if script_env_vars:
            items.append(Item.separator("── Hook Settings ──"))

            for var_name, default_value in sorted(script_env_vars.items()):
                current_value = env_config.get(var_name, default_value)
                is_bool = current_value.lower() in ("true", "false", "1", "0", "yes", "no")

                if is_bool:
                    value = current_value.lower() in ("true", "1", "yes")
                    items.append(Item.toggle(var_name, var_name, value=value))
                else:
                    items.append(Item.text(var_name, var_name, value=current_value))

        items.append(Item.separator("─────────"))
        items.append(Item.action("Back", value="back"))

        # Show menu
        menu = InteractiveList(title="Configuration", items=items, console=console)
        result = menu.show()

        # Handle exit
        if "action" in result and result["action"] == "back":
            break

        # Apply changes
        for key, value in result.items():
            if key == "debug":
                cfg["debug"] = value
                debug_changed = True
                config.save_config(cfg)
            elif key in script_env_vars:
                # Convert bool back to string for env vars
                if isinstance(value, bool):
                    env_config[key] = "true" if value else "false"
                else:
                    env_config[key] = value
                cfg["env"] = env_config
                config.save_config(cfg)
                env_changed = True

    # Regenerate runners if debug or env changed
    if debug_changed or env_changed:
        console.print()
        console.print("[bold]Regenerating runners...[/bold]")
        runners = generator.generate_all_runners()
        for runner in runners:
            console.print(f"  [green]✓[/green] {runner.name}")
        if debug_changed:
            console.print(f"[dim]Log file: {config.get_log_path()}[/dim]")

    console.print()
```

**Step 3: Test manually**

Run: `hawk-hooks` → select "Config"
Expected:
- Menu shows with Rich.Live rendering
- No flickering on toggle
- Cursor stays in place
- Text editing works inline
- Back returns to main menu

**Step 4: Commit**

```bash
git add src/hawk_hooks/cli.py
git commit -m "refactor: replace questionary with rich_menu in config"
```

---

## Task 10: Update dependencies and cleanup

**Files:**
- Modify: `pyproject.toml:26-29`
- Delete: `test_menu.py` (if created)

**Step 1: Make questionary optional**

Since questionary is still used elsewhere in cli.py, keep it for now:
```toml
dependencies = [
    "questionary>=2.0.0",
    "rich>=13.0.0",
    "readchar>=4.0.0",
]
```

**Step 2: Clean up test file**

```bash
rm test_menu.py
```

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: cleanup test files"
```

---

## Task 11: Polish and document

**Files:**
- Modify: `src/hawk_hooks/rich_menu.py` (add docstrings)

**Step 1: Add module docstring**

Update top of `rich_menu.py`:
```python
"""Rich.Live-based interactive menu system.

A single-file, reusable menu library for building flicker-free CLI menus.

Example:
    from hawk_hooks.rich_menu import InteractiveList, Item

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
```

**Step 2: Add class docstrings**

Ensure all classes have docstrings explaining their purpose.

**Step 3: Test full workflow**

Manual test:
1. Run `hawk-hooks`
2. Select "Config"
3. Toggle several options
4. Edit a text field
5. Select "Back"
6. Verify changes persisted

**Step 4: Commit**

```bash
git add src/hawk_hooks/rich_menu.py
git commit -m "docs: add docstrings to rich_menu module"
```

---

## Task 12: Final verification

**Files:**
- None (testing only)

**Step 1: Full integration test**

Test checklist:
- [ ] Menu renders without flicker
- [ ] Cursor position preserved after toggle
- [ ] j/k and arrow keys work
- [ ] Enter and Space both work
- [ ] Text editing shows cursor
- [ ] Backspace works in text editing
- [ ] Esc cancels text editing
- [ ] Enter commits text changes
- [ ] Separators are skipped
- [ ] Action items exit menu
- [ ] Changes persist after save

**Step 2: Document any issues**

If bugs found, create follow-up tasks.

**Step 3: Ready for review**

Run: `git log --oneline`
Expected: ~12 commits implementing the feature

---

## Success Criteria

- ✅ `src/hawk_hooks/rich_menu.py` created (~250-300 lines)
- ✅ No screen flickering when toggling items
- ✅ Cursor stays in place after interactions
- ✅ Inline text editing works smoothly
- ✅ Config menu uses Rich.Live instead of questionary
- ✅ Module is reusable (single file, clean API)

## Next Steps

After this plan is complete:
1. Test thoroughly in real usage
2. Consider replacing other questionary menus in cli.py
3. Extract to separate package if needed for pyafk
