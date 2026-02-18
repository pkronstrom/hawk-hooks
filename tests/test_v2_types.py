"""Tests for v2 type definitions."""

from hawk_hooks.types import ComponentType, ResolvedSet, SyncResult, Tool


class TestTool:
    def test_values(self):
        assert str(Tool.CLAUDE) == "claude"
        assert str(Tool.GEMINI) == "gemini"
        assert str(Tool.CODEX) == "codex"
        assert str(Tool.OPENCODE) == "opencode"

    def test_all(self):
        tools = Tool.all()
        assert len(tools) == 6
        assert Tool.CLAUDE in tools
        assert Tool.OPENCODE in tools
        assert Tool.CURSOR in tools
        assert Tool.ANTIGRAVITY in tools

    def test_str_enum(self):
        assert Tool.CLAUDE == "claude"
        assert Tool("gemini") == Tool.GEMINI


class TestComponentType:
    def test_values(self):
        assert str(ComponentType.SKILL) == "skill"
        assert str(ComponentType.HOOK) == "hook"
        assert str(ComponentType.COMMAND) == "command"
        assert str(ComponentType.AGENT) == "agent"
        assert str(ComponentType.MCP) == "mcp"
        assert str(ComponentType.PROMPT) == "prompt"

    def test_registry_dir(self):
        assert ComponentType.SKILL.registry_dir == "skills"
        assert ComponentType.HOOK.registry_dir == "hooks"
        assert ComponentType.MCP.registry_dir == "mcp"

    def test_str_enum(self):
        assert ComponentType("skill") == ComponentType.SKILL


class TestResolvedSet:
    def test_defaults(self):
        rs = ResolvedSet()
        assert rs.skills == []
        assert rs.hooks == []
        assert rs.commands == []
        assert rs.agents == []
        assert rs.mcp == []

    def test_get(self):
        rs = ResolvedSet(skills=["tdd"], hooks=["block-secrets"])
        assert rs.get(ComponentType.SKILL) == ["tdd"]
        assert rs.get(ComponentType.HOOK) == ["block-secrets"]
        assert rs.get(ComponentType.COMMAND) == []

    def test_hash_key_deterministic(self):
        rs1 = ResolvedSet(skills=["a", "b"], hooks=["c"])
        rs2 = ResolvedSet(skills=["a", "b"], hooks=["c"])
        assert rs1.hash_key() == rs2.hash_key()

    def test_hash_key_different(self):
        rs1 = ResolvedSet(skills=["a"])
        rs2 = ResolvedSet(skills=["b"])
        assert rs1.hash_key() != rs2.hash_key()

    def test_hash_key_order_independent(self):
        rs1 = ResolvedSet(skills=["a", "b"])
        rs2 = ResolvedSet(skills=["b", "a"])
        # sorted internally, so same hash
        assert rs1.hash_key() == rs2.hash_key()


class TestSyncResult:
    def test_defaults(self):
        sr = SyncResult(tool="claude")
        assert sr.tool == "claude"
        assert sr.linked == []
        assert sr.unlinked == []
        assert sr.errors == []
