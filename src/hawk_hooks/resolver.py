"""Resolve the active component set from config layers.

Resolution order: global + profile + dir.enabled - dir.disabled + per-tool overrides

Supports both single dir_config (backward compat) and dir_chain (hierarchical).
"""

from __future__ import annotations

from typing import Any

from .types import ComponentType, ResolvedSet, Tool

COMPONENT_FIELDS = ["skills", "hooks", "agents", "mcp", "prompts"]


def _merge_list(base: list[str], add: list[str], remove: list[str]) -> list[str]:
    """Merge lists: base + add - remove, preserving order, no duplicates."""
    seen: set[str] = set()
    result: list[str] = []
    remove_set = set(remove)

    for item in base + add:
        if item not in seen and item not in remove_set:
            seen.add(item)
            result.append(item)

    return result


def _apply_profile(result: ResolvedSet, profile: dict[str, Any]) -> None:
    """Apply a profile layer to the result (adds only, no removes)."""
    for field_name in COMPONENT_FIELDS:
        current = getattr(result, field_name)
        additions = profile.get(field_name, [])
        if field_name == "prompts":
            # Backward compatibility: commands are merged into prompts.
            additions = _merge_list(list(additions), profile.get("commands", []), [])
        merged = _merge_list(current, additions, [])
        setattr(result, field_name, merged)


def _apply_dir_config(
    result: ResolvedSet, dir_config: dict[str, Any], tool: Tool | None = None
) -> None:
    """Apply a directory config layer (enabled/disabled + per-tool overrides)."""
    for field_name in COMPONENT_FIELDS:
        section = dir_config.get(field_name, {})
        if field_name == "prompts" and "commands" in dir_config:
            # Backward compatibility: commands sections migrate into prompts.
            section = _merge_legacy_sections(dir_config.get("commands", {}), section)
        if isinstance(section, dict):
            enabled = section.get("enabled", [])
            disabled = section.get("disabled", [])
        elif isinstance(section, list):
            enabled = section
            disabled = []
        else:
            continue

        current = getattr(result, field_name)
        merged = _merge_list(current, enabled, disabled)
        setattr(result, field_name, merged)

    # Per-tool overrides within dir_config
    if tool:
        tool_overrides = dir_config.get("tools", {}).get(str(tool), {})
        for field_name in COMPONENT_FIELDS:
            tool_section = tool_overrides.get(field_name, {})
            if field_name == "prompts" and "commands" in tool_overrides:
                tool_section = _merge_legacy_sections(tool_overrides.get("commands", {}), tool_section)
            if not isinstance(tool_section, dict):
                continue
            extra = tool_section.get("extra", [])
            exclude = tool_section.get("exclude", [])
            current = getattr(result, field_name)
            merged = _merge_list(current, extra, exclude)
            setattr(result, field_name, merged)


def resolve(
    global_config: dict[str, Any],
    profile: dict[str, Any] | None = None,
    dir_config: dict[str, Any] | None = None,
    dir_chain: list[tuple[dict[str, Any], dict[str, Any] | None]] | None = None,
    tool: Tool | None = None,
) -> ResolvedSet:
    """Compute the resolved set of active components.

    Args:
        global_config: The global config dict (has a "global" key with component lists).
        profile: Optional profile dict (has component list keys directly).
            Used with single dir_config for backward compat.
        dir_config: Optional per-directory config.
            Used for backward compat when dir_chain is not provided.
        dir_chain: Optional list of (config, profile) tuples for hierarchical resolution.
            When provided, dir_config and profile are ignored.
            Each tuple is (dir_config_dict, optional_profile_dict).
            Order: outermost first.
        tool: Optional tool for per-tool overrides from dir_config.

    Returns:
        ResolvedSet with the final lists.
    """
    # Start from global
    global_section = global_config.get("global", {})

    result = ResolvedSet(
        skills=list(global_section.get("skills", [])),
        hooks=list(global_section.get("hooks", [])),
        agents=list(global_section.get("agents", [])),
        mcp=list(global_section.get("mcp", [])),
        prompts=_merge_list(
            list(global_section.get("prompts", [])),
            list(global_section.get("commands", [])),
            [],
        ),
    )

    if dir_chain is not None:
        # Hierarchical resolution: iterate layers outermost → innermost
        for layer_config, layer_profile in dir_chain:
            if layer_profile:
                _apply_profile(result, layer_profile)
            _apply_dir_config(result, layer_config, tool)
    else:
        # Backward compat: single profile + dir_config
        if profile:
            _apply_profile(result, profile)
        if dir_config:
            _apply_dir_config(result, dir_config, tool)

    return result


def _merge_legacy_sections(legacy: Any, current: Any) -> dict[str, list[str]]:
    """Merge legacy commands-style section into prompts-style section."""
    current_enabled: list[str] = []
    current_disabled: list[str] = []
    if isinstance(current, dict):
        current_enabled = list(current.get("enabled", []))
        current_disabled = list(current.get("disabled", []))
    elif isinstance(current, list):
        current_enabled = list(current)

    legacy_enabled: list[str] = []
    legacy_disabled: list[str] = []
    if isinstance(legacy, dict):
        if isinstance(legacy.get("extra"), list) or isinstance(legacy.get("exclude"), list):
            legacy_enabled = list(legacy.get("extra", []))
            legacy_disabled = list(legacy.get("exclude", []))
        else:
            legacy_enabled = list(legacy.get("enabled", []))
            legacy_disabled = list(legacy.get("disabled", []))
    elif isinstance(legacy, list):
        legacy_enabled = list(legacy)

    return {
        "enabled": _merge_list(current_enabled, legacy_enabled, []),
        "disabled": _merge_list(current_disabled, legacy_disabled, []),
    }
