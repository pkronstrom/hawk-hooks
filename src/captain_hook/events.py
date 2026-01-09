"""Event constants for captain-hook.

This module provides the canonical list of supported Claude Code hook events
and their metadata. Import from here to avoid duplication.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventDefinition:
    """Definition of a Claude Code hook event.

    Attributes:
        name: Internal event name (e.g., "pre_tool_use")
        claude_name: Claude's event name (e.g., "PreToolUse")
        description: Human-readable description for UI
        matchers: Tuple of tool matchers for Claude settings (None = no matcher)
    """

    name: str
    claude_name: str
    description: str
    matchers: tuple[str | None, ...] = (None,)


# Unified event definitions - single source of truth
EVENTS: dict[str, EventDefinition] = {
    "pre_tool_use": EventDefinition(
        name="pre_tool_use",
        claude_name="PreToolUse",
        description="Before each tool is executed",
        matchers=("Edit|Write|MultiEdit", "Bash"),
    ),
    "post_tool_use": EventDefinition(
        name="post_tool_use",
        claude_name="PostToolUse",
        description="After each tool completes",
        matchers=("Edit|Write|MultiEdit",),
    ),
    "notification": EventDefinition(
        name="notification",
        claude_name="Notification",
        description="On system notifications",
    ),
    "stop": EventDefinition(
        name="stop",
        claude_name="Stop",
        description="Before completing a response",
    ),
    "subagent_stop": EventDefinition(
        name="subagent_stop",
        claude_name="SubagentStop",
        description="When a subagent completes",
    ),
    "user_prompt_submit": EventDefinition(
        name="user_prompt_submit",
        claude_name="UserPromptSubmit",
        description="When user sends a message",
    ),
    "session_start": EventDefinition(
        name="session_start",
        claude_name="SessionStart",
        description="At the start of a session",
    ),
    "session_end": EventDefinition(
        name="session_end",
        claude_name="SessionEnd",
        description="When a session ends",
    ),
    "pre_compact": EventDefinition(
        name="pre_compact",
        claude_name="PreCompact",
        description="Before conversation is summarized",
    ),
    "permission_request": EventDefinition(
        name="permission_request",
        claude_name="PermissionRequest",
        description="When permission is requested",
    ),
}

# List of event names for iteration (maintains backwards compatibility)
EVENT_NAMES: list[str] = list(EVENTS.keys())


def get_event_display(event: str) -> tuple[str, str]:
    """Get display name and description for an event.

    Returns (display_name, description) tuple.
    Falls back to formatted event name if not in EVENTS.
    """
    if event in EVENTS:
        ev = EVENTS[event]
        return (ev.claude_name, ev.description)
    # Fallback for unknown events
    display = event.replace("_", " ").title()
    return (display, "")


# Backwards compatibility aliases
EVENT_INFO: dict[str, tuple[str, str]] = {
    name: (ev.claude_name, ev.description) for name, ev in EVENTS.items()
}
