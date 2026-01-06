"""Configuration management for captain-hook."""

import json
import os
from pathlib import Path
from typing import Any

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
]

# Default config
DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": {event: [] for event in EVENTS},
    "projects": [],
    "debug": False,
    "notify": {
        "desktop": True,
        "ntfy": {
            "enabled": False,
            "server": "https://ntfy.sh",
            "topic": "",
        },
    },
}


def get_config_dir() -> Path:
    """Get the captain-hook config directory."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(xdg_config) / "captain-hook"


def get_config_path() -> Path:
    """Get the path to the main config file."""
    return get_config_dir() / "config.json"


def get_hooks_dir() -> Path:
    """Get the path to the hooks directory."""
    return get_config_dir() / "hooks"


def get_runners_dir() -> Path:
    """Get the path to the runners directory."""
    return get_config_dir() / "runners"


def get_venv_dir() -> Path:
    """Get the path to the Python venv."""
    return get_config_dir() / ".venv"


def get_venv_python() -> Path:
    """Get the path to the venv Python executable."""
    return get_venv_dir() / "bin" / "python"


def get_log_path() -> Path:
    """Get the path to the debug log file."""
    return get_config_dir() / "debug.log"


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled."""
    return load_config().get("debug", False)


def get_project_config_path(project_dir: Path | None = None) -> Path:
    """Get the path to project-specific config."""
    if project_dir is None:
        project_dir = Path.cwd()
    return project_dir / ".claude" / "captain-hook" / "config.json"


def get_project_runners_dir(project_dir: Path | None = None) -> Path:
    """Get the path to project-specific runners."""
    if project_dir is None:
        project_dir = Path.cwd()
    return project_dir / ".claude" / "captain-hook" / "runners"


def ensure_dirs() -> None:
    """Ensure all required directories exist."""
    get_config_dir().mkdir(parents=True, exist_ok=True)
    get_hooks_dir().mkdir(parents=True, exist_ok=True)
    get_runners_dir().mkdir(parents=True, exist_ok=True)

    # Create event subdirectories
    for event in EVENTS:
        (get_hooks_dir() / event).mkdir(parents=True, exist_ok=True)


def config_exists() -> bool:
    """Check if config file exists (for first-run detection)."""
    return get_config_path().exists()


def load_config() -> dict[str, Any]:
    """Load the global configuration file."""
    config_path = get_config_path()

    try:
        with open(config_path) as f:
            config = json.load(f)
        if not isinstance(config, dict):
            return DEFAULT_CONFIG.copy()
        # Merge with defaults to ensure all keys exist
        return _deep_merge(DEFAULT_CONFIG.copy(), config)
    except FileNotFoundError:
        return DEFAULT_CONFIG.copy()
    except (json.JSONDecodeError, OSError):
        # Corrupted or unreadable config - return defaults
        return DEFAULT_CONFIG.copy()


def save_config(config: dict[str, Any]) -> None:
    """Save the global configuration file."""
    ensure_dirs()
    config_path = get_config_path()

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def load_project_config(project_dir: Path | None = None) -> dict[str, Any] | None:
    """Load project-specific config if it exists."""
    config_path = get_project_config_path(project_dir)

    try:
        with open(config_path) as f:
            config = json.load(f)
        if isinstance(config, dict):
            return config
        return None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def save_project_config(
    config: dict[str, Any],
    project_dir: Path | None = None,
    add_to_git_exclude: bool = True,
) -> None:
    """Save project-specific config."""
    if project_dir is None:
        project_dir = Path.cwd()

    config_path = get_project_config_path(project_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    # Track project
    global_config = load_config()
    project_str = str(project_dir.resolve())
    if project_str not in global_config["projects"]:
        global_config["projects"].append(project_str)
        save_config(global_config)

    # Optionally add to .git/info/exclude
    if add_to_git_exclude:
        _add_to_git_exclude(project_dir)


def _add_to_git_exclude(project_dir: Path) -> None:
    """Add captain-hook dir to .git/info/exclude."""
    git_exclude = project_dir / ".git" / "info" / "exclude"
    if git_exclude.parent.exists():
        exclude_entry = ".claude/captain-hook/"
        try:
            content = git_exclude.read_text() if git_exclude.exists() else ""
            if exclude_entry not in content:
                with open(git_exclude, "a") as f:
                    if content and not content.endswith("\n"):
                        f.write("\n")
                    f.write(f"{exclude_entry}\n")
        except (OSError, UnicodeDecodeError, PermissionError):
            pass  # Silent fail - git exclude is non-critical


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def is_hook_enabled(event: str, hook_name: str, project_dir: Path | None = None) -> bool:
    """Check if a hook is enabled (considering project overrides)."""
    # Check project config first
    project_config = load_project_config(project_dir)
    if project_config:
        project_enabled = project_config.get("enabled", {}).get(event, None)
        if project_enabled is not None:
            return hook_name in project_enabled

    # Fall back to global config
    config = load_config()
    return hook_name in config.get("enabled", {}).get(event, [])


def get_enabled_hooks(event: str, project_dir: Path | None = None) -> list[str]:
    """Get list of enabled hooks for an event."""
    # Check project config first
    project_config = load_project_config(project_dir)
    if project_config:
        project_enabled = project_config.get("enabled", {}).get(event, None)
        if project_enabled is not None:
            return project_enabled

    # Fall back to global config
    config = load_config()
    return config.get("enabled", {}).get(event, [])


def set_enabled_hooks(
    event: str,
    hooks: list[str],
    scope: str = "global",
    project_dir: Path | None = None,
    add_to_git_exclude: bool = True,
) -> None:
    """Set the list of enabled hooks for an event."""
    if scope == "global":
        config = load_config()
        config["enabled"][event] = hooks
        save_config(config)
    else:
        config = load_project_config(project_dir) or {"enabled": {}}
        config["enabled"][event] = hooks
        save_project_config(config, project_dir, add_to_git_exclude)


def get_tracked_projects() -> list[str]:
    """Get list of tracked projects."""
    config = load_config()
    return config.get("projects", [])


def remove_tracked_project(project_path: str) -> None:
    """Remove a project from tracking."""
    config = load_config()
    if project_path in config["projects"]:
        config["projects"].remove(project_path)
        save_config(config)
