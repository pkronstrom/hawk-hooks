"""Scanner for prompts and agents directories.

Scans ~/.config/captain-hook/prompts/ and agents/ for markdown files
with valid frontmatter.
"""

from __future__ import annotations

from pathlib import Path

from . import config
from .frontmatter import parse_frontmatter
from .types import PromptInfo, PromptType


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
        except (ValueError, OSError, UnicodeDecodeError):
            # Invalid file, skip silently
            continue

    return results


def get_prompt_by_name(name: str, prompt_type: PromptType | None = None) -> PromptInfo | None:
    """Get a specific prompt/agent by name.

    Args:
        name: Name to search for.
        prompt_type: Optional type filter.

    Returns:
        PromptInfo if found, None otherwise.
    """
    all_prompts = scan_all_prompts()
    for prompt in all_prompts:
        if prompt.name == name:
            if prompt_type is None or prompt.prompt_type == prompt_type:
                return prompt
    return None


def get_prompts_with_hooks() -> list[PromptInfo]:
    """Get all prompts/agents that have hook configurations.

    Returns:
        List of PromptInfo with has_hooks=True.
    """
    return [p for p in scan_all_prompts() if p.has_hooks]
