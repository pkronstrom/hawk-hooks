"""Resolve the active component set from config layers.

Resolution order: global + profile + dir.enabled - dir.disabled + per-tool overrides
"""

from __future__ import annotations

from typing import Any

from .types import ComponentType, ResolvedSet, Tool


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


def resolve(
    global_config: dict[str, Any],
    profile: dict[str, Any] | None = None,
    dir_config: dict[str, Any] | None = None,
    tool: Tool | None = None,
) -> ResolvedSet:
    """Compute the resolved set of active components.

    Args:
        global_config: The global config dict (has a "global" key with component lists).
        profile: Optional profile dict (has component list keys directly).
        dir_config: Optional per-directory config.
        tool: Optional tool for per-tool overrides from dir_config.

    Returns:
        ResolvedSet with the final lists.
    """
    # Start from global
    global_section = global_config.get("global", {})

    result = ResolvedSet(
        skills=list(global_section.get("skills", [])),
        hooks=list(global_section.get("hooks", [])),
        commands=list(global_section.get("commands", [])),
        agents=list(global_section.get("agents", [])),
        mcp=list(global_section.get("mcp", [])),
    )

    # Layer in profile
    if profile:
        result.skills = _merge_list(result.skills, profile.get("skills", []), [])
        result.hooks = _merge_list(result.hooks, profile.get("hooks", []), [])
        result.commands = _merge_list(result.commands, profile.get("commands", []), [])
        result.agents = _merge_list(result.agents, profile.get("agents", []), [])
        result.mcp = _merge_list(result.mcp, profile.get("mcp", []), [])

    # Layer in directory config (enabled/disabled)
    if dir_config:
        for field_name in ["skills", "hooks", "commands", "agents", "mcp"]:
            section = dir_config.get(field_name, {})
            if isinstance(section, dict):
                enabled = section.get("enabled", [])
                disabled = section.get("disabled", [])
            elif isinstance(section, list):
                # Simple list format means "these are enabled, nothing disabled"
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
            for field_name in ["skills", "hooks", "commands", "agents", "mcp"]:
                tool_section = tool_overrides.get(field_name, {})
                if not isinstance(tool_section, dict):
                    continue
                extra = tool_section.get("extra", [])
                exclude = tool_section.get("exclude", [])
                current = getattr(result, field_name)
                merged = _merge_list(current, extra, exclude)
                setattr(result, field_name, merged)

    return result
