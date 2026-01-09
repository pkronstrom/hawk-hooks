"""Auto-discovery scanner for hook scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import config
from .types import HookType

# Security: Package name validation pattern
# Allows alphanumeric, hyphens, underscores, dots, and @ for scoped npm packages
VALID_PACKAGE_NAME = re.compile(r"^[@a-zA-Z0-9._-]+$")

# Security: Max length for env var values
MAX_ENV_VALUE_LENGTH = 1000

# Max lines to scan for metadata comments at start of hook files
METADATA_SCAN_LINES = 20


def validate_package_name(name: str) -> bool:
    """Validate a package name is safe for shell commands.

    Returns True if the name contains only allowed characters.
    """
    if not name or len(name) > 200:
        return False
    return bool(VALID_PACKAGE_NAME.match(name))


def validate_env_value(value: str) -> bool:
    """Validate an environment variable value is safe.

    Returns True if the value is within length limits.
    """
    return len(value) <= MAX_ENV_VALUE_LENGTH


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
    env_vars: dict[str, str]  # VAR_NAME -> default_value
    hook_type: HookType
    extension: str

    @property
    def is_stdout(self) -> bool:
        """Check if this is a stdout hook (content output)."""
        return self.hook_type == HookType.STDOUT

    @property
    def is_native_prompt(self) -> bool:
        """Check if this is a native Claude prompt hook."""
        return self.hook_type == HookType.PROMPT

    @property
    def is_command(self) -> bool:
        """Check if this is a command hook (executable script)."""
        return self.hook_type == HookType.COMMAND

    @property
    def interpreter(self) -> str | None:
        """Get the interpreter for this hook."""
        if self.hook_type != HookType.COMMAND:
            return None
        return INTERPRETERS.get(self.extension)


def parse_hook_metadata(path: Path, hook_name: str) -> tuple[str, list[str], dict[str, str]]:
    """Parse description, deps, and env vars from a hook file.

    Looks for:
    - # Description: ...
    - # Deps: dep1, dep2, ...
    - # Env: VAR_NAME=default_value

    Env vars are namespaced by hook name:
    - Hook: notify.py, Env: DESKTOP=true -> NOTIFY_DESKTOP=true
    """
    description = ""
    deps: list[str] = []
    env_vars: dict[str, str] = {}

    # Convert hook name to env var prefix: my-cool-hook -> MY_COOL_HOOK_
    prefix = hook_name.upper().replace("-", "_").replace(".", "_") + "_"

    try:
        content = path.read_text()
        lines = content.split("\n")

        for line in lines[:METADATA_SCAN_LINES]:
            # Description pattern
            desc_match = re.match(r"^[#/\-*\s]*Description:\s*(.+)$", line, re.IGNORECASE)
            if desc_match:
                description = desc_match.group(1).strip()

            # Deps pattern
            deps_match = re.match(r"^[#/\-*\s]*Deps:\s*(.+)$", line, re.IGNORECASE)
            if deps_match:
                deps_str = deps_match.group(1).strip()
                # Security: validate each package name
                raw_deps = [d.strip() for d in deps_str.split(",") if d.strip()]
                deps = [d for d in raw_deps if validate_package_name(d)]

            # Env pattern: # Env: VAR_NAME=default_value
            env_match = re.match(
                r"^[#/\-*\s]*Env:\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line, re.IGNORECASE
            )
            if env_match:
                var_name = env_match.group(1).upper()
                default_value = env_match.group(2).strip()
                # Security: validate env value length
                if validate_env_value(default_value):
                    # Namespace by hook name
                    full_var_name = prefix + var_name
                    env_vars[full_var_name] = default_value

    except (OSError, UnicodeDecodeError):
        # Skip metadata parsing if file can't be read or decoded
        # This is non-critical - hook still works without metadata
        pass

    return description, deps, env_vars


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
            # Security: skip symlinks entirely for safety
            # This prevents path traversal attacks and accidental inclusion of sensitive files
            if path.is_symlink():
                continue

            if not path.is_file():
                continue

            filename = path.name.lower()
            ext = path.suffix.lower()

            # Determine hook type based on filename pattern
            if STDOUT_PATTERN in filename:
                # e.g., reminder.stdout.md → stdout hook (cat content)
                hook_type = HookType.STDOUT
                # Get the base name without .stdout.ext
                name = filename.split(STDOUT_PATTERN)[0]
            elif filename.endswith(PROMPT_SUFFIX):
                # e.g., completion-check.prompt.json → native Claude prompt hook
                hook_type = HookType.PROMPT
                name = filename[: -len(PROMPT_SUFFIX)]
            elif ext in INTERPRETERS:
                # Regular command hook
                hook_type = HookType.COMMAND
                name = path.stem
            else:
                continue  # Unsupported file type

            # Parse metadata
            description, deps, env_vars = parse_hook_metadata(path, name)

            # Create hook info
            hook = HookInfo(
                name=name,
                path=path,
                event=event,
                description=description or f"{name} hook",
                deps=deps,
                env_vars=env_vars,
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


def get_all_env_vars() -> dict[str, str]:
    """Get all env vars from all hooks with their default values.

    Returns:
        Dict mapping env var names to default values.
    """
    result: dict[str, str] = {}
    hooks = scan_all_hooks()

    for hook in hooks:
        result.update(hook.env_vars)

    return result
