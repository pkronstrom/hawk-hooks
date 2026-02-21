"""Tests for the Antigravity adapter."""

import json

import pytest

from hawk_hooks.adapters.antigravity import AntigravityAdapter
from hawk_hooks.types import ResolvedSet, Tool


@pytest.fixture
def adapter():
    return AntigravityAdapter()


class TestAntigravityAdapter:
    def test_tool(self, adapter):
        assert adapter.tool == Tool.ANTIGRAVITY

    def test_global_dir(self, adapter):
        assert str(adapter.get_global_dir()).endswith(".gemini/antigravity")

    def test_hook_support_flag(self, adapter):
        assert adapter.hook_support == "unsupported"


class TestAntigravityHooks:
    def test_sync_warns_when_hooks_configured(self, adapter, tmp_path):
        registry = tmp_path / "registry"
        target = tmp_path / "antigravity"
        target.mkdir(parents=True)

        result = adapter.sync(ResolvedSet(hooks=["guard.py"]), target, registry)
        assert any("antigravity hook registration is unsupported" in e for e in result.errors)


class TestAntigravityMCP:
    def test_write_mcp_sidecar(self, adapter, tmp_path):
        target = tmp_path / "antigravity"
        target.mkdir(parents=True)

        adapter.write_mcp_config({"gh": {"command": "gh-mcp"}}, target)
        data = json.loads((target / "mcp_config.json").read_text())
        assert "gh" in data["mcpServers"]
        sidecar = json.loads((target / ".hawk-mcp.json").read_text())
        assert "gh" in sidecar
