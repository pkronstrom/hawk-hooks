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
        if specific in _REVERSE_MAPPING and _REVERSE_MAPPING[specific] != canonical:
            import logging

            logging.getLogger(__name__).warning(
                f"Event mapping collision: '{specific}' maps to both "
                f"'{_REVERSE_MAPPING[specific]}' and '{canonical}'"
            )
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
