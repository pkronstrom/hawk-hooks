"""Abstract base class for tool adapters."""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

from ..registry import _validate_name
from ..types import ResolvedSet, SyncResult, Tool
from .mixins import HookRunnerMixin, MCPMixin
from .mixins.mcp import HAWK_MCP_MARKER as _HAWK_MCP_MARKER

# Backwards-compatible re-export for existing adapter imports.
HAWK_MCP_MARKER = _HAWK_MCP_MARKER


class ToolAdapter(HookRunnerMixin, MCPMixin, ABC):
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
