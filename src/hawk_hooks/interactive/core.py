"""Core utilities for interactive UI.

Console management, header, pagination, styles, and command execution.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import readchar
from questionary import Style
from rich.console import Console
from rich.panel import Panel

from rich_menu.keys import is_down, is_enter, is_exit, is_up

from .. import __version__

if TYPE_CHECKING:
    pass

# Console management for testability
# Tests can call set_console() to inject a mock console
_console_instance: Console | None = None


def _get_console() -> Console:
    """Get the console instance, creating one if needed."""
    global _console_instance
    if _console_instance is None:
        _console_instance = Console()
    return _console_instance


def set_console(new_console: Console | None) -> None:
    """Set the console instance (for testing).

    Args:
        new_console: Console to use, or None to reset to default.

    Example:
        from io import StringIO
        from rich.console import Console
        from hawk_hooks.interactive import set_console

        # Capture output in tests
        output = StringIO()
        set_console(Console(file=output, force_terminal=True))
        # ... run code ...
        set_console(None)  # Reset
    """
    global _console_instance
    _console_instance = new_console


class _ConsoleProxy:
    """Proxy that delegates to the current console instance.

    This allows set_console() to affect all code using the module-level
    `console` variable, even after import.
    """

    def __getattr__(self, name: str):
        return getattr(_get_console(), name)

    def __enter__(self):
        return _get_console().__enter__()

    def __exit__(self, *args):
        return _get_console().__exit__(*args)


# Module-level console that can be swapped via set_console()
console = _ConsoleProxy()

# Custom style for questionary
custom_style = Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "fg:white bold"),
        ("answer", "fg:cyan"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:green"),
        ("separator", "fg:gray"),
        ("instruction", "fg:gray"),
    ]
)


def print_header():
    """Print the application header."""
    console.print(
        Panel(
            f"[bold cyan]hawk-hooks[/bold cyan] v{__version__}\n"
            "[dim]A modular Claude Code hooks manager[/dim]",
            border_style="cyan",
            width=100,
        )
    )
    console.print()


def _paginate_output(lines: list[str], max_lines_per_page: int) -> None:
    """Display paginated output with scroll support."""
    if len(lines) <= max_lines_per_page:
        for line in lines:
            print(line)
        console.print("[dim]Press Enter or q to exit...[/dim]")

        while True:
            key = readchar.readkey()
            if is_enter(key) or is_exit(key):
                break
        return

    window_offset = 0

    while True:
        console.clear()
        print()

        window_end = min(window_offset + max_lines_per_page, len(lines))
        visible_lines = lines[window_offset:window_end]

        for line in visible_lines:
            print(line)

        hint_parts = []
        lines_above = window_offset
        lines_below = len(lines) - window_end

        if lines_above > 0:
            hint_parts.append(f"[dim]↑ {lines_above} more above[/dim]")
        if lines_below > 0:
            hint_parts.append(f"[dim]↓ {lines_below} more below[/dim]")

        hint_parts.append(f"[dim]Line {window_offset + 1}-{window_end}/{len(lines)}[/dim]")
        hint_parts.append("[dim]↑/↓ scroll  Enter/q exit[/dim]")

        console.print("\n" + "  ".join(hint_parts))

        key = readchar.readkey()

        if is_down(key) and window_end < len(lines):
            window_offset += 1
        elif is_up(key) and window_offset > 0:
            window_offset -= 1
        elif is_enter(key) or is_exit(key):
            break


def _run_command(cmd: list[str], timeout: int = 300, description: str = "") -> tuple[bool, str]:
    """Run a command with error handling.

    Args:
        cmd: Command and arguments as a list.
        timeout: Timeout in seconds (default 300).
        description: Human-readable description for error messages.

    Returns:
        Tuple of (success, output_or_error_message).
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else ""
            if not error_msg:
                error_msg = f"Command failed with exit code {result.returncode}"
            return False, error_msg
        return True, result.stdout
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout}s"
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}"
    except Exception as e:
        return False, str(e)


def _with_paused_live(menu, action):
    """Execute action with menu live display paused.

    Handles both public API (if available) and private API fallback.

    Args:
        menu: InteractiveList menu instance.
        action: Callable to execute while live is paused.

    Returns:
        Result of action().
    """
    # Try public API first (if/when rich_menu adds it)
    if hasattr(menu, "pause_live"):
        with menu.pause_live():
            return action()

    # Fallback to private API with safety check
    live = getattr(menu, "_live", None)
    if live is None:
        return action()

    try:
        live.stop()
        result = action()
        menu.console.clear()
        live.start()
        return result
    except Exception:
        # Ensure live restarts even on error
        if live:
            try:
                live.start()
            except Exception:
                pass
        raise
