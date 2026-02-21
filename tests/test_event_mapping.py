"""Tests for event mapping and capability status across tools."""

from hawk_hooks.event_mapping import (
    get_canonical_event,
    get_event_support,
    get_tool_event,
    get_tool_event_or_none,
    is_event_supported,
    is_tool_specific_event,
)


class TestMappings:
    def test_legacy_alias_maps_to_claude(self):
        assert get_tool_event("pre_tool", "claude") == "PreToolUse"

    def test_hawk_event_maps_to_gemini(self):
        assert get_tool_event("pre_tool_use", "gemini") == "BeforeTool"

    def test_unsupported_returns_input_for_compat(self):
        assert get_tool_event("permission_request", "gemini") == "permission_request"

    def test_get_tool_event_or_none(self):
        assert get_tool_event_or_none("stop", "codex") == "agent-turn-complete"
        assert get_tool_event_or_none("pre_tool_use", "codex") is None


class TestSupportLevels:
    def test_claude_native(self):
        assert get_event_support("permission_request", "claude") == "native"

    def test_gemini_native_subset(self):
        assert get_event_support("user_prompt_submit", "gemini") == "native"
        assert get_event_support("permission_request", "gemini") == "unsupported"

    def test_codex_bridge(self):
        assert get_event_support("stop", "codex") == "bridge"
        assert get_event_support("notification", "codex") == "bridge"
        assert get_event_support("pre_tool_use", "codex") == "unsupported"

    def test_is_event_supported_uses_native_or_bridge(self):
        assert is_event_supported("stop", "codex") is True
        assert is_event_supported("pre_tool_use", "codex") is False


class TestToolSpecificEvents:
    def test_before_model_is_gemini_specific(self):
        assert is_tool_specific_event("BeforeModel", "gemini") is True
        assert is_tool_specific_event("BeforeModel", "claude") is False


class TestReverseMapping:
    def test_reverse_to_legacy_canonical_alias(self):
        assert get_canonical_event("PreToolUse") == "pre_tool"
        assert get_canonical_event("pre_tool_use") == "pre_tool"

    def test_unknown_stays_as_is(self):
        assert get_canonical_event("unknown_event") == "unknown_event"
