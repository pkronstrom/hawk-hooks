"""MCP action dispatch — testable without FastMCP.

All actions return plain dicts. The MCP server wrapper calls handle_action()
and returns the result directly (FastMCP serializes it).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from . import v2_config
from .registry import Registry
from .types import ComponentType, Tool

# ── Valid values ─────────────────────────────────────────────────────────

VALID_TYPES = {ct.value for ct in ComponentType}
VALID_TOOLS = {t.value for t in Tool}

# ── Action registry (for describe) ──────────────────────────────────────

ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "describe": {
        "description": "Describe available actions and their parameters",
        "params": {
            "action_name": {"type": "string", "required": False,
                            "description": "Action name to describe in detail"},
        },
    },
    "list": {
        "description": "List registry contents with enabled/disabled state",
        "params": {
            "type": {"type": "string", "required": False,
                     "enum": sorted(VALID_TYPES),
                     "description": "Filter by component type"},
        },
    },
    "status": {
        "description": "Show enabled components, installed tools, and sync state",
        "params": {
            "dir": {"type": "string", "required": False,
                    "description": "Project directory (default: global scope)"},
        },
    },
    "list_packages": {
        "description": "List installed packages",
        "params": {},
    },
    "add": {
        "description": "Register a component. Supports file path OR inline content.",
        "params": {
            "type": {"type": "string", "required": True, "enum": sorted(VALID_TYPES),
                     "description": "Component type"},
            "path": {"type": "string", "required": False,
                     "description": "Absolute path to source file/dir"},
            "content": {"type": "string", "required": False,
                        "description": "Inline content (alternative to path)"},
            "name": {"type": "string", "required": False,
                     "description": "Name in registry (required with content)"},
            "force": {"type": "boolean", "required": False, "default": False,
                      "description": "Replace if exists"},
            "enable": {"type": "boolean", "required": False, "default": False,
                       "description": "Enable after adding"},
            "sync": {"type": "boolean", "required": False, "default": False,
                     "description": "Sync to tools after adding"},
            "dir": {"type": "string", "required": False,
                    "description": "Enable in this dir's config instead of global"},
        },
    },
    "remove": {
        "description": "Remove a component from the registry",
        "params": {
            "type": {"type": "string", "required": True, "enum": sorted(VALID_TYPES)},
            "name": {"type": "string", "required": True},
            "sync": {"type": "boolean", "required": False, "default": False},
        },
    },
    "enable": {
        "description": "Enable a component or package",
        "params": {
            "target": {"type": "string", "required": True,
                       "description": "registry-dir/name (e.g. skills/my-skill.md), package name, package/type, or bare name"},
            "dir": {"type": "string", "required": False},
            "sync": {"type": "boolean", "required": False, "default": False},
        },
    },
    "disable": {
        "description": "Disable a component or package",
        "params": {
            "target": {"type": "string", "required": True,
                       "description": "registry-dir/name (e.g. skills/my-skill.md), package name, package/type, or bare name"},
            "dir": {"type": "string", "required": False},
            "sync": {"type": "boolean", "required": False, "default": False},
        },
    },
    "sync": {
        "description": "Sync enabled components to tool configs",
        "params": {
            "dir": {"type": "string", "required": False},
            "tool": {"type": "string", "required": False, "enum": sorted(VALID_TOOLS)},
            "force": {"type": "boolean", "required": False, "default": False},
            "dry_run": {"type": "boolean", "required": False, "default": False},
        },
    },
    "download": {
        "description": "Download and install a package from a git URL",
        "params": {
            "url": {"type": "string", "required": True},
            "select_all": {"type": "boolean", "required": False, "default": True,
                           "description": "Install all items (default true for MCP)"},
            "replace": {"type": "boolean", "required": False, "default": False},
            "name": {"type": "string", "required": False},
            "enable": {"type": "boolean", "required": False, "default": False},
            "sync": {"type": "boolean", "required": False, "default": False},
        },
    },
    "update": {
        "description": "Update installed packages from their sources",
        "params": {
            "package": {"type": "string", "required": False},
            "check": {"type": "boolean", "required": False, "default": False},
            "force": {"type": "boolean", "required": False, "default": False},
            "prune": {"type": "boolean", "required": False, "default": False},
        },
    },
    "remove_package": {
        "description": "Remove an installed package and its components",
        "params": {
            "name": {"type": "string", "required": True},
        },
    },
}


# ── Context helper ───────────────────────────────────────────────────────

def _build_context(dir_param: str | None = None) -> dict[str, Any]:
    """Build the CWD context hint block."""
    cwd = os.getcwd()
    ctx: dict[str, Any] = {"cwd": cwd}

    registered = v2_config.get_registered_directories()
    if cwd in registered:
        ctx["cwd_registered"] = True
        config_path = v2_config.get_dir_config_path(Path(cwd))
        ctx["local_config"] = str(config_path)
        if not dir_param:
            ctx["hint"] = (
                f"Local hawk config exists — pass dir='{cwd}' to target it"
            )
    else:
        ctx["cwd_registered"] = False

    return ctx


# ── Validation helpers ───────────────────────────────────────────────────

def _validate_component_type(value: str) -> ComponentType:
    if value == "command":
        return ComponentType.PROMPT
    if value not in VALID_TYPES:
        return _error_type(value)
    return ComponentType(value)


def _error_type(value: str) -> Any:
    """Raise a descriptive ValueError for invalid type."""
    raise ValueError(
        f"Parameter 'type' must be one of: {', '.join(sorted(VALID_TYPES))} (got '{value}')"
    )


def _require(data: dict, key: str) -> Any:
    """Get a required param or raise ValueError."""
    val = data.get(key)
    if val is None:
        raise ValueError(f"Missing required parameter: '{key}'")
    return val


# ── Enable/disable helpers (reused from cli.py logic) ────────────────────

def _resolve_enable_targets(target: str) -> list[tuple[ComponentType, str]]:
    """Resolve an enable/disable target string to (ComponentType, name) pairs."""
    dir_to_ct: dict[str, ComponentType] = {}
    for ct in ComponentType:
        dir_to_ct[ct.registry_dir] = ct

    registry = Registry(v2_config.get_registry_path())

    if "/" in target:
        type_part, name_part = target.split("/", 1)
        if type_part in dir_to_ct and name_part:
            ct = dir_to_ct[type_part]
            if not registry.has(ct, name_part):
                raise ValueError(f"'{target}' not found in registry")
            return [(ct, name_part)]

        packages = v2_config.load_packages()
        if type_part in packages:
            # package/type format
            target_ct = dir_to_ct.get(name_part)
            if target_ct is None:
                for ct in ComponentType:
                    if name_part == ct.value:
                        target_ct = ct
                        break
            if target_ct is not None:
                pkg_items = v2_config.list_package_items(type_part)
                filtered = [
                    (ComponentType(t), n) for t, n in pkg_items
                    if ComponentType(t) == target_ct
                ]
                if not filtered:
                    raise ValueError(f"No {name_part} items in package '{type_part}'")
                return filtered

        raise ValueError(
            f"Cannot resolve '{target}'. Use type/name, package name, or package/type."
        )

    # Package name?
    packages = v2_config.load_packages()
    if target in packages:
        pkg_items = v2_config.list_package_items(target)
        if not pkg_items:
            raise ValueError(f"Package '{target}' has no items")
        return [(ComponentType(t), n) for t, n in pkg_items]

    # Bare name search
    all_items = registry.list_flat()
    matches = [(ct, n) for ct, n in all_items if n == target]
    if len(matches) == 1:
        return matches
    elif len(matches) > 1:
        locations = ", ".join(f"{ct.registry_dir}/{n}" for ct, n in matches)
        raise ValueError(f"Ambiguous name '{target}' found in: {locations}")
    else:
        raise ValueError(f"'{target}' not found in registry")


def _enable_items(
    items: list[tuple[ComponentType, str]],
    cfg: dict,
    section_key: str = "global",
) -> list[str]:
    """Enable items in a config section. Returns newly enabled names."""
    section = cfg.get(section_key, {})
    newly_enabled = []
    for ct, name in items:
        field = ct.registry_dir
        enabled = section.get(field, [])
        if name not in enabled:
            enabled.append(name)
            section[field] = enabled
            newly_enabled.append(f"{ct.registry_dir}/{name}")
    cfg[section_key] = section
    return newly_enabled


def _disable_items(
    items: list[tuple[ComponentType, str]],
    cfg: dict,
    section_key: str = "global",
) -> list[str]:
    """Disable items in a config section. Returns newly disabled names."""
    section = cfg.get(section_key, {})
    newly_disabled = []
    for ct, name in items:
        field = ct.registry_dir
        enabled = section.get(field, [])
        if name in enabled:
            enabled.remove(name)
            section[field] = enabled
            newly_disabled.append(f"{ct.registry_dir}/{name}")
    cfg[section_key] = section
    return newly_disabled


# ── Sync helper ──────────────────────────────────────────────────────────

def _run_sync(
    dir_param: str | None = None,
    tool_param: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run sync and return structured results, nested by scope then tool."""
    from .v2_sync import sync_all, sync_directory

    tools = [Tool(tool_param)] if tool_param else None

    if dir_param:
        project_dir = Path(dir_param).resolve()
        results = sync_directory(project_dir, tools=tools, dry_run=dry_run, force=force)
        raw = {str(project_dir): results}
    else:
        raw = sync_all(tools=tools, dry_run=dry_run, force=force)

    formatted: dict[str, Any] = {}
    for scope_key, result_list in raw.items():
        scope_results: dict[str, Any] = {}
        for sr in result_list:
            scope_results[sr.tool] = {
                "linked": sr.linked,
                "unlinked": sr.unlinked,
                "skipped": sr.skipped,
                "errors": sr.errors,
            }
        formatted[scope_key] = scope_results
    return formatted


# ── Main dispatch ────────────────────────────────────────────────────────

async def handle_action(data: dict[str, Any]) -> dict[str, Any]:
    """Dispatch an MCP action and return a structured result dict."""
    action = data.get("action")
    if not action:
        return {"error": "Missing 'action' parameter"}

    try:
        if action == "describe":
            return _action_describe(data)
        elif action == "list":
            return _action_list(data)
        elif action == "status":
            return _action_status(data)
        elif action == "list_packages":
            return _action_list_packages(data)
        elif action == "add":
            return _action_add(data)
        elif action == "remove":
            return _action_remove(data)
        elif action == "enable":
            return _action_enable(data)
        elif action == "disable":
            return _action_disable(data)
        elif action == "sync":
            return _action_sync(data)
        elif action == "download":
            return _action_download(data)
        elif action == "update":
            return _action_update(data)
        elif action == "remove_package":
            return _action_remove_package(data)
        else:
            return {
                "error": f"Unknown action: '{action}'",
                "hint": f"Available actions: {', '.join(sorted(ACTION_SCHEMAS.keys()))}",
            }
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Internal error: {e}"}


# ── Action implementations ───────────────────────────────────────────────

def _action_describe(data: dict) -> dict:
    action_name = data.get("action_name")
    if action_name:
        schema = ACTION_SCHEMAS.get(action_name)
        if not schema:
            return {
                "error": f"Unknown action: '{action_name}'",
                "hint": f"Available: {', '.join(sorted(ACTION_SCHEMAS.keys()))}",
            }
        return {"action": action_name, **schema}

    return {
        "actions": {
            name: schema["description"]
            for name, schema in ACTION_SCHEMAS.items()
        },
    }


def _action_list(data: dict) -> dict:
    registry = Registry(v2_config.get_registry_path())
    cfg = v2_config.load_global_config()
    global_section = cfg.get("global", {})

    type_filter = data.get("type")
    if type_filter:
        ct = _validate_component_type(type_filter)
        contents = registry.list(ct)
    else:
        contents = registry.list()

    # Build enriched list with enabled state + package info
    packages = v2_config.load_packages()
    pkg_owner: dict[tuple[str, str], str] = {}
    for pkg_name, pkg_data in packages.items():
        for item in pkg_data.get("items", []):
            t, n = item.get("type"), item.get("name")
            if t and n:
                pkg_owner[(t, n)] = pkg_name

    # Check dir-scoped enabled state
    dir_param = data.get("dir")
    dir_enabled: dict[str, list[str]] = {}
    if dir_param:
        dir_config = v2_config.load_dir_config(Path(dir_param).resolve())
        if dir_config:
            dir_section = dir_config.get("global", dir_config)
            for ct in ComponentType:
                dir_enabled[ct.registry_dir] = dir_section.get(ct.registry_dir, [])

    components: dict[str, list[dict]] = {}
    for ct, names in contents.items():
        items = []
        field = ct.registry_dir
        global_enabled = global_section.get(field, [])
        for name in names:
            entry: dict[str, Any] = {
                "name": name,
                "enabled_global": name in global_enabled,
            }
            if dir_param:
                entry["enabled_local"] = name in dir_enabled.get(field, [])
            pkg = pkg_owner.get((ct.value, name))
            if pkg:
                entry["package"] = pkg
            items.append(entry)
        if items:
            components[field] = items

    return {"components": components, "context": _build_context(dir_param)}


def _action_status(data: dict) -> dict:
    from .adapters import get_adapter
    from .resolver import resolve
    from .v2_sync import count_unsynced_targets

    cfg = v2_config.load_global_config()
    dir_param = data.get("dir")

    if dir_param:
        from .scope_resolution import build_resolver_dir_chain
        project_dir = Path(dir_param).resolve()
        dir_chain = build_resolver_dir_chain(project_dir, cfg=cfg)
        resolved = resolve(cfg, dir_chain=dir_chain)
        scope = str(project_dir)
    else:
        resolved = resolve(cfg)
        scope = "global"

    enabled: dict[str, list[str]] = {}
    for field in ("skills", "hooks", "prompts", "agents", "mcp"):
        items = getattr(resolved, field)
        if items:
            enabled[field] = items

    tools_status: dict[str, dict] = {}
    for tool in Tool.all():
        adapter = get_adapter(tool)
        tool_cfg = cfg.get("tools", {}).get(str(tool), {})
        tools_status[str(tool)] = {
            "installed": adapter.detect_installed(),
            "enabled": tool_cfg.get("enabled", True),
        }

    unsynced, total = count_unsynced_targets(
        project_dir=Path(dir_param).resolve() if dir_param else None,
        include_global=True,
        only_installed=True,
    )

    result: dict[str, Any] = {
        "scope": scope,
        "enabled": enabled,
        "tools": tools_status,
        "unsynced_count": unsynced,
        "context": _build_context(dir_param),
    }

    # Include profile if applicable
    if dir_param:
        dir_config = v2_config.load_dir_config(Path(dir_param).resolve())
        if dir_config and dir_config.get("profile"):
            result["profile"] = dir_config["profile"]

    return result


def _action_list_packages(data: dict) -> dict:
    packages = v2_config.load_packages()
    result = []
    for name, pkg_data in sorted(packages.items()):
        entry: dict[str, Any] = {
            "name": name,
            "items_count": len(pkg_data.get("items", [])),
            "installed": pkg_data.get("installed", "unknown"),
        }
        if pkg_data.get("url"):
            entry["url"] = pkg_data["url"]
            entry["source"] = "git"
        elif pkg_data.get("path"):
            entry["path"] = pkg_data["path"]
            entry["source"] = "local"
        else:
            entry["source"] = "manual"
        result.append(entry)
    return {"packages": result}


def _action_add(data: dict) -> dict:
    type_str = _require(data, "type")
    ct = _validate_component_type(type_str)

    path_param = data.get("path")
    content_param = data.get("content")
    name_param = data.get("name")
    force = bool(data.get("force", False))
    do_enable = bool(data.get("enable", False))
    do_sync = bool(data.get("sync", False))
    dir_param = data.get("dir")

    if path_param and content_param:
        raise ValueError("Provide 'path' or 'content', not both")
    if not path_param and not content_param:
        raise ValueError("One of 'path' or 'content' is required")
    if content_param and not name_param:
        raise ValueError("'name' is required when using 'content'")

    registry = Registry(v2_config.get_registry_path())
    registry.ensure_dirs()

    # Resolve source
    tmp_dir = None
    try:
        if content_param:
            tmp_dir = Path(tempfile.mkdtemp(prefix="hawk-mcp-"))
            source = tmp_dir / name_param
            source.write_text(content_param)
            name = name_param
        else:
            source = Path(path_param).resolve()
            if not source.exists():
                raise ValueError(f"Path does not exist: {path_param}")
            name = name_param or source.name

        # Handle clash
        if registry.detect_clash(ct, name):
            if not force:
                raise ValueError(
                    f"{ct.value}/{name} already exists in registry. "
                    "Pass force=true to replace."
                )
            reg_path = registry.replace(ct, name, source)
        else:
            reg_path = registry.add(ct, name, source)
    finally:
        if tmp_dir and tmp_dir.exists():
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    result: dict[str, Any] = {
        "added": name,
        "type": ct.value,
        "registry_path": str(reg_path),
    }

    # Enable
    if do_enable:
        if dir_param:
            project_dir = Path(dir_param).resolve()
            cfg = v2_config.load_dir_config(project_dir) or {}
            _enable_items([(ct, name)], cfg, section_key="global")
            v2_config.save_dir_config(project_dir, cfg)
        else:
            cfg = v2_config.load_global_config()
            _enable_items([(ct, name)], cfg, section_key="global")
            v2_config.save_global_config(cfg)
        result["enabled"] = True

    # Sync
    if do_sync:
        result["sync_results"] = _run_sync(dir_param=dir_param, force=True)

    result["context"] = _build_context(dir_param)
    return result


def _action_remove(data: dict) -> dict:
    type_str = _require(data, "type")
    ct = _validate_component_type(type_str)
    name = _require(data, "name")
    do_sync = bool(data.get("sync", False))

    registry = Registry(v2_config.get_registry_path())
    if not registry.remove(ct, name):
        raise ValueError(f"{ct.value}/{name} not found in registry")

    # Remove from global config enabled lists
    cfg = v2_config.load_global_config()
    global_section = cfg.get("global", {})
    field = ct.registry_dir
    enabled = global_section.get(field, [])
    if name in enabled:
        enabled.remove(name)
        global_section[field] = enabled
        cfg["global"] = global_section
        v2_config.save_global_config(cfg)

    # Remove from all registered directory configs
    for dir_path_str in v2_config.get_registered_directories():
        dir_cfg = v2_config.load_dir_config(Path(dir_path_str))
        if dir_cfg is None:
            continue
        dir_section = dir_cfg.get("global", dir_cfg)
        dir_enabled = dir_section.get(field, [])
        if name in dir_enabled:
            dir_enabled.remove(name)
            dir_section[field] = dir_enabled
            if "global" in dir_cfg:
                dir_cfg["global"] = dir_section
            v2_config.save_dir_config(Path(dir_path_str), dir_cfg)

    result: dict[str, Any] = {"removed": f"{ct.value}/{name}"}

    if do_sync:
        result["sync_results"] = _run_sync(force=True)

    result["context"] = _build_context()
    return result


def _action_enable(data: dict) -> dict:
    target = _require(data, "target")
    dir_param = data.get("dir")
    do_sync = bool(data.get("sync", False))

    items = _resolve_enable_targets(target)

    if dir_param:
        project_dir = Path(dir_param).resolve()
        cfg = v2_config.load_dir_config(project_dir) or {}
        newly = _enable_items(items, cfg, section_key="global")
        v2_config.save_dir_config(project_dir, cfg)
        scope = str(project_dir)
    else:
        cfg = v2_config.load_global_config()
        newly = _enable_items(items, cfg, section_key="global")
        v2_config.save_global_config(cfg)
        scope = "global"

    result: dict[str, Any] = {"enabled": newly, "scope": scope}

    if do_sync:
        result["sync_results"] = _run_sync(dir_param=dir_param, force=True)

    result["context"] = _build_context(dir_param)
    return result


def _action_disable(data: dict) -> dict:
    target = _require(data, "target")
    dir_param = data.get("dir")
    do_sync = bool(data.get("sync", False))

    items = _resolve_enable_targets(target)

    if dir_param:
        project_dir = Path(dir_param).resolve()
        cfg = v2_config.load_dir_config(project_dir) or {}
        newly = _disable_items(items, cfg, section_key="global")
        v2_config.save_dir_config(project_dir, cfg)
        scope = str(project_dir)
    else:
        cfg = v2_config.load_global_config()
        newly = _disable_items(items, cfg, section_key="global")
        v2_config.save_global_config(cfg)
        scope = "global"

    result: dict[str, Any] = {"disabled": newly, "scope": scope}

    if do_sync:
        result["sync_results"] = _run_sync(dir_param=dir_param, force=True)

    result["context"] = _build_context(dir_param)
    return result


def _action_sync(data: dict) -> dict:
    dir_param = data.get("dir")
    tool_param = data.get("tool")
    force = bool(data.get("force", False))
    dry_run = bool(data.get("dry_run", False))

    if tool_param and tool_param not in VALID_TOOLS:
        raise ValueError(
            f"Parameter 'tool' must be one of: {', '.join(sorted(VALID_TOOLS))} "
            f"(got '{tool_param}')"
        )

    results = _run_sync(dir_param, tool_param, force, dry_run)
    return {
        "dry_run": dry_run,
        "results": results,
        "context": _build_context(dir_param),
    }


def _action_download(data: dict) -> dict:
    from .download_service import download_and_install

    url = _require(data, "url")
    select_all = bool(data.get("select_all", True))  # default true for MCP
    replace = bool(data.get("replace", False))
    name = data.get("name")
    do_enable = bool(data.get("enable", False))
    do_sync = bool(data.get("sync", False))

    logs: list[str] = []
    result_obj = download_and_install(
        url,
        select_all=select_all,
        replace=replace,
        name=name,
        log=logs.append,
    )

    result: dict[str, Any] = {
        "success": result_obj.success,
        "added": result_obj.added,
        "skipped": result_obj.skipped,
        "package_name": result_obj.package_name,
        "log": logs,
    }

    if result_obj.clashes:
        result["clashes"] = result_obj.clashes
    if result_obj.error:
        result["error"] = result_obj.error

    # Enable added items
    if do_enable and result_obj.added:
        cfg = v2_config.load_global_config()
        global_section = cfg.get("global", {})
        enabled_count = 0
        for item_key in result_obj.added:
            parts = item_key.split("/", 1)
            if len(parts) != 2:
                continue
            type_str, item_name = parts
            try:
                ct = ComponentType(type_str)
            except ValueError:
                continue
            field = ct.registry_dir
            enabled = global_section.get(field, [])
            if item_name not in enabled:
                enabled.append(item_name)
                global_section[field] = enabled
                enabled_count += 1
        if enabled_count:
            cfg["global"] = global_section
            v2_config.save_global_config(cfg)
            result["enabled_count"] = enabled_count

    if do_sync:
        result["sync_results"] = _run_sync(force=True)

    result["context"] = _build_context()
    return result


def _action_update(data: dict) -> dict:
    from .package_service import (
        PackageNotFoundError,
        PackageUpdateFailedError,
        update_packages,
    )

    package = data.get("package")
    check = bool(data.get("check", False))
    force = bool(data.get("force", False))
    prune = bool(data.get("prune", False))

    logs: list[str] = []
    try:
        report = update_packages(
            package=package,
            check=check,
            force=force,
            prune=prune,
            sync_on_change=True,
            log=logs.append,
        )
        return {
            "any_changes": report.any_changes,
            "check_only": report.check_only,
            "up_to_date": report.up_to_date,
            "log": logs,
        }
    except PackageNotFoundError as e:
        return {
            "error": f"Package not found: {e.package_name}",
            "installed": e.installed,
        }
    except PackageUpdateFailedError as e:
        return {
            "error": str(e),
            "failed_packages": e.failed_packages,
            "log": logs,
        }


def _action_remove_package(data: dict) -> dict:
    from .package_service import PackageNotFoundError, remove_package

    name = _require(data, "name")
    logs: list[str] = []

    try:
        report = remove_package(name, sync_after=True, log=logs.append)
        return {
            "removed": name,
            "removed_items": report.removed_items,
            "log": logs,
        }
    except PackageNotFoundError as e:
        return {
            "error": f"Package not found: {e.package_name}",
            "installed": e.installed,
        }
