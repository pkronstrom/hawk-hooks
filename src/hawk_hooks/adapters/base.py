"""Abstract base class for tool adapters."""

from __future__ import annotations

import json
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..registry import _validate_name
from ..types import ResolvedSet, SyncResult, Tool

# Shared marker for hawk-managed MCP entries
HAWK_MCP_MARKER = "__hawk_managed"


class ToolAdapter(ABC):
    """Abstract base for AI CLI tool adapters.

    Each adapter knows how to link/unlink components and manage
    tool-specific configuration files.
    """

    @property
    @abstractmethod
    def tool(self) -> Tool:
        """Which tool this adapter manages."""

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
        for dir_getter in [self.get_skills_dir, self.get_agents_dir, self.get_commands_dir, self.get_prompts_dir]:
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

        # Sync commands
        self._sync_component(
            resolved.commands,
            registry_path / "commands",
            target_dir,
            self.link_command,
            self.unlink_command,
            self.get_commands_dir,
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
            registered = self.register_hooks(resolved.hooks, target_dir, registry_path=registry_path)
            result.linked.extend(f"hook:{h}" for h in registered)
        except Exception as e:
            result.errors.append(f"hooks: {e}")

        # Sync MCP servers
        if resolved.mcp:
            try:
                servers = self._load_mcp_servers(resolved.mcp, registry_path / "mcp")
                if servers:
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
        """Generate bash runners from hook references.

        Hook names use event/filename format (e.g. "pre_tool_use/file-guard.py").
        Groups hooks by event, generates one runner per event that chains
        all enabled hooks for that event.

        Returns dict of {event_name: runner_path}.
        """
        from collections import defaultdict
        import shlex
        from ..generator import _get_interpreter_path, _atomic_write_executable

        # Group by event
        hooks_by_event: dict[str, list[Path]] = defaultdict(list)
        hooks_dir = registry_path / "hooks"
        for ref in hook_names:
            if "/" not in ref:
                continue
            event, filename = ref.split("/", 1)
            hook_path = hooks_dir / event / filename
            if hook_path.is_file():
                hooks_by_event[event].append(hook_path)

        runners: dict[str, Path] = {}
        runners_dir.mkdir(parents=True, exist_ok=True)

        for event, scripts in hooks_by_event.items():
            calls: list[str] = []
            for script in scripts:
                safe_path = shlex.quote(str(script))
                suffix = script.suffix

                if script.name.endswith((".stdout.md", ".stdout.txt")):
                    # Stdout hook: cat the file
                    try:
                        cat_path = _get_interpreter_path("cat")
                    except FileNotFoundError:
                        cat_path = "cat"
                    calls.append(f'[[ -f {safe_path} ]] && {cat_path} {safe_path}')
                elif suffix == ".py":
                    calls.append(
                        f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | python3 {safe_path} || exit $?; }}'
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
                    # Assume executable
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
    ) -> None:
        """Sync a set of components: link desired, unlink stale."""
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

        # Find currently linked items (symlinks only)
        current: set[str] = set()
        if comp_dir.exists():
            for entry in comp_dir.iterdir():
                if entry.is_symlink():
                    # Check if it points into our registry
                    try:
                        target = entry.resolve()
                        resolved_source = source_dir.resolve()
                        if target == resolved_source or target.is_relative_to(resolved_source):
                            current.add(entry.name)
                    except (OSError, ValueError):
                        pass

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
        return {
            k: v for k, v in servers.items()
            if isinstance(v, dict) and v.get(HAWK_MCP_MARKER)
        }

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
