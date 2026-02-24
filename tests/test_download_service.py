"""Tests for shared download service operations."""

from __future__ import annotations

from pathlib import Path

from hawk_hooks import config


def _patch_config_paths(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    registry_dir = tmp_path / "registry"
    monkeypatch.setattr(config, "get_config_dir", lambda: config_dir)
    monkeypatch.setattr(config, "get_global_config_path", lambda: config_dir / "config.yaml")
    monkeypatch.setattr(config, "get_profiles_dir", lambda: config_dir / "profiles")
    monkeypatch.setattr(config, "get_packages_path", lambda: config_dir / "packages.yaml")
    monkeypatch.setattr(config, "get_registry_path", lambda cfg=None: registry_dir)
    return config_dir, registry_dir


def test_download_and_install_success_returns_result(monkeypatch, tmp_path):
    from hawk_hooks.download_service import DownloadResult, download_and_install

    _patch_config_paths(monkeypatch, tmp_path)

    repo_dir = tmp_path / "repo"
    commands_dir = repo_dir / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "hello.md").write_text("# Hello\n")

    monkeypatch.setattr("hawk_hooks.download_service.shallow_clone", lambda _url: repo_dir)
    monkeypatch.setattr("hawk_hooks.download_service.get_head_commit", lambda _path: "abcdef123456")

    result = download_and_install(
        "https://github.com/example/demo.git",
        select_all=True,
        replace=False,
    )

    assert isinstance(result, DownloadResult)
    assert result.success is True
    assert result.error is None
    assert result.added == ["prompt/hello.md"]
    assert result.skipped == []
    assert result.clashes == []
    assert result.package_name == "example/demo"

    packages = config.load_packages()
    assert "example/demo" in packages
    assert packages["example/demo"]["url"] == "https://github.com/example/demo.git"
    assert len(packages["example/demo"]["items"]) == 1


def test_download_and_install_clone_error_returns_failure(monkeypatch, tmp_path):
    from hawk_hooks.download_service import DownloadResult, download_and_install

    _patch_config_paths(monkeypatch, tmp_path)

    def _raise(_url: str):
        raise RuntimeError("clone failed")

    monkeypatch.setattr("hawk_hooks.download_service.shallow_clone", _raise)

    result = download_and_install(
        "https://github.com/example/demo.git",
        select_all=True,
        replace=False,
    )

    assert isinstance(result, DownloadResult)
    assert result.success is False
    assert result.added == []
    assert result.skipped == []
    assert result.clashes == []
    assert result.package_name is None
    assert result.error is not None
    assert "clone failed" in result.error


def _make_repo(tmp_path, items: dict[str, str]) -> Path:
    """Create a fake repo dir with component files.

    items: {"commands/foo.md": "# Foo", "skills/bar.md": "# Bar"}
    """
    repo_dir = tmp_path / "repo"
    for relpath, content in items.items():
        p = repo_dir / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return repo_dir


def test_download_clashes_without_replace_renames_item(monkeypatch, tmp_path):
    """When a component clashes, it's renamed with package prefix and added."""
    from hawk_hooks.download_service import download_and_install
    from hawk_hooks.registry import Registry

    _, registry_dir = _patch_config_paths(monkeypatch, tmp_path)

    repo_dir = _make_repo(tmp_path, {"commands/hello.md": "# Hello\n"})
    monkeypatch.setattr("hawk_hooks.download_service.shallow_clone", lambda _url: repo_dir)
    monkeypatch.setattr("hawk_hooks.download_service.get_head_commit", lambda _path: "abc123")

    # Pre-populate registry with the same component to trigger a clash
    registry = Registry(registry_dir)
    registry.ensure_dirs()
    prompts_dir = registry_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "hello.md").write_text("# Existing\n")

    result = download_and_install(
        "https://github.com/example/clash-test.git",
        select_all=True,
        replace=False,
    )

    assert result.success is True
    # Original clashes are recorded
    assert len(result.clashes) > 0
    assert any("hello" in c for c in result.clashes)
    # But the item was renamed and added
    assert any("clash-test-hello.md" in a for a in result.added)


def test_download_select_fn_cancel_returns_empty(monkeypatch, tmp_path):
    """When select_fn returns cancel action, no components are installed."""
    from hawk_hooks.download_service import download_and_install

    _patch_config_paths(monkeypatch, tmp_path)

    repo_dir = _make_repo(tmp_path, {"commands/hello.md": "# Hello\n"})
    monkeypatch.setattr("hawk_hooks.download_service.shallow_clone", lambda _url: repo_dir)
    monkeypatch.setattr("hawk_hooks.download_service.get_head_commit", lambda _path: "abc123")

    def _cancel_select(*args, **kwargs):
        return ([], "cancel")

    result = download_and_install(
        "https://github.com/example/demo.git",
        select_all=False,
        replace=False,
        select_fn=_cancel_select,
    )

    assert result.success is True
    assert result.added == []
    assert result.package_name is None


def test_download_select_fn_returns_list(monkeypatch, tmp_path):
    """When select_fn returns a plain list (no tuple), it works correctly."""
    from hawk_hooks.download_service import download_and_install

    _patch_config_paths(monkeypatch, tmp_path)

    repo_dir = _make_repo(tmp_path, {"commands/hello.md": "# Hello\n"})
    monkeypatch.setattr("hawk_hooks.download_service.shallow_clone", lambda _url: repo_dir)
    monkeypatch.setattr("hawk_hooks.download_service.get_head_commit", lambda _path: "abc123")

    def _select_all(items, *args, **kwargs):
        return items  # plain list, no tuple wrapping

    result = download_and_install(
        "https://github.com/example/demo.git",
        select_all=False,
        replace=False,
        select_fn=_select_all,
    )

    assert result.success is True
    assert len(result.added) == 1


def test_get_interactive_select_fn():
    """get_interactive_select_fn returns a callable from the CLI module."""
    from hawk_hooks.download_service import get_interactive_select_fn

    fn = get_interactive_select_fn()
    assert callable(fn)
