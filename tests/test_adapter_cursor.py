"""Tests for the Cursor adapter."""

import json

import pytest

from hawk_hooks.adapters.cursor import CursorAdapter
from hawk_hooks.types import ResolvedSet, Tool


@pytest.fixture
def adapter():
    return CursorAdapter()


class TestCursorAdapter:
    def test_tool(self, adapter):
        assert adapter.tool == Tool.CURSOR

    def test_global_dir(self, adapter):
        assert str(adapter.get_global_dir()).endswith(".cursor")

    def test_hook_support_flag(self, adapter):
        assert adapter.hook_support == "unsupported"


class TestCursorHooks:
    def test_sync_warns_when_hooks_configured(self, adapter, tmp_path):
        registry = tmp_path / "registry"
        target = tmp_path / "cursor"
        target.mkdir(parents=True)

        result = adapter.sync(ResolvedSet(hooks=["guard.py"]), target, registry)
        assert any("cursor hook registration is unsupported" in e for e in result.errors)


class TestCursorMCP:
    def test_write_mcp(self, adapter, tmp_path):
        target = tmp_path / "cursor"
        target.mkdir(parents=True)

        adapter.write_mcp_config({"gh": {"command": "gh-mcp"}}, target)
        data = json.loads((target / "mcp.json").read_text())
        assert "gh" in data["mcpServers"]
