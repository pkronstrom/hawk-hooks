"""Tests for the component registry."""

import pytest

from hawk_hooks.registry import Registry
from hawk_hooks.types import ComponentType


@pytest.fixture
def registry(tmp_path):
    """Create a test registry in a temp directory."""
    reg = Registry(registry_path=tmp_path / "registry")
    reg.ensure_dirs()
    return reg


class TestAdd:
    def test_add_file(self, registry, tmp_path):
        source = tmp_path / "my-skill.md"
        source.write_text("# My Skill")

        path = registry.add(ComponentType.SKILL, "my-skill.md", source)
        assert path.exists()
        assert path.read_text() == "# My Skill"

    def test_add_directory(self, registry, tmp_path):
        source = tmp_path / "my-hook"
        source.mkdir()
        (source / "hook.py").write_text("print('hello')")

        path = registry.add(ComponentType.HOOK, "my-hook", source)
        assert path.is_dir()
        assert (path / "hook.py").read_text() == "print('hello')"

    def test_add_duplicate_raises(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("content")
        registry.add(ComponentType.SKILL, "skill.md", source)

        with pytest.raises(FileExistsError):
            registry.add(ComponentType.SKILL, "skill.md", source)

    def test_add_missing_source_raises(self, registry, tmp_path):
        with pytest.raises(FileNotFoundError):
            registry.add(ComponentType.SKILL, "x.md", tmp_path / "nonexistent.md")


class TestRemove:
    def test_remove_existing(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("content")
        registry.add(ComponentType.SKILL, "skill.md", source)

        assert registry.remove(ComponentType.SKILL, "skill.md") is True
        assert not registry.has(ComponentType.SKILL, "skill.md")

    def test_remove_missing_returns_false(self, registry):
        assert registry.remove(ComponentType.SKILL, "nonexistent") is False

    def test_remove_directory(self, registry, tmp_path):
        source = tmp_path / "my-hook"
        source.mkdir()
        (source / "hook.py").write_text("x")
        registry.add(ComponentType.HOOK, "my-hook", source)

        assert registry.remove(ComponentType.HOOK, "my-hook") is True


class TestList:
    def test_list_all(self, registry, tmp_path):
        s1 = tmp_path / "a.md"
        s1.write_text("a")
        s2 = tmp_path / "b.md"
        s2.write_text("b")
        registry.add(ComponentType.SKILL, "a.md", s1)
        registry.add(ComponentType.SKILL, "b.md", s2)

        result = registry.list(ComponentType.SKILL)
        assert result[ComponentType.SKILL] == ["a.md", "b.md"]

    def test_list_empty(self, registry):
        result = registry.list(ComponentType.SKILL)
        assert result[ComponentType.SKILL] == []

    def test_list_all_types(self, registry, tmp_path):
        source = tmp_path / "item.md"
        source.write_text("x")
        registry.add(ComponentType.SKILL, "item.md", source)

        result = registry.list()
        assert len(result) == len(ComponentType)
        assert "item.md" in result[ComponentType.SKILL]

    def test_list_flat(self, registry, tmp_path):
        source = tmp_path / "item.md"
        source.write_text("x")
        registry.add(ComponentType.SKILL, "item.md", source)

        flat = registry.list_flat()
        assert (ComponentType.SKILL, "item.md") in flat


class TestHasAndGetPath:
    def test_has(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("content")
        registry.add(ComponentType.SKILL, "skill.md", source)

        assert registry.has(ComponentType.SKILL, "skill.md") is True
        assert registry.has(ComponentType.SKILL, "other.md") is False

    def test_get_path(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("content")
        registry.add(ComponentType.SKILL, "skill.md", source)

        path = registry.get_path(ComponentType.SKILL, "skill.md")
        assert path is not None
        assert path.exists()

    def test_get_path_missing(self, registry):
        assert registry.get_path(ComponentType.SKILL, "nope") is None


class TestNameValidation:
    def test_rejects_path_traversal(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("x")
        with pytest.raises(ValueError, match="path traversal"):
            registry.add(ComponentType.SKILL, "../../etc/passwd", source)

    def test_rejects_slash(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("x")
        with pytest.raises(ValueError, match="path traversal"):
            registry.add(ComponentType.SKILL, "sub/skill.md", source)

    def test_rejects_dotdot(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("x")
        with pytest.raises(ValueError, match="path traversal"):
            registry.add(ComponentType.SKILL, "..", source)

    def test_rejects_hidden(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("x")
        with pytest.raises(ValueError, match="hidden"):
            registry.add(ComponentType.SKILL, ".hidden", source)

    def test_rejects_empty(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("x")
        with pytest.raises(ValueError):
            registry.add(ComponentType.SKILL, "", source)

    def test_remove_rejects_traversal(self, registry):
        with pytest.raises(ValueError, match="path traversal"):
            registry.remove(ComponentType.SKILL, "../secret")

    def test_has_rejects_traversal(self, registry):
        with pytest.raises(ValueError, match="path traversal"):
            registry.has(ComponentType.SKILL, "../../etc/passwd")

    def test_get_path_rejects_traversal(self, registry):
        with pytest.raises(ValueError, match="path traversal"):
            registry.get_path(ComponentType.SKILL, "../secret")

    def test_has_from_name_rejects_traversal(self, registry):
        with pytest.raises(ValueError, match="path traversal"):
            registry.has_from_name("skills", "../../etc/passwd")


class TestClashDetection:
    def test_detects_clash(self, registry, tmp_path):
        source = tmp_path / "skill.md"
        source.write_text("content")
        registry.add(ComponentType.SKILL, "skill.md", source)

        assert registry.detect_clash(ComponentType.SKILL, "skill.md") is True

    def test_no_clash(self, registry):
        assert registry.detect_clash(ComponentType.SKILL, "new-skill.md") is False
