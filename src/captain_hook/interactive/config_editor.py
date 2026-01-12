"""Configuration editor for captain-hook.

Interactive config editing with Save/Cancel menu.
"""

from __future__ import annotations

import readchar
from rich.panel import Panel

from rich_menu import InteractiveList, Item
from rich_menu.keys import is_enter

from .. import config, generator, scanner
from .core import console


def interactive_config():
    """Interactive config editor with Save/Cancel menu."""
    cfg = config.load_config()

    script_env_vars = scanner.get_all_env_vars()
    env_config = cfg.get("env", {})

    original_debug = cfg.get("debug", False)
    original_env = dict(env_config)

    console.clear()
    items = [
        Item.toggle("debug", "Log hook calls", value=cfg.get("debug", False)),
    ]

    if script_env_vars:
        items.append(Item.separator("── Hook Settings ──"))

        for var_name, default_value in sorted(script_env_vars.items()):
            current_value = env_config.get(var_name, default_value)
            if not isinstance(current_value, str):
                current_value = str(current_value) if current_value is not None else ""
            is_bool = current_value.lower() in ("true", "false", "1", "0", "yes", "no")

            if is_bool:
                value = current_value.lower() in ("true", "1", "yes")
                items.append(Item.toggle(var_name, var_name, value=value))
            else:
                items.append(Item.text(var_name, var_name, value=current_value))

    items.append(Item.separator("─────────"))
    items.append(Item.action("Save", value="save"))
    items.append(Item.action("Cancel", value="cancel"))

    menu = InteractiveList(title="Configuration", items=items, console=console)
    result = menu.show()

    if result.get("action") == "cancel" or not result:
        return

    if "action" not in result:
        return

    debug_changed = False
    env_changed = False

    for key, value in result.items():
        if key == "action":
            continue
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
            if is_enter(key):
                break
    else:
        console.clear()
        console.print()
        console.print(Panel("[dim]No changes[/dim]", title="Configuration", border_style="dim"))
        console.print()
        console.print("[dim]Press Enter to continue...[/dim]")

        while True:
            key = readchar.readkey()
            if is_enter(key):
                break
