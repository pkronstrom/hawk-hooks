"""Event mapping and capability contract across supported tools.

This module normalizes hawk hook events to tool-specific matcher/event names
and exposes support status per tool:
- native: tool supports this event directly
- bridge: emulated via a reduced mechanism
- unsupported: no reliable integration
"""

from __future__ import annotations

from typing import Literal

SupportLevel = Literal["native", "bridge", "unsupported"]

# Backward-compatible aliases used by older docs/tests.
_ALIASES_TO_HAWK: dict[str, str] = {
    "pre_tool": "pre_tool_use",
    "post_tool": "post_tool_use",
}

_HAWK_TO_ALIASES: dict[str, str] = {
    "pre_tool_use": "pre_tool",
    "post_tool_use": "post_tool",
}

# Hawk event -> tool-specific matcher/event name where available.
_TOOL_EVENT_MAP: dict[str, dict[str, str]] = {
    "claude": {
        "pre_tool_use": "PreToolUse",
        "post_tool_use": "PostToolUse",
        "post_tool_use_failure": "PostToolUseFailure",
        "notification": "Notification",
        "stop": "Stop",
        "subagent_start": "SubagentStart",
        "subagent_stop": "SubagentStop",
        "user_prompt_submit": "UserPromptSubmit",
        "session_start": "SessionStart",
        "session_end": "SessionEnd",
        "pre_compact": "PreCompact",
        "permission_request": "PermissionRequest",
    },
    "gemini": {
        "pre_tool_use": "BeforeTool",
        "post_tool_use": "AfterTool",
        "notification": "Notification",
        "stop": "AfterAgent",
        "user_prompt_submit": "BeforeAgent",
        "session_start": "SessionStart",
        "session_end": "SessionEnd",
        "pre_compact": "PreCompress",
    },
    "codex": {
        # Limited bridge mode: Codex notify callbacks currently model
        # "agent-turn-complete" semantics rather than full event hooks.
        "stop": "agent-turn-complete",
        "notification": "agent-turn-complete",
    },
    "opencode": {
        # Hook bridge support via generated OpenCode plugin wrappers.
        "pre_tool_use": "tool.execute.before",
        "post_tool_use": "tool.execute.after",
        "stop": "stop",
    },
}

_EVENT_SUPPORT: dict[str, dict[str, SupportLevel]] = {
    "claude": {
        event: "native" for event in _TOOL_EVENT_MAP["claude"]
    },
    "gemini": {
        event: "native" for event in _TOOL_EVENT_MAP["gemini"]
    },
    "codex": {
        "stop": "bridge",
        "notification": "bridge",
    },
    "opencode": {
        "pre_tool_use": "bridge",
        "post_tool_use": "bridge",
        "stop": "bridge",
    },
}

# Tool-specific events that are not part of hawk event names.
_TOOL_SPECIFIC_EVENTS: dict[str, list[str]] = {
    "claude": [],
    "gemini": ["BeforeModel", "AfterModel", "BeforeToolSelection"],
    "codex": ["agent-turn-complete"],
    "opencode": [],
}

# Reverse mapping (tool-specific -> hawk event).
_REVERSE_MAPPING: dict[str, str] = {}
for tool_name, event_map in _TOOL_EVENT_MAP.items():
    for hawk_event, tool_event in event_map.items():
        # Keep first definition if multiple tools share same token.
        _REVERSE_MAPPING.setdefault(tool_event, hawk_event)


def _normalize_hawk_event(event: str) -> str:
    """Normalize legacy aliases to hawk event names."""
    return _ALIASES_TO_HAWK.get(event, event)


def get_tool_event(event: str, tool: str) -> str:
    """Map event to a tool-specific event/matcher name.

    Returns the input event unchanged when no mapping exists.
    """
    normalized = _normalize_hawk_event(event)
    mapped = _TOOL_EVENT_MAP.get(tool, {}).get(normalized)
    if mapped:
        return mapped
    return event


def get_tool_event_or_none(event: str, tool: str) -> str | None:
    """Map event to tool-specific name, or None if unsupported."""
    normalized = _normalize_hawk_event(event)
    return _TOOL_EVENT_MAP.get(tool, {}).get(normalized)


def get_canonical_event(event: str) -> str:
    """Get canonical event identifier (legacy canonical aliases where defined)."""
    hawk_event = _REVERSE_MAPPING.get(event, _normalize_hawk_event(event))
    return _HAWK_TO_ALIASES.get(hawk_event, hawk_event)


def get_event_support(event: str, tool: str) -> SupportLevel:
    """Return support level for an event on a tool."""
    normalized = _normalize_hawk_event(event)
    return _EVENT_SUPPORT.get(tool, {}).get(normalized, "unsupported")


def is_tool_specific_event(event: str, tool: str) -> bool:
    """Check whether event is tool-specific for the given tool."""
    return event in _TOOL_SPECIFIC_EVENTS.get(tool, [])


def is_event_supported(event: str, tool: str) -> bool:
    """Check whether a tool supports an event natively or via bridge."""
    return get_event_support(event, tool) != "unsupported" or is_tool_specific_event(event, tool)
