"""Tests for symlink sync module."""


import pytest
from hawk_hooks.sync import (
    create_symlink,
    generate_gemini_toml,
    remove_symlink,
    sync_prompt,
    unsync_prompt,
)

from hawk_hooks.frontmatter import PromptFrontmatter
from hawk_hooks.types import PromptInfo, PromptType


@pytest.fixture
def prompt_info(tmp_path):
    """Create a test PromptInfo."""
    source = tmp_path / "source" / "test.md"
    source.parent.mkdir()
    source.write_text("""---
name: test-cmd
description: Test command
tools: [claude, gemini]
---
Test content.
""")
    return PromptInfo(
        path=source,
        frontmatter=PromptFrontmatter(
            name="test-cmd",
            description="Test command",
            tools=["claude", "gemini"],
            hooks=[],
        ),
        prompt_type=PromptType.COMMAND,
    )


class TestSymlinkOperations:
    """Test basic symlink operations."""

    def test_create_symlink(self, tmp_path):
        source = tmp_path / "source.md"
        source.write_text("content")
        dest = tmp_path / "dest" / "link.md"

        create_symlink(source, dest)
        assert dest.is_symlink()
        assert dest.resolve() == source.resolve()

    def test_create_symlink_overwrites(self, tmp_path):
        source = tmp_path / "source.md"
        source.write_text("content")
        dest = tmp_path / "dest" / "link.md"
        dest.parent.mkdir()
        dest.write_text("old")

        create_symlink(source, dest)
        assert dest.is_symlink()

    def test_remove_symlink(self, tmp_path):
        source = tmp_path / "source.md"
        source.write_text("content")
        dest = tmp_path / "link.md"
        dest.symlink_to(source)

        remove_symlink(dest)
        assert not dest.exists()

    def test_remove_symlink_nonexistent(self, tmp_path):
        # Should not raise
        remove_symlink(tmp_path / "nonexistent.md")


class TestGeminiToml:
    """Test Gemini TOML generation."""

    def test_generate_toml(self, prompt_info):
        toml = generate_gemini_toml(prompt_info)
        assert 'name = "test-cmd"' in toml
        assert 'description = "Test command"' in toml
        assert "Test content." in toml


class TestSyncPrompt:
    """Test prompt syncing."""

    def test_sync_creates_claude_symlink(self, prompt_info, tmp_path, monkeypatch):
        from hawk_hooks import config

        claude_dest = tmp_path / "claude" / "commands"
        claude_dest.mkdir(parents=True)
        monkeypatch.setattr(
            config,
            "get_destination",
            lambda tool, item_type: str(claude_dest)
            if tool == "claude"
            else str(tmp_path / "other"),
        )

        sync_prompt(prompt_info, ["claude"])
        expected = claude_dest / "test-cmd.md"
        assert expected.is_symlink()

    def test_sync_creates_gemini_toml(self, prompt_info, tmp_path, monkeypatch):
        from hawk_hooks import config

        gemini_dest = tmp_path / "gemini" / "commands"
        gemini_dest.mkdir(parents=True)
        monkeypatch.setattr(
            config,
            "get_destination",
            lambda tool, item_type: str(gemini_dest)
            if tool == "gemini"
            else str(tmp_path / "other"),
        )

        sync_prompt(prompt_info, ["gemini"])
        expected = gemini_dest / "test-cmd.toml"
        assert expected.exists()
        assert not expected.is_symlink()  # Generated, not symlink


class TestUnsyncPrompt:
    """Test prompt unsyncing."""

    def test_unsync_removes_files(self, prompt_info, tmp_path, monkeypatch):
        from hawk_hooks import config

        claude_dest = tmp_path / "claude" / "commands"
        claude_dest.mkdir(parents=True)
        link = claude_dest / "test-cmd.md"
        link.symlink_to(prompt_info.path)

        monkeypatch.setattr(config, "get_destination", lambda tool, item_type: str(claude_dest))

        unsync_prompt(prompt_info, ["claude"])
        assert not link.exists()
