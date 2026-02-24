"""Abstract base class for tool adapters."""

from __future__ import annotations

import json
import logging
import re
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from typing import Literal

from ..registry import _validate_name
from ..types import ResolvedSet, SyncResult, Tool

# Shared marker for hawk-managed MCP entries
HAWK_MCP_MARKER = "__hawk_managed"
_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
logger = logging.getLogger(__name__)


class ToolAdapter(ABC):
    """Abstract base for AI CLI tool adapters.

    Each adapter knows how to link/unlink components and manage
    tool-specific configuration files.
    """
    HOOK_SUPPORT: Literal["native", "bridge", "unsupported"] = "unsupported"

    def __init__(self) -> None:
        # Adapters can record non-fatal hook skips and fatal hook errors.
        self._hook_skipped: list[str] = []
        self._hook_errors: list[str] = []

    @property
    @abstractmethod
    def tool(self) -> Tool:
        """Which tool this adapter manages."""

    @property
    def hook_support(self) -> Literal["native", "bridge", "unsupported"]:
        """Declared hook capability for this adapter."""
        return self.HOOK_SUPPORT

    def capability_fingerprint(self) -> str:
        """Fingerprint of sync-relevant tool capabilities.

        This is used by v2 sync cache identity to force re-sync when
        adapter-declared capabilities change.
        """
        from ..event_mapping import get_event_support
        from ..events import EVENTS

        event_caps = ",".join(
            f"{event}:{get_event_support(event, str(self.tool))}"
            for event in sorted(EVENTS.keys())
        )
        return f"tool={self.tool}|hook_support={self.hook_support}|events={event_caps}"

    @abstractmethod
    def detect_installed(self) -> bool:
        """Check if this tool is installed on the system."""

    @abstractmethod
    def get_global_dir(self) -> Path:
        """Get the global config directory for this tool."""

    @abstractmethod
    def get_project_dir(self, project: Path) -> Path:
        """Get the project-level config directory for this tool."""

    # ── Skill operations ──

    def get_skills_dir(self, target_dir: Path) -> Path:
        """Get the skills subdirectory within a target dir."""
        return target_dir / "skills"

    def link_skill(self, source: Path, target_dir: Path) -> Path:
        """Symlink a skill into the tool's skills directory."""
        dest = self.get_skills_dir(target_dir) / source.name
        self._create_symlink(source, dest)
        return dest

    def unlink_skill(self, name: str, target_dir: Path) -> bool:
        """Remove a skill symlink. Returns True if removed."""
        dest = self.get_skills_dir(target_dir) / name
        return self._remove_link(dest)

    # ── Agent operations ──

    def get_agents_dir(self, target_dir: Path) -> Path:
        """Get the agents subdirectory within a target dir."""
        return target_dir / "agents"

    def link_agent(self, source: Path, target_dir: Path) -> Path:
        """Symlink an agent into the tool's agents directory."""
        dest = self.get_agents_dir(target_dir) / source.name
        self._create_symlink(source, dest)
        return dest

    def unlink_agent(self, name: str, target_dir: Path) -> bool:
        """Remove an agent symlink. Returns True if removed."""
        dest = self.get_agents_dir(target_dir) / name
        return self._remove_link(dest)

    # ── Command operations ──

    def get_commands_dir(self, target_dir: Path) -> Path:
        """Get the commands subdirectory within a target dir."""
        return target_dir / "commands"

    def link_command(self, source: Path, target_dir: Path) -> Path:
        """Link a command. Default is symlink; override for format conversion."""
        dest = self.get_commands_dir(target_dir) / source.name
        self._create_symlink(source, dest)
        return dest

    def unlink_command(self, name: str, target_dir: Path) -> bool:
        """Remove a command. Returns True if removed."""
        dest = self.get_commands_dir(target_dir) / name
        return self._remove_link(dest)

    # ── Prompt operations ──

    def get_prompts_dir(self, target_dir: Path) -> Path:
        """Get the prompts subdirectory within a target dir."""
        return target_dir / "prompts"

    def link_prompt(self, source: Path, target_dir: Path) -> Path:
        """Symlink a prompt into the tool's prompts directory."""
        dest = self.get_prompts_dir(target_dir) / source.name
        self._create_symlink(source, dest)
        return dest

    def unlink_prompt(self, name: str, target_dir: Path) -> bool:
        """Remove a prompt symlink. Returns True if removed."""
        dest = self.get_prompts_dir(target_dir) / name
        return self._remove_link(dest)

    # ── Hook operations ──

    @abstractmethod
    def register_hooks(self, hook_names: list[str], target_dir: Path, registry_path: Path | None = None) -> list[str]:
        """Register hooks for this tool. Returns list of registered hook names."""

    # ── MCP operations ──

    @abstractmethod
    def write_mcp_config(
        self, servers: dict[str, dict], target_dir: Path
    ) -> None:
        """Write MCP server configuration for this tool.

        Must preserve manually-added entries and only manage hawk-owned ones.
        """

    # ── Sync ──

    def sync(
        self,
        resolved: ResolvedSet,
        target_dir: Path,
        registry_path: Path,
    ) -> SyncResult:
        """Sync a resolved set to the tool's directories.

        Args:
            resolved: The resolved set of components to sync.
            target_dir: The tool's target directory (global or project).
            registry_path: Path to the hawk registry.

        Returns:
            SyncResult with what was linked/unlinked.
        """
        result = SyncResult(tool=str(self.tool))

        # Ensure target subdirs exist
        for dir_getter in [self.get_skills_dir, self.get_agents_dir, self.get_prompts_dir]:
            dir_getter(target_dir).mkdir(parents=True, exist_ok=True)

        # Sync skills
        self._sync_component(
            resolved.skills,
            registry_path / "skills",
            target_dir,
            self.link_skill,
            self.unlink_skill,
            self.get_skills_dir,
            result,
        )

        # Sync agents
        self._sync_component(
            resolved.agents,
            registry_path / "agents",
            target_dir,
            self.link_agent,
            self.unlink_agent,
            self.get_agents_dir,
            result,
        )

        # Sync prompts
        self._sync_component(
            resolved.prompts,
            registry_path / "prompts",
            target_dir,
            self.link_prompt,
            self.unlink_prompt,
            self.get_prompts_dir,
            result,
        )

        # Register hooks
        try:
            self._set_hook_diagnostics(skipped=[], errors=[])
            registered = self.register_hooks(resolved.hooks, target_dir, registry_path=registry_path)
            result.linked.extend(f"hook:{h}" for h in registered)
            for skipped in self._take_hook_skipped():
                result.skipped.append(f"hooks: {skipped}")
            for hook_error in self._take_hook_errors():
                result.errors.append(f"hooks: {hook_error}")
        except Exception as e:
            result.errors.append(f"hooks: {e}")

        # Sync MCP servers (always call to clean up stale entries)
        try:
            servers = self._load_mcp_servers(resolved.mcp, registry_path / "mcp") if resolved.mcp else {}
            self.write_mcp_config(servers, target_dir)
            result.linked.extend(f"mcp:{name}" for name in servers)
        except Exception as e:
            result.errors.append(f"mcp: {e}")

        return result

    # ── Runner generation ──

    def _generate_runners(
        self,
        hook_names: list[str],
        registry_path: Path,
        runners_dir: Path,
    ) -> dict[str, Path]:
        """Generate bash runners from hook files using hawk-hook metadata.

        Hook names are plain filenames (e.g. "file-guard.py").
        Each hook's metadata declares which events it targets.
        One runner is generated per event, chaining all hooks for that event.

        Returns dict of {event_name: runner_path}.
        """
        from collections import defaultdict
        import shlex
        from ..runner_utils import _get_interpreter_path, _atomic_write_executable
        from ..events import EVENTS
        from ..hook_meta import parse_hook_meta

        from ..hook_meta import HookMeta

        # Resolve hooks and group by event, keeping metadata
        hooks_by_event: dict[str, list[tuple[Path, HookMeta]]] = defaultdict(list)
        hooks_dir = registry_path / "hooks"
        for name in hook_names:
            hook_path = hooks_dir / name
            if not hook_path.is_file():
                continue
            meta = parse_hook_meta(hook_path)
            for event in meta.events:
                # Validate event name against canonical events to prevent
                # path traversal (e.g. events=../../foo) and unknown events
                if event not in EVENTS:
                    continue
                hooks_by_event[event].append((hook_path, meta))

        runners: dict[str, Path] = {}
        runners_dir.mkdir(parents=True, exist_ok=True)

        # Check for venv python
        from .. import v2_config
        venv_python = v2_config.get_config_dir() / ".venv" / "bin" / "python"
        python_cmd = shlex.quote(str(venv_python)) if venv_python.is_file() else "python3"

        for event, hook_entries in hooks_by_event.items():
            calls: list[str] = []
            for script, meta in hook_entries:
                safe_path = shlex.quote(str(script))
                suffix = script.suffix

                # Inject env var exports for entries with = (value assigned)
                env_exports: list[str] = []
                for env_entry in meta.env:
                    if "=" in env_entry:
                        var_name, _, var_value = env_entry.partition("=")
                        if not _ENV_VAR_NAME_RE.fullmatch(var_name):
                            logger.warning(
                                "Skipping invalid env var name in hook metadata: %r (hook=%s)",
                                var_name,
                                script.name,
                            )
                            continue
                        env_exports.append(f"export {var_name}={shlex.quote(var_value)}")
                if env_exports:
                    calls.extend(env_exports)

                # Content hooks: cat the file
                if script.name.endswith((".stdout.md", ".stdout.txt")) or suffix in (".md", ".txt"):
                    try:
                        cat_path = _get_interpreter_path("cat")
                    except FileNotFoundError:
                        cat_path = "cat"
                    calls.append(f'[[ -f {safe_path} ]] && {cat_path} {safe_path}')
                elif suffix == ".py":
                    calls.append(
                        f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {python_cmd} {safe_path} || exit $?; }}'
                    )
                elif suffix == ".sh":
                    try:
                        bash_path = _get_interpreter_path("bash")
                    except FileNotFoundError:
                        bash_path = "bash"
                    calls.append(
                        f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {bash_path} {safe_path} || exit $?; }}'
                    )
                elif suffix == ".js":
                    try:
                        node_path = _get_interpreter_path("node")
                    except FileNotFoundError:
                        node_path = "node"
                    calls.append(
                        f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {node_path} {safe_path} || exit $?; }}'
                    )
                elif suffix == ".ts":
                    try:
                        bun_path = _get_interpreter_path("bun")
                    except FileNotFoundError:
                        bun_path = "bun"
                    calls.append(
                        f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {bun_path} run {safe_path} || exit $?; }}'
                    )
                else:
                    calls.append(
                        f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {safe_path} || exit $?; }}'
                    )

            hook_calls_str = "\n".join(calls)
            content = f"""#!/usr/bin/env bash
# Auto-generated by hawk v2 - do not edit manually
# Event: {event}
# Regenerate with: hawk sync --force

set -euo pipefail

INPUT=$(cat)

{hook_calls_str}

exit 0
"""
            runner_path = runners_dir / f"{event}.sh"
            _atomic_write_executable(runner_path, content)
            runners[event] = runner_path

        # Clean up stale runners for events that no longer have hooks
        for existing in runners_dir.iterdir():
            if existing.suffix == ".sh" and existing.stem not in hooks_by_event:
                existing.unlink()

        return runners

    # ── Helpers ──

    def _sync_component(
        self,
        names: list[str],
        source_dir: Path,
        target_dir: Path,
        link_fn,
        unlink_fn,
        get_dir_fn,
        result: SyncResult,
        find_current_fn=None,
    ) -> None:
        """Sync a set of components: link desired, unlink stale.

        Args:
            find_current_fn: Optional callable(comp_dir, source_dir) -> set[str]
                that returns names of currently-managed items. Defaults to
                scanning for symlinks pointing into the registry. Adapters that
                write regular files (e.g. Gemini toml) should provide a custom
                finder.
        """
        # Validate all names to prevent path traversal from config
        validated: list[str] = []
        for name in names:
            try:
                _validate_name(name)
                validated.append(name)
            except ValueError as e:
                result.errors.append(f"invalid name {name!r}: {e}")
        desired = set(validated)
        comp_dir = get_dir_fn(target_dir)

        # Find currently managed items
        if find_current_fn is not None:
            current = find_current_fn(comp_dir, source_dir)
        else:
            # Default: scan for symlinks pointing into our registry
            current = self._find_current_symlinks(comp_dir, source_dir)

        # Unlink stale
        for name in current - desired:
            try:
                if unlink_fn(name, target_dir):
                    result.unlinked.append(name)
            except Exception as e:
                result.errors.append(f"unlink {name}: {e}")

        # Link new
        for name in desired - current:
            source = source_dir / name
            if not source.exists():
                continue
            # Check if destination already exists but belongs to something else
            dest = get_dir_fn(target_dir) / name
            if dest.exists() or dest.is_symlink():
                is_ours = False
                if dest.is_symlink():
                    try:
                        resolved_target = dest.resolve()
                        resolved_source = source_dir.resolve()
                        is_ours = resolved_target == resolved_source or resolved_target.is_relative_to(resolved_source)
                    except (OSError, ValueError):
                        pass
                if not is_ours:
                    result.errors.append(f"skip {name}: already exists (not managed by hawk)")
                    continue
            try:
                link_fn(source, target_dir)
                result.linked.append(name)
            except Exception as e:
                result.errors.append(f"link {name}: {e}")

    @staticmethod
    def _find_current_symlinks(comp_dir: Path, source_dir: Path) -> set[str]:
        """Find symlinks in *comp_dir* that point into *source_dir*."""
        current: set[str] = set()
        if not comp_dir.exists():
            return current
        for entry in comp_dir.iterdir():
            if entry.is_symlink():
                try:
                    target = entry.resolve()
                    resolved_source = source_dir.resolve()
                    if target == resolved_source or target.is_relative_to(resolved_source):
                        current.add(entry.name)
                except (OSError, ValueError):
                    pass
        return current

    @staticmethod
    def _load_mcp_servers(
        mcp_names: list[str],
        mcp_dir: Path,
    ) -> dict[str, dict[str, Any]]:
        """Load MCP server configs from registry yaml files.

        Each .yaml file in registry/mcp/ defines a server config.
        Returns dict of {server_name: config_dict}.
        """
        import yaml

        servers: dict[str, dict[str, Any]] = {}
        for name in mcp_names:
            try:
                _validate_name(name)
            except ValueError:
                continue

            # Try with and without extension
            candidates = [mcp_dir / name]
            if not name.endswith((".yaml", ".yml", ".json")):
                candidates.extend([
                    mcp_dir / f"{name}.yaml",
                    mcp_dir / f"{name}.yml",
                    mcp_dir / f"{name}.json",
                ])

            for path in candidates:
                if path.exists() and path.is_file():
                    try:
                        data = yaml.safe_load(path.read_text())
                        if isinstance(data, dict):
                            server_name = path.stem
                            servers[server_name] = data
                    except Exception:
                        pass
                    break

        return servers

    @staticmethod
    def _merge_mcp_json(
        config_path: Path,
        servers: dict[str, dict],
        server_key: str = "mcpServers",
    ) -> None:
        """Merge hawk-managed MCP servers into a JSON config file.

        Preserves manually-added entries, replaces hawk-managed ones.
        """
        data: dict = {}
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}

        existing = data.get(server_key, {})
        if not isinstance(existing, dict):
            logger.warning(
                "Expected %s to be a dict in %s, got %s; ignoring malformed section",
                server_key,
                config_path,
                type(existing).__name__,
            )
            existing = {}

        # Remove old hawk-managed entries
        cleaned = {
            k: v for k, v in existing.items()
            if not (isinstance(v, dict) and v.get(HAWK_MCP_MARKER))
        }

        # Add new hawk-managed entries
        for name, cfg in servers.items():
            cleaned[name] = {**cfg, HAWK_MCP_MARKER: True}

        data[server_key] = cleaned
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2) + "\n")

    @staticmethod
    def _read_mcp_json(
        config_path: Path,
        server_key: str = "mcpServers",
    ) -> dict[str, dict]:
        """Read only hawk-managed MCP entries from a JSON config file."""
        if not config_path.exists():
            return {}
        try:
            data = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
        servers = data.get(server_key, {})
        if not isinstance(servers, dict):
            logger.warning(
                "Expected %s to be a dict in %s, got %s; skipping malformed section",
                server_key,
                config_path,
                type(servers).__name__,
            )
            return {}
        return {
            k: v for k, v in servers.items()
            if isinstance(v, dict) and v.get(HAWK_MCP_MARKER)
        }

    @staticmethod
    def _merge_mcp_sidecar(
        config_path: Path,
        servers: dict[str, dict],
        server_key: str = "mcpServers",
    ) -> None:
        """Merge hawk-managed MCP servers using a sidecar tracking file.

        Like _merge_mcp_json but keeps the server entries clean (no marker
        key injected). Managed server names are tracked in a .hawk-mcp.json
        sidecar file next to the config. Use this for tools with strict
        config validation that reject unknown keys (e.g. Gemini).
        """
        sidecar_path = config_path.parent / ".hawk-mcp.json"

        # Read existing managed names from sidecar
        old_managed: set[str] = set()
        if sidecar_path.exists():
            try:
                old_managed = set(json.loads(sidecar_path.read_text()))
            except (json.JSONDecodeError, OSError):
                pass

        # Also detect legacy inline markers and migrate them
        data: dict = {}
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}

        existing = data.get(server_key, {})
        if not isinstance(existing, dict):
            logger.warning(
                "Expected %s to be a dict in %s, got %s; ignoring malformed section",
                server_key,
                config_path,
                type(existing).__name__,
            )
            existing = {}

        # Collect legacy inline-marked entries
        for k, v in existing.items():
            if isinstance(v, dict) and v.get(HAWK_MCP_MARKER):
                old_managed.add(k)

        # Remove old hawk-managed entries (sidecar-tracked + legacy inline)
        cleaned = {}
        for k, v in existing.items():
            if k in old_managed:
                continue
            # Also strip any leftover inline markers
            if isinstance(v, dict):
                v = {ek: ev for ek, ev in v.items() if ek != HAWK_MCP_MARKER}
            cleaned[k] = v

        # Add new hawk-managed entries (clean, no marker)
        for name, cfg in servers.items():
            cleaned[name] = cfg

        data[server_key] = cleaned
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2) + "\n")

        # Write sidecar with current managed names
        new_managed = sorted(servers.keys())
        if new_managed:
            sidecar_path.write_text(json.dumps(new_managed, indent=2) + "\n")
        elif sidecar_path.exists():
            sidecar_path.unlink()

    @staticmethod
    def _create_symlink(source: Path, dest: Path) -> None:
        """Create a symlink, replacing existing."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            if dest.is_dir() and not dest.is_symlink():
                raise ValueError(f"Destination is a directory: {dest}")
            dest.unlink()
        dest.symlink_to(source.resolve())

    @staticmethod
    def _remove_link(path: Path) -> bool:
        """Remove a symlink or file. Returns True if removed."""
        if path.exists() or path.is_symlink():
            if path.is_dir() and not path.is_symlink():
                return False
            path.unlink()
            return True
        return False

    def _set_hook_diagnostics(
        self,
        *,
        skipped: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        """Set hook diagnostics for the current sync cycle."""
        self._hook_skipped = list(skipped or [])
        self._hook_errors = list(errors or [])

    def _take_hook_skipped(self) -> list[str]:
        """Return and clear hook skipped diagnostics from current sync cycle."""
        skipped = self._hook_skipped
        self._hook_skipped = []
        return skipped

    def _take_hook_errors(self) -> list[str]:
        """Return and clear hook error diagnostics from current sync cycle."""
        errors = self._hook_errors
        self._hook_errors = []
        return errors

    def _set_hook_warnings(self, warnings: list[str]) -> None:
        """Backwards-compatible alias for skipped hook diagnostics."""
        self._set_hook_diagnostics(skipped=warnings, errors=[])

    def _warn_hooks_unsupported(self, tool_name: str, hook_names: list[str]) -> None:
        """Record a standard warning for tools without hook support."""
        if not hook_names:
            self._set_hook_diagnostics(skipped=[], errors=[])
            return
        self._set_hook_diagnostics(
            skipped=[f"{tool_name} hook registration is unsupported; skipped {len(hook_names)} hook(s)"],
            errors=[],
        )
