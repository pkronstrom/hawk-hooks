"""Install/uninstall hooks to Claude Code settings."""

import json
from pathlib import Path
from typing import Any

from . import config

# Claude event mapping
CLAUDE_EVENTS = {
    "pre_tool_use": {
        "claude_event": "PreToolUse",
        "matchers": ["Edit|Write|MultiEdit", "Bash"],
    },
    "post_tool_use": {
        "claude_event": "PostToolUse",
        "matchers": ["Edit|Write|MultiEdit"],
    },
    "stop": {
        "claude_event": "Stop",
        "matchers": [None],
    },
    "notification": {
        "claude_event": "Notification",
        "matchers": [None],
    },
    "user_prompt_submit": {
        "claude_event": "UserPromptSubmit",
        "matchers": [None],
    },
}


def get_user_settings_path() -> Path:
    """Get path to user-level Claude settings."""
    return Path.home() / ".claude" / "settings.json"


def get_project_settings_path(project_dir: Path | None = None) -> Path:
    """Get path to project-level Claude settings."""
    if project_dir is None:
        project_dir = Path.cwd()
    return project_dir / ".claude" / "settings.json"


def load_claude_settings(path: Path) -> dict[str, Any]:
    """Load Claude settings from a file."""
    try:
        with open(path) as f:
            settings = json.load(f)
        if isinstance(settings, dict):
            return settings
        return {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_claude_settings(path: Path, settings: dict[str, Any]) -> None:
    """Save Claude settings to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)


def is_our_hook(hook: dict[str, Any]) -> bool:
    """Check if a hook was installed by captain-hook."""
    command = hook.get("command", "")
    # Check for our runner paths
    if "captain-hook/runners/" in command:
        return True
    # Legacy: check for old dispatcher command
    if command.startswith("captain-hook"):
        return True
    return False


def get_runner_command(event: str) -> str:
    """Get the runner command for an event."""
    runner_path = config.get_runners_dir() / f"{event}.sh"
    return str(runner_path)


def install_hooks(level: str = "user", project_dir: Path | None = None) -> dict[str, bool]:
    """
    Install captain-hook runners to Claude settings.

    Args:
        level: 'user' or 'project'
        project_dir: Project directory for project-level installation

    Returns:
        Dict mapping event names to success status
    """
    # Ensure directories and runners exist
    config.ensure_dirs()

    if level == "user":
        settings_path = get_user_settings_path()
    else:
        settings_path = get_project_settings_path(project_dir)

    settings = load_claude_settings(settings_path)

    if "hooks" not in settings:
        settings["hooks"] = {}

    results = {}

    for event, event_config in CLAUDE_EVENTS.items():
        claude_event = event_config["claude_event"]
        matchers = event_config["matchers"]

        if claude_event not in settings["hooks"]:
            settings["hooks"][claude_event] = []

        runner_cmd = get_runner_command(event)

        for matcher in matchers:
            # Check if we already have this hook
            existing = False
            for hook_group in settings["hooks"][claude_event]:
                if hook_group.get("matcher") == matcher:
                    for hook in hook_group.get("hooks", []):
                        if is_our_hook(hook):
                            existing = True
                            break
                if existing:
                    break

            if not existing:
                hook_entry = {"type": "command", "command": runner_cmd}
                new_group = {"hooks": [hook_entry]}
                if matcher:
                    new_group["matcher"] = matcher
                settings["hooks"][claude_event].append(new_group)

        results[event] = True

    save_claude_settings(settings_path, settings)
    return results


def uninstall_hooks(level: str = "user", project_dir: Path | None = None) -> dict[str, bool]:
    """
    Uninstall captain-hook from Claude settings.

    Args:
        level: 'user' or 'project'
        project_dir: Project directory for project-level uninstallation

    Returns:
        Dict mapping event names to success status
    """
    if level == "user":
        settings_path = get_user_settings_path()
    else:
        settings_path = get_project_settings_path(project_dir)

    settings = load_claude_settings(settings_path)

    if "hooks" not in settings:
        return {}

    results = {}

    for event, event_config in CLAUDE_EVENTS.items():
        claude_event = event_config["claude_event"]

        if claude_event not in settings["hooks"]:
            continue

        # Filter out our hooks
        new_hook_groups = []
        for hook_group in settings["hooks"][claude_event]:
            new_hooks = [h for h in hook_group.get("hooks", []) if not is_our_hook(h)]
            if new_hooks:
                hook_group["hooks"] = new_hooks
                new_hook_groups.append(hook_group)

        if new_hook_groups:
            settings["hooks"][claude_event] = new_hook_groups
        else:
            del settings["hooks"][claude_event]

        results[claude_event] = True

    # Clean up empty hooks dict
    if not settings.get("hooks"):
        settings.pop("hooks", None)

    save_claude_settings(settings_path, settings)
    return results


def get_status(project_dir: Path | None = None) -> dict[str, Any]:
    """
    Get status of installed hooks.

    Returns:
        Dict with 'user' and 'project' keys containing installation info
    """
    user_path = get_user_settings_path()
    project_path = get_project_settings_path(project_dir)

    user_settings = load_claude_settings(user_path)
    project_settings = load_claude_settings(project_path)

    def has_our_hooks(settings: dict) -> bool:
        for event_hooks in settings.get("hooks", {}).values():
            for hook_group in event_hooks:
                for hook in hook_group.get("hooks", []):
                    if is_our_hook(hook):
                        return True
        return False

    return {
        "user": {
            "path": str(user_path),
            "installed": has_our_hooks(user_settings),
        },
        "project": {
            "path": str(project_path),
            "installed": has_our_hooks(project_settings),
        },
    }
