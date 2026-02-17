"""Abstract base class for tool adapters."""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from ..types import ResolvedSet, SyncResult, Tool


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

    # ── Hook operations ──

    @abstractmethod
    def register_hooks(self, hook_names: list[str], target_dir: Path) -> list[str]:
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
        for dir_getter in [self.get_skills_dir, self.get_agents_dir, self.get_commands_dir]:
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

        # Register hooks
        try:
            registered = self.register_hooks(resolved.hooks, target_dir)
            result.linked.extend(f"hook:{h}" for h in registered)
        except Exception as e:
            result.errors.append(f"hooks: {e}")

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
    ) -> None:
        """Sync a set of components: link desired, unlink stale."""
        desired = set(names)
        comp_dir = get_dir_fn(target_dir)

        # Find currently linked items (symlinks only)
        current: set[str] = set()
        if comp_dir.exists():
            for entry in comp_dir.iterdir():
                if entry.is_symlink():
                    # Check if it points into our registry
                    try:
                        target = entry.resolve()
                        if str(source_dir.resolve()) in str(target):
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
            if source.exists():
                try:
                    link_fn(source, target_dir)
                    result.linked.append(name)
                except Exception as e:
                    result.errors.append(f"link {name}: {e}")

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
