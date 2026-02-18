"""v2 YAML-based configuration management.

Manages three config layers:
1. Global: ~/.config/hawk-hooks/config.yaml
2. Profile: ~/.config/hawk-hooks/profiles/<name>.yaml
3. Directory: <project>/.hawk/config.yaml
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

from .types import Tool

# Default global config
DEFAULT_GLOBAL_CONFIG: dict[str, Any] = {
    "registry_path": "~/.config/hawk-hooks/registry",
    "debug": False,
    "global": {
        "skills": [],
        "hooks": [],
        "commands": [],
        "agents": [],
        "mcp": [],
    },
    "tools": {
        "claude": {"enabled": True, "global_dir": "~/.claude"},
        "gemini": {"enabled": True, "global_dir": "~/.gemini"},
        "codex": {"enabled": True, "global_dir": "~/.codex"},
        "opencode": {"enabled": True, "global_dir": "~/.config/opencode"},
        "cursor": {"enabled": True, "global_dir": "~/.cursor"},
        "antigravity": {"enabled": True, "global_dir": "~/.gemini/antigravity"},
    },
    "directories": {},
}


def get_config_dir() -> Path:
    """Get the hawk-hooks config directory."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(xdg_config) / "hawk-hooks"


def get_global_config_path() -> Path:
    """Get the path to the v2 global config file."""
    return get_config_dir() / "config.yaml"


def get_registry_path(cfg: dict[str, Any] | None = None) -> Path:
    """Get the registry directory path."""
    if cfg is None:
        cfg = load_global_config()
    raw = cfg.get("registry_path", DEFAULT_GLOBAL_CONFIG["registry_path"])
    return Path(os.path.expanduser(raw))


def get_profiles_dir() -> Path:
    """Get the profiles directory path."""
    return get_config_dir() / "profiles"


def get_dir_config_path(project_dir: Path) -> Path:
    """Get the per-directory config path."""
    return project_dir / ".hawk" / "config.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def ensure_v2_dirs(cfg: dict[str, Any] | None = None) -> None:
    """Ensure all v2 directories exist."""
    get_config_dir().mkdir(parents=True, exist_ok=True)
    get_profiles_dir().mkdir(parents=True, exist_ok=True)

    registry = get_registry_path(cfg)
    for subdir in ["skills", "hooks", "commands", "agents", "mcp", "prompts"]:
        (registry / subdir).mkdir(parents=True, exist_ok=True)

    # Cache dir for resolved sets
    (get_config_dir() / "cache" / "resolved").mkdir(parents=True, exist_ok=True)


def load_global_config() -> dict[str, Any]:
    """Load the global v2 config (config.yaml)."""
    config_path = get_global_config_path()
    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return copy.deepcopy(DEFAULT_GLOBAL_CONFIG)
        return _deep_merge(copy.deepcopy(DEFAULT_GLOBAL_CONFIG), data)
    except FileNotFoundError:
        return copy.deepcopy(DEFAULT_GLOBAL_CONFIG)
    except (yaml.YAMLError, OSError):
        return copy.deepcopy(DEFAULT_GLOBAL_CONFIG)


def save_global_config(cfg: dict[str, Any]) -> None:
    """Save the global v2 config."""
    config_path = get_global_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)


def load_profile(name: str) -> dict[str, Any] | None:
    """Load a profile by name.

    Returns None if the profile does not exist.
    """
    profile_path = get_profiles_dir() / f"{name}.yaml"
    try:
        with open(profile_path) as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
        return None
    except (FileNotFoundError, yaml.YAMLError, OSError):
        return None


def save_profile(name: str, data: dict[str, Any]) -> None:
    """Save a profile."""
    profile_path = get_profiles_dir() / f"{name}.yaml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    with open(profile_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def list_profiles() -> list[str]:
    """List available profile names."""
    profiles_dir = get_profiles_dir()
    if not profiles_dir.exists():
        return []
    return sorted(
        p.stem for p in profiles_dir.iterdir() if p.is_file() and p.suffix == ".yaml"
    )


def load_dir_config(project_dir: Path) -> dict[str, Any] | None:
    """Load per-directory config.

    Returns None if the config does not exist.
    """
    config_path = get_dir_config_path(project_dir)
    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
        return None
    except (FileNotFoundError, yaml.YAMLError, OSError):
        return None


def save_dir_config(project_dir: Path, data: dict[str, Any]) -> None:
    """Save per-directory config."""
    config_path = get_dir_config_path(project_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def register_directory(project_dir: Path, profile: str | None = None) -> None:
    """Register a directory in the global index."""
    cfg = load_global_config()
    dir_str = str(project_dir.resolve())
    entry: dict[str, Any] = {}
    if profile:
        entry["profile"] = profile
    cfg.setdefault("directories", {})[dir_str] = entry
    save_global_config(cfg)


def unregister_directory(project_dir: Path) -> None:
    """Remove a directory from the global index."""
    cfg = load_global_config()
    dir_str = str(project_dir.resolve())
    cfg.get("directories", {}).pop(dir_str, None)
    save_global_config(cfg)


def get_registered_directories() -> dict[str, dict[str, Any]]:
    """Get all registered directories and their settings."""
    cfg = load_global_config()
    return cfg.get("directories", {})


def get_enabled_tools(cfg: dict[str, Any] | None = None) -> list[Tool]:
    """Get list of enabled tools."""
    if cfg is None:
        cfg = load_global_config()
    tools_cfg = cfg.get("tools", {})
    enabled = []
    for tool in Tool.all():
        tool_cfg = tools_cfg.get(str(tool), {})
        if tool_cfg.get("enabled", True):
            enabled.append(tool)
    return enabled


def get_tool_global_dir(tool: Tool, cfg: dict[str, Any] | None = None) -> Path:
    """Get the global directory for a tool."""
    if cfg is None:
        cfg = load_global_config()
    tools_cfg = cfg.get("tools", {})
    tool_cfg = tools_cfg.get(str(tool), {})
    default_dirs = {
        Tool.CLAUDE: "~/.claude",
        Tool.GEMINI: "~/.gemini",
        Tool.CODEX: "~/.codex",
        Tool.OPENCODE: "~/.config/opencode",
        Tool.CURSOR: "~/.cursor",
        Tool.ANTIGRAVITY: "~/.gemini/antigravity",
    }
    raw = tool_cfg.get("global_dir", default_dirs.get(tool, ""))
    return Path(os.path.expanduser(raw))
