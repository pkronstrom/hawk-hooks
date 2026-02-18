"""v2 YAML-based configuration management.

Manages three config layers:
1. Global: ~/.config/hawk-hooks/config.yaml
2. Profile: ~/.config/hawk-hooks/profiles/<name>.yaml
3. Directory: <project>/.hawk/config.yaml

Also manages the package index (packages.yaml) for tracking
downloaded packages and their items.
"""

from __future__ import annotations

import copy
import hashlib
import os
from datetime import date
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
        "prompts": [],
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


def get_config_chain(from_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Find registered dirs that are parents of from_dir, plus from_dir itself.

    Uses directory index (no filesystem walk-up). Returns outermost-first.
    Each entry is (dir_path, dir_config).
    """
    dirs = get_registered_directories()
    chain: list[tuple[Path, dict[str, Any]]] = []
    from_resolved = from_dir.resolve()

    for dir_path_str in dirs:
        dir_path = Path(dir_path_str)
        try:
            if from_resolved.is_relative_to(dir_path):
                config = load_dir_config(dir_path)
                if config is not None:
                    chain.append((dir_path, config))
        except (ValueError, TypeError):
            continue

    # Sort outermost first (fewest path parts)
    chain.sort(key=lambda x: len(x[0].parts))
    return chain


def auto_register_if_needed(cwd: Path) -> None:
    """If cwd has .hawk/config.yaml but isn't registered, register it."""
    cwd = cwd.resolve()
    config_path = get_dir_config_path(cwd)
    if not config_path.exists():
        return

    dirs = get_registered_directories()
    if str(cwd) not in dirs:
        register_directory(cwd)


def prune_stale_directories() -> list[str]:
    """Remove entries where .hawk/config.yaml no longer exists. Returns pruned paths."""
    dirs = get_registered_directories()
    stale: list[str] = []

    for dir_path_str in list(dirs.keys()):
        config_path = get_dir_config_path(Path(dir_path_str))
        if not config_path.exists():
            stale.append(dir_path_str)

    if stale:
        cfg = load_global_config()
        for path in stale:
            cfg.get("directories", {}).pop(path, None)
        save_global_config(cfg)

    return stale


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


# ---------------------------------------------------------------------------
# Package index (packages.yaml)
# ---------------------------------------------------------------------------

def get_packages_path() -> Path:
    """Get the path to the packages index file."""
    return get_config_dir() / "packages.yaml"


def load_packages() -> dict[str, Any]:
    """Load the packages index.

    Returns the inner ``packages`` dict (mapping package name to metadata).
    Returns empty dict if file doesn't exist or is invalid.
    """
    path = get_packages_path()
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data.get("packages", {})
        return {}
    except (FileNotFoundError, yaml.YAMLError, OSError):
        return {}


def save_packages(packages: dict[str, Any]) -> None:
    """Save the packages index.

    Args:
        packages: The packages dict (name -> metadata).
    """
    path = get_packages_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump({"packages": packages}, f, default_flow_style=False, sort_keys=False)


def get_package_for_item(component_type: str, name: str) -> str | None:
    """Reverse lookup: find which package owns a given item.

    Args:
        component_type: The component type value (e.g. "skill", "command").
        name: The item name.

    Returns:
        Package name, or None if not in any package.
    """
    packages = load_packages()
    for pkg_name, pkg_data in packages.items():
        for item in pkg_data.get("items", []):
            if item.get("type") == component_type and item.get("name") == name:
                return pkg_name
    return None


def list_package_items(package_name: str) -> list[tuple[str, str]]:
    """List all items belonging to a package.

    Returns list of (type, name) tuples.
    """
    packages = load_packages()
    pkg = packages.get(package_name, {})
    return [(item["type"], item["name"]) for item in pkg.get("items", [])]


def remove_package(package_name: str) -> bool:
    """Remove a package entry from the index.

    Returns True if removed, False if not found.
    """
    packages = load_packages()
    if package_name not in packages:
        return False
    del packages[package_name]
    save_packages(packages)
    return True


def package_name_from_url(url: str) -> str:
    """Derive a package name from a git URL.

    Takes the last path segment, strips .git suffix.
    """
    # Strip trailing slashes and .git
    name = url.rstrip("/")
    if name.endswith(".git"):
        name = name[:-4]
    # Take last segment
    name = name.rsplit("/", 1)[-1]
    return name or "unknown"


def record_package(
    name: str,
    url: str,
    commit: str,
    items: list[dict[str, str]],
) -> None:
    """Record or update a package in the index.

    Args:
        name: Package name.
        url: Git clone URL.
        commit: HEAD commit hash.
        items: List of dicts with "type", "name", "hash" keys.
    """
    packages = load_packages()
    packages[name] = {
        "url": url,
        "installed": date.today().isoformat(),
        "commit": commit,
        "items": items,
    }
    save_packages(packages)


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------

def hash_registry_item(path: Path) -> str:
    """Compute a content hash for a registry item (file or directory).

    For files: SHA-256 of file contents, truncated to 8 hex chars.
    For directories: SHA-256 of sorted (relative_path, file_hash) pairs.

    Returns 8-char hex string.
    """
    if path.is_file():
        return _hash_file(path)
    elif path.is_dir():
        return _hash_dir(path)
    return "00000000"


def _hash_file(path: Path) -> str:
    """SHA-256 of file contents, truncated to 8 hex chars."""
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except OSError:
        return "00000000"
    return h.hexdigest()[:8]


def _hash_dir(path: Path) -> str:
    """SHA-256 of sorted (relative_path, file_hash) pairs."""
    h = hashlib.sha256()
    entries: list[tuple[str, str]] = []
    for child in sorted(path.rglob("*")):
        if child.is_file() and not child.name.startswith("."):
            rel = str(child.relative_to(path))
            file_hash = _hash_file(child)
            entries.append((rel, file_hash))
    for rel, fh in entries:
        h.update(f"{rel}:{fh}\n".encode())
    return h.hexdigest()[:8]
