"""Helpers for building directory config/profile chains for resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import v2_config


def resolve_profile_name_for_dir(
    dir_config: dict[str, Any] | None,
    directory: Path,
    cfg: dict[str, Any],
) -> str | None:
    """Resolve profile name for a directory layer.

    Lookup order:
    1. Local dir config `profile`
    2. Global directory index entry profile
    """
    profile_name = None
    if dir_config:
        profile_name = dir_config.get("profile")
    if not profile_name:
        dirs = cfg.get("directories", {})
        dir_entry = dirs.get(str(directory.resolve()), {})
        profile_name = dir_entry.get("profile")
    return str(profile_name) if profile_name else None


def build_config_layers_with_profiles(
    project_dir: Path,
    cfg: dict[str, Any] | None = None,
) -> list[tuple[Path, dict[str, Any], dict[str, Any] | None]]:
    """Build ordered config layers with resolved profiles.

    Returns a list of `(directory, dir_config, profile_config)` tuples
    ordered outermost-first.

    If no registered chain is found, falls back to a direct local
    `.hawk/config.yaml` in `project_dir`.
    """
    if cfg is None:
        cfg = v2_config.load_global_config()

    layers: list[tuple[Path, dict[str, Any], dict[str, Any] | None]] = []
    for chain_dir, chain_config in v2_config.get_config_chain(project_dir):
        profile_name = resolve_profile_name_for_dir(chain_config, chain_dir, cfg)
        profile = v2_config.load_profile(profile_name) if profile_name else None
        layers.append((chain_dir, chain_config, profile))

    if layers:
        # Include unregistered leaf local config when parent chain is registered.
        project_dir_resolved = project_dir.resolve()
        if not any(layer_dir == project_dir_resolved for layer_dir, _cfg, _profile in layers):
            dir_config = v2_config.load_dir_config(project_dir_resolved)
            if dir_config is not None:
                profile_name = resolve_profile_name_for_dir(dir_config, project_dir_resolved, cfg)
                profile = v2_config.load_profile(profile_name) if profile_name else None
                layers.append((project_dir_resolved, dir_config, profile))
        return layers

    dir_config = v2_config.load_dir_config(project_dir)
    if dir_config is None:
        return []

    profile_name = resolve_profile_name_for_dir(dir_config, project_dir, cfg)
    profile = v2_config.load_profile(profile_name) if profile_name else None
    return [(project_dir.resolve(), dir_config, profile)]


def build_resolver_dir_chain(
    project_dir: Path,
    cfg: dict[str, Any] | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    """Build resolver `dir_chain` argument for `resolve(...)` calls."""
    if cfg is None:
        cfg = v2_config.load_global_config()

    layers = build_config_layers_with_profiles(project_dir, cfg=cfg)
    return [(dir_config, profile) for _d, dir_config, profile in layers]
