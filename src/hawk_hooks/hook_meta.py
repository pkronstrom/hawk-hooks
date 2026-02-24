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

from .event_mapping import _ALIASES_TO_HAWK
from .events import EVENTS

# Matches: # hawk-hook: key=value  OR  // hawk-hook: key=value
_COMMENT_RE = re.compile(r"^(?:#|//)\s*hawk-hook:\s*(\w+)=(.+)$")

# Matches YAML frontmatter delimiters
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass
class HookMeta:
    """Metadata parsed from a hawk hook file."""

    events: list[str] = field(default_factory=list)
    description: str = ""
    deps: str = ""
    env: list[str] = field(default_factory=list)
    timeout: int = 0


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

    # Try JSON metadata for .prompt.json / .json files
    if suffix == ".json":
        meta = _parse_json_meta(text)
        if _has_parsed_metadata(meta):
            return _normalize_events(meta)

    # Try comment headers for scripts
    if suffix in (".py", ".sh", ".js", ".ts"):
        meta = _parse_comment_headers(text, js_style=suffix in (".js", ".ts"))
        if _has_parsed_metadata(meta):
            return _normalize_events(meta)

    # Try YAML frontmatter for markdown/text
    if suffix in (".md", ".txt"):
        meta = _parse_frontmatter(text)
        if _has_parsed_metadata(meta):
            return _normalize_events(meta)

    # Also try frontmatter for .stdout.md / .stdout.txt
    if path.name.endswith((".stdout.md", ".stdout.txt")):
        meta = _parse_frontmatter(text)
        if _has_parsed_metadata(meta):
            return _normalize_events(meta)

    # Fallback: parent directory name
    return _fallback_from_parent(path)


def _parse_comment_headers(text: str, js_style: bool = False) -> HookMeta:
    """Parse # hawk-hook: key=value (or // hawk-hook:) lines from script header."""
    meta = HookMeta()
    found_any = False

    for line in text.splitlines():
        stripped = line.strip()

        # Skip shebang
        if stripped.startswith("#!"):
            continue

        # Stop at first non-comment, non-empty line
        if stripped and not stripped.startswith("#") and not stripped.startswith("//"):
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
            elif key == "timeout":
                try:
                    meta.timeout = int(value)
                except ValueError:
                    pass

    return meta if found_any else HookMeta()


def _has_parsed_metadata(meta: HookMeta) -> bool:
    """Check whether any metadata fields were parsed."""
    return bool(meta.events or meta.description or meta.deps or meta.env or meta.timeout > 0)


def _normalize_events(meta: HookMeta) -> HookMeta:
    """Normalize legacy event aliases to canonical hawk event names."""
    if meta.events:
        meta.events = [_ALIASES_TO_HAWK.get(event, event) for event in meta.events]
    return meta


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

    timeout_raw = hawk.get("timeout", 0)
    try:
        timeout = int(timeout_raw)
    except (ValueError, TypeError):
        timeout = 0

    return HookMeta(
        events=events,
        description=str(hawk.get("description", "")),
        deps=str(hawk.get("deps", "")),
        env=env,
        timeout=timeout,
    )


def _parse_json_meta(text: str) -> HookMeta:
    """Parse hawk-hook metadata from a JSON file (e.g. .prompt.json).

    Looks for a top-level "hawk-hook" key with the same fields
    as YAML frontmatter (events, description, deps, env, timeout).
    """
    import json as _json

    try:
        data = _json.loads(text)
    except (_json.JSONDecodeError, ValueError):
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

    timeout_raw = hawk.get("timeout", 0)
    try:
        timeout = int(timeout_raw)
    except (ValueError, TypeError):
        timeout = 0

    return HookMeta(
        events=events,
        description=str(hawk.get("description", "")),
        deps=str(hawk.get("deps", "")),
        env=env,
        timeout=timeout,
    )


def _fallback_from_parent(path: Path) -> HookMeta:
    """Infer events from parent directory name if it's a known event."""
    parent_name = path.parent.name
    if parent_name in EVENTS:
        return HookMeta(events=[parent_name])
    return HookMeta()
