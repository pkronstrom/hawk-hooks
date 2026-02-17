"""v2 sync engine - orchestrates syncing resolved sets to tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import v2_config
from .adapters import get_adapter
from .registry import Registry
from .resolver import resolve
from .types import ResolvedSet, SyncResult, Tool


def sync_directory(
    project_dir: Path,
    tools: list[Tool] | None = None,
    dry_run: bool = False,
) -> list[SyncResult]:
    """Sync a single directory to all enabled tools.

    Args:
        project_dir: The project directory to sync.
        tools: Optional filter to specific tools.
        dry_run: If True, compute what would change but don't apply.

    Returns:
        List of SyncResult, one per tool.
    """
    cfg = v2_config.load_global_config()
    dir_config = v2_config.load_dir_config(project_dir)

    # Load profile if specified
    profile = None
    profile_name = None
    if dir_config:
        profile_name = dir_config.get("profile")
    if not profile_name:
        # Check global directory index for profile
        dirs = cfg.get("directories", {})
        dir_entry = dirs.get(str(project_dir.resolve()), {})
        profile_name = dir_entry.get("profile")
    if profile_name:
        profile = v2_config.load_profile(profile_name)

    # Determine which tools to sync
    enabled_tools = tools or v2_config.get_enabled_tools(cfg)
    registry = Registry(v2_config.get_registry_path(cfg))
    results: list[SyncResult] = []

    for tool in enabled_tools:
        adapter = get_adapter(tool)

        # Resolve the component set for this tool
        resolved = resolve(cfg, profile=profile, dir_config=dir_config, tool=tool)

        if dry_run:
            result = SyncResult(tool=str(tool))
            result.linked = _compute_would_link(resolved, registry, adapter, project_dir)
            results.append(result)
            continue

        # Determine target directory
        target_dir = adapter.get_project_dir(project_dir)

        # For global scope, use the tool's global dir
        result = adapter.sync(resolved, target_dir, registry.path)
        results.append(result)

    return results


def sync_global(
    tools: list[Tool] | None = None,
    dry_run: bool = False,
) -> list[SyncResult]:
    """Sync global config to all enabled tools.

    Args:
        tools: Optional filter to specific tools.
        dry_run: If True, compute what would change but don't apply.

    Returns:
        List of SyncResult, one per tool.
    """
    cfg = v2_config.load_global_config()
    enabled_tools = tools or v2_config.get_enabled_tools(cfg)
    registry = Registry(v2_config.get_registry_path(cfg))
    results: list[SyncResult] = []

    for tool in enabled_tools:
        adapter = get_adapter(tool)
        resolved = resolve(cfg)

        if dry_run:
            result = SyncResult(tool=str(tool))
            result.linked = _compute_would_link(resolved, registry, adapter, None)
            results.append(result)
            continue

        target_dir = adapter.get_global_dir()
        result = adapter.sync(resolved, target_dir, registry.path)
        results.append(result)

    return results


def sync_all(
    tools: list[Tool] | None = None,
    dry_run: bool = False,
) -> dict[str, list[SyncResult]]:
    """Sync global + all registered directories.

    Returns:
        Dict mapping "global" or directory path to list of SyncResults.
    """
    all_results: dict[str, list[SyncResult]] = {}

    # Sync global
    all_results["global"] = sync_global(tools=tools, dry_run=dry_run)

    # Sync each registered directory
    directories = v2_config.get_registered_directories()
    for dir_path_str in directories:
        dir_path = Path(dir_path_str)
        if dir_path.exists():
            all_results[dir_path_str] = sync_directory(
                dir_path, tools=tools, dry_run=dry_run
            )

    return all_results


def _compute_would_link(
    resolved: ResolvedSet,
    registry: Registry,
    adapter,
    project_dir: Path | None,
) -> list[str]:
    """Compute what would be linked in a dry run."""
    would_link: list[str] = []
    for skill in resolved.skills:
        if registry.has_from_name("skills", skill):
            would_link.append(f"skill:{skill}")
    for agent in resolved.agents:
        if registry.has_from_name("agents", agent):
            would_link.append(f"agent:{agent}")
    for cmd in resolved.commands:
        if registry.has_from_name("commands", cmd):
            would_link.append(f"command:{cmd}")
    for hook in resolved.hooks:
        would_link.append(f"hook:{hook}")
    return would_link


def format_sync_results(results: dict[str, list[SyncResult]]) -> str:
    """Format sync results into a human-readable summary."""
    lines: list[str] = []

    for scope, tool_results in results.items():
        lines.append(f"\n  {scope}:")
        for result in tool_results:
            if not result.linked and not result.unlinked and not result.errors:
                lines.append(f"    {result.tool}: no changes")
                continue

            parts = []
            if result.linked:
                parts.append(f"+{len(result.linked)} linked")
            if result.unlinked:
                parts.append(f"-{len(result.unlinked)} unlinked")
            if result.errors:
                parts.append(f"!{len(result.errors)} errors")
            lines.append(f"    {result.tool}: {', '.join(parts)}")

            for item in result.linked:
                lines.append(f"      + {item}")
            for item in result.unlinked:
                lines.append(f"      - {item}")
            for err in result.errors:
                lines.append(f"      ! {err}")

    return "\n".join(lines)
