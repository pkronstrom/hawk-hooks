"""Tests for shared package service operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from hawk_hooks import v2_config
from hawk_hooks.package_service import (
    PackageUpdateFailedError,
    remove_package,
    update_packages,
)
from hawk_hooks.registry import Registry
from hawk_hooks.types import ComponentType


def _patch_config_paths(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    registry_dir = tmp_path / "registry"
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
    monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
    monkeypatch.setattr(v2_config, "get_profiles_dir", lambda: config_dir / "profiles")
    monkeypatch.setattr(v2_config, "get_packages_path", lambda: config_dir / "packages.yaml")
    monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)
    return config_dir, registry_dir


def test_update_packages_local_missing_path_raises(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)
    missing_path = tmp_path / "does-not-exist"
    v2_config.save_packages({
        "local-pkg": {
            "url": "",
            "path": str(missing_path),
            "installed": "2026-02-23",
            "commit": "",
            "items": [],
        }
    })

    lines: list[str] = []
    with pytest.raises(PackageUpdateFailedError) as exc:
        update_packages(log=lines.append)

    assert exc.value.failed_packages == ["local-pkg"]
    joined = "\n".join(lines)
    assert "local source path not found" in joined
    assert "hawk remove-package local-pkg" in joined
    assert "Failed (1): local-pkg" in joined


def test_remove_package_cleans_registry_and_configs(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("hawk_hooks.v2_sync.sync_all", lambda force=False: {})

    registry = Registry(v2_config.get_registry_path())
    registry.ensure_dirs()

    source = tmp_path / "src" / "tdd"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("# TDD")
    registry.add(ComponentType.SKILL, "tdd", source)

    cfg = v2_config.load_global_config()
    cfg["global"]["skills"] = ["tdd"]
    v2_config.save_global_config(cfg)

    project = tmp_path / "project"
    project.mkdir()
    v2_config.save_dir_config(project, {"skills": {"enabled": ["tdd"], "disabled": []}})
    v2_config.register_directory(project)

    v2_config.save_packages({
        "starter": {
            "url": "",
            "path": str(tmp_path / "starter"),
            "installed": "2026-02-23",
            "commit": "",
            "items": [{"type": "skill", "name": "tdd", "hash": "deadbeef"}],
        }
    })

    result = remove_package("starter", sync_after=True, log=lambda _msg: None)

    assert result.package_name == "starter"
    assert result.removed_items == 1
    assert "starter" not in v2_config.load_packages()
    assert v2_config.load_global_config()["global"]["skills"] == []
    assert v2_config.load_dir_config(project)["skills"]["enabled"] == []
    assert registry.get_path(ComponentType.SKILL, "tdd") is None
