"""Tests for event mapping between tools."""

from captain_hook.event_mapping import (
    get_canonical_event,
    get_tool_event,
    is_tool_specific_event,
)


class TestCanonicalEvents:
    """Test canonical event definitions."""

    def test_pre_tool_maps_to_claude(self):
        assert get_tool_event("pre_tool", "claude") == "pre_tool_use"

    def test_pre_tool_maps_to_gemini(self):
        assert get_tool_event("pre_tool", "gemini") == "BeforeTool"

    def test_post_tool_maps_to_claude(self):
        assert get_tool_event("post_tool", "claude") == "post_tool_use"

    def test_post_tool_maps_to_gemini(self):
        assert get_tool_event("post_tool", "gemini") == "AfterTool"

    def test_session_start_maps_correctly(self):
        assert get_tool_event("session_start", "claude") == "session_start"
        assert get_tool_event("session_start", "gemini") == "SessionStart"

    def test_unknown_tool_returns_canonical(self):
        assert get_tool_event("pre_tool", "unknown") == "pre_tool"


class TestToolSpecificEvents:
    """Test tool-specific event handling."""

    def test_user_prompt_submit_is_claude_specific(self):
        assert is_tool_specific_event("user_prompt_submit", "claude") is True
        assert is_tool_specific_event("user_prompt_submit", "gemini") is False

    def test_before_model_is_gemini_specific(self):
        assert is_tool_specific_event("BeforeModel", "gemini") is True
        assert is_tool_specific_event("BeforeModel", "claude") is False

    def test_canonical_events_are_not_tool_specific(self):
        assert is_tool_specific_event("pre_tool", "claude") is False


class TestReverseMapping:
    """Test getting canonical from tool-specific."""

    def test_pre_tool_use_to_canonical(self):
        assert get_canonical_event("pre_tool_use") == "pre_tool"

    def test_before_tool_to_canonical(self):
        assert get_canonical_event("BeforeTool") == "pre_tool"

    def test_canonical_stays_canonical(self):
        assert get_canonical_event("pre_tool") == "pre_tool"

    def test_tool_specific_stays_as_is(self):
        assert get_canonical_event("user_prompt_submit") == "user_prompt_submit"
