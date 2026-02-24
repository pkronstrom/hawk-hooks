"""One-shot migration: commands schema -> prompts schema."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

from . import config


def _merge_unique(existing: list[str], incoming: list[str]) -> list[str]:
    seen = set(existing)
    merged = list(existing)
    for item in incoming:
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return merged


def _normalize_section(value: Any) -> tuple[list[str], list[str]]:
    if isinstance(value, dict):
        enabled = list(value.get("enabled", []))
        disabled = list(value.get("disabled", []))
        return enabled, disabled
    if isinstance(value, list):
        return list(value), []
    return [], []


def _normalize_override_section(value: Any) -> tuple[list[str], list[str]]:
    if isinstance(value, dict):
        extra = value.get("extra")
        exclude = value.get("exclude")
        if isinstance(extra, list) or isinstance(exclude, list):
            return list(extra or []), list(exclude or [])
        # Fallback for malformed-but-mappable configs.
        return list(value.get("enabled", [])), list(value.get("disabled", []))
    if isinstance(value, list):
        return list(value), []
    return [], []


def _backup_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    backup_path = path.with_name(path.name + ".commands-to-prompts.bak")
    shutil.copy2(path, backup_path)


def _migrate_config_dict(cfg: dict[str, Any], changes: list[str]) -> bool:
    changed = False

    global_section = cfg.setdefault("global", {})
    had_global_commands = "commands" in global_section
    global_commands = list(global_section.pop("commands", []))
    global_prompts = list(global_section.get("prompts", []))

    if had_global_commands:
        merged = _merge_unique(global_prompts, global_commands)
        global_section["prompts"] = merged
        changes.append("migrated global.commands -> global.prompts")
        changed = True

    tools_cfg = cfg.get("tools", {})
    for tool_name, tool_cfg in tools_cfg.items():
        if not isinstance(tool_cfg, dict) or "commands" not in tool_cfg:
            continue

        cmd_section = tool_cfg.pop("commands")
        prompt_section = tool_cfg.get("prompts", {})

        cmd_extra, cmd_exclude = _normalize_override_section(cmd_section)
        prompt_extra, prompt_exclude = _normalize_override_section(prompt_section)

        tool_cfg["prompts"] = {
            "extra": _merge_unique(prompt_extra, cmd_extra),
            "exclude": _merge_unique(prompt_exclude, cmd_exclude),
        }

        changes.append(f"migrated tools.{tool_name}.commands -> tools.{tool_name}.prompts")
        changed = True

    return changed


def _migrate_dir_config(path: Path, changes: list[str], backup: bool) -> bool:
    dir_cfg = config.load_dir_config(path)
    if not dir_cfg:
        return False

    changed = False

    if "commands" in dir_cfg:
        cmd_enabled, cmd_disabled = _normalize_section(dir_cfg.pop("commands"))
        p_enabled, p_disabled = _normalize_section(dir_cfg.get("prompts", {}))

        dir_cfg["prompts"] = {
            "enabled": _merge_unique(p_enabled, cmd_enabled),
            "disabled": _merge_unique(p_disabled, cmd_disabled),
        }
        changed = True

    tools_cfg = dir_cfg.get("tools", {})
    if isinstance(tools_cfg, dict):
        for tool_name, tool_cfg in tools_cfg.items():
            if not isinstance(tool_cfg, dict) or "commands" not in tool_cfg:
                continue

            cmd_extra, cmd_exclude = _normalize_override_section(tool_cfg.pop("commands"))
            p_extra, p_exclude = _normalize_override_section(tool_cfg.get("prompts", {}))
            tool_cfg["prompts"] = {
                "extra": _merge_unique(p_extra, cmd_extra),
                "exclude": _merge_unique(p_exclude, cmd_exclude),
            }
            changed = True
            changes.append(
                f"migrated {path}/.hawk/config.yaml tools.{tool_name}.commands -> prompts"
            )

    if changed:
        if backup:
            _backup_file(config.get_dir_config_path(path))
        config.save_dir_config(path, dir_cfg)
        changes.append(f"migrated {path}/.hawk/config.yaml commands -> prompts")

    return changed


def _migrate_registry(cfg: dict[str, Any], changes: list[str]) -> bool:
    changed = False

    registry_path = config.get_registry_path(cfg)
    commands_dir = registry_path / "commands"
    prompts_dir = registry_path / "prompts"

    try:
        commands_exists = commands_dir.exists()
    except OSError:
        changes.append(f"skipped registry migration: cannot access {commands_dir}")
        return False

    if not commands_exists:
        return False

    try:
        prompts_dir.mkdir(parents=True, exist_ok=True)
        sources = sorted(commands_dir.iterdir())
    except OSError:
        changes.append(f"skipped registry migration: cannot modify {registry_path}")
        return False

    for src in sources:
        dst = prompts_dir / src.name
        if dst.exists():
            if src.is_dir():
                shutil.rmtree(src)
            else:
                src.unlink()
            changes.append(f"collision: kept prompts/{src.name}, dropped commands/{src.name}")
            changed = True
            continue

        shutil.move(str(src), str(dst))
        changes.append(f"moved registry/commands/{src.name} -> registry/prompts/{src.name}")
        changed = True

    try:
        if commands_dir.exists() and not any(commands_dir.iterdir()):
            commands_dir.rmdir()
    except OSError:
        # Best-effort cleanup; migration already completed for entries.
        pass

    return changed


def _migrate_packages(changes: list[str], backup: bool) -> bool:
    packages = config.load_packages()
    changed = False

    for pkg_data in packages.values():
        items = pkg_data.get("items", [])
        for item in items:
            if item.get("type") == "command":
                item["type"] = "prompt"
                changed = True

    if changed:
        if backup:
            _backup_file(config.get_packages_path())
        config.save_packages(packages)
        changes.append("rewrote packages item type command -> prompt")

    return changed


def _clear_resolved_cache(changes: list[str]) -> bool:
    cache_dir = config.get_config_dir() / "cache" / "resolved"
    if not cache_dir.exists():
        return False

    changed = False
    for entry in cache_dir.iterdir():
        if entry.is_file():
            entry.unlink()
            changed = True

    if changed:
        changes.append("cleared resolved cache")
    return changed


def _collect_check_messages(cfg: dict[str, Any]) -> list[str]:
    messages: list[str] = []

    global_section = cfg.get("global", {})
    if "commands" in global_section:
        messages.append("global.commands needs migration")

    for tool_name, tool_cfg in cfg.get("tools", {}).items():
        if isinstance(tool_cfg, dict) and "commands" in tool_cfg:
            messages.append(f"tools.{tool_name}.commands needs migration")

    for dir_path_str in cfg.get("directories", {}):
        dir_cfg = config.load_dir_config(Path(dir_path_str))
        if not dir_cfg:
            continue
        if "commands" in dir_cfg:
            messages.append(f"{dir_path_str}/.hawk/config.yaml commands needs migration")

    registry_path = config.get_registry_path(cfg)
    commands_dir = registry_path / "commands"
    try:
        if commands_dir.exists() and any(commands_dir.iterdir()):
            messages.append("registry/commands contains items")
    except OSError:
        messages.append(f"registry/commands is not accessible: {commands_dir}")

    packages = config.load_packages()
    for pkg_name, pkg_data in packages.items():
        for item in pkg_data.get("items", []):
            if item.get("type") == "command":
                messages.append(f"packages.yaml has command item in {pkg_name}")
                break

    return messages


def run_migrate_prompts(*, check_only: bool, backup: bool = True) -> tuple[bool, str]:
    """Run commands->prompts migration.

    Returns:
        tuple of (changed_or_needed, summary)
    """
    cfg = config.load_global_config()

    if check_only:
        messages = _collect_check_messages(cfg)
        if not messages:
            return False, "No changes needed."
        return True, "\n".join(messages)

    changes: list[str] = []
    changed = False

    config_path = config.get_global_config_path()
    if backup:
        _backup_file(config_path)

    cfg_to_save = copy.deepcopy(cfg)
    if _migrate_config_dict(cfg_to_save, changes):
        changed = True
        config.save_global_config(cfg_to_save)

    for dir_path_str in cfg_to_save.get("directories", {}):
        if _migrate_dir_config(Path(dir_path_str), changes, backup=backup):
            changed = True

    if _migrate_registry(cfg_to_save, changes):
        changed = True

    if _migrate_packages(changes, backup=backup):
        changed = True

    if _clear_resolved_cache(changes):
        changed = True

    if not changed:
        return False, "No changes needed."

    return True, "\n".join(changes)
