from __future__ import annotations

from hawk_hooks.v2_interactive import theme


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
