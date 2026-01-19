"""Configuration management for hawk-hooks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .events import EVENTS
from .types import Scope

# Default config
DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": {event: [] for event in EVENTS},
    "projects": [],
    "debug": False,
    "env": {},  # Env vars from scripts: {VAR_NAME: value}
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


def get_config_dir() -> Path:
    """Get the hawk-hooks config directory."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(xdg_config) / "hawk-hooks"


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


def get_docs_dir() -> Path:
    """Get the path to the docs directory."""
    return get_config_dir() / "docs"


def get_prompts_dir() -> Path:
    """Get the path to the prompts directory."""
    return get_config_dir() / "prompts"


def get_agents_dir() -> Path:
    """Get the path to the agents directory."""
    return get_config_dir() / "agents"


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled."""
    return load_config().get("debug", False)


def _validate_project_dir(project_dir: Path) -> Path:
    """Validate that a project directory is safe to use.

    Security: Validates that the directory is a legitimate project directory
    to prevent writing config files to sensitive system locations.

    Returns the resolved absolute path if valid, raises ValueError otherwise.
    """
    resolved = project_dir.resolve()

    # Must be an existing directory
    if not resolved.is_dir():
        raise ValueError(f"Not a directory: {resolved}")

    resolved_str = str(resolved)

    # Block sensitive system directories (Linux + macOS)
    blocked_prefixes = [
        "/etc",
        "/usr",
        "/bin",
        "/sbin",
        "/var",
        "/root",
        "/sys",
        "/proc",
        "/boot",
        "/dev",
        "/tmp",
        # macOS-specific
        "/Library",
        "/System",
        "/Applications",
        "/private/etc",
        "/private/var",
    ]
    for prefix in blocked_prefixes:
        if resolved_str.startswith(prefix):
            raise ValueError(f"Cannot use system directory: {resolved}")

    # Additional check: reject if path contains ".." after resolution
    # (shouldn't happen with resolve(), but defense in depth)
    if ".." in resolved_str:
        raise ValueError(f"Path traversal detected: {resolved}")

    # Prefer directories that look like projects (have .git or common project files)
    # This is a soft check - we still allow other directories but log a warning
    project_indicators = [".git", "package.json", "pyproject.toml", "Cargo.toml", "go.mod"]
    has_indicator = any((resolved / indicator).exists() for indicator in project_indicators)

    if not has_indicator:
        # Still allow but could add warning in future
        pass

    return resolved


def get_project_config_path(project_dir: Path | None = None) -> Path:
    """Get the path to project-specific config."""
    if project_dir is None:
        project_dir = Path.cwd()
    # Security: validate project directory
    validated = _validate_project_dir(project_dir)
    return validated / ".claude" / "hawk-hooks" / "config.json"


def get_project_runners_dir(project_dir: Path | None = None) -> Path:
    """Get the path to project-specific runners."""
    if project_dir is None:
        project_dir = Path.cwd()
    # Security: validate project directory
    validated = _validate_project_dir(project_dir)
    return validated / ".claude" / "hawk-hooks" / "runners"


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


def config_exists() -> bool:
    """Check if config file exists (for first-run detection)."""
    return get_config_path().exists()


def load_config() -> dict[str, Any]:
    """Load the global configuration file."""
    import copy

    config_path = get_config_path()

    try:
        with open(config_path) as f:
            config = json.load(f)
        if not isinstance(config, dict):
            return copy.deepcopy(DEFAULT_CONFIG)
        # Merge with defaults to ensure all keys exist
        return _deep_merge(copy.deepcopy(DEFAULT_CONFIG), config)
    except FileNotFoundError:
        return copy.deepcopy(DEFAULT_CONFIG)
    except (json.JSONDecodeError, OSError):
        # Corrupted or unreadable config - return defaults
        return copy.deepcopy(DEFAULT_CONFIG)


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
    """Add hawk-hooks dir to .git/info/exclude."""
    git_exclude = project_dir / ".git" / "info" / "exclude"
    if git_exclude.parent.exists():
        exclude_entry = ".claude/hawk-hooks/"
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
    scope: Scope | str = Scope.USER,
    project_dir: Path | None = None,
    add_to_git_exclude: bool = True,
) -> None:
    """Set the list of enabled hooks for an event.

    Args:
        event: The event name.
        hooks: List of hook names to enable.
        scope: USER for global settings, PROJECT for project-specific.
               Accepts Scope enum or string ("user", "global", "project").
        project_dir: Project directory (for PROJECT scope).
        add_to_git_exclude: Whether to add project config to .git/info/exclude.
    """
    # Normalize string to Scope enum (handles legacy "global" -> USER mapping)
    if isinstance(scope, str):
        scope = Scope.from_string(scope)

    if scope == Scope.USER:
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


def get_env_var(var_name: str, default: str = "") -> str:
    """Get an env var value from config, falling back to default."""
    cfg = load_config()
    return cfg.get("env", {}).get(var_name, default)


def set_env_var(var_name: str, value: str) -> None:
    """Set an env var value in config."""
    cfg = load_config()
    if "env" not in cfg:
        cfg["env"] = {}
    cfg["env"][var_name] = value
    save_config(cfg)


def get_all_env_config() -> dict[str, str]:
    """Get all env vars from config."""
    cfg = load_config()
    return cfg.get("env", {})


# Destination management


def get_default_destinations() -> dict[str, dict[str, str]]:
    """Get default destination paths."""
    import copy

    return copy.deepcopy(DEFAULT_CONFIG["destinations"])


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


# Prompts configuration


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


# Agents configuration


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
