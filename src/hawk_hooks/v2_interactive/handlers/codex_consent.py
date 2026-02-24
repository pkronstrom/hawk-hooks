"""Codex consent handlers for the dashboard."""

from __future__ import annotations

from ... import v2_config
from ...types import Tool
from .. import dashboard as _dashboard

console = _dashboard.console
_CODEX_CONSENT_OPTIONS = _dashboard._CODEX_CONSENT_OPTIONS


def TerminalMenu(*args, **kwargs):
    return _dashboard.TerminalMenu(*args, **kwargs)


def warning_style(*args, **kwargs):
    return _dashboard.warning_style(*args, **kwargs)


def terminal_menu_style_kwargs(*args, **kwargs):
    return _dashboard.terminal_menu_style_kwargs(*args, **kwargs)


def get_codex_multi_agent_consent(cfg: dict) -> str:
    """Return codex multi-agent consent state with backward compatibility."""
    codex_cfg = cfg.get("tools", {}).get("codex", {})
    consent = codex_cfg.get("multi_agent_consent")
    if consent in _CODEX_CONSENT_OPTIONS:
        return str(consent)

    # Backward compatibility with earlier boolean gate.
    if codex_cfg.get("allow_multi_agent") is True:
        return "granted"
    return "ask"


def is_codex_multi_agent_setup_required(state: dict) -> bool:
    """Whether codex multi-agent consent should be surfaced to the user."""
    codex_status = state.get("tools_status", {}).get(Tool.CODEX, {})
    if not codex_status.get("enabled", True):
        return False
    active_agents = len(getattr(state.get("resolved_active"), "agents", []))
    if active_agents <= 0:
        return False
    return state.get("codex_multi_agent_consent", "ask") == "ask"

def handle_codex_multi_agent_setup(state: dict, *, from_sync: bool = False) -> bool:
    """Prompt for codex multi-agent consent and persist the chosen state."""
    cfg = state.get("cfg") or v2_config.load_global_config()
    tools_cfg = cfg.setdefault("tools", {})
    codex_cfg = tools_cfg.setdefault("codex", {})
    consent = _dashboard._get_codex_multi_agent_consent(cfg)

    body_lines = [
        "[bold]Enable Codex multi-agent support?[/bold]",
        "",
        "To sync Hawk agents into Codex, Codex must have multi-agent mode enabled.",
        "",
        "Hawk can manage this in [cyan].codex/config.toml[/cyan] by writing:",
        "[cyan]  [features][/cyan]",
        "[cyan]  multi_agent = true[/cyan]",
        "",
        "[green]Enable now[/green]: let Hawk manage it automatically.",
        "[yellow]Not now[/yellow]: skip for now (you will be asked again).",
        "[red]Never[/red]: do not manage this setting.",
    ]
    if from_sync:
        body_lines.extend(["", "[yellow]Sync is about to run.[/yellow]"])

    console.print()
    warn_start, warn_end = warning_style(True)
    console.print(f"{warn_start}Codex setup required{warn_end}")
    console.print("[dim]" + ("\u2500" * 50) + "[/dim]")
    console.print("\n".join(body_lines))

    menu = TerminalMenu(
        ["Enable now", "Not now", "Never"],
        title="\nChoose an option",
        cursor_index=0,
        menu_cursor="\u203a ",
        **terminal_menu_style_kwargs(),
        quit_keys=("q", "\x1b"),
    )
    choice = menu.show()
    if choice is None:
        return False

    if choice == 0:
        new_consent = "granted"
    elif choice == 1:
        new_consent = "ask"
    else:
        new_consent = "denied"

    changed = new_consent != consent or codex_cfg.get("allow_multi_agent") != (new_consent == "granted")
    codex_cfg["multi_agent_consent"] = new_consent
    # Backward-compatible mirror for older adapter code paths.
    codex_cfg["allow_multi_agent"] = new_consent == "granted"
    tools_cfg["codex"] = codex_cfg
    cfg["tools"] = tools_cfg
    v2_config.save_global_config(cfg)

    # Update in-memory state for immediate menu refresh.
    state["cfg"] = cfg
    state["codex_multi_agent_consent"] = new_consent
    state["codex_multi_agent_required"] = _dashboard._is_codex_multi_agent_setup_required(state)

    return changed
