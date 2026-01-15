"""Keyboard input helpers for rich_menu.

This module provides helper functions for detecting key presses,
replacing repeated inline conditionals with readable function calls.
"""

from __future__ import annotations

import readchar


def is_enter(key: str) -> bool:
    """Check if key is Enter/Return."""
    return key in (readchar.key.ENTER, "\r", "\n")


def is_escape(key: str) -> bool:
    """Check if key is Escape (handles terminal variations)."""
    return key in (readchar.key.ESC, "\x1b", "\x1b\x1b")


def is_exit(key: str) -> bool:
    """Check if key is a quit/exit key (q only).

    Note: Escape is intentionally NOT included here.
    Escape is only used to cancel text editing mode.
    Use q or Ctrl+C to exit menus (like dodo's pattern).
    """
    return key.lower() == "q"


def is_up(key: str) -> bool:
    """Check if key is up arrow or vim 'k'."""
    return key.lower() == "k" or key == readchar.key.UP


def is_down(key: str) -> bool:
    """Check if key is down arrow or vim 'j'."""
    return key.lower() == "j" or key == readchar.key.DOWN


def is_backspace(key: str) -> bool:
    """Check if key is backspace (handles terminal variations)."""
    return key in (readchar.key.BACKSPACE, "\x7f", "\b")


def is_space(key: str) -> bool:
    """Check if key is space."""
    return key == " "


def is_select(key: str) -> bool:
    """Check if key is a selection key (Enter or Space)."""
    return is_enter(key) or is_space(key)
