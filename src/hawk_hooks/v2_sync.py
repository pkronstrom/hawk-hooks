"""v2 sync engine - orchestrates syncing resolved sets to tools."""

from __future__ import annotations

import os
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


def _cache_identity(resolved_hash: str, adapter) -> str:
    """Compose cache identity from desired state hash + tool capabilities."""
    try:
        fingerprint = adapter.capability_fingerprint()
    except Exception:
        fingerprint = "unknown"
    return f"{resolved_hash}|cap:{fingerprint}"


def count_unsynced_targets(
    project_dir: Path | None = None,
    tools: list[Tool] | None = None,
    *,
    include_global: bool = True,
    only_installed: bool = False,
) -> tuple[int, int]:
    """Count unsynced scope/tool targets using resolved-set cache hashes.

    Returns:
        (unsynced_count, total_targets_checked)
    """
    cfg = v2_config.load_global_config()
    registry = Registry(v2_config.get_registry_path(cfg))
    enabled_tools = tools or v2_config.get_enabled_tools(cfg)

    selected_tools: list[Tool] = []
    for tool in enabled_tools:
        if only_installed and not get_adapter(tool).detect_installed():
            continue
        selected_tools.append(tool)

    unsynced = 0
    total = 0

    if include_global:
        resolved_global = resolve(cfg)
        global_hash = resolved_global.hash_key(registry_path=registry.path)
        for tool in selected_tools:
            adapter = get_adapter(tool)
            expected = _cache_identity(global_hash, adapter)
            total += 1
            if _read_cached_hash("global", tool) != expected:
                unsynced += 1

    if project_dir is not None:
        dir_chain: list[tuple[dict, dict | None]] = []
        for chain_dir, chain_config in v2_config.get_config_chain(project_dir):
            profile_name = _load_profile_for_dir(chain_config, chain_dir, cfg)
            profile = v2_config.load_profile(profile_name) if profile_name else None
            dir_chain.append((chain_config, profile))

        if not dir_chain:
            dir_config = v2_config.load_dir_config(project_dir)
            if dir_config:
                profile_name = _load_profile_for_dir(dir_config, project_dir, cfg)
                profile = v2_config.load_profile(profile_name) if profile_name else None
                dir_chain.append((dir_config, profile))

        resolved_project = resolve(cfg, dir_chain=dir_chain) if dir_chain else resolve(cfg)
        project_hash = resolved_project.hash_key(registry_path=registry.path)
        scope_key = str(project_dir.resolve())

        for tool in selected_tools:
            adapter = get_adapter(tool)
            expected = _cache_identity(project_hash, adapter)
            total += 1
            if _read_cached_hash(scope_key, tool) != expected:
                unsynced += 1

    return unsynced, total


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
        current_hash = resolved.hash_key(registry_path=registry.path)
        identity = _cache_identity(current_hash, adapter)
        if not force and _read_cached_hash(scope_key, tool) == identity:
            results.append(SyncResult(tool=str(tool)))
            continue

        # Determine target directory
        target_dir = adapter.get_project_dir(project_dir)

        result = adapter.sync(resolved, target_dir, registry.path)
        results.append(result)

        # Update cache after successful sync
        if not result.errors:
            _write_cached_hash(scope_key, tool, identity)

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
        current_hash = resolved.hash_key(registry_path=registry.path)
        identity = _cache_identity(current_hash, adapter)
        if not force and _read_cached_hash("global", tool) == identity:
            results.append(SyncResult(tool=str(tool)))
            continue

        target_dir = adapter.get_global_dir()
        result = adapter.sync(resolved, target_dir, registry.path)
        results.append(result)

        # Update cache after successful sync
        if not result.errors:
            _write_cached_hash("global", tool, identity)

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


def purge_directory(
    project_dir: Path,
    tools: list[Tool] | None = None,
    dry_run: bool = False,
) -> list[SyncResult]:
    """Aggressively clean a directory's tool configs.

    Runs normal clean first, then prunes stale/dangling hawk-linked symlinks.
    """
    cleaned = clean_directory(project_dir, tools=tools, dry_run=dry_run)
    pruned = _prune_scope(project_dir, tools=tools, dry_run=dry_run, is_global=False)
    return _merge_results(cleaned, pruned)


def purge_global(
    tools: list[Tool] | None = None,
    dry_run: bool = False,
) -> list[SyncResult]:
    """Aggressively clean global tool configs.

    Runs normal clean first, then prunes stale/dangling hawk-linked symlinks.
    """
    cleaned = clean_global(tools=tools, dry_run=dry_run)
    pruned = _prune_scope(None, tools=tools, dry_run=dry_run, is_global=True)
    return _merge_results(cleaned, pruned)


def purge_all(
    tools: list[Tool] | None = None,
    dry_run: bool = False,
) -> dict[str, list[SyncResult]]:
    """Aggressively clean global + registered directory tool configs."""
    results: dict[str, list[SyncResult]] = {
        "global": purge_global(tools=tools, dry_run=dry_run)
    }

    for dir_path_str in v2_config.get_registered_directories():
        dir_path = Path(dir_path_str)
        if dir_path.exists():
            results[dir_path_str] = purge_directory(
                dir_path, tools=tools, dry_run=dry_run
            )

    return results


def uninstall_all(
    tools: list[Tool] | None = None,
    dry_run: bool = False,
    remove_project_configs: bool = True,
) -> dict[str, list[SyncResult]]:
    """Full teardown for hawk-managed state.

    Performs aggressive unlink/prune from tool configs, then clears hawk
    configuration selections, package index, registry items, directory
    registrations, and sync cache.

    Args:
        tools: Optional tool filter.
        dry_run: If True, report what would change without mutating state.
        remove_project_configs: When True, remove registered projects'
            local ``.hawk/config.yaml`` files (and empty ``.hawk`` dirs).
    """
    purge_results = purge_all(tools=tools, dry_run=dry_run)
    if dry_run:
        return purge_results

    cfg = v2_config.load_global_config()
    registered_dirs = list(v2_config.get_registered_directories().keys())

    # Remove per-project hawk config files for registered directories.
    if remove_project_configs:
        for dir_path_str in registered_dirs:
            cfg_path = v2_config.get_dir_config_path(Path(dir_path_str))
            try:
                if cfg_path.exists():
                    cfg_path.unlink()
                if cfg_path.parent.exists() and not any(cfg_path.parent.iterdir()):
                    cfg_path.parent.rmdir()
            except OSError:
                # Best effort: keep going even if one project can't be cleaned.
                pass

    # Clear global component selections + directory registrations.
    global_section = cfg.get("global", {})
    for field in ["skills", "hooks", "prompts", "commands", "agents", "mcp"]:
        global_section[field] = []
    cfg["global"] = global_section
    cfg["directories"] = {}

    # Reset Codex multi-agent consent state as part of hawk-managed teardown.
    tools_cfg = cfg.setdefault("tools", {})
    codex_cfg = tools_cfg.setdefault("codex", {})
    codex_cfg["multi_agent_consent"] = "ask"
    codex_cfg["allow_multi_agent"] = False
    tools_cfg["codex"] = codex_cfg
    cfg["tools"] = tools_cfg

    v2_config.save_global_config(cfg)

    # Clear package index.
    v2_config.save_packages({})

    # Remove all registry items.
    registry = Registry(v2_config.get_registry_path(cfg))
    for ct, names in registry.list().items():
        for name in list(names):
            try:
                registry.remove(ct, name)
            except Exception:
                pass

    # Clear sync cache.
    cache_dir = _get_cache_dir()
    if cache_dir.exists():
        for entry in cache_dir.iterdir():
            try:
                if entry.is_file() or entry.is_symlink():
                    entry.unlink()
            except OSError:
                pass

    # Seed global cache to represent the empty post-uninstall state.
    # This prevents a false "unsynced" signal immediately after uninstall.
    enabled_tools = tools or v2_config.get_enabled_tools(cfg)
    empty_hash = resolve(cfg).hash_key(registry_path=registry.path)
    for tool in enabled_tools:
        adapter = get_adapter(tool)
        _write_cached_hash("global", tool, _cache_identity(empty_hash, adapter))

    return purge_results


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
        ("prompt", adapter.get_prompts_dir),
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


def _merge_results(
    primary: list[SyncResult],
    secondary: list[SyncResult],
) -> list[SyncResult]:
    """Merge per-tool SyncResults by tool name."""
    merged: dict[str, SyncResult] = {}
    ordered_tools: list[str] = []

    for result in primary + secondary:
        if result.tool not in merged:
            merged[result.tool] = SyncResult(tool=result.tool)
            ordered_tools.append(result.tool)
        target = merged[result.tool]
        target.linked.extend(result.linked)
        target.unlinked.extend(result.unlinked)
        target.skipped.extend(result.skipped)
        target.errors.extend(result.errors)

    return [merged[t] for t in ordered_tools]


def _prune_scope(
    project_dir: Path | None,
    tools: list[Tool] | None,
    dry_run: bool,
    *,
    is_global: bool,
) -> list[SyncResult]:
    """Prune stale hawk-linked symlinks for one scope."""
    cfg = v2_config.load_global_config()
    enabled_tools = tools or v2_config.get_enabled_tools(cfg)
    registry = Registry(v2_config.get_registry_path(cfg))
    hawk_roots = [v2_config.get_config_dir().resolve(), registry.path.resolve()]

    results: list[SyncResult] = []
    for tool in enabled_tools:
        adapter = get_adapter(tool)
        target_dir = adapter.get_global_dir() if is_global else adapter.get_project_dir(project_dir)  # type: ignore[arg-type]
        result = SyncResult(tool=str(tool))

        result.unlinked.extend(
            _prune_tool_symlinks(adapter, target_dir, hawk_roots, dry_run=dry_run)
        )

        results.append(result)

    return results


def _prune_tool_symlinks(
    adapter,
    target_dir: Path,
    hawk_roots: list[Path],
    *,
    dry_run: bool,
) -> list[str]:
    """Prune stale hawk-linked symlinks under a tool target directory."""
    removed: list[str] = []
    specs = [
        ("skill", adapter.get_skills_dir, adapter.unlink_skill),
        ("agent", adapter.get_agents_dir, adapter.unlink_agent),
        ("prompt", adapter.get_prompts_dir, adapter.unlink_prompt),
    ]

    for prefix, get_dir_fn, unlink_fn in specs:
        comp_dir = get_dir_fn(target_dir)
        if not comp_dir.exists():
            continue
        for entry in comp_dir.iterdir():
            if not entry.is_symlink():
                continue
            if not _is_hawk_link(entry, hawk_roots):
                continue

            removed.append(f"{prefix}:{entry.name}")
            if not dry_run:
                try:
                    unlink_fn(entry.name, target_dir)
                except Exception:
                    # Best-effort prune; cleanup errors are surfaced by normal clean.
                    pass

    return removed


def _is_hawk_link(link_path: Path, hawk_roots: list[Path]) -> bool:
    """Return True if symlink target points into hawk config/registry roots."""
    try:
        raw_target = Path(os.readlink(link_path))
    except OSError:
        return False

    if not raw_target.is_absolute():
        target = (link_path.parent / raw_target).resolve(strict=False)
    else:
        target = raw_target.resolve(strict=False)

    for root in hawk_roots:
        try:
            if target == root or target.is_relative_to(root):
                return True
        except (OSError, ValueError):
            continue
    return False


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
    for prompt in resolved.prompts:
        if registry.has_from_name("prompts", prompt):
            would_link.append(f"prompt:{prompt}")
    for hook in resolved.hooks:
        would_link.append(f"hook:{hook}")
    for mcp in resolved.mcp:
        if registry.has_from_name("mcp", mcp) or registry.has_from_name("mcp", f"{mcp}.yaml"):
            would_link.append(f"mcp:{mcp}")
    return would_link


def format_sync_results(
    results: dict[str, list[SyncResult]],
    *,
    verbose: bool = True,
) -> str:
    """Format sync/clean results into a human-readable summary.

    Args:
        results: Mapping of scope name to per-tool sync results.
        verbose: When True, include per-item link/unlink/error lines.
    """
    lines: list[str] = []

    for scope, tool_results in results.items():
        lines.append(f"\n  {scope}:")
        for result in tool_results:
            if not result.linked and not result.unlinked and not result.skipped and not result.errors:
                lines.append(f"    {result.tool}: no changes")
                continue

            parts = []
            if result.linked:
                parts.append(f"+{len(result.linked)} linked")
            if result.unlinked:
                parts.append(f"-{len(result.unlinked)} unlinked")
            if result.skipped:
                parts.append(f"~{len(result.skipped)} skipped")
            if result.errors:
                parts.append(f"!{len(result.errors)} errors")
            lines.append(f"    {result.tool}: {', '.join(parts)}")

            if verbose:
                for item in result.linked:
                    lines.append(f"      + {item}")
                for item in result.unlinked:
                    lines.append(f"      - {item}")
                for skipped in result.skipped:
                    lines.append(f"      ~ {skipped}")
                for err in result.errors:
                    lines.append(f"      ! {err}")

    return "\n".join(lines)
