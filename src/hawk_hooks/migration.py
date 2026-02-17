"""v1 JSON -> v2 YAML migration.

Converts the existing config.json format to the new config.yaml format,
preserving all user settings.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from . import v2_config


def detect_v1_config() -> Path | None:
    """Check if a v1 config.json exists. Returns path or None."""
    config_path = v2_config.get_config_dir() / "config.json"
    if config_path.exists():
        return config_path
    return None


def load_v1_config(path: Path) -> dict[str, Any]:
    """Load a v1 config.json file."""
    with open(path) as f:
        return json.load(f)


def migrate_config(v1: dict[str, Any]) -> dict[str, Any]:
    """Convert v1 config dict to v2 format.

    v1 schema:
        enabled: {event: [hook_names]}
        projects: [paths]
        debug: bool
        env: {VAR: value}
        destinations: {tool: {type: path}}
        prompts: {name: {enabled: bool, hook_enabled: bool}}
        agents: {name: {enabled: bool, hook_enabled: bool}}

    v2 schema:
        registry_path, debug, global: {skills, hooks, ...},
        tools: {claude: {...}}, directories: {path: {...}}
    """
    v2: dict[str, Any] = {
        "registry_path": "~/.config/hawk-hooks/registry",
        "debug": v1.get("debug", False),
    }

    # Migrate enabled hooks -> global.hooks
    enabled_hooks: list[str] = []
    for event, hook_names in v1.get("enabled", {}).items():
        for name in hook_names:
            if name not in enabled_hooks:
                enabled_hooks.append(name)
    v2["global"] = {
        "skills": [],
        "hooks": enabled_hooks,
        "commands": [],
        "agents": [],
        "mcp": [],
    }

    # Migrate prompts and agents to global lists
    for name, info in v1.get("prompts", {}).items():
        if info.get("enabled", False):
            v2["global"]["commands"].append(name)

    for name, info in v1.get("agents", {}).items():
        if info.get("enabled", False):
            v2["global"]["agents"].append(name)

    # Migrate destinations -> tools config
    destinations = v1.get("destinations", {})
    tools_cfg: dict[str, Any] = {}
    tool_map = {
        "claude": {"enabled": True, "global_dir": "~/.claude"},
        "gemini": {"enabled": True, "global_dir": "~/.gemini"},
        "codex": {"enabled": True, "global_dir": "~/.codex"},
        "opencode": {"enabled": True, "global_dir": "~/.config/opencode"},
    }
    for tool_name, defaults in tool_map.items():
        tool_entry = dict(defaults)
        if tool_name in destinations:
            tool_entry["destinations"] = destinations[tool_name]
        tools_cfg[tool_name] = tool_entry
    v2["tools"] = tools_cfg

    # Migrate projects -> directories index
    directories: dict[str, dict[str, Any]] = {}
    for project_path in v1.get("projects", []):
        directories[project_path] = {}
    v2["directories"] = directories

    # Preserve env vars
    env = v1.get("env", {})
    if env:
        v2["env"] = env

    return v2


def run_migration(backup: bool = True) -> tuple[bool, str]:
    """Run the full migration process.

    Args:
        backup: Whether to create a backup of config.json.

    Returns:
        Tuple of (success, message).
    """
    v1_path = detect_v1_config()
    if v1_path is None:
        return False, "No v1 config.json found"

    v2_path = v2_config.get_global_config_path()
    if v2_path.exists():
        return False, f"v2 config already exists at {v2_path}"

    try:
        v1_data = load_v1_config(v1_path)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"Failed to read v1 config: {e}"

    v2_data = migrate_config(v1_data)

    # Backup original
    if backup:
        backup_path = v1_path.with_suffix(".json.v1-backup")
        shutil.copy2(v1_path, backup_path)

    # Save v2 config
    v2_config.save_global_config(v2_data)

    # Ensure registry directories exist
    v2_config.ensure_v2_dirs(v2_data)

    return True, f"Migrated to {v2_path}"
