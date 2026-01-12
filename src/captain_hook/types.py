"""Type definitions for captain-hook.

This module provides shared type definitions (enums, dataclasses) used across
the codebase. These are designed to replace magic strings with type-safe constants.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


# Result dataclasses for typed returns
@dataclass
class InstallStatus:
    """Installation status for a scope (user or project).

    Attributes:
        path: Path to the settings file.
        installed: Whether captain-hook is installed at this scope.
    """

    path: str
    installed: bool


@dataclass
class StatusResult:
    """Result of get_status() - installation status for all scopes.

    Attributes:
        user: Status of user-level (~/.claude/settings.json) installation.
        project: Status of project-level (.claude/settings.json) installation.
    """

    user: InstallStatus
    project: InstallStatus


class HookType(Enum):
    """Type of hook based on file pattern.

    COMMAND: Executable scripts (.py, .sh, .js, .ts)
        - Receives JSON input on stdin
        - Can block/modify operations
        - Exit code non-zero = block

    STDOUT: Content output files (.stdout.md, .stdout.txt)
        - Content is cat'd to stdout
        - Used for context injection
        - No execution, just output

    PROMPT: Native Claude prompt hooks (.prompt.json)
        - Registered directly in Claude settings
        - Evaluated by Haiku (LLM-based decision)
        - JSON structure with "prompt" field
    """

    COMMAND = auto()
    STDOUT = auto()
    PROMPT = auto()

    @classmethod
    def from_string(cls, value: str) -> "HookType":
        """Create HookType from string value.

        Args:
            value: "command", "stdout", or "prompt"

        Returns:
            The corresponding HookType enum value.

        Raises:
            ValueError: If value is not recognized.
        """
        mapping = {
            "command": cls.COMMAND,
            "stdout": cls.STDOUT,
            "prompt": cls.PROMPT,
        }
        if value.lower() not in mapping:
            raise ValueError(
                f"Invalid hook type: {value!r}. Must be one of: command, stdout, prompt"
            )
        return mapping[value.lower()]


class Scope(str, Enum):
    """Configuration scope for hooks.

    USER (previously "global" or "user"):
        - Config: ~/.config/captain-hook/config.json
        - Claude: ~/.claude/settings.json
        - Applies to all projects

    PROJECT:
        - Config: .claude/captain-hook/config.json
        - Claude: .claude/settings.json
        - Applies only to current project
    """

    USER = "user"
    PROJECT = "project"

    def __str__(self) -> str:
        """Return the string value for compatibility with existing code."""
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "Scope":
        """Create Scope from string, handling legacy 'global' value.

        Args:
            value: "user", "global" (legacy), or "project"

        Returns:
            The corresponding Scope enum value.

        Raises:
            ValueError: If value is not recognized.
        """
        # Handle legacy "global" -> "user" mapping
        if value == "global":
            return cls.USER
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"Invalid scope: {value!r}. Must be 'user', 'global', or 'project'.")


class PromptType(str, Enum):
    """Type of prompt file.

    COMMAND: Slash command (prompts/ directory)
    AGENT: Agent/persona (agents/ directory)
    """

    COMMAND = "command"
    AGENT = "agent"

    @classmethod
    def from_string(cls, value: str) -> "PromptType":
        """Create PromptType from string.

        Args:
            value: "command" or "agent"

        Returns:
            The corresponding PromptType enum value.

        Raises:
            ValueError: If value is not recognized.
        """
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"Invalid prompt type: {value!r}. Must be 'command' or 'agent'.")


@dataclass
class PromptInfo:
    """Information about a discovered prompt/agent.

    Attributes:
        path: Path to the source file.
        frontmatter: Parsed frontmatter data.
        prompt_type: Whether this is a command or agent.
    """

    path: "Path"
    frontmatter: "PromptFrontmatter"
    prompt_type: PromptType

    @property
    def name(self) -> str:
        """Get the prompt name from frontmatter."""
        return self.frontmatter.name

    @property
    def description(self) -> str:
        """Get the description from frontmatter."""
        return self.frontmatter.description

    @property
    def tools(self) -> list[str]:
        """Get target tools from frontmatter."""
        return self.frontmatter.tools

    @property
    def has_hooks(self) -> bool:
        """Check if this prompt has hook registrations."""
        return self.frontmatter.has_hooks

    @property
    def hooks(self) -> list:
        """Get hook configurations."""
        return self.frontmatter.hooks
