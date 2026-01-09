"""Type definitions for captain-hook.

This module provides shared type definitions (enums, dataclasses) used across
the codebase. These are designed to replace magic strings with type-safe constants.
"""

from enum import Enum


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
