"""Cleanup for artifacts written by the removed Gemini CLI adapter.

Google sunset Gemini CLI and replaced it with Antigravity, so hawk dropped the
`gemini` tool. Installs that synced to it still carry hawk-managed state under
`~/.gemini/` and `<project>/.gemini/` that ordinary `hawk clean` can no longer
reach — the adapter that knew how to remove it is gone.

This module removes only what hawk itself wrote:

- hook entries in `settings.json` carrying the `__hawk_managed` marker
- MCP servers tracked by the `.hawk-mcp.json` sidecar
- the generated `runners/` directory
- `commands/*.toml` converted from registry prompts
- `agents/*` symlinks pointing into the registry

Everything else in those files — auth, UI preferences, hand-added MCP servers,
foreign hooks — is preserved. `.agents/skills/` is deliberately untouched: the
Codex adapter shares that directory and still manages it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import config

_HAWK_HOOK_MARKER = "__hawk_managed"
_HAWK_MCP_SIDECAR = ".hawk-mcp.json"


def legacy_scopes(project_dir: Path | None = None) -> list[Path]:
    """Every `.gemini` directory hawk may have written to, global first."""
    scopes = [Path.home() / ".gemini"]
    seen = {scopes[0].resolve()}

    candidates = [Path(d) for d in config.get_registered_directories()]
    if project_dir is not None:
        candidates.append(project_dir)

    for directory in candidates:
        gemini_dir = directory / ".gemini"
        try:
            resolved = gemini_dir.resolve()
        except OSError:
            continue
        if resolved not in seen:
            seen.add(resolved)
            scopes.append(gemini_dir)

    return scopes


def cleanup_legacy_gemini(
    project_dir: Path | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Remove hawk-managed Gemini CLI artifacts. Returns a description per action."""
    registry_path = config.get_registry_path()
    actions: list[str] = []

    for scope in legacy_scopes(project_dir):
        if not scope.is_dir():
            continue
        actions.extend(_clean_settings(scope, dry_run))
        actions.extend(_clean_runners(scope, dry_run))
        actions.extend(_clean_commands(scope, registry_path, dry_run))
        actions.extend(_clean_agents(scope, registry_path, dry_run))

    return actions


def _clean_settings(scope: Path, dry_run: bool) -> list[str]:
    """Strip hawk hooks and hawk-tracked MCP servers from settings.json."""
    settings_path = scope / "settings.json"
    sidecar_path = scope / _HAWK_MCP_SIDECAR
    actions: list[str] = []

    managed_servers: set[str] = set()
    if sidecar_path.exists():
        try:
            managed_servers = set(json.loads(sidecar_path.read_text()))
        except (json.JSONDecodeError, OSError, TypeError):
            managed_servers = set()

    data: dict = {}
    if settings_path.exists():
        try:
            loaded = json.loads(settings_path.read_text())
            if isinstance(loaded, dict):
                data = loaded
        except (json.JSONDecodeError, OSError):
            data = {}

    changed = False

    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        kept_events: dict[str, list] = {}
        removed = 0
        for event, entries in hooks.items():
            if not isinstance(entries, list):
                continue
            kept = [e for e in entries if not _is_hawk_hook(e)]
            removed += len(entries) - len(kept)
            if kept:
                kept_events[event] = kept
        if removed:
            actions.append(f"{settings_path}: removed {removed} hawk hook(s)")
            changed = True
            if kept_events:
                data["hooks"] = kept_events
            else:
                data.pop("hooks", None)

    servers = data.get("mcpServers")
    if isinstance(servers, dict):
        kept_servers = {}
        removed_names = []
        for name, cfg in servers.items():
            inline_marked = isinstance(cfg, dict) and cfg.get(_HAWK_HOOK_MARKER)
            if name in managed_servers or inline_marked:
                removed_names.append(name)
            else:
                kept_servers[name] = cfg
        if removed_names:
            actions.append(
                f"{settings_path}: removed hawk MCP server(s) {', '.join(sorted(removed_names))}"
            )
            changed = True
            if kept_servers:
                data["mcpServers"] = kept_servers
            else:
                data.pop("mcpServers", None)

    if changed and not dry_run:
        if data:
            settings_path.write_text(json.dumps(data, indent=2) + "\n")
        else:
            settings_path.unlink()

    if sidecar_path.exists():
        actions.append(f"{sidecar_path}: removed")
        if not dry_run:
            sidecar_path.unlink()

    return actions


def _clean_runners(scope: Path, dry_run: bool) -> list[str]:
    """Delete the generated runners directory."""
    runners = scope / "runners"
    if not runners.is_dir():
        return []
    if not dry_run:
        shutil.rmtree(runners)
    return [f"{runners}: removed generated hook runners"]


def _clean_commands(scope: Path, registry_path: Path, dry_run: bool) -> list[str]:
    """Delete .toml commands converted from registry prompts."""
    commands_dir = scope / "commands"
    prompts_dir = registry_path / "prompts"
    if not commands_dir.is_dir() or not prompts_dir.is_dir():
        return []

    prompt_stems = {f.stem for f in prompts_dir.iterdir() if f.is_file()}
    removed = []
    for entry in commands_dir.iterdir():
        if entry.suffix == ".toml" and entry.stem in prompt_stems:
            removed.append(entry.name)
            if not dry_run:
                entry.unlink()

    if not removed:
        return []
    return [f"{commands_dir}: removed {len(removed)} converted command file(s)"]


def _clean_agents(scope: Path, registry_path: Path, dry_run: bool) -> list[str]:
    """Delete agent symlinks pointing into the registry."""
    agents_dir = scope / "agents"
    source_dir = registry_path / "agents"
    if not agents_dir.is_dir() or not source_dir.is_dir():
        return []

    try:
        resolved_source = source_dir.resolve()
    except OSError:
        return []

    removed = []
    for entry in agents_dir.iterdir():
        if not entry.is_symlink():
            continue
        try:
            target = entry.resolve()
        except OSError:
            continue
        if target == resolved_source or target.is_relative_to(resolved_source):
            removed.append(entry.name)
            if not dry_run:
                entry.unlink()

    if not removed:
        return []
    return [f"{agents_dir}: removed {len(removed)} agent symlink(s)"]


def _is_hawk_hook(entry: object) -> bool:
    """Match both the grouped and flat hook shapes hawk wrote."""
    if not isinstance(entry, dict):
        return False
    if entry.get(_HAWK_HOOK_MARKER):
        return True
    hooks = entry.get("hooks")
    if not isinstance(hooks, list):
        return False
    return any(isinstance(h, dict) and h.get(_HAWK_HOOK_MARKER) for h in hooks)
