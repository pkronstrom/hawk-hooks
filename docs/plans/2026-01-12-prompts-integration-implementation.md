# Prompts Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add unified prompt/agent management to captain-hook with frontmatter-based multi-tool targeting and symlink syncing.

**Architecture:** New modules for frontmatter parsing (`frontmatter.py`), prompt/agent scanning (`prompt_scanner.py`), symlink syncing (`sync.py`), and event mapping (`event_mapping.py`). Updates to config, types, and interactive modules for new data structures and menus.

**Tech Stack:** Python 3.10+, PyYAML for frontmatter parsing, existing Rich/questionary for UI.

---

## Task 1: Add PyYAML Dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add pyyaml to dependencies**

Edit `pyproject.toml` dependencies section:

```toml
dependencies = [
    "rich>=13.0.0",
    "questionary>=2.0.0",
    "rich-menu>=0.1.0",
    "pyyaml>=6.0",
]
```

**Step 2: Install updated dependencies**

Run: `~/.config/captain-hook/.venv/bin/pip install -e .`
Expected: Successfully installed pyyaml

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pyyaml dependency for frontmatter parsing"
```

---

## Task 2: Create Event Mapping Module

**Files:**
- Create: `src/captain_hook/event_mapping.py`
- Create: `tests/test_event_mapping.py`

**Step 1: Write the failing test**

```python
# tests/test_event_mapping.py
"""Tests for event mapping between tools."""

import pytest
from captain_hook.event_mapping import (
    CANONICAL_EVENTS,
    get_tool_event,
    get_canonical_event,
    is_tool_specific_event,
)


class TestCanonicalEvents:
    """Test canonical event definitions."""

    def test_pre_tool_maps_to_claude(self):
        assert get_tool_event("pre_tool", "claude") == "pre_tool_use"

    def test_pre_tool_maps_to_gemini(self):
        assert get_tool_event("pre_tool", "gemini") == "BeforeTool"

    def test_post_tool_maps_to_claude(self):
        assert get_tool_event("post_tool", "claude") == "post_tool_use"

    def test_post_tool_maps_to_gemini(self):
        assert get_tool_event("post_tool", "gemini") == "AfterTool"

    def test_session_start_maps_correctly(self):
        assert get_tool_event("session_start", "claude") == "session_start"
        assert get_tool_event("session_start", "gemini") == "SessionStart"

    def test_unknown_tool_returns_canonical(self):
        assert get_tool_event("pre_tool", "unknown") == "pre_tool"


class TestToolSpecificEvents:
    """Test tool-specific event handling."""

    def test_user_prompt_submit_is_claude_specific(self):
        assert is_tool_specific_event("user_prompt_submit", "claude") is True
        assert is_tool_specific_event("user_prompt_submit", "gemini") is False

    def test_before_model_is_gemini_specific(self):
        assert is_tool_specific_event("BeforeModel", "gemini") is True
        assert is_tool_specific_event("BeforeModel", "claude") is False

    def test_canonical_events_are_not_tool_specific(self):
        assert is_tool_specific_event("pre_tool", "claude") is False


class TestReverseMapping:
    """Test getting canonical from tool-specific."""

    def test_pre_tool_use_to_canonical(self):
        assert get_canonical_event("pre_tool_use") == "pre_tool"

    def test_before_tool_to_canonical(self):
        assert get_canonical_event("BeforeTool") == "pre_tool"

    def test_canonical_stays_canonical(self):
        assert get_canonical_event("pre_tool") == "pre_tool"

    def test_tool_specific_stays_as_is(self):
        assert get_canonical_event("user_prompt_submit") == "user_prompt_submit"
```

**Step 2: Run test to verify it fails**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_event_mapping.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'captain_hook.event_mapping'"

**Step 3: Write minimal implementation**

```python
# src/captain_hook/event_mapping.py
"""Canonical event mapping between AI coding tools.

Maps canonical event names to tool-specific events:
- pre_tool -> pre_tool_use (Claude), BeforeTool (Gemini)
- post_tool -> post_tool_use (Claude), AfterTool (Gemini)
- etc.

Tool-specific events (user_prompt_submit, BeforeModel) pass through as-is
and are skipped for unsupported tools.
"""

from __future__ import annotations

# Canonical event -> tool-specific mapping
CANONICAL_EVENTS: dict[str, dict[str, str]] = {
    "pre_tool": {
        "claude": "pre_tool_use",
        "gemini": "BeforeTool",
        "codex": "pre_tool",  # TBD
    },
    "post_tool": {
        "claude": "post_tool_use",
        "gemini": "AfterTool",
        "codex": "post_tool",  # TBD
    },
    "stop": {
        "claude": "stop",
        "gemini": "AfterAgent",
        "codex": "stop",  # TBD
    },
    "notification": {
        "claude": "notification",
        "gemini": "Notification",
        "codex": "notification",  # TBD
    },
    "session_start": {
        "claude": "session_start",
        "gemini": "SessionStart",
        "codex": "session_start",  # TBD
    },
    "session_end": {
        "claude": "session_end",
        "gemini": "SessionEnd",
        "codex": "session_end",  # TBD
    },
    "pre_compact": {
        "claude": "pre_compact",
        "gemini": "PreCompress",
        "codex": "pre_compact",  # TBD
    },
}

# Tool-specific events (not in canonical mapping)
TOOL_SPECIFIC_EVENTS: dict[str, list[str]] = {
    "claude": ["user_prompt_submit", "subagent_stop"],
    "gemini": ["BeforeModel", "AfterModel", "BeforeToolSelection"],
    "codex": [],
}

# Reverse mapping: tool-specific -> canonical
_REVERSE_MAPPING: dict[str, str] = {}
for canonical, tools in CANONICAL_EVENTS.items():
    for tool, specific in tools.items():
        _REVERSE_MAPPING[specific] = canonical


def get_tool_event(canonical: str, tool: str) -> str:
    """Get the tool-specific event name for a canonical event.

    Args:
        canonical: Canonical event name (e.g., "pre_tool")
        tool: Tool name ("claude", "gemini", "codex")

    Returns:
        Tool-specific event name, or canonical if not mapped.
    """
    if canonical in CANONICAL_EVENTS:
        return CANONICAL_EVENTS[canonical].get(tool, canonical)
    # Pass through tool-specific events as-is
    return canonical


def get_canonical_event(event: str) -> str:
    """Get the canonical event name from a tool-specific event.

    Args:
        event: Tool-specific or canonical event name.

    Returns:
        Canonical event name, or event as-is if not found.
    """
    return _REVERSE_MAPPING.get(event, event)


def is_tool_specific_event(event: str, tool: str) -> bool:
    """Check if an event is specific to a tool (not canonical).

    Args:
        event: Event name to check.
        tool: Tool to check support for.

    Returns:
        True if the event is tool-specific and supported by the tool.
    """
    # If it's a canonical event, it's not tool-specific
    if event in CANONICAL_EVENTS:
        return False
    # If it's in the tool's specific events, it's supported
    if event in TOOL_SPECIFIC_EVENTS.get(tool, []):
        return True
    # If it's in another tool's specific events, it's not supported
    for other_tool, events in TOOL_SPECIFIC_EVENTS.items():
        if event in events and other_tool != tool:
            return False
    return False


def is_event_supported(event: str, tool: str) -> bool:
    """Check if an event is supported by a tool.

    Args:
        event: Event name (canonical or tool-specific).
        tool: Tool to check.

    Returns:
        True if the tool supports this event.
    """
    # Canonical events are supported by all tools
    if event in CANONICAL_EVENTS:
        return True
    # Tool-specific events are only supported by their tool
    return event in TOOL_SPECIFIC_EVENTS.get(tool, [])
```

**Step 4: Run test to verify it passes**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_event_mapping.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/captain_hook/event_mapping.py tests/test_event_mapping.py
git commit -m "feat: add event mapping module for multi-tool support"
```

---

## Task 3: Create Frontmatter Parser

**Files:**
- Create: `src/captain_hook/frontmatter.py`
- Create: `tests/test_frontmatter.py`

**Step 1: Write the failing test**

```python
# tests/test_frontmatter.py
"""Tests for frontmatter parsing."""

import pytest
from captain_hook.frontmatter import parse_frontmatter, PromptFrontmatter


class TestParseFrontmatter:
    """Test frontmatter parsing from markdown content."""

    def test_parse_basic_frontmatter(self):
        content = """---
name: my-command
description: A test command
tools: [claude]
---

Command content here.
"""
        fm, body = parse_frontmatter(content)
        assert fm.name == "my-command"
        assert fm.description == "A test command"
        assert fm.tools == ["claude"]
        assert fm.hooks == []
        assert body.strip() == "Command content here."

    def test_parse_tools_all_shorthand(self):
        content = """---
name: universal
description: Works everywhere
tools: all
---
Content.
"""
        fm, body = parse_frontmatter(content)
        assert fm.tools == ["claude", "gemini", "codex"]

    def test_parse_with_hooks(self):
        content = """---
name: my-guard
description: Guards dangerous operations
tools: [claude, gemini]
hooks:
  - event: pre_tool
    matchers: [Bash, Edit]
  - session_start
---
Content.
"""
        fm, body = parse_frontmatter(content)
        assert len(fm.hooks) == 2
        assert fm.hooks[0].event == "pre_tool"
        assert fm.hooks[0].matchers == ["Bash", "Edit"]
        assert fm.hooks[1].event == "session_start"
        assert fm.hooks[1].matchers == []

    def test_parse_no_frontmatter(self):
        content = "Just plain content without frontmatter."
        fm, body = parse_frontmatter(content)
        assert fm is None
        assert body == content

    def test_parse_empty_frontmatter(self):
        content = """---
---
Content only.
"""
        fm, body = parse_frontmatter(content)
        assert fm is None
        assert body.strip() == "Content only."

    def test_missing_required_fields(self):
        content = """---
name: incomplete
---
Content.
"""
        with pytest.raises(ValueError, match="Missing required field"):
            parse_frontmatter(content)


class TestPromptFrontmatter:
    """Test PromptFrontmatter dataclass."""

    def test_has_hooks(self):
        fm = PromptFrontmatter(
            name="test",
            description="Test",
            tools=["claude"],
            hooks=[],
        )
        assert fm.has_hooks is False

    def test_has_hooks_with_hooks(self):
        from captain_hook.frontmatter import HookConfig
        fm = PromptFrontmatter(
            name="test",
            description="Test",
            tools=["claude"],
            hooks=[HookConfig(event="pre_tool", matchers=[])],
        )
        assert fm.has_hooks is True
```

**Step 2: Run test to verify it fails**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_frontmatter.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/captain_hook/frontmatter.py
"""Frontmatter parsing for prompts and agents.

Parses YAML frontmatter from markdown files:
---
name: my-command
description: A description
tools: [claude, gemini]
hooks:
  - event: pre_tool
    matchers: [Bash]
---
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

# All supported tools
ALL_TOOLS = ["claude", "gemini", "codex"]

# Frontmatter regex: matches --- at start, content, ---
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass
class HookConfig:
    """Configuration for a hook registration."""

    event: str
    matchers: list[str] = field(default_factory=list)


@dataclass
class PromptFrontmatter:
    """Parsed frontmatter from a prompt/agent file."""

    name: str
    description: str
    tools: list[str]
    hooks: list[HookConfig] = field(default_factory=list)

    @property
    def has_hooks(self) -> bool:
        """Check if this prompt has any hook registrations."""
        return len(self.hooks) > 0


def parse_frontmatter(content: str) -> tuple[PromptFrontmatter | None, str]:
    """Parse frontmatter from markdown content.

    Args:
        content: Full file content with potential frontmatter.

    Returns:
        Tuple of (parsed frontmatter or None, body content).

    Raises:
        ValueError: If frontmatter exists but is invalid.
    """
    match = FRONTMATTER_RE.match(content)
    if not match:
        return None, content

    yaml_content = match.group(1)
    body = content[match.end() :]

    # Parse YAML
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in frontmatter: {e}")

    if not data:
        return None, body

    # Validate required fields
    if "name" not in data:
        raise ValueError("Missing required field: name")
    if "description" not in data:
        raise ValueError("Missing required field: description")
    if "tools" not in data:
        raise ValueError("Missing required field: tools")

    # Parse tools
    tools = data["tools"]
    if tools == "all":
        tools = ALL_TOOLS.copy()
    elif isinstance(tools, str):
        tools = [tools]

    # Parse hooks
    hooks = []
    for hook_data in data.get("hooks", []):
        if isinstance(hook_data, str):
            # Shorthand: just event name
            hooks.append(HookConfig(event=hook_data, matchers=[]))
        elif isinstance(hook_data, dict):
            hooks.append(
                HookConfig(
                    event=hook_data.get("event", ""),
                    matchers=hook_data.get("matchers", []),
                )
            )

    return (
        PromptFrontmatter(
            name=data["name"],
            description=data["description"],
            tools=tools,
            hooks=hooks,
        ),
        body,
    )


def parse_file(path: str) -> tuple[PromptFrontmatter | None, str]:
    """Parse frontmatter from a file path.

    Args:
        path: Path to the markdown file.

    Returns:
        Tuple of (parsed frontmatter or None, body content).
    """
    from pathlib import Path

    content = Path(path).read_text()
    return parse_frontmatter(content)
```

**Step 4: Run test to verify it passes**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_frontmatter.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/captain_hook/frontmatter.py tests/test_frontmatter.py
git commit -m "feat: add frontmatter parser for prompts/agents"
```

---

## Task 4: Update Types Module

**Files:**
- Modify: `src/captain_hook/types.py`
- Modify: `tests/test_cli.py` (add type tests)

**Step 1: Write the failing test**

Add to existing test file or create `tests/test_types.py`:

```python
# tests/test_types.py
"""Tests for type definitions."""

import pytest
from captain_hook.types import PromptInfo, PromptType


class TestPromptType:
    """Test PromptType enum."""

    def test_command_type(self):
        assert PromptType.COMMAND.value == "command"

    def test_agent_type(self):
        assert PromptType.AGENT.value == "agent"

    def test_from_string(self):
        assert PromptType.from_string("command") == PromptType.COMMAND
        assert PromptType.from_string("agent") == PromptType.AGENT

    def test_from_string_invalid(self):
        with pytest.raises(ValueError):
            PromptType.from_string("invalid")


class TestPromptInfo:
    """Test PromptInfo dataclass."""

    def test_create_prompt_info(self):
        from pathlib import Path
        from captain_hook.frontmatter import PromptFrontmatter, HookConfig

        fm = PromptFrontmatter(
            name="test",
            description="A test",
            tools=["claude"],
            hooks=[HookConfig(event="pre_tool", matchers=["Bash"])],
        )
        info = PromptInfo(
            path=Path("/tmp/test.md"),
            frontmatter=fm,
            prompt_type=PromptType.COMMAND,
        )
        assert info.name == "test"
        assert info.has_hooks is True
        assert "claude" in info.tools
```

**Step 2: Run test to verify it fails**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_types.py -v`
Expected: FAIL with "ImportError"

**Step 3: Add new types to types.py**

Add to end of `src/captain_hook/types.py`:

```python
# Add after existing code

class PromptType(str, Enum):
    """Type of prompt file.

    COMMAND: Slash command (prompts/ directory)
    AGENT: Agent/persona (agents/ directory)
    """

    COMMAND = "command"
    AGENT = "agent"

    @classmethod
    def from_string(cls, value: str) -> "PromptType":
        """Create PromptType from string.

        Args:
            value: "command" or "agent"

        Returns:
            The corresponding PromptType enum value.

        Raises:
            ValueError: If value is not recognized.
        """
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"Invalid prompt type: {value!r}. Must be 'command' or 'agent'.")


@dataclass
class PromptInfo:
    """Information about a discovered prompt/agent.

    Attributes:
        path: Path to the source file.
        frontmatter: Parsed frontmatter data.
        prompt_type: Whether this is a command or agent.
    """

    path: "Path"
    frontmatter: "PromptFrontmatter"
    prompt_type: PromptType

    @property
    def name(self) -> str:
        """Get the prompt name from frontmatter."""
        return self.frontmatter.name

    @property
    def description(self) -> str:
        """Get the description from frontmatter."""
        return self.frontmatter.description

    @property
    def tools(self) -> list[str]:
        """Get target tools from frontmatter."""
        return self.frontmatter.tools

    @property
    def has_hooks(self) -> bool:
        """Check if this prompt has hook registrations."""
        return self.frontmatter.has_hooks

    @property
    def hooks(self) -> list:
        """Get hook configurations."""
        return self.frontmatter.hooks
```

Also add import at top:

```python
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .frontmatter import PromptFrontmatter
```

**Step 4: Run test to verify it passes**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_types.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/captain_hook/types.py tests/test_types.py
git commit -m "feat: add PromptType and PromptInfo types"
```

---

## Task 5: Update Config Module for Destinations

**Files:**
- Modify: `src/captain_hook/config.py`
- Create: `tests/test_config_destinations.py`

**Step 1: Write the failing test**

```python
# tests/test_config_destinations.py
"""Tests for destination configuration."""

import pytest
from captain_hook import config


class TestDestinations:
    """Test destination path management."""

    def test_default_destinations(self):
        dests = config.get_default_destinations()
        assert "claude" in dests
        assert "gemini" in dests
        assert "codex" in dests
        assert dests["claude"]["commands"] == "~/.claude/commands/"

    def test_get_destination(self, tmp_path, monkeypatch):
        # Use temp config
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        dest = config.get_destination("claude", "commands")
        assert "/.claude/commands" in dest

    def test_set_destination(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        config.set_destination("claude", "commands", "/custom/path/")
        dest = config.get_destination("claude", "commands")
        assert dest == "/custom/path/"


class TestPromptsConfig:
    """Test prompts/agents enabled state management."""

    def test_prompts_default_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        prompts = config.get_prompts_config()
        assert prompts == {}

    def test_set_prompt_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        config.set_prompt_enabled("my-command", True, hook_enabled=False)
        prompts = config.get_prompts_config()
        assert prompts["my-command"]["enabled"] is True
        assert prompts["my-command"]["hook_enabled"] is False

    def test_is_prompt_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        config.set_prompt_enabled("test", True)
        assert config.is_prompt_enabled("test") is True
        assert config.is_prompt_enabled("nonexistent") is False


class TestAgentsConfig:
    """Test agents enabled state management."""

    def test_agents_default_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        agents = config.get_agents_config()
        assert agents == {}

    def test_set_agent_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
        config.ensure_dirs()

        config.set_agent_enabled("code-reviewer", True, hook_enabled=True)
        agents = config.get_agents_config()
        assert agents["code-reviewer"]["enabled"] is True
        assert agents["code-reviewer"]["hook_enabled"] is True
```

**Step 2: Run test to verify it fails**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_config_destinations.py -v`
Expected: FAIL with "AttributeError"

**Step 3: Add destination and prompt config functions**

Add to `src/captain_hook/config.py`:

```python
# Add to DEFAULT_CONFIG
DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": {event: [] for event in EVENTS},
    "projects": [],
    "debug": False,
    "env": {},
    "destinations": {
        "claude": {
            "commands": "~/.claude/commands/",
            "agents": "~/.claude/agents/",
        },
        "gemini": {
            "commands": "~/.gemini/commands/",
            "agents": "~/.gemini/agents/",
        },
        "codex": {
            "commands": "~/.codex/prompts/",
            "agents": "~/.codex/agents/",
        },
    },
    "prompts": {},
    "agents": {},
}


def get_prompts_dir() -> Path:
    """Get the path to the prompts directory."""
    return get_config_dir() / "prompts"


def get_agents_dir() -> Path:
    """Get the path to the agents directory."""
    return get_config_dir() / "agents"


def get_default_destinations() -> dict[str, dict[str, str]]:
    """Get default destination paths."""
    return DEFAULT_CONFIG["destinations"].copy()


def get_destination(tool: str, item_type: str) -> str:
    """Get destination path for a tool and type.

    Args:
        tool: "claude", "gemini", or "codex"
        item_type: "commands" or "agents"

    Returns:
        Expanded destination path.
    """
    cfg = load_config()
    dests = cfg.get("destinations", DEFAULT_CONFIG["destinations"])
    path = dests.get(tool, {}).get(item_type, "")
    return os.path.expanduser(path)


def set_destination(tool: str, item_type: str, path: str) -> None:
    """Set destination path for a tool and type."""
    cfg = load_config()
    if "destinations" not in cfg:
        cfg["destinations"] = DEFAULT_CONFIG["destinations"].copy()
    if tool not in cfg["destinations"]:
        cfg["destinations"][tool] = {}
    cfg["destinations"][tool][item_type] = path
    save_config(cfg)


def get_prompts_config() -> dict[str, dict[str, bool]]:
    """Get prompts enabled configuration."""
    cfg = load_config()
    return cfg.get("prompts", {})


def set_prompt_enabled(name: str, enabled: bool, hook_enabled: bool = False) -> None:
    """Set prompt enabled state."""
    cfg = load_config()
    if "prompts" not in cfg:
        cfg["prompts"] = {}
    cfg["prompts"][name] = {"enabled": enabled, "hook_enabled": hook_enabled}
    save_config(cfg)


def is_prompt_enabled(name: str) -> bool:
    """Check if a prompt is enabled."""
    cfg = load_config()
    return cfg.get("prompts", {}).get(name, {}).get("enabled", False)


def is_prompt_hook_enabled(name: str) -> bool:
    """Check if a prompt's hook is enabled."""
    cfg = load_config()
    return cfg.get("prompts", {}).get(name, {}).get("hook_enabled", False)


def get_agents_config() -> dict[str, dict[str, bool]]:
    """Get agents enabled configuration."""
    cfg = load_config()
    return cfg.get("agents", {})


def set_agent_enabled(name: str, enabled: bool, hook_enabled: bool = False) -> None:
    """Set agent enabled state."""
    cfg = load_config()
    if "agents" not in cfg:
        cfg["agents"] = {}
    cfg["agents"][name] = {"enabled": enabled, "hook_enabled": hook_enabled}
    save_config(cfg)


def is_agent_enabled(name: str) -> bool:
    """Check if an agent is enabled."""
    cfg = load_config()
    return cfg.get("agents", {}).get(name, {}).get("enabled", False)


def is_agent_hook_enabled(name: str) -> bool:
    """Check if an agent's hook is enabled."""
    cfg = load_config()
    return cfg.get("agents", {}).get(name, {}).get("hook_enabled", False)
```

Also update `ensure_dirs()`:

```python
def ensure_dirs() -> None:
    """Ensure all required directories exist."""
    get_config_dir().mkdir(parents=True, exist_ok=True)
    get_hooks_dir().mkdir(parents=True, exist_ok=True)
    get_runners_dir().mkdir(parents=True, exist_ok=True)
    get_docs_dir().mkdir(parents=True, exist_ok=True)
    get_prompts_dir().mkdir(parents=True, exist_ok=True)
    get_agents_dir().mkdir(parents=True, exist_ok=True)

    # Create event subdirectories
    for event in EVENTS:
        (get_hooks_dir() / event).mkdir(parents=True, exist_ok=True)
```

**Step 4: Run test to verify it passes**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_config_destinations.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/captain_hook/config.py tests/test_config_destinations.py
git commit -m "feat: add destination and prompt/agent config management"
```

---

## Task 6: Create Prompt Scanner Module

**Files:**
- Create: `src/captain_hook/prompt_scanner.py`
- Create: `tests/test_prompt_scanner.py`

**Step 1: Write the failing test**

```python
# tests/test_prompt_scanner.py
"""Tests for prompt/agent scanner."""

import pytest
from pathlib import Path
from captain_hook.prompt_scanner import scan_prompts, scan_agents, scan_all_prompts
from captain_hook.types import PromptType


@pytest.fixture
def prompts_dir(tmp_path):
    """Create a temporary prompts directory with test files."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()

    # Valid prompt
    (prompts / "test-command.md").write_text("""---
name: test-command
description: A test command
tools: [claude]
---
Command content.
""")

    # Prompt with hooks
    (prompts / "guard.md").write_text("""---
name: guard
description: A guard hook
tools: all
hooks:
  - event: pre_tool
    matchers: [Bash]
---
Guard content.
""")

    # Invalid (no frontmatter)
    (prompts / "no-frontmatter.md").write_text("Just content")

    return prompts


@pytest.fixture
def agents_dir(tmp_path):
    """Create a temporary agents directory."""
    agents = tmp_path / "agents"
    agents.mkdir()

    (agents / "reviewer.md").write_text("""---
name: code-reviewer
description: Reviews code
tools: [claude, gemini]
hooks:
  - session_start
---
You are a code reviewer...
""")

    return agents


class TestScanPrompts:
    """Test prompt scanning."""

    def test_scan_finds_valid_prompts(self, prompts_dir):
        results = scan_prompts(prompts_dir)
        names = [p.name for p in results]
        assert "test-command" in names
        assert "guard" in names

    def test_scan_skips_invalid_files(self, prompts_dir):
        results = scan_prompts(prompts_dir)
        names = [p.name for p in results]
        assert "no-frontmatter" not in names

    def test_scan_parses_hooks(self, prompts_dir):
        results = scan_prompts(prompts_dir)
        guard = next(p for p in results if p.name == "guard")
        assert guard.has_hooks is True
        assert guard.hooks[0].event == "pre_tool"

    def test_scan_sets_prompt_type(self, prompts_dir):
        results = scan_prompts(prompts_dir)
        for p in results:
            assert p.prompt_type == PromptType.COMMAND


class TestScanAgents:
    """Test agent scanning."""

    def test_scan_finds_agents(self, agents_dir):
        results = scan_agents(agents_dir)
        assert len(results) == 1
        assert results[0].name == "code-reviewer"

    def test_scan_sets_agent_type(self, agents_dir):
        results = scan_agents(agents_dir)
        assert results[0].prompt_type == PromptType.AGENT


class TestScanAll:
    """Test combined scanning."""

    def test_scan_all_returns_both(self, prompts_dir, agents_dir, monkeypatch):
        from captain_hook import config
        monkeypatch.setattr(config, "get_prompts_dir", lambda: prompts_dir)
        monkeypatch.setattr(config, "get_agents_dir", lambda: agents_dir)

        results = scan_all_prompts()
        types = {p.prompt_type for p in results}
        assert PromptType.COMMAND in types
        assert PromptType.AGENT in types
```

**Step 2: Run test to verify it fails**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_prompt_scanner.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implementation**

```python
# src/captain_hook/prompt_scanner.py
"""Scanner for prompts and agents directories.

Scans ~/.config/captain-hook/prompts/ and agents/ for markdown files
with valid frontmatter.
"""

from __future__ import annotations

from pathlib import Path

from . import config
from .frontmatter import parse_frontmatter
from .types import PromptInfo, PromptType


def scan_prompts(prompts_dir: Path | None = None) -> list[PromptInfo]:
    """Scan prompts directory for valid prompt files.

    Args:
        prompts_dir: Directory to scan. Defaults to config prompts dir.

    Returns:
        List of PromptInfo for valid prompts.
    """
    if prompts_dir is None:
        prompts_dir = config.get_prompts_dir()

    return _scan_directory(prompts_dir, PromptType.COMMAND)


def scan_agents(agents_dir: Path | None = None) -> list[PromptInfo]:
    """Scan agents directory for valid agent files.

    Args:
        agents_dir: Directory to scan. Defaults to config agents dir.

    Returns:
        List of PromptInfo for valid agents.
    """
    if agents_dir is None:
        agents_dir = config.get_agents_dir()

    return _scan_directory(agents_dir, PromptType.AGENT)


def scan_all_prompts() -> list[PromptInfo]:
    """Scan both prompts and agents directories.

    Returns:
        Combined list of all prompts and agents.
    """
    prompts = scan_prompts()
    agents = scan_agents()
    return prompts + agents


def _scan_directory(directory: Path, prompt_type: PromptType) -> list[PromptInfo]:
    """Scan a directory for markdown files with valid frontmatter.

    Args:
        directory: Directory to scan.
        prompt_type: Type to assign to found items.

    Returns:
        List of PromptInfo for valid files.
    """
    results: list[PromptInfo] = []

    if not directory.exists():
        return results

    for path in sorted(directory.iterdir()):
        # Only process .md files
        if not path.is_file() or path.suffix.lower() != ".md":
            continue

        try:
            content = path.read_text()
            frontmatter, _ = parse_frontmatter(content)

            if frontmatter is None:
                # No valid frontmatter, skip
                continue

            results.append(
                PromptInfo(
                    path=path,
                    frontmatter=frontmatter,
                    prompt_type=prompt_type,
                )
            )
        except (ValueError, OSError, UnicodeDecodeError):
            # Invalid file, skip silently
            continue

    return results


def get_prompt_by_name(name: str, prompt_type: PromptType | None = None) -> PromptInfo | None:
    """Get a specific prompt/agent by name.

    Args:
        name: Name to search for.
        prompt_type: Optional type filter.

    Returns:
        PromptInfo if found, None otherwise.
    """
    all_prompts = scan_all_prompts()
    for prompt in all_prompts:
        if prompt.name == name:
            if prompt_type is None or prompt.prompt_type == prompt_type:
                return prompt
    return None


def get_prompts_with_hooks() -> list[PromptInfo]:
    """Get all prompts/agents that have hook configurations.

    Returns:
        List of PromptInfo with has_hooks=True.
    """
    return [p for p in scan_all_prompts() if p.has_hooks]
```

**Step 4: Run test to verify it passes**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_prompt_scanner.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/captain_hook/prompt_scanner.py tests/test_prompt_scanner.py
git commit -m "feat: add prompt/agent scanner module"
```

---

## Task 7: Create Sync Module

**Files:**
- Create: `src/captain_hook/sync.py`
- Create: `tests/test_sync.py`

**Step 1: Write the failing test**

```python
# tests/test_sync.py
"""Tests for symlink sync module."""

import pytest
from pathlib import Path
from captain_hook.sync import (
    create_symlink,
    remove_symlink,
    generate_gemini_toml,
    sync_prompt,
    unsync_prompt,
)
from captain_hook.types import PromptInfo, PromptType
from captain_hook.frontmatter import PromptFrontmatter


@pytest.fixture
def prompt_info(tmp_path):
    """Create a test PromptInfo."""
    source = tmp_path / "source" / "test.md"
    source.parent.mkdir()
    source.write_text("""---
name: test-cmd
description: Test command
tools: [claude, gemini]
---
Test content.
""")
    return PromptInfo(
        path=source,
        frontmatter=PromptFrontmatter(
            name="test-cmd",
            description="Test command",
            tools=["claude", "gemini"],
            hooks=[],
        ),
        prompt_type=PromptType.COMMAND,
    )


class TestSymlinkOperations:
    """Test basic symlink operations."""

    def test_create_symlink(self, tmp_path):
        source = tmp_path / "source.md"
        source.write_text("content")
        dest = tmp_path / "dest" / "link.md"

        create_symlink(source, dest)
        assert dest.is_symlink()
        assert dest.resolve() == source.resolve()

    def test_create_symlink_overwrites(self, tmp_path):
        source = tmp_path / "source.md"
        source.write_text("content")
        dest = tmp_path / "dest" / "link.md"
        dest.parent.mkdir()
        dest.write_text("old")

        create_symlink(source, dest)
        assert dest.is_symlink()

    def test_remove_symlink(self, tmp_path):
        source = tmp_path / "source.md"
        source.write_text("content")
        dest = tmp_path / "link.md"
        dest.symlink_to(source)

        remove_symlink(dest)
        assert not dest.exists()

    def test_remove_symlink_nonexistent(self, tmp_path):
        # Should not raise
        remove_symlink(tmp_path / "nonexistent.md")


class TestGeminiToml:
    """Test Gemini TOML generation."""

    def test_generate_toml(self, prompt_info):
        toml = generate_gemini_toml(prompt_info)
        assert "name = \"test-cmd\"" in toml
        assert "description = \"Test command\"" in toml
        assert "Test content." in toml


class TestSyncPrompt:
    """Test prompt syncing."""

    def test_sync_creates_claude_symlink(self, prompt_info, tmp_path, monkeypatch):
        from captain_hook import config
        claude_dest = tmp_path / "claude" / "commands"
        claude_dest.mkdir(parents=True)
        monkeypatch.setattr(
            config, "get_destination",
            lambda tool, item_type: str(claude_dest) if tool == "claude" else str(tmp_path / "other")
        )

        sync_prompt(prompt_info, ["claude"])
        expected = claude_dest / "test-cmd.md"
        assert expected.is_symlink()

    def test_sync_creates_gemini_toml(self, prompt_info, tmp_path, monkeypatch):
        from captain_hook import config
        gemini_dest = tmp_path / "gemini" / "commands"
        gemini_dest.mkdir(parents=True)
        monkeypatch.setattr(
            config, "get_destination",
            lambda tool, item_type: str(gemini_dest) if tool == "gemini" else str(tmp_path / "other")
        )

        sync_prompt(prompt_info, ["gemini"])
        expected = gemini_dest / "test-cmd.toml"
        assert expected.exists()
        assert not expected.is_symlink()  # Generated, not symlink


class TestUnsyncPrompt:
    """Test prompt unsyncing."""

    def test_unsync_removes_files(self, prompt_info, tmp_path, monkeypatch):
        from captain_hook import config
        claude_dest = tmp_path / "claude" / "commands"
        claude_dest.mkdir(parents=True)
        link = claude_dest / "test-cmd.md"
        link.symlink_to(prompt_info.path)

        monkeypatch.setattr(
            config, "get_destination",
            lambda tool, item_type: str(claude_dest)
        )

        unsync_prompt(prompt_info, ["claude"])
        assert not link.exists()
```

**Step 2: Run test to verify it fails**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_sync.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implementation**

```python
# src/captain_hook/sync.py
"""Symlink synchronization for prompts and agents.

Handles:
- Creating symlinks from captain-hook dirs to tool destinations
- Generating TOML wrappers for Gemini
- Removing synced files on disable
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from . import config

if TYPE_CHECKING:
    from .types import PromptInfo


def create_symlink(source: Path, dest: Path) -> None:
    """Create a symlink from dest pointing to source.

    Args:
        source: Source file path.
        dest: Destination symlink path.
    """
    # Ensure parent directory exists
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing file/symlink
    if dest.exists() or dest.is_symlink():
        dest.unlink()

    dest.symlink_to(source.resolve())


def remove_symlink(path: Path) -> None:
    """Remove a symlink or file.

    Args:
        path: Path to remove.
    """
    if path.exists() or path.is_symlink():
        path.unlink()


def generate_gemini_toml(prompt_info: "PromptInfo") -> str:
    """Generate Gemini TOML wrapper for a prompt.

    Args:
        prompt_info: Prompt to generate TOML for.

    Returns:
        TOML content as string.
    """
    # Read the body content (without frontmatter)
    from .frontmatter import parse_frontmatter

    content = prompt_info.path.read_text()
    _, body = parse_frontmatter(content)

    # Escape content for TOML multiline string
    body = body.strip()

    toml_content = f'''name = "{prompt_info.name}"
description = "{prompt_info.description}"

prompt = """
{body}
"""
'''
    return toml_content


def get_dest_filename(prompt_info: "PromptInfo", tool: str) -> str:
    """Get the destination filename for a prompt.

    Args:
        prompt_info: Prompt info.
        tool: Target tool.

    Returns:
        Filename with appropriate extension.
    """
    name = prompt_info.name
    if tool == "gemini":
        return f"{name}.toml"
    return f"{name}.md"


def get_dest_path(prompt_info: "PromptInfo", tool: str) -> Path:
    """Get the full destination path for a prompt.

    Args:
        prompt_info: Prompt info.
        tool: Target tool.

    Returns:
        Full destination path.
    """
    from .types import PromptType

    item_type = "commands" if prompt_info.prompt_type == PromptType.COMMAND else "agents"
    dest_dir = config.get_destination(tool, item_type)
    filename = get_dest_filename(prompt_info, tool)
    return Path(dest_dir) / filename


def sync_prompt(prompt_info: "PromptInfo", tools: list[str] | None = None) -> list[Path]:
    """Sync a prompt to its destination directories.

    Args:
        prompt_info: Prompt to sync.
        tools: List of tools to sync to. Defaults to prompt's tools.

    Returns:
        List of created destination paths.
    """
    if tools is None:
        tools = prompt_info.tools

    created: list[Path] = []

    for tool in tools:
        if tool not in prompt_info.tools:
            continue

        dest_path = get_dest_path(prompt_info, tool)

        if tool == "gemini":
            # Generate TOML file
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            toml_content = generate_gemini_toml(prompt_info)
            dest_path.write_text(toml_content)
        else:
            # Create symlink
            create_symlink(prompt_info.path, dest_path)

        created.append(dest_path)

    return created


def unsync_prompt(prompt_info: "PromptInfo", tools: list[str] | None = None) -> list[Path]:
    """Remove synced files for a prompt.

    Args:
        prompt_info: Prompt to unsync.
        tools: List of tools to unsync from. Defaults to prompt's tools.

    Returns:
        List of removed paths.
    """
    if tools is None:
        tools = prompt_info.tools

    removed: list[Path] = []

    for tool in tools:
        dest_path = get_dest_path(prompt_info, tool)
        if dest_path.exists() or dest_path.is_symlink():
            remove_symlink(dest_path)
            removed.append(dest_path)

    return removed


def sync_all_enabled() -> dict[str, list[Path]]:
    """Sync all enabled prompts and agents.

    Returns:
        Dict mapping prompt names to created paths.
    """
    from .prompt_scanner import scan_all_prompts

    results: dict[str, list[Path]] = {}

    for prompt in scan_all_prompts():
        # Check if enabled based on type
        from .types import PromptType

        if prompt.prompt_type == PromptType.COMMAND:
            enabled = config.is_prompt_enabled(prompt.name)
        else:
            enabled = config.is_agent_enabled(prompt.name)

        if enabled:
            results[prompt.name] = sync_prompt(prompt)

    return results


def unsync_all() -> dict[str, list[Path]]:
    """Remove all synced prompts and agents.

    Returns:
        Dict mapping prompt names to removed paths.
    """
    from .prompt_scanner import scan_all_prompts

    results: dict[str, list[Path]] = {}

    for prompt in scan_all_prompts():
        removed = unsync_prompt(prompt)
        if removed:
            results[prompt.name] = removed

    return results
```

**Step 4: Run test to verify it passes**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_sync.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/captain_hook/sync.py tests/test_sync.py
git commit -m "feat: add sync module for symlink management"
```

---

## Task 8: Update Interactive Module - Main Menu

**Files:**
- Modify: `src/captain_hook/interactive.py`

**Step 1: Understand current menu structure**

Read relevant sections of interactive.py to understand the menu system.

**Step 2: Add new menu items**

Add imports at top of `interactive.py`:

```python
from . import prompt_scanner, sync
```

Update the main menu in the `run_interactive()` function to add new items:

```python
# In the main menu choices, add after existing items:
MAIN_MENU_CHOICES = [
    ("Hooks", "hooks"),
    ("Commands", "commands"),
    ("Agents", "agents"),
    ("Add...", "add"),
    ("---", None),  # Separator
    ("Install", "install"),
    ("Uninstall", "uninstall"),
    ("Install Deps", "install_deps"),
    ("Config", "config"),
    ("---", None),
    ("Exit", "exit"),
]
```

**Step 3: Add handler functions for new menus**

```python
def _handle_commands_menu() -> None:
    """Handle the Commands submenu."""
    prompts = prompt_scanner.scan_prompts()
    if not prompts:
        console.print("[yellow]No commands found in prompts directory.[/yellow]")
        console.print(f"[dim]Add .md files to: {config.get_prompts_dir()}[/dim]")
        return

    # Build choices
    choices = []
    for p in prompts:
        enabled = config.is_prompt_enabled(p.name)
        status = "[green]ON[/green]" if enabled else "[dim]OFF[/dim]"
        hook_status = ""
        if p.has_hooks:
            hook_enabled = config.is_prompt_hook_enabled(p.name)
            hook_status = " [cyan](hook)[/cyan]" if hook_enabled else " [dim](hook off)[/dim]"
        choices.append((f"{status} {p.name}{hook_status}", p.name))

    choices.append(("Back", "back"))

    # Show menu
    selected = questionary.select(
        "Commands:",
        choices=[c[0] for c in choices],
        style=custom_style,
    ).ask()

    if selected == "Back" or selected is None:
        return

    # Find selected prompt
    for display, name in choices:
        if display == selected:
            _toggle_prompt(name)
            break


def _handle_agents_menu() -> None:
    """Handle the Agents submenu."""
    agents = prompt_scanner.scan_agents()
    if not agents:
        console.print("[yellow]No agents found in agents directory.[/yellow]")
        console.print(f"[dim]Add .md files to: {config.get_agents_dir()}[/dim]")
        return

    # Build choices
    choices = []
    for a in agents:
        enabled = config.is_agent_enabled(a.name)
        status = "[green]ON[/green]" if enabled else "[dim]OFF[/dim]"
        hook_status = ""
        if a.has_hooks:
            hook_enabled = config.is_agent_hook_enabled(a.name)
            hook_status = " [cyan](hook)[/cyan]" if hook_enabled else " [dim](hook off)[/dim]"
        choices.append((f"{status} {a.name}{hook_status}", a.name))

    choices.append(("Back", "back"))

    selected = questionary.select(
        "Agents:",
        choices=[c[0] for c in choices],
        style=custom_style,
    ).ask()

    if selected == "Back" or selected is None:
        return

    for display, name in choices:
        if display == selected:
            _toggle_agent(name)
            break


def _toggle_prompt(name: str) -> None:
    """Toggle a prompt's enabled state."""
    prompt = prompt_scanner.get_prompt_by_name(name)
    if not prompt:
        return

    current = config.is_prompt_enabled(name)
    new_state = not current

    # Update config
    hook_enabled = config.is_prompt_hook_enabled(name)
    config.set_prompt_enabled(name, new_state, hook_enabled)

    # Sync/unsync
    if new_state:
        sync.sync_prompt(prompt)
        console.print(f"[green]Enabled {name}[/green]")
    else:
        sync.unsync_prompt(prompt)
        console.print(f"[yellow]Disabled {name}[/yellow]")


def _toggle_agent(name: str) -> None:
    """Toggle an agent's enabled state."""
    agent = prompt_scanner.get_prompt_by_name(name)
    if not agent:
        return

    current = config.is_agent_enabled(name)
    new_state = not current

    hook_enabled = config.is_agent_hook_enabled(name)
    config.set_agent_enabled(name, new_state, hook_enabled)

    if new_state:
        sync.sync_prompt(agent)
        console.print(f"[green]Enabled {name}[/green]")
    else:
        sync.unsync_prompt(agent)
        console.print(f"[yellow]Disabled {name}[/yellow]")
```

**Step 4: Test manually**

Run: `captain-hook`
Expected: See new menu items

**Step 5: Commit**

```bash
git add src/captain_hook/interactive.py
git commit -m "feat: add Commands and Agents menus to interactive UI"
```

---

## Task 9: Add Auto-Sync on Startup

**Files:**
- Modify: `src/captain_hook/interactive.py`

**Step 1: Add auto-sync function**

```python
def _auto_sync_prompts() -> None:
    """Auto-sync: detect new/removed prompts, update config."""
    # Scan all prompts
    all_prompts = prompt_scanner.scan_all_prompts()
    prompt_names = {p.name for p in all_prompts if p.prompt_type == PromptType.COMMAND}
    agent_names = {p.name for p in all_prompts if p.prompt_type == PromptType.AGENT}

    # Get current config
    prompts_cfg = config.get_prompts_config()
    agents_cfg = config.get_agents_config()

    # Find new prompts (in files but not in config)
    new_prompts = prompt_names - set(prompts_cfg.keys())
    new_agents = agent_names - set(agents_cfg.keys())

    # Find removed prompts (in config but not in files)
    removed_prompts = set(prompts_cfg.keys()) - prompt_names
    removed_agents = set(agents_cfg.keys()) - agent_names

    # Add new (disabled by default)
    for name in new_prompts:
        config.set_prompt_enabled(name, False, False)
        console.print(f"[dim]Found new command: {name}[/dim]")

    for name in new_agents:
        config.set_agent_enabled(name, False, False)
        console.print(f"[dim]Found new agent: {name}[/dim]")

    # Clean up removed
    for name in removed_prompts:
        cfg = config.load_config()
        del cfg["prompts"][name]
        config.save_config(cfg)
        console.print(f"[dim]Removed command: {name}[/dim]")

    for name in removed_agents:
        cfg = config.load_config()
        del cfg["agents"][name]
        config.save_config(cfg)
        console.print(f"[dim]Removed agent: {name}[/dim]")
```

**Step 2: Call auto-sync at start of run_interactive()**

```python
def run_interactive():
    """Run the interactive CLI."""
    print_header()

    # Auto-sync prompts on startup
    _auto_sync_prompts()

    # ... rest of function
```

**Step 3: Test manually**

Run: `captain-hook`
Expected: Sees "Found new command/agent" messages if new files exist

**Step 4: Commit**

```bash
git add src/captain_hook/interactive.py
git commit -m "feat: add auto-sync on startup for prompts/agents"
```

---

## Task 10: Add "Add..." Menu with Templates

**Files:**
- Modify: `src/captain_hook/interactive.py`
- Modify: `src/captain_hook/templates.py`

**Step 1: Add template content to templates.py**

```python
# In templates.py, add:

PROMPT_TEMPLATE = '''---
name: {name}
description: {description}
tools: [claude]
---

# {name}

Your command content here...
'''

AGENT_TEMPLATE = '''---
name: {name}
description: {description}
tools: [claude]
hooks:
  - session_start
---

You are {name}, an AI assistant specialized in...

## Your Role

Describe the agent's role here.

## Guidelines

- Guideline 1
- Guideline 2
'''

HOOK_PROMPT_TEMPLATE = '''---
name: {name}
description: {description}
tools: [claude]
hooks:
  - event: pre_tool
    matchers: [Bash]
---

# {name}

This command also runs as a hook on pre_tool events.
'''
```

**Step 2: Add handler in interactive.py**

```python
def _handle_add_menu() -> None:
    """Handle the Add... submenu."""
    choices = [
        ("Hook (script)", "hook"),
        ("Command (prompt)", "command"),
        ("Agent", "agent"),
        ("Back", "back"),
    ]

    selected = questionary.select(
        "Add new:",
        choices=[c[0] for c in choices],
        style=custom_style,
    ).ask()

    if selected == "Back" or selected is None:
        return

    for display, action in choices:
        if display == selected:
            if action == "hook":
                _add_hook()
            elif action == "command":
                _add_command()
            elif action == "agent":
                _add_agent()
            break


def _add_command() -> None:
    """Add a new command from template."""
    name = questionary.text("Command name:").ask()
    if not name:
        return

    description = questionary.text("Description:").ask() or f"{name} command"

    # Create file
    from .templates import PROMPT_TEMPLATE
    content = PROMPT_TEMPLATE.format(name=name, description=description)
    path = config.get_prompts_dir() / f"{name}.md"

    if path.exists():
        console.print(f"[red]Command {name} already exists![/red]")
        return

    path.write_text(content)
    console.print(f"[green]Created {path}[/green]")
    console.print("[dim]Edit the file to customize, then toggle to enable.[/dim]")


def _add_agent() -> None:
    """Add a new agent from template."""
    name = questionary.text("Agent name:").ask()
    if not name:
        return

    description = questionary.text("Description:").ask() or f"{name} agent"

    from .templates import AGENT_TEMPLATE
    content = AGENT_TEMPLATE.format(name=name, description=description)
    path = config.get_agents_dir() / f"{name}.md"

    if path.exists():
        console.print(f"[red]Agent {name} already exists![/red]")
        return

    path.write_text(content)
    console.print(f"[green]Created {path}[/green]")
```

**Step 3: Test manually**

Run: `captain-hook` → Add... → Command
Expected: Creates new file

**Step 4: Commit**

```bash
git add src/captain_hook/interactive.py src/captain_hook/templates.py
git commit -m "feat: add Add... menu for creating prompts/agents from templates"
```

---

## Task 11: Integration Testing

**Files:**
- Create: `tests/test_integration_prompts.py`

**Step 1: Write integration tests**

```python
# tests/test_integration_prompts.py
"""Integration tests for prompts feature."""

import pytest
from pathlib import Path
from captain_hook import config, prompt_scanner, sync
from captain_hook.types import PromptType


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    """Set up test environment."""
    # Mock config dir
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    config.ensure_dirs()

    # Create test prompt
    prompts_dir = config.get_prompts_dir()
    (prompts_dir / "test-cmd.md").write_text("""---
name: test-cmd
description: Test command
tools: [claude]
---
Test content.
""")

    # Create test agent
    agents_dir = config.get_agents_dir()
    (agents_dir / "test-agent.md").write_text("""---
name: test-agent
description: Test agent
tools: [claude]
hooks:
  - session_start
---
Agent content.
""")

    # Create destination dirs
    claude_cmds = tmp_path / "claude" / "commands"
    claude_cmds.mkdir(parents=True)

    monkeypatch.setattr(
        config, "get_destination",
        lambda tool, item_type: str(tmp_path / tool / item_type)
    )

    return tmp_path


class TestFullWorkflow:
    """Test complete workflow."""

    def test_scan_enable_sync_disable(self, setup_env):
        # Scan
        prompts = prompt_scanner.scan_prompts()
        assert len(prompts) == 1
        assert prompts[0].name == "test-cmd"

        # Enable
        config.set_prompt_enabled("test-cmd", True)
        assert config.is_prompt_enabled("test-cmd")

        # Sync
        prompt = prompts[0]
        created = sync.sync_prompt(prompt)
        assert len(created) == 1
        assert created[0].exists()

        # Disable
        config.set_prompt_enabled("test-cmd", False)
        removed = sync.unsync_prompt(prompt)
        assert len(removed) == 1
        assert not removed[0].exists()

    def test_agent_with_hooks(self, setup_env):
        agents = prompt_scanner.scan_agents()
        assert len(agents) == 1
        assert agents[0].has_hooks

        # Check hook config
        hooks = agents[0].hooks
        assert hooks[0].event == "session_start"
```

**Step 2: Run tests**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/test_integration_prompts.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_integration_prompts.py
git commit -m "test: add integration tests for prompts feature"
```

---

## Task 12: Run Full Test Suite

**Step 1: Run all tests**

Run: `~/.config/captain-hook/.venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 2: Fix any failures**

If failures, investigate and fix.

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete prompts integration feature"
```

---

## Summary

This plan implements unified prompts/agents management with:

1. **Event mapping** - Canonical events mapped to tool-specific
2. **Frontmatter parsing** - YAML frontmatter for config
3. **New types** - PromptType, PromptInfo
4. **Config updates** - Destinations, prompts, agents sections
5. **Prompt scanner** - Discovers prompts/agents
6. **Sync module** - Symlinks and TOML generation
7. **Interactive UI** - New menus for Commands, Agents, Add...
8. **Auto-sync** - Detects new/removed files on startup
9. **Templates** - Quick scaffolding for new items
10. **Integration tests** - End-to-end verification
