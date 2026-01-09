"""Event constants for captain-hook.

This module provides the canonical list of supported Claude Code hook events
and their display information. Import from here to avoid duplication.
"""

# Supported events (Claude Code hook types)
EVENTS = [
    "pre_tool_use",
    "post_tool_use",
    "notification",
    "stop",
    "subagent_stop",
    "user_prompt_submit",
    "session_start",
    "session_end",
    "pre_compact",
    "permission_request",
]

# Event display names and descriptions for UI
# Format: event_name -> (DisplayName, description)
EVENT_INFO: dict[str, tuple[str, str]] = {
    "pre_tool_use": ("PreToolUse", "Before each tool is executed"),
    "post_tool_use": ("PostToolUse", "After each tool completes"),
    "user_prompt_submit": ("UserPromptSubmit", "When user sends a message"),
    "session_start": ("SessionStart", "At the start of a session"),
    "session_end": ("SessionEnd", "When a session ends"),
    "pre_compact": ("PreCompact", "Before conversation is summarized"),
    "notification": ("Notification", "On system notifications"),
    "stop": ("Stop", "Before completing a response"),
    "subagent_stop": ("SubagentStop", "When a subagent completes"),
    "permission_request": ("PermissionRequest", "When permission is requested"),
}


def get_event_display(event: str) -> tuple[str, str]:
    """Get display name and description for an event.

    Returns (display_name, description) tuple.
    Falls back to formatted event name if not in EVENT_INFO.
    """
    if event in EVENT_INFO:
        return EVENT_INFO[event]
    # Fallback for unknown events
    display = event.replace("_", " ").title()
    return (display, "")
