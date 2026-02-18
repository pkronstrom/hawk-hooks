"""Parse hawk-hook metadata from hook files.

Supports two formats:
- Comment headers in scripts: # hawk-hook: events=pre_tool_use,stop
- YAML frontmatter in .md/.txt: hawk-hook: {events: [stop]}

Fallback: infer events from parent directory name if it matches a known event.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .events import EVENTS

# Matches: # hawk-hook: key=value
_COMMENT_RE = re.compile(r"^#\s*hawk-hook:\s*(\w+)=(.+)$")

# Matches YAML frontmatter delimiters
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass
class HookMeta:
    """Metadata parsed from a hawk hook file."""

    events: list[str] = field(default_factory=list)
    description: str = ""
    deps: str = ""
    env: list[str] = field(default_factory=list)


def parse_hook_meta(path: Path) -> HookMeta:
    """Parse hawk-hook metadata from a file.

    Tries in order:
    1. hawk-hook: comment headers (scripts)
    2. YAML frontmatter with hawk-hook key (.md/.txt)
    3. Parent directory fallback (if parent is a known event name)

    Returns HookMeta with events=[] if no metadata found and no fallback applies.
    """
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return HookMeta()

    suffix = path.suffix.lower()

    # Try comment headers for scripts
    if suffix in (".py", ".sh", ".js", ".ts"):
        meta = _parse_comment_headers(text)
        if meta.events:
            return meta

    # Try YAML frontmatter for markdown/text
    if suffix in (".md", ".txt"):
        meta = _parse_frontmatter(text)
        if meta.events:
            return meta

    # Also try frontmatter for .stdout.md / .stdout.txt
    if path.name.endswith((".stdout.md", ".stdout.txt")):
        meta = _parse_frontmatter(text)
        if meta.events:
            return meta

    # Fallback: parent directory name
    return _fallback_from_parent(path)


def _parse_comment_headers(text: str) -> HookMeta:
    """Parse # hawk-hook: key=value lines from script header."""
    meta = HookMeta()
    found_any = False

    for line in text.splitlines():
        stripped = line.strip()

        # Skip shebang
        if stripped.startswith("#!"):
            continue

        # Stop at first non-comment, non-empty line
        if stripped and not stripped.startswith("#"):
            break

        m = _COMMENT_RE.match(stripped)
        if m:
            key, value = m.group(1), m.group(2).strip()
            found_any = True
            if key == "events":
                meta.events = [e.strip() for e in value.split(",") if e.strip()]
            elif key == "description":
                meta.description = value
            elif key == "deps":
                meta.deps = value
            elif key == "env":
                meta.env.append(value)

    return meta if found_any else HookMeta()


def _parse_frontmatter(text: str) -> HookMeta:
    """Parse YAML frontmatter with hawk-hook key."""
    import yaml

    m = _FRONTMATTER_RE.match(text)
    if not m:
        return HookMeta()

    try:
        data = yaml.safe_load(m.group(1))
    except Exception:
        return HookMeta()

    if not isinstance(data, dict):
        return HookMeta()

    hawk = data.get("hawk-hook")
    if not isinstance(hawk, dict):
        return HookMeta()

    events_raw = hawk.get("events", [])
    if isinstance(events_raw, str):
        events = [e.strip() for e in events_raw.split(",") if e.strip()]
    elif isinstance(events_raw, list):
        events = [str(e) for e in events_raw]
    else:
        events = []

    env_raw = hawk.get("env", [])
    if isinstance(env_raw, str):
        env = [env_raw]
    elif isinstance(env_raw, list):
        env = [str(e) for e in env_raw]
    else:
        env = []

    return HookMeta(
        events=events,
        description=str(hawk.get("description", "")),
        deps=str(hawk.get("deps", "")),
        env=env,
    )


def _fallback_from_parent(path: Path) -> HookMeta:
    """Infer events from parent directory name if it's a known event."""
    parent_name = path.parent.name
    if parent_name in EVENTS:
        return HookMeta(events=[parent_name])
    return HookMeta()
