"""Tests for v2 first-run wizard behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from hawk_hooks import v2_config

pytest.importorskip("rich")
pytest.importorskip("simple_term_menu")

from hawk_hooks.v2_interactive import wizard


@pytest.fixture
def v2_env(tmp_path, monkeypatch):
    config_dir = tmp_path / "hawk-hooks"
    config_dir.mkdir()
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
    return config_dir


class _MenuAccept:
    def __init__(self, *args, **kwargs):
        pass

    def show(self):
        return 0


class _MenuDecline:
    def __init__(self, *args, **kwargs):
        pass

    def show(self):
        return 1


class _AdapterStub:
    def detect_installed(self):
        return False


def test_offer_builtins_install_uses_scan(v2_env, tmp_path, monkeypatch):
    builtins_dir = tmp_path / "builtins"
    (builtins_dir / "commands").mkdir(parents=True)
    (builtins_dir / "commands" / "hello.md").write_text("# hello")
    (builtins_dir / "hawk-package.yaml").write_text("name: starter-builtins\nversion: 1.0.0\n")

    captured: dict[str, object] = {}

    monkeypatch.setattr(wizard, "_get_builtins_path", lambda: builtins_dir)
    monkeypatch.setattr(wizard, "TerminalMenu", _MenuAccept)

    import hawk_hooks.v2_cli as v2_cli

    def _fake_scan(args):
        captured["args"] = args

    monkeypatch.setattr(v2_cli, "cmd_scan", _fake_scan)

    wizard._offer_builtins_install()

    args = captured.get("args")
    assert args is not None
    assert getattr(args, "path") == str(builtins_dir)
    assert getattr(args, "all") is True
    assert getattr(args, "replace") is False
    assert getattr(args, "no_enable") is False


def test_offer_builtins_install_decline_skips_scan(v2_env, tmp_path, monkeypatch):
    builtins_dir = tmp_path / "builtins"
    (builtins_dir / "commands").mkdir(parents=True)
    (builtins_dir / "commands" / "hello.md").write_text("# hello")
    (builtins_dir / "hawk-package.yaml").write_text("name: starter-builtins\nversion: 1.0.0\n")

    called = {"scan": False}

    monkeypatch.setattr(wizard, "_get_builtins_path", lambda: builtins_dir)
    monkeypatch.setattr(wizard, "TerminalMenu", _MenuDecline)

    import hawk_hooks.v2_cli as v2_cli

    def _fake_scan(args):
        called["scan"] = True

    monkeypatch.setattr(v2_cli, "cmd_scan", _fake_scan)

    wizard._offer_builtins_install()

    assert called["scan"] is False


def test_run_wizard_no_git_download_prompt(v2_env, monkeypatch):
    monkeypatch.setattr(wizard, "TerminalMenu", _MenuAccept)
    monkeypatch.setattr(wizard, "get_adapter", lambda _tool: _AdapterStub())
    monkeypatch.setattr(wizard, "_offer_builtins_install", lambda: None)
    monkeypatch.setattr(wizard.console, "input", lambda *_args, **_kwargs: "")

    import hawk_hooks.v2_cli as v2_cli

    def _unexpected_download(_args):
        raise AssertionError("wizard should not invoke cmd_download during first-run")

    monkeypatch.setattr(v2_cli, "cmd_download", _unexpected_download)

    assert wizard.run_wizard() is True


def test_run_wizard_next_steps_do_not_recommend_manual_sync(v2_env, monkeypatch):
    printed: list[str] = []

    def _capture_print(*args, **kwargs):
        printed.append(" ".join(str(a) for a in args))

    monkeypatch.setattr(wizard, "TerminalMenu", _MenuAccept)
    monkeypatch.setattr(wizard, "get_adapter", lambda _tool: _AdapterStub())
    monkeypatch.setattr(wizard, "_offer_builtins_install", lambda: None)
    monkeypatch.setattr(wizard.console, "input", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(wizard.console, "print", _capture_print)

    assert wizard.run_wizard() is True

    output = "\n".join(printed)
    assert "hawk sync" not in output
