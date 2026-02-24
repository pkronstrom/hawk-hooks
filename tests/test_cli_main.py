from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from hawk_hooks import cli


def test_main_prints_tui_import_error_before_help(monkeypatch, capsys):
    class _Parser:
        def parse_args(self):
            return SimpleNamespace(command=None, main_dir=None)

        def print_help(self):
            print("HELP")

    monkeypatch.setattr(cli, "build_parser", lambda: _Parser())

    fake_module = types.ModuleType("hawk_hooks.interactive")

    def _fail_tui(**_kwargs):
        raise ImportError("simple_term_menu missing")

    fake_module.interactive_menu = _fail_tui
    monkeypatch.setitem(sys.modules, "hawk_hooks.interactive", fake_module)

    cli.main()
    out = capsys.readouterr().out
    assert "simple_term_menu missing" in out
    assert "HELP" in out
