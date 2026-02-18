"""Interactive config editor for hawk v2.

Single unified settings menu — toggle, cycle, and edit config values.
Changes save immediately.
"""

from __future__ import annotations

import os

import readchar
from rich.console import Console
from rich.live import Live
from rich.text import Text

from .. import v2_config
from .toggle import _get_terminal_height, _calculate_visible_range

console = Console()

# Setting definitions: (key, label, type, options_or_default)
# Types: "toggle", "cycle", "text"
SETTINGS = [
    ("debug", "Debug mode", "toggle", False),
    ("editor", "Editor", "text", ""),
    ("sync_on_exit", "Sync on exit", "cycle", ["ask", "always", "never"]),
    ("registry_path", "Registry path", "text", "~/.config/hawk-hooks/registry"),
]


def _get_value(cfg: dict, key: str, default):
    """Get a config value with default."""
    return cfg.get(key, default)


def _display_value(key: str, value, setting_type: str, options=None) -> str:
    """Format a value for display."""
    if setting_type == "toggle":
        return "[green]on[/green]" if value else "[dim]off[/dim]"
    if setting_type == "cycle":
        return str(value)
    if setting_type == "text":
        if key == "editor":
            if value:
                return str(value)
            env_editor = os.environ.get("EDITOR", "vim")
            return f"[dim]$EDITOR ({env_editor})[/dim]"
        if value:
            return str(value)
        return f"[dim]{options}[/dim]" if options else "[dim](empty)[/dim]"
    return str(value)


def run_config_editor() -> None:
    """Run the interactive config editor."""
    cfg = v2_config.load_global_config()

    cursor = 0
    status_msg = ""
    items = list(SETTINGS)  # Copy so we can reference stably

    def _build_display() -> str:
        lines: list[str] = []
        lines.append("[bold]Settings[/bold]")
        lines.append("[dim]\u2500" * 50 + "[/dim]")

        total = len(items) + 2  # items + separator + Done
        max_visible = _get_terminal_height() - 7
        _, vis_start, vis_end = _calculate_visible_range(cursor, total, max_visible, 0)

        if vis_start > 0:
            lines.append(f"[dim]  \u2191 {vis_start} more[/dim]")

        for i in range(vis_start, vis_end):
            is_cur = i == cursor
            prefix = "[cyan]\u276f[/cyan] " if is_cur else "  "

            if i < len(items):
                key, label, setting_type, default = items[i]
                if setting_type == "cycle":
                    value = _get_value(cfg, key, default[0])
                else:
                    value = _get_value(cfg, key, default)
                display = _display_value(key, value, setting_type, default)

                name_style = "[bold]" if is_cur else ""
                name_end = "[/bold]" if is_cur else ""
                lines.append(f"{prefix}{name_style}{label:<20}{name_end} {display}")

            elif i == len(items):
                # Separator
                lines.append("  [dim]\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500[/dim]")
            elif i == len(items) + 1:
                # Done
                style = "[cyan bold]" if is_cur else "[dim]"
                end = "[/cyan bold]" if is_cur else "[/dim]"
                lines.append(f"{prefix}{style}Done{end}")

        if vis_end < total:
            lines.append(f"[dim]  \u2193 {total - vis_end} more[/dim]")

        if status_msg:
            lines.append(f"\n[dim]{status_msg}[/dim]")

        lines.append("")
        lines.append("[dim]Space/Enter: change  \u2191\u2193/jk: navigate  q: done[/dim]")
        return "\n".join(lines)

    def _handle_change(idx: int) -> str:
        """Handle changing a setting. Returns status message."""
        if idx >= len(items):
            return ""

        key, label, setting_type, default = items[idx]

        if setting_type == "toggle":
            if setting_type == "cycle":
                current = _get_value(cfg, key, default[0])
            else:
                current = _get_value(cfg, key, default)
            cfg[key] = not current
            v2_config.save_global_config(cfg)
            state = "on" if cfg[key] else "off"
            return f"{label} \u2192 {state}"

        elif setting_type == "cycle":
            options = default  # default is the options list for cycle type
            current = _get_value(cfg, key, options[0])
            try:
                idx_cur = options.index(current)
            except ValueError:
                idx_cur = -1
            next_val = options[(idx_cur + 1) % len(options)]
            cfg[key] = next_val
            v2_config.save_global_config(cfg)
            return f"{label} \u2192 {next_val}"

        elif setting_type == "text":
            return ""  # Handled separately (needs input)

        return ""

    def _handle_text_edit(idx: int) -> str:
        """Handle editing a text setting. Returns status message."""
        if idx >= len(items):
            return ""

        key, label, setting_type, default = items[idx]
        if setting_type != "text":
            return ""

        current = _get_value(cfg, key, default)
        try:
            new_val = console.input(f"\n[cyan]{label}[/cyan] [{current}]: ").strip()
        except (KeyboardInterrupt, EOFError):
            return "Cancelled"

        if new_val:
            cfg[key] = new_val
            v2_config.save_global_config(cfg)
            return f"{label} \u2192 {new_val}"
        return ""

    with Live("", console=console, refresh_per_second=15, transient=True) as live:
        live.update(Text.from_markup(_build_display()))
        while True:
            try:
                key = readchar.readkey()
            except (KeyboardInterrupt, EOFError):
                break

            total = len(items) + 2
            status_msg = ""

            # Navigation
            if key in (readchar.key.UP, "k"):
                cursor = (cursor - 1) % total
                # Skip separator
                if cursor == len(items):
                    cursor = (cursor - 1) % total
            elif key in (readchar.key.DOWN, "j"):
                cursor = (cursor + 1) % total
                if cursor == len(items):
                    cursor = (cursor + 1) % total

            # Change value
            elif key in (" ", "\r", "\n", readchar.key.ENTER):
                if cursor < len(items):
                    _, _, setting_type, _ = items[cursor]
                    if setting_type == "text":
                        live.stop()
                        status_msg = _handle_text_edit(cursor)
                        live.start()
                    else:
                        status_msg = _handle_change(cursor)
                elif cursor == len(items) + 1:
                    # Done
                    break

            # Quit
            elif key in ("q", "\x1b"):
                break

            live.update(Text.from_markup(_build_display()))
