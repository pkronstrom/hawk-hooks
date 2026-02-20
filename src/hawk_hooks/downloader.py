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

import yaml

from .registry import Registry
from .types import ComponentType

# Manifest filename for package declarations
PACKAGE_MANIFEST = "hawk-package.yaml"


@dataclass
class PackageMeta:
    """Metadata from a hawk-package.yaml manifest."""

    name: str
    description: str = ""
    version: str = ""


@dataclass
class ClassifiedItem:
    """A classified item found in a downloaded repository."""

    component_type: ComponentType
    name: str
    source_path: Path
    description: str = ""
    package: str = ""  # package name this item belongs to (empty = unpackaged)


@dataclass
class ClassifiedContent:
    """Result of classifying a directory's contents."""

    items: list[ClassifiedItem] = field(default_factory=list)
    source_url: str = ""
    package_meta: PackageMeta | None = None
    packages: list[PackageMeta] = field(default_factory=list)  # all discovered packages

    @property
    def by_type(self) -> dict[ComponentType, list[ClassifiedItem]]:
        """Group items by component type."""
        result: dict[ComponentType, list[ClassifiedItem]] = {}
        for item in self.items:
            result.setdefault(item.component_type, []).append(item)
        return result

    @property
    def by_package(self) -> dict[str, list[ClassifiedItem]]:
        """Group items by package name. Empty string key = unpackaged."""
        result: dict[str, list[ClassifiedItem]] = {}
        for item in self.items:
            result.setdefault(item.package, []).append(item)
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


def get_head_commit(clone_dir: Path) -> str:
    """Get the HEAD commit hash from a cloned repository.

    Returns the full SHA hash, or empty string on failure.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(clone_dir),
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return ""


def _parse_package_manifest(path: Path) -> PackageMeta | None:
    """Parse a hawk-package.yaml manifest file.

    Returns PackageMeta if valid (has required 'name' field), None otherwise.
    """
    try:
        text = path.read_text(errors="replace")
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return None
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        desc = data.get("description")
        ver = data.get("version")
        return PackageMeta(
            name=name.strip(),
            description=str(desc) if desc is not None else "",
            version=str(ver) if ver is not None else "",
        )
    except (yaml.YAMLError, OSError):
        return None


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

    # Check for hawk-package.yaml manifest
    manifest = directory / PACKAGE_MANIFEST
    if manifest.is_file():
        content.package_meta = _parse_package_manifest(manifest)

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
            if component_type == ComponentType.HOOK:
                # Legacy event-dir layout: recurse one level into event dirs
                for sub in sorted(entry.iterdir()):
                    if sub.name.startswith(".") or sub.is_symlink() or not sub.is_file():
                        continue
                    # Validate file is actually a hook (skip READMEs, configs, etc.)
                    if not _is_hook_file(sub):
                        continue
                    content.items.append(
                        ClassifiedItem(
                            component_type=component_type,
                            name=sub.name,
                            source_path=sub,
                        )
                    )
            else:
                # Directory-style component (e.g., skill with multiple files)
                content.items.append(
                    ClassifiedItem(
                        component_type=component_type,
                        name=entry.name,
                        source_path=entry,
                    )
                )
        elif entry.is_file():
            if component_type == ComponentType.HOOK:
                # For hooks: validate file is a hook
                if _is_hook_file(entry):
                    content.items.append(
                        ClassifiedItem(
                            component_type=component_type,
                            name=entry.name,
                            source_path=entry,
                        )
                    )
            else:
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
    """Check which items would clash with existing registry entries or each other.

    Returns list of items that have clashes (registry or intra-batch duplicates).
    """
    clashes = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item.component_type.value, item.name)
        if registry.detect_clash(item.component_type, item.name) or key in seen:
            clashes.append(item)
        seen.add(key)
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


# Directories to skip during recursive scan
_SCAN_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".env", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".eggs", ".hawk", ".claude",
}

# File patterns that indicate a skill directory
_SKILL_MARKERS = {"SKILL.md", "skill.md"}


def scan_directory(directory: Path, max_depth: int = 5) -> ClassifiedContent:
    """Recursively scan a directory tree for hawk-compatible components.

    Unlike classify() which expects a well-structured repo layout,
    scan_directory() walks the tree and uses heuristics to find
    components at any depth:

    - Directories containing SKILL.md → skill
    - .md files in dirs named commands/ → command
    - .md files in dirs named agents/ → agent
    - .md files in dirs named prompts/ → prompt
    - Scripts in dirs named hooks/ → hook
    - .yaml/.json in dirs named mcp/ → mcp
    - Standalone .md files with frontmatter → command (if has name/description)
    - Standalone .md files → skill (fallback)

    Args:
        directory: Root directory to scan.
        max_depth: Maximum recursion depth.

    Returns:
        ClassifiedContent with all discovered items.
    """
    content = ClassifiedContent()
    seen_paths: set[Path] = set()  # avoid duplicates

    # Track package manifests: map resolved dir → PackageMeta
    # Items under a package dir get tagged with that package name
    package_dirs: dict[Path, str] = {}  # resolved_path → package_name

    # Check for hawk-package.yaml manifest at scan root
    root = directory.resolve()
    manifest = root / PACKAGE_MANIFEST
    if manifest.is_file():
        meta = _parse_package_manifest(manifest)
        content.package_meta = meta
        if meta:
            content.packages.append(meta)
            package_dirs[root] = meta.name

    def _current_package(path: Path) -> str:
        """Find which package a path belongs to (longest matching prefix)."""
        resolved = path.resolve()
        best = ""
        best_len = 0
        for pkg_dir, pkg_name in package_dirs.items():
            try:
                resolved.relative_to(pkg_dir)
                if len(str(pkg_dir)) > best_len:
                    best = pkg_name
                    best_len = len(str(pkg_dir))
            except ValueError:
                continue
        return best

    def _walk(path: Path, depth: int) -> None:
        if depth > max_depth:
            return
        if not path.is_dir():
            return

        try:
            entries = sorted(path.iterdir())
        except PermissionError:
            return

        # Discover nested hawk-package.yaml manifests
        pkg_manifest = path / PACKAGE_MANIFEST
        if pkg_manifest.is_file() and path.resolve() not in package_dirs:
            meta = _parse_package_manifest(pkg_manifest)
            if meta:
                content.packages.append(meta)
                package_dirs[path.resolve()] = meta.name
                # Set as primary if none set yet
                if content.package_meta is None:
                    content.package_meta = meta

        pkg_name = _current_package(path)

        # Check if this directory IS a skill (has SKILL.md)
        entry_names = {e.name for e in entries if e.is_file()}
        if entry_names & _SKILL_MARKERS:
            if path not in seen_paths:
                seen_paths.add(path)
                content.items.append(ClassifiedItem(
                    component_type=ComponentType.SKILL,
                    name=path.name,
                    source_path=path,
                    package=pkg_name,
                ))
            return  # Don't recurse into skill dirs

        # Classify based on parent directory name
        parent_name = path.name.lower()

        for entry in entries:
            if entry.name.startswith(".") or entry.name.startswith("_"):
                continue
            if entry.is_symlink():
                continue

            if entry.is_dir():
                if entry.name in _SCAN_SKIP_DIRS:
                    continue
                _walk(entry, depth + 1)

            elif entry.is_file() and entry not in seen_paths:
                item = _classify_file(entry, parent_name)
                if item:
                    item.package = _current_package(entry)
                    seen_paths.add(entry)
                    content.items.append(item)

    _walk(root, 0)
    return content


def _is_hook_file(path: Path) -> bool:
    """Check if a file is a valid hook (script, .stdout.*, .prompt.json, or has hawk-hook header)."""
    suffix = path.suffix.lower()

    # .prompt.json files are always valid hooks (Claude native prompt hooks)
    if path.name.endswith(".prompt.json"):
        return True

    # Scripts are always valid hooks
    if suffix in (".py", ".sh", ".js", ".ts"):
        return True

    # .stdout.* files are always content hooks
    if path.name.endswith((".stdout.md", ".stdout.txt")):
        return True

    # .md/.txt only if they have explicit hawk-hook metadata
    # (not the parent-directory fallback, which would match any .md in an event dir)
    if suffix in (".md", ".txt"):
        try:
            from .hook_meta import _parse_frontmatter, _parse_comment_headers
            text = path.read_text(errors="replace")
            meta = _parse_frontmatter(text)
            if meta.events:
                return True
            meta = _parse_comment_headers(text)
            return bool(meta.events)
        except Exception:
            return False

    return False


def _classify_file(path: Path, parent_dir_name: str) -> ClassifiedItem | None:
    """Classify a single file based on its extension and parent directory."""
    suffix = path.suffix.lower()
    name = path.name

    # MCP configs
    if parent_dir_name == "mcp" and suffix in (".yaml", ".yml", ".json"):
        return ClassifiedItem(ComponentType.MCP, name, path)

    # Commands
    if parent_dir_name == "commands" and suffix == ".md":
        return ClassifiedItem(ComponentType.COMMAND, name, path)

    # Agents
    if parent_dir_name == "agents" and suffix == ".md":
        return ClassifiedItem(ComponentType.AGENT, name, path)

    # Prompts
    if parent_dir_name == "prompts" and suffix == ".md":
        return ClassifiedItem(ComponentType.PROMPT, name, path)

    # Hooks — .prompt.json in hooks/ dir
    if parent_dir_name == "hooks" and name.endswith(".prompt.json"):
        return ClassifiedItem(ComponentType.HOOK, name, path)

    # Hooks — scripts in hooks/ dir
    if parent_dir_name == "hooks" and suffix in (".py", ".sh", ".js", ".ts"):
        return ClassifiedItem(ComponentType.HOOK, name, path)

    # Hooks — .stdout.* in hooks/
    if parent_dir_name == "hooks" and name.endswith((".stdout.md", ".stdout.txt")):
        return ClassifiedItem(ComponentType.HOOK, name, path)

    # Hooks — .md/.txt in hooks/ with hawk-hook frontmatter
    if parent_dir_name == "hooks" and suffix in (".md", ".txt"):
        if _is_hook_file(path):
            return ClassifiedItem(ComponentType.HOOK, name, path)
        return None  # Skip plain markdown in hooks/

    # Markdown with frontmatter → try to classify as command
    if suffix == ".md":
        try:
            head = path.read_text(errors="replace")[:500]
            if head.startswith("---"):
                # Has frontmatter — likely a command
                if "name:" in head and "description:" in head:
                    return ClassifiedItem(ComponentType.COMMAND, name, path)
        except OSError:
            pass

    return None
