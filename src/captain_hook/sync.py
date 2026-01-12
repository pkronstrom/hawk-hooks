"""Symlink synchronization for prompts and agents.

Handles:
- Creating symlinks from captain-hook dirs to tool destinations
- Generating TOML wrappers for Gemini
- Removing synced files on disable
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from . import config

if TYPE_CHECKING:
    from .types import PromptInfo


def create_symlink(source: Path, dest: Path) -> None:
    """Create a symlink from dest pointing to source.

    Args:
        source: Source file path.
        dest: Destination symlink path.

    Raises:
        ValueError: If destination is a directory (not a symlink to one).
    """
    # Ensure parent directory exists
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing file/symlink
    if dest.exists() or dest.is_symlink():
        if dest.is_dir() and not dest.is_symlink():
            # Safety: don't delete actual directories
            raise ValueError(f"Destination is a directory, not a file: {dest}")
        dest.unlink()

    dest.symlink_to(source.resolve())


def remove_symlink(path: Path) -> None:
    """Remove a symlink or file.

    Args:
        path: Path to remove.
    """
    if path.exists() or path.is_symlink():
        if path.is_dir() and not path.is_symlink():
            # Safety: don't delete actual directories
            return
        path.unlink()


def _escape_toml_basic_string(s: str) -> str:
    """Escape a string for TOML basic string (double-quoted)."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def generate_gemini_toml(prompt_info: "PromptInfo") -> str:
    """Generate Gemini TOML wrapper for a prompt.

    Args:
        prompt_info: Prompt to generate TOML for.

    Returns:
        TOML content as string.
    """
    # Read the body content (without frontmatter)
    from .frontmatter import parse_frontmatter

    content = prompt_info.path.read_text()
    _, body = parse_frontmatter(content)

    # Escape name/description for TOML basic strings
    name = _escape_toml_basic_string(prompt_info.name)
    desc = _escape_toml_basic_string(prompt_info.description)

    # For body, use TOML multiline literal string (''') which preserves content as-is
    # Only need to handle the case where body contains '''
    body = body.strip().replace("'''", "'''\"'''\"'''")

    toml_content = f"""name = "{name}"
description = "{desc}"

prompt = '''
{body}
'''
"""
    return toml_content


def get_dest_filename(prompt_info: "PromptInfo", tool: str) -> str:
    """Get the destination filename for a prompt.

    Args:
        prompt_info: Prompt info.
        tool: Target tool.

    Returns:
        Filename with appropriate extension.
    """
    name = prompt_info.name
    if tool == "gemini":
        return f"{name}.toml"
    return f"{name}.md"


def get_dest_path(prompt_info: "PromptInfo", tool: str) -> Path:
    """Get the full destination path for a prompt.

    Args:
        prompt_info: Prompt info.
        tool: Target tool.

    Returns:
        Full destination path.
    """
    from .types import PromptType

    item_type = "commands" if prompt_info.prompt_type == PromptType.COMMAND else "agents"
    dest_dir = config.get_destination(tool, item_type)
    filename = get_dest_filename(prompt_info, tool)
    return Path(dest_dir) / filename


def sync_prompt(prompt_info: "PromptInfo", tools: list[str] | None = None) -> list[Path]:
    """Sync a prompt to its destination directories.

    Args:
        prompt_info: Prompt to sync.
        tools: List of tools to sync to. Defaults to prompt's tools.

    Returns:
        List of created destination paths.
    """
    if tools is None:
        tools = prompt_info.tools

    created: list[Path] = []

    for tool in tools:
        if tool not in prompt_info.tools:
            continue

        dest_path = get_dest_path(prompt_info, tool)

        if tool == "gemini":
            # Generate TOML file
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            toml_content = generate_gemini_toml(prompt_info)
            dest_path.write_text(toml_content)
        else:
            # Create symlink
            create_symlink(prompt_info.path, dest_path)

        created.append(dest_path)

    return created


def unsync_prompt(prompt_info: "PromptInfo", tools: list[str] | None = None) -> list[Path]:
    """Remove synced files for a prompt.

    Args:
        prompt_info: Prompt to unsync.
        tools: List of tools to unsync from. Defaults to prompt's tools.

    Returns:
        List of removed paths.
    """
    if tools is None:
        tools = prompt_info.tools

    removed: list[Path] = []

    for tool in tools:
        dest_path = get_dest_path(prompt_info, tool)
        if dest_path.exists() or dest_path.is_symlink():
            remove_symlink(dest_path)
            removed.append(dest_path)

    return removed


def sync_all_enabled() -> dict[str, list[Path]]:
    """Sync all enabled prompts and agents.

    Returns:
        Dict mapping prompt names to created paths.
    """
    from .prompt_scanner import scan_all_prompts

    results: dict[str, list[Path]] = {}

    for prompt in scan_all_prompts():
        # Check if enabled based on type
        from .types import PromptType

        if prompt.prompt_type == PromptType.COMMAND:
            enabled = config.is_prompt_enabled(prompt.name)
        else:
            enabled = config.is_agent_enabled(prompt.name)

        if enabled:
            results[prompt.name] = sync_prompt(prompt)

    return results


def unsync_all() -> dict[str, list[Path]]:
    """Remove all synced prompts and agents.

    Returns:
        Dict mapping prompt names to removed paths.
    """
    from .prompt_scanner import scan_all_prompts

    results: dict[str, list[Path]] = {}

    for prompt in scan_all_prompts():
        removed = unsync_prompt(prompt)
        if removed:
            results[prompt.name] = removed

    return results
