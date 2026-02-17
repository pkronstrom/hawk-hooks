"""Download and classify components from git repositories.

hawk download <url> flow:
1. Shallow clone to temp dir
2. Classify contents (skills, hooks, commands, agents, MCP, prompts)
3. Check for name clashes
4. Copy selected items to registry
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .registry import Registry
from .types import ComponentType


@dataclass
class ClassifiedItem:
    """A classified item found in a downloaded repository."""

    component_type: ComponentType
    name: str
    source_path: Path
    description: str = ""


@dataclass
class ClassifiedContent:
    """Result of classifying a directory's contents."""

    items: list[ClassifiedItem] = field(default_factory=list)
    source_url: str = ""

    @property
    def by_type(self) -> dict[ComponentType, list[ClassifiedItem]]:
        """Group items by component type."""
        result: dict[ComponentType, list[ClassifiedItem]] = {}
        for item in self.items:
            result.setdefault(item.component_type, []).append(item)
        return result


def shallow_clone(url: str, dest: Path | None = None) -> Path:
    """Shallow clone a git repository.

    Args:
        url: Git URL to clone.
        dest: Destination directory. If None, creates a temp dir.

    Returns:
        Path to the cloned directory.

    Raises:
        subprocess.CalledProcessError: If git clone fails.
    """
    if dest is None:
        dest = Path(tempfile.mkdtemp(prefix="hawk-download-"))

    subprocess.run(
        ["git", "clone", "--depth", "1", "--single-branch", url, str(dest)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return dest


def classify(directory: Path) -> ClassifiedContent:
    """Classify the contents of a directory into component types.

    Detection heuristics:
    - skills/: directories containing SKILL.md or *.md with skill frontmatter
    - hooks/: directories organized by event name, or scripts with hook metadata
    - commands/: .md files in commands/ directory
    - agents/: .md files in agents/ directory
    - mcp/: .yaml or .json files with mcpServers definitions
    - prompts/: .md files in prompts/ directory
    - Top-level .md files: classified as skills by default
    """
    content = ClassifiedContent()

    if not directory.exists():
        return content

    # Check for well-known directory structures
    _scan_typed_dir(directory / "skills", ComponentType.SKILL, content)
    _scan_typed_dir(directory / "hooks", ComponentType.HOOK, content)
    _scan_typed_dir(directory / "commands", ComponentType.COMMAND, content)
    _scan_typed_dir(directory / "agents", ComponentType.AGENT, content)
    _scan_typed_dir(directory / "prompts", ComponentType.PROMPT, content)
    _scan_mcp_dir(directory / "mcp", content)

    # Check for top-level items if no subdirectories found
    if not content.items:
        _scan_top_level(directory, content)

    return content


def _scan_typed_dir(
    directory: Path,
    component_type: ComponentType,
    content: ClassifiedContent,
) -> None:
    """Scan a typed subdirectory for components."""
    if not directory.exists() or not directory.is_dir():
        return

    for entry in sorted(directory.iterdir()):
        if entry.name.startswith("."):
            continue
        # Skip symlinks for security (untrusted repos could link outside clone)
        if entry.is_symlink():
            continue

        if entry.is_dir():
            # Directory-style component (e.g., skill with multiple files)
            content.items.append(
                ClassifiedItem(
                    component_type=component_type,
                    name=entry.name,
                    source_path=entry,
                )
            )
        elif entry.is_file():
            content.items.append(
                ClassifiedItem(
                    component_type=component_type,
                    name=entry.name,
                    source_path=entry,
                )
            )


def _scan_mcp_dir(directory: Path, content: ClassifiedContent) -> None:
    """Scan for MCP configuration files."""
    if not directory.exists():
        return

    for entry in sorted(directory.iterdir()):
        if entry.is_symlink():
            continue
        if entry.is_file() and entry.suffix in (".yaml", ".yml", ".json"):
            content.items.append(
                ClassifiedItem(
                    component_type=ComponentType.MCP,
                    name=entry.name,
                    source_path=entry,
                )
            )


def _scan_top_level(directory: Path, content: ClassifiedContent) -> None:
    """Scan top-level files when no structured subdirectories found."""
    for entry in sorted(directory.iterdir()):
        if entry.name.startswith(".") or entry.name.startswith("_"):
            continue
        if entry.is_symlink():
            continue

        if entry.is_file():
            if entry.suffix == ".md":
                # Default: classify as skill
                content.items.append(
                    ClassifiedItem(
                        component_type=ComponentType.SKILL,
                        name=entry.name,
                        source_path=entry,
                    )
                )
            elif entry.suffix in (".py", ".sh", ".js", ".ts"):
                content.items.append(
                    ClassifiedItem(
                        component_type=ComponentType.HOOK,
                        name=entry.name,
                        source_path=entry,
                    )
                )
        elif entry.is_dir() and not entry.name.startswith("."):
            # Check if it looks like a skill directory
            if (entry / "SKILL.md").exists() or any(
                f.suffix == ".md" for f in entry.iterdir() if f.is_file()
            ):
                content.items.append(
                    ClassifiedItem(
                        component_type=ComponentType.SKILL,
                        name=entry.name,
                        source_path=entry,
                    )
                )


def check_clashes(
    items: list[ClassifiedItem], registry: Registry
) -> list[ClassifiedItem]:
    """Check which items would clash with existing registry entries.

    Returns list of items that have clashes.
    """
    clashes = []
    for item in items:
        if registry.detect_clash(item.component_type, item.name):
            clashes.append(item)
    return clashes


def add_items_to_registry(
    items: list[ClassifiedItem],
    registry: Registry,
    replace: bool = False,
) -> tuple[list[str], list[str]]:
    """Add classified items to the registry.

    Args:
        items: Items to add.
        registry: Target registry.
        replace: If True, replace existing items.

    Returns:
        Tuple of (added_names, skipped_names).
    """
    added: list[str] = []
    skipped: list[str] = []

    for item in items:
        if registry.detect_clash(item.component_type, item.name):
            if replace:
                registry.remove(item.component_type, item.name)
            else:
                skipped.append(f"{item.component_type}/{item.name}")
                continue

        try:
            registry.add(item.component_type, item.name, item.source_path)
            added.append(f"{item.component_type}/{item.name}")
        except (FileNotFoundError, FileExistsError, OSError) as e:
            skipped.append(f"{item.component_type}/{item.name}: {e}")

    return added, skipped
