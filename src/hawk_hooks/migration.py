"""v1 JSON -> v2 YAML migration.

Converts the existing config.json format to the new config.yaml format,
preserving all user settings.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

from . import config


def detect_v1_config() -> Path | None:
    """Check if a v1 config.json exists. Returns path or None."""
    config_path = config.get_config_dir() / "config.json"
    if config_path.exists():
        return config_path
    return None


def load_v1_config(path: Path) -> dict[str, Any]:
    """Load a v1 config.json file."""
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("v1 config must be a JSON object")
    return data


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
    if not isinstance(v1, dict):
        raise ValueError("v1 config must be a mapping")

    v2: dict[str, Any] = copy.deepcopy(config.DEFAULT_GLOBAL_CONFIG)
    v2["debug"] = bool(v1.get("debug", False))

    # Migrate enabled hooks -> global.hooks
    enabled_hooks: list[str] = []
    enabled_cfg = v1.get("enabled", {})
    if not isinstance(enabled_cfg, dict):
        enabled_cfg = {}
    for _event, hook_names in enabled_cfg.items():
        if not isinstance(hook_names, list):
            continue
        for name in hook_names:
            if isinstance(name, str) and name not in enabled_hooks:
                enabled_hooks.append(name)
    v2["global"]["hooks"] = enabled_hooks
    v2["global"]["prompts"] = []
    v2["global"]["agents"] = []
    v2["global"]["skills"] = []
    v2["global"]["mcp"] = []

    # Migrate prompts and agents to global lists
    prompts_cfg = v1.get("prompts", {})
    if not isinstance(prompts_cfg, dict):
        prompts_cfg = {}
    for name, info in prompts_cfg.items():
        if isinstance(name, str) and isinstance(info, dict) and info.get("enabled", False):
            v2["global"]["prompts"].append(name)

    agents_cfg = v1.get("agents", {})
    if not isinstance(agents_cfg, dict):
        agents_cfg = {}
    for name, info in agents_cfg.items():
        if isinstance(name, str) and isinstance(info, dict) and info.get("enabled", False):
            v2["global"]["agents"].append(name)

    # Migrate destinations -> tools config
    destinations = v1.get("destinations", {})
    if not isinstance(destinations, dict):
        destinations = {}
    tools_cfg: dict[str, Any] = {}
    for tool_name, defaults in config.DEFAULT_GLOBAL_CONFIG.get("tools", {}).items():
        tool_entry = copy.deepcopy(defaults)
        tool_destinations = destinations.get(tool_name)
        if isinstance(tool_destinations, dict):
            tool_dests = dict(tool_destinations)
            if "commands" in tool_dests and "prompts" not in tool_dests:
                tool_dests["prompts"] = tool_dests.pop("commands")
            tool_entry["destinations"] = tool_dests
        tools_cfg[tool_name] = tool_entry
    v2["tools"] = tools_cfg

    # Migrate projects -> directories index
    directories: dict[str, dict[str, Any]] = {}
    projects = v1.get("projects", [])
    if isinstance(projects, list):
        for project_path in projects:
            if isinstance(project_path, str):
                directories[project_path] = {}
    v2["directories"] = directories

    # Preserve env vars
    env = v1.get("env", {})
    if isinstance(env, dict) and env:
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

    v2_path = config.get_global_config_path()
    if v2_path.exists():
        return False, f"v2 config already exists at {v2_path}"

    try:
        v1_data = load_v1_config(v1_path)
    except (ValueError, json.JSONDecodeError, OSError) as e:
        return False, f"Failed to read v1 config: {e}"

    try:
        v2_data = migrate_config(v1_data)
    except (TypeError, ValueError) as e:
        return False, f"Failed to migrate v1 config: {e}"

    # Backup original
    if backup:
        backup_path = v1_path.with_suffix(".json.v1-backup")
        try:
            shutil.copy2(v1_path, backup_path)
        except OSError as e:
            return False, f"Failed to backup v1 config: {e}"

    # Save v2 config
    try:
        config.save_global_config(v2_data)

        # Ensure registry directories exist
        config.ensure_v2_dirs(v2_data)
    except OSError as e:
        return False, f"Failed to write v2 config: {e}"

    return True, f"Migrated to {v2_path}"
