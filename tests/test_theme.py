from __future__ import annotations

from hawk_hooks.interactive import theme


def test_set_project_theme_selects_known_project_palette():
    selected = theme.set_project_theme("owl-afk")
    assert selected.name == "owl-afk"
    assert selected.accent_term == "fg_blue"


def test_set_project_theme_uses_path_name():
    selected = theme.set_project_theme("/tmp/goose-scripts")
    assert selected.name == "goose-scripts"
    assert selected.accent_term == "fg_yellow"


def test_set_project_theme_honors_env_override(monkeypatch):
    monkeypatch.setenv("HAWK_TUI_THEME", "dodo-tasks")
    selected = theme.set_project_theme("hawk-hooks")
    assert selected.name == "dodo-tasks"


def test_keybinding_hint_includes_nav_and_back():
    hint = theme.keybinding_hint(
        ["space/↵ change"],
        include_nav=True,
    )
    assert "space/↵ change" in hint
    assert "↑↓/jk nav" in hint
    assert "q/esc back" in hint
