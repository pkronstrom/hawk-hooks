"""Scanner for prompts and agents directories.

Scans ~/.config/hawk-hooks/prompts/ and agents/ for markdown files
with valid frontmatter.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from time import time

from . import config
from .frontmatter import parse_frontmatter
from .types import PromptInfo, PromptType

logger = logging.getLogger(__name__)

# Cache configuration
_cache_timestamp: float = 0
_CACHE_TTL: float = 5.0  # seconds


def _get_cache_key() -> int:
    """Return cache key that changes when cache should invalidate.

    The cache is invalidated after _CACHE_TTL seconds.
    """
    global _cache_timestamp
    now = time()
    if now - _cache_timestamp > _CACHE_TTL:
        _cache_timestamp = now
    return int(_cache_timestamp)


def invalidate_cache() -> None:
    """Force cache invalidation on next call."""
    global _cache_timestamp
    _cache_timestamp = 0
    _cached_scan_all.cache_clear()


def scan_prompts(prompts_dir: Path | None = None) -> list[PromptInfo]:
    """Scan prompts directory for valid prompt files.

    Args:
        prompts_dir: Directory to scan. Defaults to config prompts dir.

    Returns:
        List of PromptInfo for valid prompts.
    """
    if prompts_dir is None:
        prompts_dir = config.get_prompts_dir()

    return _scan_directory(prompts_dir, PromptType.COMMAND)


def scan_agents(agents_dir: Path | None = None) -> list[PromptInfo]:
    """Scan agents directory for valid agent files.

    Args:
        agents_dir: Directory to scan. Defaults to config agents dir.

    Returns:
        List of PromptInfo for valid agents.
    """
    if agents_dir is None:
        agents_dir = config.get_agents_dir()

    return _scan_directory(agents_dir, PromptType.AGENT)


def scan_all_prompts() -> list[PromptInfo]:
    """Scan both prompts and agents directories.

    Returns:
        Combined list of all prompts and agents.
    """
    prompts = scan_prompts()
    agents = scan_agents()
    return prompts + agents


@lru_cache(maxsize=1)
def _cached_scan_all(cache_key: int) -> tuple[PromptInfo, ...]:
    """Cached scan with TTL-based invalidation.

    Args:
        cache_key: Cache key from _get_cache_key().

    Returns:
        Tuple of all prompts (tuple for hashability).
    """
    return tuple(scan_all_prompts())


def _scan_directory(directory: Path, prompt_type: PromptType) -> list[PromptInfo]:
    """Scan a directory for markdown files with valid frontmatter.

    Args:
        directory: Directory to scan.
        prompt_type: Type to assign to found items.

    Returns:
        List of PromptInfo for valid files.
    """
    results: list[PromptInfo] = []

    if not directory.exists():
        return results

    for path in sorted(directory.iterdir()):
        # Only process .md files
        if not path.is_file() or path.suffix.lower() != ".md":
            continue

        try:
            content = path.read_text()
            frontmatter, _ = parse_frontmatter(content)

            if frontmatter is None:
                # No valid frontmatter, skip
                continue

            results.append(
                PromptInfo(
                    path=path,
                    frontmatter=frontmatter,
                    prompt_type=prompt_type,
                )
            )
        except (ValueError, OSError, UnicodeDecodeError) as e:
            # Log at debug level - visible when debug mode enabled
            logger.debug(f"Skipping {path}: {e}")
            continue

    return results


def get_prompt_by_name(name: str, prompt_type: PromptType | None = None) -> PromptInfo | None:
    """Get a specific prompt/agent by name (cached).

    Uses TTL-based caching to avoid rescanning on every call.

    Args:
        name: Name to search for.
        prompt_type: Optional type filter.

    Returns:
        PromptInfo if found, None otherwise.
    """
    all_prompts = _cached_scan_all(_get_cache_key())
    for prompt in all_prompts:
        if prompt.name == name:
            if prompt_type is None or prompt.prompt_type == prompt_type:
                return prompt
    return None


def get_prompts_with_hooks() -> list[PromptInfo]:
    """Get all prompts/agents that have hook configurations (cached).

    Uses TTL-based caching to avoid rescanning on every call.

    Returns:
        List of PromptInfo with has_hooks=True.
    """
    return [p for p in _cached_scan_all(_get_cache_key()) if p.has_hooks]
