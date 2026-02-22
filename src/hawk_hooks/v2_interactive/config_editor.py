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
from simple_term_menu import TerminalMenu

from .. import v2_config
from .pause import wait_for_continue
from .toggle import _get_terminal_height, _calculate_visible_range

console = Console()

# Setting definitions: (key, label, type, options_or_default)
# Types: "toggle", "cycle", "text"
SETTINGS = [
    ("debug", "Debug mode", "toggle", False),
    ("editor", "Editor", "text", ""),
    ("sync_on_exit", "Sync on exit", "cycle", ["ask", "always", "never"]),
    ("registry_path", "Registry path", "text", "~/.config/hawk-hooks/registry"),
    ("unlink_uninstall", "Unlink and uninstall", "action", None),
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
    if setting_type == "action":
        return "[red]Run cleanup[/red]"
    return str(value)


def run_config_editor() -> bool:
    """Run the interactive config editor."""
    cfg = v2_config.load_global_config()
    dirty = False

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
        lines.append("[dim]Space/Enter: change  \u2191\u2193/jk: navigate  q: back[/dim]")
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
        elif setting_type == "action":
            return ""  # Handled separately (needs confirmation + output)

        return ""

    def _handle_uninstall_action() -> str:
        """Unlink from tools and clear hawk-managed local state."""
        nonlocal cfg
        menu = TerminalMenu(
            ["No", "Yes, unlink + uninstall"],
            title=(
                "\nUnlink and uninstall hawk-managed state?\n"
                "This will purge tool links and clear registry/packages/config selections."
            ),
            cursor_index=0,
            menu_cursor="\u276f ",
            menu_cursor_style=("fg_cyan", "bold"),
            menu_highlight_style=("fg_cyan", "bold"),
            quit_keys=("q", "\x1b"),
        )
        choice = menu.show()
        if choice != 1:
            return "Uninstall cancelled"

        from ..v2_sync import format_sync_results, uninstall_all

        console.print("\n[bold red]Unlinking and uninstalling...[/bold red]")
        results = uninstall_all()
        formatted = format_sync_results(results, verbose=False)
        console.print(formatted or "  No changes.")
        console.print("\n[green]\u2714 Cleared hawk-managed config, packages, and registry state.[/green]\n")
        cfg = v2_config.load_global_config()
        wait_for_continue()
        return "Uninstall cleanup completed"

    def _handle_text_edit(idx: int) -> str:
        """Handle editing a text setting via $EDITOR or inline fallback."""
        import tempfile

        if idx >= len(items):
            return ""

        key, label, setting_type, default = items[idx]
        if setting_type != "text":
            return ""

        current = str(_get_value(cfg, key, default))
        editor = os.environ.get("EDITOR", "vim")

        # Write current value to a temp file, open in editor
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", prefix=f"hawk-{key}-", delete=False
            ) as f:
                f.write(current)
                tmp_path = f.name

            import subprocess
            result = subprocess.run([editor, tmp_path], check=False)

            if result.returncode == 0:
                new_val = open(tmp_path).read().strip()
                if new_val and new_val != current:
                    cfg[key] = new_val
                    v2_config.save_global_config(cfg)
                    return f"{label} \u2192 {new_val}"
                elif not new_val and current:
                    # Cleared the value — reset to default
                    cfg.pop(key, None)
                    v2_config.save_global_config(cfg)
                    return f"{label} \u2192 (default)"
        except (KeyboardInterrupt, EOFError):
            return "Cancelled"
        except OSError:
            # Editor not found — fall back to inline
            try:
                new_val = console.input(f"\n[cyan]{label}[/cyan] [{current}]: ").strip()
            except (KeyboardInterrupt, EOFError):
                return "Cancelled"
            if new_val:
                cfg[key] = new_val
                v2_config.save_global_config(cfg)
                return f"{label} \u2192 {new_val}"
        finally:
            try:
                os.unlink(tmp_path)
            except (OSError, UnboundLocalError):
                pass
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
                        if "→" in status_msg:
                            dirty = True
                        live.start()
                    elif setting_type == "action":
                        live.stop()
                        status_msg = _handle_uninstall_action()
                        if status_msg == "Uninstall cleanup completed":
                            dirty = True
                        live.start()
                    else:
                        status_msg = _handle_change(cursor)
                        if status_msg:
                            dirty = True
                elif cursor == len(items) + 1:
                    # Done
                    break

            # Quit
            elif key in ("q", "\x1b"):
                break

            live.update(Text.from_markup(_build_display()))

    return dirty
