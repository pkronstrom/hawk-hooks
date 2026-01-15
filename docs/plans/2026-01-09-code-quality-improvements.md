# Code Quality Improvements

Identified improvements to make hawk-hooks more Pythonic, DRY, and maintainable.

## Issue #1: Unify Event Definitions

**Current state:** Event metadata split across two files with duplication.

```python
# events.py
EVENT_INFO = {
    "pre_tool_use": ("PreToolUse", "Before each tool is executed"),
}

# installer.py
CLAUDE_EVENTS = {
    "pre_tool_use": {
        "claude_event": "PreToolUse",  # Duplicated!
        "matchers": ["Edit|Write|MultiEdit", "Bash"],
    },
}
```

**Solution:** Single `EventDefinition` dataclass:

```python
@dataclass(frozen=True)
class EventDefinition:
    name: str                         # "pre_tool_use"
    claude_name: str                  # "PreToolUse"
    description: str                  # "Before each tool is executed"
    matchers: tuple[str | None, ...]  # ("Edit|Write|MultiEdit", "Bash")

EVENTS = {
    "pre_tool_use": EventDefinition(
        name="pre_tool_use",
        claude_name="PreToolUse",
        description="Before each tool is executed",
        matchers=("Edit|Write|MultiEdit", "Bash"),
    ),
    # ...
}
```

**Files affected:** `events.py`, `installer.py`, all consumers of EVENT_INFO/CLAUDE_EVENTS

---

## Issue #2: Scope Terminology Inconsistency

**Current state:** "global" and "user" mean the same thing but use different strings.

```python
# generator.py
def generate_all_runners(scope: str = "global", ...)

# installer.py
def sync_prompt_hooks(scope: str = "user", ...)

# HookManager mixes them:
generator.generate_all_runners(scope="global")
installer.sync_prompt_hooks(scope="user")  # Different string!
```

**Solution:** Use an Enum:

```python
from enum import Enum

class Scope(str, Enum):
    USER = "user"       # ~/.config/hawk-hooks/ and ~/.claude/settings.json
    PROJECT = "project" # .claude/hawk-hooks/ and .claude/settings.json

    @property
    def is_global(self) -> bool:
        return self == Scope.USER
```

**Files affected:** `config.py`, `generator.py`, `installer.py`, `hook_manager.py`, `interactive.py`, `cli.py`

---

## Issue #3: Hook Type as Magic String

**Current state:** Hook types are magic strings with property wrappers.

```python
hook_type: str  # "command", "stdout", or "prompt"

@property
def is_stdout(self) -> bool:
    return self.hook_type == "stdout"
```

**Solution:** Use an Enum:

```python
from enum import Enum, auto

class HookType(Enum):
    COMMAND = auto()  # .py, .sh, .js, .ts
    STDOUT = auto()   # .stdout.md
    PROMPT = auto()   # .prompt.json

@dataclass
class HookInfo:
    hook_type: HookType  # Now typed!

    @property
    def is_stdout(self) -> bool:
        return self.hook_type == HookType.STDOUT
```

**Files affected:** `scanner.py`, `generator.py`, `installer.py`

---

## Issue #4: Repeated Key Handling Pattern

**Current state:** Same key-checking logic repeated 5+ times.

```python
# Repeated everywhere:
if key == readchar.key.ENTER or key == "\r" or key == "\n":
    break

is_escape = key == readchar.key.ESC or key == "\x1b" or key == "\x1b\x1b"
```

**Solution:** Create `rich_menu/keys.py`:

```python
import readchar

def is_enter(key: str) -> bool:
    return key in (readchar.key.ENTER, "\r", "\n")

def is_exit(key: str) -> bool:
    return key.lower() == "q" or is_escape(key)

def is_escape(key: str) -> bool:
    return key in (readchar.key.ESC, "\x1b", "\x1b\x1b")

def is_up(key: str) -> bool:
    return key.lower() == "k" or key == readchar.key.UP

def is_down(key: str) -> bool:
    return key.lower() == "j" or key == readchar.key.DOWN
```

**Files affected:** `rich_menu/keys.py` (new), `rich_menu/menu.py`, `interactive.py`

---

## Issue #5: Long Methods Need Extraction

**Current state:** Methods with 100-170 lines mixing multiple concerns.

| Method | Lines | Responsibilities |
|--------|-------|------------------|
| `show_status()` | 170 | Load data, format output, handle scrolling, handle input |
| `interactive_toggle()` | 160 | Scope selection, build menu, save changes, show result |
| `install_deps()` | 100 | Venv creation, Python deps, shell tools, Node deps |

**Solution:** Extract into focused functions:

```python
# Before
def show_status():
    # 170 lines of mixed concerns...

# After
def _gather_status_data() -> StatusData:
    """Gather all status information."""
    ...

def _render_status(data: StatusData, console: Console) -> str:
    """Render status data to string (pure function, testable)."""
    ...

def _display_with_scroll(content: str, console: Console) -> None:
    """Display content with optional scrolling (reusable)."""
    ...

def show_status():
    console.clear()
    data = _gather_status_data()
    content = _render_status(data, console)
    _display_with_scroll(content, console)
```

**Files affected:** `interactive.py`

---

## Issue #6: Repeated Config Loading

**Current state:** Config loaded from disk multiple times in same operation.

```python
# generator.py - generate_runner() calls:
cfg = config.load_config()  # Load 1

# _get_env_exports() also calls:
cfg = config.load_config()  # Load 2

# _get_debug_snippets() also calls:
cfg = config.load_config()  # Load 3
```

**Solution:** Pass config explicitly:

```python
def generate_runner(event: str, enabled_hooks: list[str], cfg: dict | None = None):
    if cfg is None:
        cfg = config.load_config()
    env_exports = _get_env_exports(cfg)
    debug = _get_debug_snippets(event, cfg)
```

**Files affected:** `generator.py`

---

## Issue #7: CheckboxItem.render() Too Complex

**Current state:** 65-line method with nested conditionals.

**Solution:** Extract helper methods:

```python
@dataclass
class CheckboxItem(MenuItem):
    def _get_checkbox_icon(self, theme: Theme) -> str:
        if self.checked:
            return f"[{theme.checked_color}]{theme.checked_icon}[/{theme.checked_color}]"
        return f"[{theme.unchecked_color}]{theme.unchecked_icon}[/{theme.unchecked_color}]"

    def _get_change_indicator(self, theme: Theme) -> str:
        if self.checked != self.original_checked:
            return f" [{theme.warning_color}]{theme.change_icon}[/{theme.warning_color}]"
        return ""

    def _render_label(self, name: str, theme: Theme) -> str:
        indicator = self._get_change_indicator(theme)
        if self.checked:
            return f"[{theme.checked_color}]{name}[/{theme.checked_color}]{indicator}"
        return f"[strike {theme.unchecked_color} {theme.dim_color}]{name}[/]{indicator}"

    def render(self, is_selected: bool, is_editing: bool, theme: Theme) -> str:
        checkbox = self._get_checkbox_icon(theme)
        if " - " in self.label:
            name, desc = self.label.split(" - ", 1)
            return f"{checkbox} {self._render_label(name, theme)} - {self._render_desc(desc, theme)}"
        return f"{checkbox} {self._render_label(self.label, theme)}"
```

**Files affected:** `rich_menu/components.py`

---

## Issue #8: Eager Template Evaluation

**Current state:** `_get_ts_template()` called on every `get_template()` call.

```python
def get_template(extension: str) -> str:
    templates = {
        ".py": PYTHON_TEMPLATE,
        ".ts": _get_ts_template(),  # Called even for .py requests!
    }
    return templates.get(extension, "")
```

**Solution:** Lazy evaluation:

```python
_STATIC_TEMPLATES = {
    ".py": PYTHON_TEMPLATE,
    ".sh": SHELL_TEMPLATE,
    ".js": NODE_TEMPLATE,
}

_DYNAMIC_TEMPLATES = {
    ".ts": _get_ts_template,  # Function reference, not call
}

def get_template(extension: str) -> str:
    if extension in _STATIC_TEMPLATES:
        return _STATIC_TEMPLATES[extension]
    if extension in _DYNAMIC_TEMPLATES:
        return _DYNAMIC_TEMPLATES[extension]()
    return ""
```

**Files affected:** `templates.py`

---

## Issue #9: Bare Exception Handling

**Current state:** Some exception handlers are too broad.

```python
# generator.py:38
except Exception:
    os.close(fd)
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
    raise

# scanner.py:130
except Exception:
    pass  # Silently swallows ALL errors including programming bugs
```

**Solution:** Be specific about what you're catching:

```python
# generator.py - this one is actually OK (re-raises), but could be more specific
except (OSError, IOError):
    ...

# scanner.py - should at minimum log or be specific
except (OSError, UnicodeDecodeError) as e:
    logger.debug(f"Failed to parse metadata from {path}: {e}")
```

**Files affected:** `generator.py`, `scanner.py`

---

## Issue #10: Raw Dicts Instead of Typed Results

**Current state:** Functions return untyped dictionaries.

```python
def get_status(...) -> dict[str, Any]:
    return {
        "user": {"path": str, "installed": bool},
        "project": {"path": str, "installed": bool},
    }
```

**Solution:** Use dataclasses for structured returns:

```python
@dataclass
class InstallStatus:
    path: str
    installed: bool

@dataclass
class StatusResult:
    user: InstallStatus
    project: InstallStatus

def get_status(...) -> StatusResult:
    return StatusResult(
        user=InstallStatus(path=str(user_path), installed=has_our_hooks(user_settings)),
        project=InstallStatus(path=str(project_path), installed=has_our_hooks(project_settings)),
    )
```

Benefits: IDE autocomplete, type checking, self-documenting.

**Files affected:** `installer.py`, `hook_manager.py`

---

## Issue #11: Global Console Instance

**Current state:** Console is a module-level global.

```python
# interactive.py line 22
console = Console()  # Global

def show_status():
    console.clear()  # Uses global - hard to test
```

**Solution:** Pass console as parameter with default:

```python
def show_status(console: Console | None = None):
    if console is None:
        console = Console()
    console.clear()
```

Or use a simple factory:

```python
def _get_console() -> Console:
    """Get or create console instance. Override in tests."""
    return Console()

# In tests:
interactive._get_console = lambda: mock_console
```

**Files affected:** `interactive.py`

---

## Issue #12: Magic Numbers and Constants

**Current state:** Hardcoded values scattered throughout code.

```python
# interactive.py
width=100,                    # Panel width
console.print("─" * 50)       # Divider (repeated 3x)
timeout=120,                  # Venv creation timeout
timeout=300,                  # Pip install timeout

# scanner.py
lines[:20]                    # Metadata scan limit
MAX_ENV_VALUE_LENGTH = 1000   # Already a constant, good

# installer.py
MAX_PROMPT_LENGTH = 10000     # Already a constant, good
```

**Solution:**

A. User-configurable values go in config:

```python
# config.py
DEFAULT_CONFIG = {
    "enabled": {...},
    "debug": False,
    "env": {},
    # New configurable settings:
    "timeouts": {
        "venv_creation": 120,
        "pip_install": 300,
        "npm_install": 300,
    },
    "ui": {
        "panel_width": 100,
    },
}
```

B. Internal constants go in a constants module or at module top:

```python
# constants.py (new) or top of each module
DIVIDER = "─"
DIVIDER_WIDTH = 50
METADATA_SCAN_LINES = 20

# Usage:
console.print(DIVIDER * DIVIDER_WIDTH)
```

**Files affected:** `config.py`, `interactive.py`, `scanner.py`, possibly new `constants.py`

---

## Issue #13: HOOKS_DOC Duplicates Event Info

**Current state:** `templates.py` has `HOOKS_DOC` with event descriptions that duplicate `events.py`.

```python
# templates.py
HOOKS_DOC = '''# Captain-Hook Reference
...
### pre_tool_use
Runs before tool execution. Can block.
Fields: session_id, cwd, tool_name, tool_input, tool_use_id
...
'''

# events.py
EVENT_INFO = {
    "pre_tool_use": ("PreToolUse", "Before each tool is executed"),
}
```

**Solution:** Generate HOOKS_DOC from EVENT_INFO or create richer event metadata:

```python
# events.py - extend EventDefinition
@dataclass(frozen=True)
class EventDefinition:
    name: str
    claude_name: str
    description: str
    matchers: tuple[str | None, ...]
    fields: tuple[str, ...]  # ("session_id", "cwd", "tool_name", ...)
    can_block: bool = False

# templates.py - generate docs
def generate_hooks_doc() -> str:
    lines = ["# Captain-Hook Reference\n"]
    for event in EVENTS.values():
        lines.append(f"### {event.name}")
        lines.append(event.description)
        if event.can_block:
            lines.append("Can block.")
        lines.append(f"Fields: {', '.join(event.fields)}")
    return "\n".join(lines)
```

**Files affected:** `events.py`, `templates.py`

---

## Issue #14: Dead Code - Unused Functions

**Current state:** Several functions are defined but never called.

### config.py - 4 unused functions

```python
def is_debug_enabled() -> bool:        # Never called
def is_hook_enabled(...) -> bool:      # Never called
def get_env_var(...) -> str:           # Never called
def set_env_var(...) -> None:          # Never called
```

### scanner.py - 1 unused function

```python
def get_hook_by_name(event: str, name: str) -> HookInfo | None:  # Never called
```

### generator.py - 1 unused function

```python
def _make_executable(path: Path) -> None:  # Never called (atomic write handles this)
```

### hook_manager.py - 3 unused methods

```python
def find_hook_with_event(self, name: str) -> tuple[str, HookInfo] | None:  # Never called
def get_all_enabled(self) -> dict[str, list[str]]:                          # Never called
def get_changes_summary(self, original, current) -> dict:                   # Never called
```

### interactive.py - 1 unused import

```python
from .events import EVENT_INFO, EVENTS, get_event_display
#                   ^^^^^^^^^^  - imported but never used (only get_event_display is used)
```

**Solution:** Either remove these functions or document them as public API for external use.

- **Remove:** `_make_executable` (redundant), unused imports
- **Keep if public API:** `is_hook_enabled`, `get_env_var`, `set_env_var`, `get_hook_by_name` (useful for scripts/plugins)
- **Decide:** HookManager helper methods - were they planned for future use?

**Files affected:** `config.py`, `scanner.py`, `generator.py`, `hook_manager.py`, `interactive.py`

---

## Implementation Priority

| Priority | Issue | Impact | Effort |
|----------|-------|--------|--------|
| 1 | #2 Scope Enum | Prevents bugs | Low |
| 2 | #1 Unify Events | DRY, single source of truth | Medium |
| 3 | #3 HookType Enum | Type safety | Low |
| 4 | #4 Key helpers | DRY, readability | Low |
| 5 | #14 Dead code | Cleanliness | Low |
| 6 | #6 Config passing | Performance, consistency | Low |
| 7 | #8 Lazy templates | Performance | Low |
| 8 | #9 Exception handling | Debuggability | Low |
| 9 | #10 Typed results | Type safety, IDE support | Medium |
| 10 | #11 Global console | Testability | Low |
| 11 | #12 Magic numbers | Configurability, DRY | Low |
| 12 | #13 HOOKS_DOC duplication | DRY, maintainability | Medium |
| 13 | #7 CheckboxItem | Readability, testability | Medium |
| 14 | #5 Long methods | Testability, maintainability | High |
