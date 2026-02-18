"""v2 sync engine - orchestrates syncing resolved sets to tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import v2_config
from .adapters import get_adapter
from .registry import Registry
from .resolver import resolve
from .types import ResolvedSet, SyncResult, Tool


def _get_cache_dir() -> Path:
    """Get the resolved-set cache directory."""
    return v2_config.get_config_dir() / "cache" / "resolved"


def _cache_key(scope: str, tool: Tool) -> str:
    """Build a cache filename for a scope+tool combination."""
    safe_scope = scope.replace("/", "_").replace("\\", "_").lstrip("_")
    return f"{safe_scope}_{tool.value}"


def _read_cached_hash(scope: str, tool: Tool) -> str | None:
    """Read the cached hash for a scope+tool, or None if missing."""
    cache_file = _get_cache_dir() / _cache_key(scope, tool)
    try:
        return cache_file.read_text().strip()
    except (FileNotFoundError, OSError):
        return None


def _write_cached_hash(scope: str, tool: Tool, hash_val: str) -> None:
    """Write a resolved-set hash to the cache."""
    cache_dir = _get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / _cache_key(scope, tool)).write_text(hash_val)


def _load_profile_for_dir(
    dir_config: dict | None, project_dir: Path, cfg: dict
) -> str | None:
    """Determine the profile name for a directory from its config or global index."""
    profile_name = None
    if dir_config:
        profile_name = dir_config.get("profile")
    if not profile_name:
        dirs = cfg.get("directories", {})
        dir_entry = dirs.get(str(project_dir.resolve()), {})
        profile_name = dir_entry.get("profile")
    return profile_name


def sync_directory(
    project_dir: Path,
    tools: list[Tool] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> list[SyncResult]:
    """Sync a single directory to all enabled tools.

    Uses config chain for hierarchical resolution: registered parent dirs
    are included outermost-first, each with their own profile.

    Args:
        project_dir: The project directory to sync.
        tools: Optional filter to specific tools.
        dry_run: If True, compute what would change but don't apply.
        force: If True, bypass hash cache and sync unconditionally.

    Returns:
        List of SyncResult, one per tool.
    """
    cfg = v2_config.load_global_config()

    # Build dir_chain from config chain (hierarchical parent lookup)
    config_chain = v2_config.get_config_chain(project_dir)
    dir_chain: list[tuple[dict, dict | None]] = []
    for chain_dir, chain_config in config_chain:
        profile_name = _load_profile_for_dir(chain_config, chain_dir, cfg)
        profile = v2_config.load_profile(profile_name) if profile_name else None
        dir_chain.append((chain_config, profile))

    # If no chain found, fall back to loading dir config directly
    # (handles case where dir has config but isn't in the index)
    if not dir_chain:
        dir_config = v2_config.load_dir_config(project_dir)
        if dir_config:
            profile_name = _load_profile_for_dir(dir_config, project_dir, cfg)
            profile = v2_config.load_profile(profile_name) if profile_name else None
            dir_chain.append((dir_config, profile))

    # Determine which tools to sync
    enabled_tools = tools or v2_config.get_enabled_tools(cfg)
    registry = Registry(v2_config.get_registry_path(cfg))
    results: list[SyncResult] = []

    scope_key = str(project_dir.resolve())

    for tool in enabled_tools:
        adapter = get_adapter(tool)

        # Resolve using dir_chain for hierarchical layering
        resolved = resolve(cfg, dir_chain=dir_chain, tool=tool)

        if dry_run:
            result = SyncResult(tool=str(tool))
            result.linked = _compute_would_link(resolved, registry, adapter, project_dir)
            results.append(result)
            continue

        # Check cache — skip if resolved set hasn't changed
        current_hash = resolved.hash_key()
        if not force and _read_cached_hash(scope_key, tool) == current_hash:
            results.append(SyncResult(tool=str(tool)))
            continue

        # Determine target directory
        target_dir = adapter.get_project_dir(project_dir)

        result = adapter.sync(resolved, target_dir, registry.path)
        results.append(result)

        # Update cache after successful sync
        if not result.errors:
            _write_cached_hash(scope_key, tool, current_hash)

    return results


def sync_global(
    tools: list[Tool] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> list[SyncResult]:
    """Sync global config to all enabled tools.

    Args:
        tools: Optional filter to specific tools.
        dry_run: If True, compute what would change but don't apply.
        force: If True, bypass hash cache and sync unconditionally.

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

        # Check cache — skip if resolved set hasn't changed
        current_hash = resolved.hash_key()
        if not force and _read_cached_hash("global", tool) == current_hash:
            results.append(SyncResult(tool=str(tool)))
            continue

        target_dir = adapter.get_global_dir()
        result = adapter.sync(resolved, target_dir, registry.path)
        results.append(result)

        # Update cache after successful sync
        if not result.errors:
            _write_cached_hash("global", tool, current_hash)

    return results


def sync_all(
    tools: list[Tool] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, list[SyncResult]]:
    """Sync global + all registered directories.

    Returns:
        Dict mapping "global" or directory path to list of SyncResults.
    """
    all_results: dict[str, list[SyncResult]] = {}

    # Sync global
    all_results["global"] = sync_global(tools=tools, dry_run=dry_run, force=force)

    # Sync each registered directory
    directories = v2_config.get_registered_directories()
    for dir_path_str in directories:
        dir_path = Path(dir_path_str)
        if dir_path.exists():
            all_results[dir_path_str] = sync_directory(
                dir_path, tools=tools, dry_run=dry_run, force=force
            )

    return all_results


def clean_directory(
    project_dir: Path,
    tools: list[Tool] | None = None,
    dry_run: bool = False,
) -> list[SyncResult]:
    """Remove all hawk-managed items from a directory's tool configs.

    Syncs with an empty resolved set, which causes all hawk-managed
    symlinks to be unlinked.
    """
    cfg = v2_config.load_global_config()
    enabled_tools = tools or v2_config.get_enabled_tools(cfg)
    registry = Registry(v2_config.get_registry_path(cfg))
    empty = ResolvedSet()
    results: list[SyncResult] = []
    scope_key = str(project_dir.resolve())

    for tool in enabled_tools:
        adapter = get_adapter(tool)
        target_dir = adapter.get_project_dir(project_dir)

        if dry_run:
            result = SyncResult(tool=str(tool))
            result.unlinked = _compute_would_unlink(registry.path, adapter, target_dir)
            results.append(result)
            continue

        result = adapter.sync(empty, target_dir, registry.path)
        results.append(result)

        # Clear cache for this scope+tool
        cache_file = _get_cache_dir() / _cache_key(scope_key, tool)
        if cache_file.exists():
            cache_file.unlink()

    return results


def clean_global(
    tools: list[Tool] | None = None,
    dry_run: bool = False,
) -> list[SyncResult]:
    """Remove all hawk-managed items from global tool configs."""
    cfg = v2_config.load_global_config()
    enabled_tools = tools or v2_config.get_enabled_tools(cfg)
    registry = Registry(v2_config.get_registry_path(cfg))
    empty = ResolvedSet()
    results: list[SyncResult] = []

    for tool in enabled_tools:
        adapter = get_adapter(tool)
        target_dir = adapter.get_global_dir()

        if dry_run:
            result = SyncResult(tool=str(tool))
            result.unlinked = _compute_would_unlink(registry.path, adapter, target_dir)
            results.append(result)
            continue

        result = adapter.sync(empty, target_dir, registry.path)
        results.append(result)

        # Clear cache
        cache_file = _get_cache_dir() / _cache_key("global", tool)
        if cache_file.exists():
            cache_file.unlink()

    return results


def clean_all(
    tools: list[Tool] | None = None,
    dry_run: bool = False,
) -> dict[str, list[SyncResult]]:
    """Remove all hawk-managed items from global + all registered directories."""
    all_results: dict[str, list[SyncResult]] = {}

    all_results["global"] = clean_global(tools=tools, dry_run=dry_run)

    directories = v2_config.get_registered_directories()
    for dir_path_str in directories:
        dir_path = Path(dir_path_str)
        if dir_path.exists():
            all_results[dir_path_str] = clean_directory(
                dir_path, tools=tools, dry_run=dry_run
            )

    return all_results


def _compute_would_unlink(
    registry_path: Path,
    adapter,
    target_dir: Path,
) -> list[str]:
    """Compute what would be unlinked in a dry-run clean."""
    would_unlink: list[str] = []
    for comp_type, get_dir_fn in [
        ("skill", adapter.get_skills_dir),
        ("agent", adapter.get_agents_dir),
        ("command", adapter.get_commands_dir),
    ]:
        comp_dir = get_dir_fn(target_dir)
        source_dir = registry_path / (comp_type + "s")
        if not comp_dir.exists():
            continue
        for entry in comp_dir.iterdir():
            if entry.is_symlink():
                try:
                    target = entry.resolve()
                    resolved_source = source_dir.resolve()
                    if target == resolved_source or target.is_relative_to(resolved_source):
                        would_unlink.append(f"{comp_type}:{entry.name}")
                except (OSError, ValueError):
                    pass
    return would_unlink


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
    for mcp in resolved.mcp:
        if registry.has_from_name("mcp", mcp) or registry.has_from_name("mcp", f"{mcp}.yaml"):
            would_link.append(f"mcp:{mcp}")
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
