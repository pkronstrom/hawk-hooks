"""Semantic style helpers and project-aware palettes for v2 TUI screens."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SEPARATOR_WIDTH = 50


@dataclass(frozen=True)
class TuiTheme:
    """Semantic palette tokens for Rich and TerminalMenu renderers."""

    name: str
    accent_rich: str
    info_rich: str
    success_rich: str
    warning_rich: str
    error_rich: str
    muted_rich: str
    accent_term: str
    info_term: str
    warning_term: str
    error_term: str


# Base palette follows docs/tui-color-philosophy.md defaults.
_BASE_THEME = TuiTheme(
    name="default",
    accent_rich="color(130)",  # warm rust
    info_rich="color(24)",     # deep blue
    success_rich="color(28)",  # dark green
    warning_rich="color(136)",  # ochre
    error_rich="color(124)",   # brick red
    muted_rich="grey50",
    accent_term="fg_yellow",
    info_term="fg_blue",
    warning_term="fg_yellow",
    error_term="fg_red",
)


# Bird-inspired project variants (shared semantics, tuned accent mood).
_THEMES: dict[str, TuiTheme] = {
    "hawk-hooks": TuiTheme(
        name="hawk-hooks",
        accent_rich="color(130)",   # sharp, warm raptor rust
        info_rich="color(24)",
        success_rich="color(28)",
        warning_rich="color(136)",
        error_rich="color(124)",
        muted_rich="grey50",
        accent_term="fg_yellow",
        info_term="fg_blue",
        warning_term="fg_yellow",
        error_term="fg_red",
    ),
    "dodo-tasks": TuiTheme(
        name="dodo-tasks",
        accent_rich="color(95)",    # muted volcanic plum
        info_rich="color(25)",
        success_rich="color(29)",
        warning_rich="color(137)",
        error_rich="color(124)",
        muted_rich="grey50",
        accent_term="fg_magenta",
        info_term="fg_blue",
        warning_term="fg_yellow",
        error_term="fg_red",
    ),
    "owl-afk": TuiTheme(
        name="owl-afk",
        accent_rich="color(60)",    # nocturnal indigo
        info_rich="color(24)",
        success_rich="color(29)",
        warning_rich="color(101)",
        error_rich="color(124)",
        muted_rich="grey50",
        accent_term="fg_blue",
        info_term="fg_cyan",
        warning_term="fg_yellow",
        error_term="fg_red",
    ),
    "goose-scripts": TuiTheme(
        name="goose-scripts",
        accent_rich="color(130)",   # warm editorial rust
        info_rich="color(24)",
        success_rich="color(28)",
        warning_rich="color(136)",
        error_rich="color(124)",
        muted_rich="grey50",
        accent_term="fg_yellow",
        info_term="fg_blue",
        warning_term="fg_yellow",
        error_term="fg_red",
    ),
}


_current_theme: TuiTheme = _BASE_THEME


def _normalize_theme_key(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _candidate_project_names(path_like: str | Path | None) -> list[str]:
    """Return possible project names for theme matching."""
    if path_like is None:
        return []
    path = Path(path_like).expanduser()
    candidates: list[str] = []
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path

    for candidate in (resolved.name, path.name):
        if candidate:
            candidates.append(_normalize_theme_key(candidate))
    return candidates


def set_project_theme(project: str | Path | None) -> TuiTheme:
    """Select active theme from project name/path (or env override)."""
    global _current_theme

    env_theme = os.environ.get("HAWK_TUI_THEME")
    if env_theme:
        env_key = _normalize_theme_key(env_theme)
        _current_theme = _THEMES.get(env_key, _BASE_THEME)
        return _current_theme

    for key in _candidate_project_names(project):
        if key in _THEMES:
            _current_theme = _THEMES[key]
            return _current_theme

    _current_theme = _BASE_THEME
    return _current_theme


def get_theme() -> TuiTheme:
    """Return current active theme."""
    return _current_theme


def terminal_menu_style_kwargs(*, include_status_bar: bool = False) -> dict[str, Any]:
    """Shared style kwargs for simple_term_menu."""
    theme = get_theme()
    kwargs: dict[str, Any] = {
        "menu_cursor_style": (theme.accent_term, "bold"),
        "menu_highlight_style": (theme.accent_term, "bold"),
    }
    if include_status_bar:
        kwargs["status_bar_style"] = (theme.info_term, "bg_black")
    return kwargs


def dim_separator(width: int = SEPARATOR_WIDTH) -> str:
    """Return a standard muted separator line."""
    theme = get_theme()
    return f"[{theme.muted_rich}]{'─' * width}[/{theme.muted_rich}]"


def cursor_prefix(is_current: bool) -> str:
    """Return the standard row cursor prefix."""
    if not is_current:
        return "  "
    theme = get_theme()
    return f"[{theme.accent_rich}]❯[/{theme.accent_rich}] "


def scoped_header(title: str, scope_label: str, tab_hint: str = "") -> str:
    """Render a standard section header with scope and optional Tab hint."""
    theme = get_theme()
    line = f"[bold {theme.accent_rich}]{title}[/bold {theme.accent_rich}] — {scope_label}"
    if tab_hint:
        line += f"    [{theme.muted_rich}]{tab_hint}[/{theme.muted_rich}]"
    return line


def row_style(is_current: bool) -> tuple[str, str]:
    """Return base row style tags."""
    return ("[bold]", "[/bold]") if is_current else ("", "")


def action_style(is_current: bool) -> tuple[str, str]:
    """Return action row style tags."""
    if not is_current:
        return "", ""
    theme = get_theme()
    return f"[{theme.accent_rich} bold]", f"[/{theme.accent_rich} bold]"


def warning_style(is_current: bool) -> tuple[str, str]:
    """Return warning row style tags."""
    theme = get_theme()
    if is_current:
        return f"[bold {theme.warning_rich}]", f"[/bold {theme.warning_rich}]"
    return f"[{theme.warning_rich}]", f"[/{theme.warning_rich}]"


def enabled_count_style(enabled_count: int) -> str:
    """Style for enabled/total counters."""
    theme = get_theme()
    return "white" if enabled_count > 0 else theme.muted_rich


def keybinding_hint(
    actions: list[str],
    *,
    include_nav: bool = False,
    include_back: bool = True,
) -> str:
    """Return a standardized dim keybinding hint line."""
    parts = list(actions)
    if include_nav:
        parts.append("↑↓/jk nav")
    if include_back:
        parts.append("q/esc back")

    theme = get_theme()
    joined = " · ".join(parts)
    return f"[{theme.muted_rich}]{joined}[/{theme.muted_rich}]"
