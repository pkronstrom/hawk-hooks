"""Tests for shared package service operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from hawk_hooks import config
from hawk_hooks.downloader import ClassifiedContent, ClassifiedItem
from hawk_hooks.package_service import (
    PackageUpdateFailedError,
    remove_ungrouped_items,
    remove_package,
    update_packages,
)
from hawk_hooks.registry import Registry
from hawk_hooks.types import ComponentType


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


def test_update_packages_local_missing_path_raises(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)
    missing_path = tmp_path / "does-not-exist"
    config.save_packages({
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
    monkeypatch.setattr("hawk_hooks.sync.sync_all", lambda force=False: {})

    registry = Registry(config.get_registry_path())
    registry.ensure_dirs()

    source = tmp_path / "src" / "tdd"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("# TDD")
    registry.add(ComponentType.SKILL, "tdd", source)

    cfg = config.load_global_config()
    cfg["global"]["skills"] = ["tdd"]
    config.save_global_config(cfg)

    project = tmp_path / "project"
    project.mkdir()
    config.save_dir_config(project, {"skills": {"enabled": ["tdd"], "disabled": []}})
    config.register_directory(project)

    config.save_packages({
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
    assert "starter" not in config.load_packages()
    assert config.load_global_config()["global"]["skills"] == []
    assert config.load_dir_config(project)["skills"]["enabled"] == []
    assert registry.get_path(ComponentType.SKILL, "tdd") is None


def test_remove_ungrouped_items_removes_only_unowned(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("hawk_hooks.sync.sync_all", lambda force=False: {})

    registry = Registry(config.get_registry_path())
    registry.ensure_dirs()

    skill_owned_src = tmp_path / "src" / "owned"
    skill_owned_src.mkdir(parents=True)
    (skill_owned_src / "SKILL.md").write_text("# Owned")
    registry.add(ComponentType.SKILL, "owned-skill", skill_owned_src)

    skill_loose_src = tmp_path / "src" / "loose"
    skill_loose_src.mkdir(parents=True)
    (skill_loose_src / "SKILL.md").write_text("# Loose")
    registry.add(ComponentType.SKILL, "loose-skill", skill_loose_src)

    hook_loose_src = tmp_path / "src" / "guard.sh"
    hook_loose_src.parent.mkdir(parents=True, exist_ok=True)
    hook_loose_src.write_text("#!/usr/bin/env bash\necho ok\n")
    registry.add(ComponentType.HOOK, "guard.sh", hook_loose_src)

    cfg = config.load_global_config()
    cfg["global"]["skills"] = ["owned-skill", "loose-skill"]
    cfg["global"]["hooks"] = ["guard.sh"]
    config.save_global_config(cfg)

    project = tmp_path / "project"
    project.mkdir()
    config.save_dir_config(
        project,
        {
            "skills": {"enabled": ["loose-skill"], "disabled": []},
            "hooks": {"enabled": ["guard.sh"], "disabled": []},
        },
    )
    config.register_directory(project)

    config.save_packages({
        "starter": {
            "url": "",
            "path": str(tmp_path / "starter"),
            "installed": "2026-02-23",
            "commit": "",
            "items": [{"type": "skill", "name": "owned-skill", "hash": "abc123"}],
        }
    })

    report = remove_ungrouped_items(sync_after=True, log=lambda _msg: None)

    assert report.removed_items == 2
    assert report.removed_by_type == {"skill": 1, "hook": 1}
    assert registry.get_path(ComponentType.SKILL, "owned-skill") is not None
    assert registry.get_path(ComponentType.SKILL, "loose-skill") is None
    assert registry.get_path(ComponentType.HOOK, "guard.sh") is None
    assert config.load_global_config()["global"]["skills"] == ["owned-skill"]
    assert config.load_global_config()["global"]["hooks"] == []
    assert config.load_dir_config(project)["skills"]["enabled"] == []
    assert config.load_dir_config(project)["hooks"]["enabled"] == []


def test_update_packages_prune_only_removal_triggers_sync(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)

    registry = Registry(config.get_registry_path())
    registry.ensure_dirs()

    local_source = tmp_path / "local-pkg"
    local_source.mkdir()

    src_tdd = tmp_path / "src" / "tdd"
    src_tdd.mkdir(parents=True)
    (src_tdd / "SKILL.md").write_text("# TDD")
    registry.add(ComponentType.SKILL, "tdd", src_tdd)

    src_old = tmp_path / "src" / "old"
    src_old.mkdir(parents=True)
    (src_old / "SKILL.md").write_text("# Old")
    registry.add(ComponentType.SKILL, "old", src_old)

    config.save_packages({
        "local-pkg": {
            "url": "",
            "path": str(local_source),
            "installed": "2026-02-23",
            "commit": "",
            "items": [
                {"type": "skill", "name": "tdd", "hash": "same"},
                {"type": "skill", "name": "old", "hash": "oldhash"},
            ],
        }
    })

    monkeypatch.setattr(
        "hawk_hooks.package_service.scan_directory",
        lambda _path: ClassifiedContent(
            items=[
                ClassifiedItem(
                    component_type=ComponentType.SKILL,
                    name="tdd",
                    source_path=src_tdd,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        "hawk_hooks.config.hash_registry_item",
        lambda _path: "same",
    )

    sync_calls: list[bool] = []
    monkeypatch.setattr(
        "hawk_hooks.sync.sync_all",
        lambda force=False: sync_calls.append(force) or {},
    )

    report = update_packages(prune=True, sync_on_change=True, log=lambda _msg: None)

    assert report.any_changes is True
    assert sync_calls == [True]
    assert registry.get_path(ComponentType.SKILL, "old") is None


def test_update_packages_skips_malformed_package_item(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)

    local_source = tmp_path / "local-pkg"
    local_source.mkdir()
    src_tdd = tmp_path / "src" / "tdd"
    src_tdd.mkdir(parents=True)
    (src_tdd / "SKILL.md").write_text("# TDD")

    config.save_packages({
        "local-pkg": {
            "url": "",
            "path": str(local_source),
            "installed": "2026-02-24",
            "commit": "",
            "items": [{"name": "missing-type", "hash": "deadbeef"}],
        }
    })

    monkeypatch.setattr(
        "hawk_hooks.package_service.scan_directory",
        lambda _path: ClassifiedContent(
            items=[
                ClassifiedItem(
                    component_type=ComponentType.SKILL,
                    name="tdd",
                    source_path=src_tdd,
                )
            ]
        ),
    )
    monkeypatch.setattr("hawk_hooks.config.hash_registry_item", lambda _path: "hash1234")

    lines: list[str] = []
    report = update_packages(check=True, log=lines.append)

    assert report.any_changes is True
    assert any("malformed package item" in line for line in lines)
