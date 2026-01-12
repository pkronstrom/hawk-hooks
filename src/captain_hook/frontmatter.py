"""Frontmatter parsing for prompts and agents.

Parses YAML frontmatter from markdown files:
---
name: my-command
description: A description
tools: [claude, gemini]
hooks:
  - event: pre_tool
    matchers: [Bash]
---
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

# All supported tools
ALL_TOOLS = ["claude", "gemini", "codex"]

# Frontmatter regex: matches --- at start, content, ---
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n?---\s*\n?", re.DOTALL)


@dataclass
class HookConfig:
    """Configuration for a hook registration."""

    event: str
    matchers: list[str] = field(default_factory=list)


@dataclass
class PromptFrontmatter:
    """Parsed frontmatter from a prompt/agent file."""

    name: str
    description: str
    tools: list[str]
    hooks: list[HookConfig] = field(default_factory=list)

    @property
    def has_hooks(self) -> bool:
        """Check if this prompt has any hook registrations."""
        return len(self.hooks) > 0


def parse_frontmatter(content: str) -> tuple[PromptFrontmatter | None, str]:
    """Parse frontmatter from markdown content.

    Args:
        content: Full file content with potential frontmatter.

    Returns:
        Tuple of (parsed frontmatter or None, body content).

    Raises:
        ValueError: If frontmatter exists but is invalid.
    """
    match = FRONTMATTER_RE.match(content)
    if not match:
        return None, content

    yaml_content = match.group(1)
    body = content[match.end() :]

    # Parse YAML
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in frontmatter: {e}")

    if not data:
        return None, body

    # Validate type - must be a dict
    if not isinstance(data, dict):
        raise ValueError(f"Frontmatter must be a YAML mapping, got {type(data).__name__}")

    # Validate required fields exist and have correct types
    if "name" not in data:
        raise ValueError("Missing required field: name")
    if not isinstance(data["name"], str):
        raise ValueError(f"Field 'name' must be a string, got {type(data['name']).__name__}")

    if "description" not in data:
        raise ValueError("Missing required field: description")
    if not isinstance(data["description"], str):
        raise ValueError(
            f"Field 'description' must be a string, got {type(data['description']).__name__}"
        )

    if "tools" not in data:
        raise ValueError("Missing required field: tools")

    # Parse and validate tools
    tools = data["tools"]
    if tools == "all":
        tools = ALL_TOOLS.copy()
    elif isinstance(tools, str):
        tools = [tools]
    elif not isinstance(tools, list):
        raise ValueError(
            f"Field 'tools' must be a string, list, or 'all', got {type(tools).__name__}"
        )

    # Warn on unknown tools (but don't reject - allow extension)
    unknown = set(tools) - set(ALL_TOOLS)
    if unknown:
        import logging

        logging.getLogger(__name__).warning(
            f"Unknown tools in frontmatter: {unknown}. Known: {ALL_TOOLS}"
        )

    # Parse hooks
    hooks = []
    for hook_data in data.get("hooks", []):
        if isinstance(hook_data, str):
            # Shorthand: just event name
            hooks.append(HookConfig(event=hook_data, matchers=[]))
        elif isinstance(hook_data, dict):
            hooks.append(
                HookConfig(
                    event=hook_data.get("event", ""),
                    matchers=hook_data.get("matchers", []),
                )
            )

    return (
        PromptFrontmatter(
            name=data["name"],
            description=data["description"],
            tools=tools,
            hooks=hooks,
        ),
        body,
    )


def parse_file(path: str) -> tuple[PromptFrontmatter | None, str]:
    """Parse frontmatter from a file path.

    Args:
        path: Path to the markdown file.

    Returns:
        Tuple of (parsed frontmatter or None, body content).
    """
    from pathlib import Path

    content = Path(path).read_text()
    return parse_frontmatter(content)
