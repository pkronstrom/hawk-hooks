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
        doc_description: Longer description for documentation
        fields: Tuple of field names available in the event JSON
    """

    name: str
    claude_name: str
    description: str
    matchers: tuple[str | None, ...] = (None,)
    doc_description: str = ""
    fields: tuple[str, ...] = ()


# Unified event definitions - single source of truth
EVENTS: dict[str, EventDefinition] = {
    "pre_tool_use": EventDefinition(
        name="pre_tool_use",
        claude_name="PreToolUse",
        description="Before each tool is executed",
        matchers=("Edit|Write|MultiEdit", "Bash"),
        doc_description="Runs before tool execution. Can block.",
        fields=("session_id", "cwd", "tool_name", "tool_input", "tool_use_id"),
    ),
    "post_tool_use": EventDefinition(
        name="post_tool_use",
        claude_name="PostToolUse",
        description="After each tool completes",
        matchers=("Edit|Write|MultiEdit",),
        doc_description="Runs after tool completes. Can provide feedback.",
        fields=("session_id", "cwd", "tool_name", "tool_input", "tool_response"),
    ),
    "notification": EventDefinition(
        name="notification",
        claude_name="Notification",
        description="On system notifications",
        doc_description="Runs when Claude sends notifications.",
        fields=("session_id", "cwd", "message"),
    ),
    "stop": EventDefinition(
        name="stop",
        claude_name="Stop",
        description="Before completing a response",
        doc_description="Runs when agent finishes. Can request continuation.",
        fields=("session_id", "cwd", "stop_reason"),
    ),
    "subagent_stop": EventDefinition(
        name="subagent_stop",
        claude_name="SubagentStop",
        description="When a subagent completes",
        doc_description="Runs when subagent/Task tool finishes.",
        fields=("session_id", "cwd", "stop_reason"),
    ),
    "user_prompt_submit": EventDefinition(
        name="user_prompt_submit",
        claude_name="UserPromptSubmit",
        description="When user sends a message",
        doc_description="Runs when user submits prompt. Can block or add context.",
        fields=("session_id", "cwd", "prompt"),
    ),
    "session_start": EventDefinition(
        name="session_start",
        claude_name="SessionStart",
        description="At the start of a session",
        doc_description="Runs at session start/resume/clear.",
        fields=("session_id", "cwd", "source"),
    ),
    "session_end": EventDefinition(
        name="session_end",
        claude_name="SessionEnd",
        description="When a session ends",
        doc_description="Runs when session ends.",
        fields=("session_id", "cwd", "reason"),
    ),
    "pre_compact": EventDefinition(
        name="pre_compact",
        claude_name="PreCompact",
        description="Before conversation is summarized",
        doc_description="Runs before context compaction.",
        fields=("session_id", "cwd", "source"),
    ),
    "permission_request": EventDefinition(
        name="permission_request",
        claude_name="PermissionRequest",
        description="When permission is requested",
        doc_description="Runs when permission is requested.",
        fields=("session_id", "cwd", "permission"),
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


def generate_events_doc() -> str:
    """Generate documentation for all events.

    Returns markdown-formatted event documentation.
    """
    lines = ["## Events", ""]
    for event_def in EVENTS.values():
        lines.append(f"### {event_def.name}")
        lines.append(event_def.doc_description or event_def.description)
        if event_def.fields:
            lines.append(f"Fields: {', '.join(event_def.fields)}")
        lines.append("")
    return "\n".join(lines)
