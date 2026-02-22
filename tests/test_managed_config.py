"""Tests for shared managed-config helpers."""

from pathlib import Path

from hawk_hooks.managed_config import ManagedConfigOp, TomlBlockDriver


def test_toml_block_upsert_and_replace(tmp_path: Path):
    path = tmp_path / "config.toml"
    TomlBlockDriver.upsert(path, "unit-a", 'foo = "bar"')
    TomlBlockDriver.upsert(path, "unit-a", 'foo = "baz"')
    text = path.read_text()
    assert text.count("hawk-hooks managed: unit-a") == 2  # begin + end markers
    assert 'foo = "baz"' in text
    assert 'foo = "bar"' not in text


def test_toml_block_remove(tmp_path: Path):
    path = tmp_path / "config.toml"
    TomlBlockDriver.upsert(path, "unit-a", "foo = true")
    changed = TomlBlockDriver.remove(path, "unit-a")
    assert changed is True
    assert "unit-a" not in path.read_text()


def test_strip_all_managed_blocks():
    text = (
        "# >>> hawk-hooks managed: one >>>\n"
        "a = 1\n"
        "# <<< hawk-hooks managed: one <<<\n\n"
        "[manual]\n"
        "x = true\n\n"
        "# >>> hawk-hooks managed: two >>>\n"
        "b = 2\n"
        "# <<< hawk-hooks managed: two <<<\n"
    )
    stripped = TomlBlockDriver.strip_all(text)
    assert "[manual]" in stripped
    assert "hawk-hooks managed" not in stripped


def test_apply_ops(tmp_path: Path):
    path = tmp_path / "config.toml"
    result = TomlBlockDriver.apply(
        [
            ManagedConfigOp(file=path, unit_id="one", action="upsert", payload="x = 1"),
            ManagedConfigOp(file=path, unit_id="one", action="remove"),
        ]
    )
    assert "one" in result.applied
    assert not result.errors
