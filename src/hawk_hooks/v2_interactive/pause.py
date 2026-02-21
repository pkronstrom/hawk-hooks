"""Shared pause helpers for v2 interactive screens."""

from __future__ import annotations

import readchar
from rich.console import Console

console = Console(highlight=False)


def wait_for_continue(prompt: str = "[dim]Press Enter to continue...[/dim]") -> None:
    """Wait for Enter, q, or Ctrl+C before returning.

    This keeps lightweight info/error screens skippable with a single key,
    while preserving Enter as the default action.
    """
    console.print(prompt)
    while True:
        try:
            key = readchar.readkey()
        except (KeyboardInterrupt, EOFError):
            return
        if key in ("\r", "\n", readchar.key.ENTER, "q", "Q", readchar.key.CTRL_C, "\x03"):
            return
