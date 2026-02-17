"""Component registry for hawk-hooks v2.

Manages the registry directory (~/.config/hawk-hooks/registry/) containing
skills, hooks, commands, agents, MCP configs, and prompts.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .types import ComponentType
from . import v2_config


class Registry:
    """Manages the hawk-hooks component registry."""

    def __init__(self, registry_path: Path | None = None):
        """Initialize with an optional registry path override."""
        self._registry_path = registry_path

    @property
    def path(self) -> Path:
        """Get the registry root path."""
        if self._registry_path is not None:
            return self._registry_path
        return v2_config.get_registry_path()

    def _type_dir(self, component_type: ComponentType) -> Path:
        """Get the directory for a component type."""
        return self.path / component_type.registry_dir

    def ensure_dirs(self) -> None:
        """Ensure all registry subdirectories exist."""
        for ct in ComponentType:
            self._type_dir(ct).mkdir(parents=True, exist_ok=True)

    def add(self, component_type: ComponentType, name: str, source: Path) -> Path:
        """Add a component to the registry.

        Args:
            component_type: Type of component.
            name: Name for the component in the registry.
            source: Source path (file or directory).

        Returns:
            Path to the component in the registry.

        Raises:
            FileNotFoundError: If source does not exist.
            FileExistsError: If name already exists (use detect_clash first).
        """
        if not source.exists():
            raise FileNotFoundError(f"Source not found: {source}")

        type_dir = self._type_dir(component_type)
        type_dir.mkdir(parents=True, exist_ok=True)

        dest = type_dir / name
        if dest.exists():
            raise FileExistsError(f"Already exists in registry: {component_type}/{name}")

        if source.is_dir():
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)

        return dest

    def remove(self, component_type: ComponentType, name: str) -> bool:
        """Remove a component from the registry.

        Returns True if removed, False if not found.
        """
        dest = self._type_dir(component_type) / name
        if not dest.exists():
            return False

        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()
        return True

    def has(self, component_type: ComponentType, name: str) -> bool:
        """Check if a component exists in the registry."""
        return (self._type_dir(component_type) / name).exists()

    def get_path(self, component_type: ComponentType, name: str) -> Path | None:
        """Get the path to a component, or None if not found."""
        path = self._type_dir(component_type) / name
        if path.exists():
            return path
        return None

    def list(self, component_type: ComponentType | None = None) -> dict[ComponentType, list[str]]:
        """List registry contents.

        Args:
            component_type: Filter to a specific type, or None for all.

        Returns:
            Dict mapping component types to sorted lists of names.
        """
        types = [component_type] if component_type else list(ComponentType)
        result: dict[ComponentType, list[str]] = {}

        for ct in types:
            type_dir = self._type_dir(ct)
            if not type_dir.exists():
                result[ct] = []
                continue
            names = sorted(
                entry.name
                for entry in type_dir.iterdir()
                if not entry.name.startswith(".")
            )
            result[ct] = names

        return result

    def detect_clash(self, component_type: ComponentType, name: str) -> bool:
        """Check if adding this name would clash with existing entries.

        Returns True if there IS a clash.
        """
        return self.has(component_type, name)

    def list_flat(self) -> list[tuple[ComponentType, str]]:
        """List all registry contents as flat (type, name) tuples."""
        result = []
        for ct, names in self.list().items():
            for name in names:
                result.append((ct, name))
        return result

    def has_from_name(self, type_dir: str, name: str) -> bool:
        """Check if a name exists in a registry subdirectory by dir name."""
        return (self.path / type_dir / name).exists()
