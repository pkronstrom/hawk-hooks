"""Configuration editor for hawk-hooks.

Interactive config editing with dodo-style ANSI rendering.
"""

from __future__ import annotations

import sys

import readchar
from rich.panel import Panel

from .. import config, generator, scanner
from .core import console


def interactive_config():
    """Interactive config editor with dodo-style rendering."""
    cfg = config.load_config()

    script_env_vars = scanner.get_all_env_vars()
    env_config = cfg.get("env", {})

    original_debug = cfg.get("debug", False)
    original_env = dict(env_config)

    # Build settings items: (key, label, kind, value)
    # kind: "toggle", "text", "divider", "action"
    items: list[tuple[str, str, str, object]] = [
        ("debug", "Log hook calls", "toggle", cfg.get("debug", False)),
    ]

    if script_env_vars:
        items.append(("", "── Hook Settings ──", "divider", None))

        for var_name, default_value in sorted(script_env_vars.items()):
            current_value = env_config.get(var_name, default_value)
            if not isinstance(current_value, str):
                current_value = str(current_value) if current_value is not None else ""
            is_bool = current_value.lower() in ("true", "false", "1", "0", "yes", "no")

            if is_bool:
                value = current_value.lower() in ("true", "1", "yes")
                items.append((var_name, var_name, "toggle", value))
            else:
                items.append((var_name, var_name, "text", current_value))

    items.append(("", "─────────", "divider", None))
    items.append(("save", "Save", "action", None))
    items.append(("cancel", "Cancel", "action", None))

    # Track pending values
    pending = {key: value for key, _, _, value in items if key}

    # Find navigable items (not dividers)
    navigable_indices = [i for i, (_, _, kind, _) in enumerate(items) if kind != "divider"]
    cursor = 0

    def render() -> None:
        sys.stdout.write("\033[H")  # Move cursor to top-left
        sys.stdout.flush()
        console.print("[bold]Configuration[/bold]                              ")
        sys.stdout.write("\033[K")
        console.print()

        value_col = 28

        for i, (key, label, kind, _) in enumerate(items):
            if kind == "divider":
                sys.stdout.write("\033[K")
                console.print(f"  [dim]{label}[/dim]")
                continue

            marker = "[cyan]>[/cyan]" if i == cursor else " "
            value = pending.get(key)

            if kind == "toggle":
                check = "[bold blue]✓[/bold blue]" if value else " "
                base = f" {marker} {label}"
                label_len = len(label) + 3
                pad1 = max(1, value_col - label_len)
                line = f"{base}{' ' * pad1}{check}"
            elif kind == "text":
                display = str(value)[:20] if value else "–"
                base = f" {marker} {label}"
                label_len = len(label) + 3
                pad1 = max(1, value_col - label_len)
                line = f"{base}{' ' * pad1}[dim]{display}[/dim]"
            elif kind == "action":
                base = f" {marker} {label}"
                line = base

            sys.stdout.write("\033[K")
            console.print(line)

        # Legend at bottom
        sys.stdout.write("\033[K")
        console.print()
        sys.stdout.write("\033[K")
        console.print("[dim]↑↓/jk navigate · space/enter toggle · q back[/dim]")

    def find_next_navigable(current: int, direction: int) -> int:
        idx = navigable_indices.index(current) if current in navigable_indices else 0
        idx = (idx + direction) % len(navigable_indices)
        return navigable_indices[idx]

    action_result = None

    with console.screen():
        render()
        while True:
            try:
                key = readchar.readkey()
            except KeyboardInterrupt:
                return

            if key in (readchar.key.UP, "k"):
                cursor = find_next_navigable(cursor, -1)
            elif key in (readchar.key.DOWN, "j", "\t"):
                cursor = find_next_navigable(cursor, 1)
            elif key == "q":
                return
            elif key in (" ", "\r", "\n"):
                item_key, _, kind, _ = items[cursor]
                if kind == "toggle":
                    pending[item_key] = not pending[item_key]
                elif kind == "action":
                    action_result = item_key
                    break

            render()

    if action_result == "cancel" or action_result is None:
        return

    # Apply changes
    debug_changed = False
    env_changed = False

    for key, _, kind, _ in items:
        if not key or kind not in ("toggle", "text"):
            continue
        value = pending.get(key)
        if key == "debug":
            cfg["debug"] = value
            if value != original_debug:
                debug_changed = True
        elif key in script_env_vars:
            if isinstance(value, bool):
                env_config[key] = "true" if value else "false"
            else:
                env_config[key] = value.strip() if isinstance(value, str) else value
            cfg["env"] = env_config
            if env_config.get(key) != original_env.get(key):
                env_changed = True

    if debug_changed or env_changed:
        config.save_config(cfg)
        generator.generate_all_runners()

        lines = []
        if debug_changed:
            new_val = cfg.get("debug", False)
            lines.append(f"[cyan]debug:[/cyan] {original_debug} → {new_val}")

        for key in sorted(env_config.keys()):
            if env_config.get(key) != original_env.get(key):
                old_val = original_env.get(key, "")
                new_val = env_config.get(key, "")
                lines.append(f"[cyan]{key}:[/cyan] {old_val} → {new_val}")

        result_content = "\n".join(lines) if lines else "[dim]No changes[/dim]"

        console.clear()
        console.print()
        console.print(
            Panel(
                f"{result_content}\n\n[dim]Changes take effect immediately.[/dim]"
                + (f"\n[dim]Log file: {config.get_log_path()}[/dim]" if debug_changed else "")
                + "\n\n[dim]Press Enter to continue...[/dim]",
                title="[bold green]Configuration updated[/bold green]",
                border_style="green",
            )
        )

        while True:
            key = readchar.readkey()
            if key in ("\r", "\n"):
                break
    else:
        console.clear()
        console.print()
        console.print(Panel("[dim]No changes[/dim]", title="Configuration", border_style="dim"))
        console.print()
        console.print("[dim]Press Enter to continue...[/dim]")

        while True:
            key = readchar.readkey()
            if key in ("\r", "\n"):
                break
