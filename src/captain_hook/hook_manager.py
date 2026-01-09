"""Hook management service layer.

This module provides HookManager, which orchestrates hook state management
and synchronization operations. It consolidates the scattered enable/disable
logic from cli.py into a single, testable service.

Example:
    manager = HookManager(scope=Scope.USER)
    manager.enable_hook("pre_tool_use", "my-hook")
    manager.sync()  # Regenerates runners and syncs prompt hooks
"""

from __future__ import annotations

from pathlib import Path

from . import config, generator, installer, scanner
from .events import EVENTS
from .scanner import HookInfo
from .types import Scope


class HookManager:
    """Manages hook enabled/disabled state and orchestrates sync operations.

    This class provides a facade over config, generator, and installer modules,
    ensuring that all state changes are properly synchronized.

    Attributes:
        scope: Either Scope.USER or Scope.PROJECT.
        project_dir: Project directory (required when scope is PROJECT).
    """

    def __init__(self, scope: Scope | str = Scope.USER, project_dir: Path | None = None):
        """Initialize the hook manager.

        Args:
            scope: USER for user-wide hooks, PROJECT for project-specific.
                   Accepts Scope enum or string ("user", "global", "project").
            project_dir: Project directory when scope is PROJECT.
                         Defaults to current working directory.
        """
        # Normalize string to Scope enum (handles legacy "global" -> USER mapping)
        if isinstance(scope, str):
            scope = Scope.from_string(scope)

        self.scope = scope
        self.project_dir = project_dir if project_dir else Path.cwd()

    def get_enabled_hooks(self, event: str) -> list[str]:
        """Get list of enabled hook names for an event.

        Args:
            event: The event name (e.g., "pre_tool_use").

        Returns:
            List of enabled hook names.
        """
        if self.scope == Scope.PROJECT:
            return config.get_enabled_hooks(event, self.project_dir)
        return config.get_enabled_hooks(event)

    def set_enabled_hooks(
        self,
        event: str,
        hooks: list[str],
        add_to_git_exclude: bool = True,
    ) -> None:
        """Set the list of enabled hooks for an event.

        Does NOT automatically sync - call sync() after making changes.

        Args:
            event: The event name.
            hooks: List of hook names to enable.
            add_to_git_exclude: Whether to add project config to .git/info/exclude.
        """
        config.set_enabled_hooks(
            event=event,
            hooks=hooks,
            scope=self.scope,
            project_dir=self.project_dir if self.scope == Scope.PROJECT else None,
            add_to_git_exclude=add_to_git_exclude,
        )

    def enable_hook(self, event: str, hook_name: str, auto_sync: bool = True) -> bool:
        """Enable a single hook.

        Args:
            event: The event name.
            hook_name: Name of the hook to enable.
            auto_sync: Whether to sync after enabling (regenerate runners, etc.).

        Returns:
            True if the hook was enabled (wasn't already enabled).
        """
        enabled = self.get_enabled_hooks(event)
        if hook_name in enabled:
            return False

        enabled.append(hook_name)
        self.set_enabled_hooks(event, enabled)

        if auto_sync:
            self.sync()

        return True

    def disable_hook(self, event: str, hook_name: str, auto_sync: bool = True) -> bool:
        """Disable a single hook.

        Args:
            event: The event name.
            hook_name: Name of the hook to disable.
            auto_sync: Whether to sync after disabling.

        Returns:
            True if the hook was disabled (was previously enabled).
        """
        enabled = self.get_enabled_hooks(event)
        if hook_name not in enabled:
            return False

        enabled.remove(hook_name)
        self.set_enabled_hooks(event, enabled)

        if auto_sync:
            self.sync()

        return True

    def sync(self) -> None:
        """Synchronize hook state with Claude settings.

        This regenerates all runners and syncs native prompt hooks.
        Call this after batch changes to enabled hooks.
        """
        if self.scope == Scope.PROJECT:
            generator.generate_all_runners(scope=Scope.PROJECT, project_dir=self.project_dir)
            installer.sync_prompt_hooks(scope=Scope.PROJECT, project_dir=self.project_dir)
        else:
            generator.generate_all_runners(scope=Scope.USER)
            installer.sync_prompt_hooks(scope=Scope.USER)

    def find_hook(self, name: str) -> HookInfo | None:
        """Find a hook by name across all events.

        Args:
            name: The hook name to find.

        Returns:
            HookInfo if found, None otherwise.
        """
        hooks = scanner.scan_hooks()
        for event_hooks in hooks.values():
            for hook in event_hooks:
                if hook.name == name:
                    return hook
        return None

    def find_hook_with_event(self, name: str) -> tuple[str, HookInfo] | None:
        """Find a hook by name and return with its event.

        Args:
            name: The hook name to find.

        Returns:
            Tuple of (event, HookInfo) if found, None otherwise.
        """
        hooks = scanner.scan_hooks()
        for event, event_hooks in hooks.items():
            for hook in event_hooks:
                if hook.name == name:
                    return (event, hook)
        return None

    def scan_hooks(self) -> dict[str, list[HookInfo]]:
        """Scan for all available hooks.

        Returns:
            Dict mapping event names to lists of HookInfo objects.
        """
        return scanner.scan_hooks()

    def get_all_enabled(self) -> dict[str, list[str]]:
        """Get all enabled hooks across all events.

        Returns:
            Dict mapping event names to lists of enabled hook names.
        """
        result = {}
        for event in EVENTS:
            enabled = self.get_enabled_hooks(event)
            if enabled:
                result[event] = enabled
        return result

    def get_changes_summary(
        self,
        original: dict[str, list[str]],
        current: dict[str, list[str]],
    ) -> dict[str, dict[str, list[str]]]:
        """Compare two enabled states and return changes.

        Args:
            original: Original enabled state by event.
            current: Current enabled state by event.

        Returns:
            Dict with "enabled" and "disabled" keys, each mapping
            event names to lists of hook names.
        """
        changes = {"enabled": {}, "disabled": {}}

        all_events = set(original.keys()) | set(current.keys())
        for event in all_events:
            orig_set = set(original.get(event, []))
            curr_set = set(current.get(event, []))

            newly_enabled = curr_set - orig_set
            newly_disabled = orig_set - curr_set

            if newly_enabled:
                changes["enabled"][event] = sorted(newly_enabled)
            if newly_disabled:
                changes["disabled"][event] = sorted(newly_disabled)

        return changes
