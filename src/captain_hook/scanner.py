"""Auto-discovery scanner for hook scripts."""

import re
from dataclasses import dataclass
from pathlib import Path

from . import config

# Supported file extensions and their interpreters
INTERPRETERS: dict[str, str] = {
    ".py": "python",
    ".js": "node",
    ".sh": "bash",
    ".ts": "bun run",
}

# Hook types based on filename patterns
# filename.stdout.md / filename.stdout.txt → output content to stdout
# filename.prompt.json → native Claude prompt hook (Haiku evaluates)
STDOUT_PATTERN = ".stdout."  # e.g., reminder.stdout.md
PROMPT_SUFFIX = ".prompt.json"  # e.g., completion-check.prompt.json


@dataclass
class HookInfo:
    """Information about a discovered hook."""

    name: str
    path: Path
    event: str
    description: str
    deps: list[str]
    hook_type: str  # "command", "stdout", or "prompt"
    extension: str

    @property
    def is_stdout(self) -> bool:
        """Check if this is a stdout hook (content output)."""
        return self.hook_type == "stdout"

    @property
    def is_native_prompt(self) -> bool:
        """Check if this is a native Claude prompt hook."""
        return self.hook_type == "prompt"

    @property
    def interpreter(self) -> str | None:
        """Get the interpreter for this hook."""
        if self.hook_type != "command":
            return None
        return INTERPRETERS.get(self.extension)


def parse_hook_metadata(path: Path) -> tuple[str, list[str]]:
    """Parse description and deps from a hook file.

    Looks for:
    - # Description: ... (second line for scripts, first line for prompts)
    - # Deps: dep1, dep2, ...
    """
    description = ""
    deps: list[str] = []

    try:
        content = path.read_text()
        lines = content.split("\n")

        for i, line in enumerate(lines[:10]):  # Only check first 10 lines
            # Description pattern
            desc_match = re.match(r"^[#/\-*\s]*Description:\s*(.+)$", line, re.IGNORECASE)
            if desc_match:
                description = desc_match.group(1).strip()

            # Deps pattern
            deps_match = re.match(r"^[#/\-*\s]*Deps:\s*(.+)$", line, re.IGNORECASE)
            if deps_match:
                deps_str = deps_match.group(1).strip()
                deps = [d.strip() for d in deps_str.split(",") if d.strip()]

    except Exception:
        pass

    return description, deps


def scan_hooks(hooks_dir: Path | None = None) -> dict[str, list[HookInfo]]:
    """Scan for all hooks organized by event.

    Returns:
        Dict mapping event names to lists of HookInfo objects.
    """
    if hooks_dir is None:
        hooks_dir = config.get_hooks_dir()

    result: dict[str, list[HookInfo]] = {event: [] for event in config.EVENTS}

    for event in config.EVENTS:
        event_dir = hooks_dir / event
        if not event_dir.exists():
            continue

        resolved_event_dir = event_dir.resolve()

        for path in sorted(event_dir.iterdir()):
            # Security: skip symlinks pointing outside the hooks directory
            if path.is_symlink():
                try:
                    real_path = path.resolve()
                    if not str(real_path).startswith(str(resolved_event_dir)):
                        continue  # Skip symlinks pointing outside
                except (OSError, ValueError):
                    continue  # Skip broken symlinks

            if not path.is_file():
                continue

            filename = path.name.lower()
            ext = path.suffix.lower()

            # Determine hook type based on filename pattern
            if STDOUT_PATTERN in filename:
                # e.g., reminder.stdout.md → stdout hook (cat content)
                hook_type = "stdout"
                # Get the base name without .stdout.ext
                name = filename.split(STDOUT_PATTERN)[0]
            elif filename.endswith(PROMPT_SUFFIX):
                # e.g., completion-check.prompt.json → native Claude prompt hook
                hook_type = "prompt"
                name = filename[:-len(PROMPT_SUFFIX)]
            elif ext in INTERPRETERS:
                # Regular command hook
                hook_type = "command"
                name = path.stem
            else:
                continue  # Unsupported file type

            # Parse metadata
            description, deps = parse_hook_metadata(path)

            # Create hook info
            hook = HookInfo(
                name=name,
                path=path,
                event=event,
                description=description or f"{name} hook",
                deps=deps,
                hook_type=hook_type,
                extension=ext,
            )

            result[event].append(hook)

    return result


def scan_all_hooks() -> list[HookInfo]:
    """Scan and return all hooks as a flat list."""
    hooks_by_event = scan_hooks()
    all_hooks = []
    for hooks in hooks_by_event.values():
        all_hooks.extend(hooks)
    return all_hooks


def get_hook_by_name(event: str, name: str) -> HookInfo | None:
    """Get a specific hook by event and name."""
    hooks = scan_hooks()
    for hook in hooks.get(event, []):
        if hook.name == name:
            return hook
    return None


def get_python_deps() -> dict[str, list[str]]:
    """Get all Python dependencies from all hooks.

    Returns:
        Dict mapping hook names to their deps.
    """
    result: dict[str, list[str]] = {}
    hooks = scan_all_hooks()

    for hook in hooks:
        if hook.extension == ".py" and hook.deps:
            result[hook.name] = hook.deps

    return result


def get_non_python_deps() -> dict[str, dict[str, list[str]]]:
    """Get non-Python dependencies grouped by language.

    Returns:
        Dict mapping language to dict of hook names to deps.
    """
    result: dict[str, dict[str, list[str]]] = {}
    hooks = scan_all_hooks()

    for hook in hooks:
        if hook.extension != ".py" and hook.deps:
            lang = INTERPRETERS.get(hook.extension, "unknown")
            if lang not in result:
                result[lang] = {}
            result[lang][hook.name] = hook.deps

    return result
