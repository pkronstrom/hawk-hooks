"""Type definitions for hawk-hooks.

This module provides shared type definitions (enums, dataclasses) used across
the codebase. These are designed to replace magic strings with type-safe constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


# ── v2 enums ──────────────────────────────────────────────────────────────


class Tool(str, Enum):
    """Supported AI CLI tools."""

    CLAUDE = "claude"
    GEMINI = "gemini"
    CODEX = "codex"
    OPENCODE = "opencode"
    CURSOR = "cursor"
    ANTIGRAVITY = "antigravity"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def all(cls) -> list["Tool"]:
        return list(cls)


class ComponentType(str, Enum):
    """Types of components managed in the registry."""

    SKILL = "skill"
    HOOK = "hook"
    COMMAND = "command"
    AGENT = "agent"
    MCP = "mcp"
    PROMPT = "prompt"

    def __str__(self) -> str:
        return self.value

    @property
    def registry_dir(self) -> str:
        """Directory name in the registry (pluralized, except mcp)."""
        if self == ComponentType.MCP:
            return "mcp"
        return self.value + "s"


@dataclass
class ResolvedSet:
    """Resolved set of components for a directory + tool combination."""

    skills: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    mcp: list[str] = field(default_factory=list)

    def get(self, component_type: ComponentType) -> list[str]:
        """Get the list for a given component type."""
        mapping = {
            ComponentType.SKILL: self.skills,
            ComponentType.HOOK: self.hooks,
            ComponentType.COMMAND: self.commands,
            ComponentType.AGENT: self.agents,
            ComponentType.MCP: self.mcp,
        }
        return mapping.get(component_type, [])

    def hash_key(self) -> str:
        """Deterministic hash for cache comparison."""
        import hashlib

        parts = [
            ",".join(sorted(self.skills)),
            ",".join(sorted(self.hooks)),
            ",".join(sorted(self.commands)),
            ",".join(sorted(self.agents)),
            ",".join(sorted(self.mcp)),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


@dataclass
class ToggleScope:
    """A scope layer for the toggle list."""

    key: str  # "global" or absolute dir path
    label: str  # "All projects" / "monorepo" / "This project: frontend"
    enabled: list[str] = field(default_factory=list)
    is_new: bool = False  # True if config doesn't exist yet (will be created on save)


@dataclass
class ToggleGroup:
    """A group of items in the toggle list (e.g. a downloaded package)."""

    key: str  # package name or "__ungrouped__"
    label: str  # "📦 superpowers-marketplace" or "ungrouped"
    items: list[str] = field(default_factory=list)
    collapsed: bool = False


@dataclass
class SyncResult:
    """Result of syncing a resolved set to a tool."""

    tool: str
    linked: list[str] = field(default_factory=list)
    unlinked: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── v1 types (preserved for backwards compatibility) ──────────────────────


# Result dataclasses for typed returns
@dataclass
class InstallStatus:
    """Installation status for a scope (user or project).

    Attributes:
        path: Path to the settings file.
        installed: Whether hawk-hooks is installed at this scope.
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
        - Config: ~/.config/hawk-hooks/config.json
        - Claude: ~/.claude/settings.json
        - Applies to all projects

    PROJECT:
        - Config: .claude/hawk-hooks/config.json
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
