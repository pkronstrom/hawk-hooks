"""Tests for shared scope/profile chain resolution helpers."""

from __future__ import annotations

from pathlib import Path

from hawk_hooks import v2_config
from hawk_hooks.scope_resolution import (
    build_config_layers_with_profiles,
    build_resolver_dir_chain,
    resolve_profile_name_for_dir,
)


def _patch_config_paths(monkeypatch, tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
    monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
    monkeypatch.setattr(v2_config, "get_profiles_dir", lambda: config_dir / "profiles")
    return config_dir


def test_resolve_profile_name_prefers_dir_config(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()

    cfg = v2_config.load_global_config()
    cfg["directories"][str(project.resolve())] = {"profile": "from-index"}
    v2_config.save_global_config(cfg)

    name = resolve_profile_name_for_dir({"profile": "from-dir"}, project, cfg)
    assert name == "from-dir"


def test_build_layers_orders_parent_then_child(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)

    root = tmp_path / "mono"
    child = root / "apps" / "api"
    child.mkdir(parents=True)

    v2_config.save_dir_config(root, {"skills": {"enabled": ["tdd"], "disabled": []}})
    v2_config.save_dir_config(child, {"skills": {"enabled": ["api"], "disabled": []}})
    v2_config.register_directory(root)
    v2_config.register_directory(child)

    layers = build_config_layers_with_profiles(child)
    assert [d for d, _cfg, _profile in layers] == [root.resolve(), child.resolve()]


def test_build_layers_uses_directory_index_profile_fallback(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)

    project = tmp_path / "project"
    project.mkdir()
    v2_config.save_profile("web", {"name": "web", "skills": ["tdd"]})
    v2_config.save_dir_config(project, {"skills": {"enabled": ["tdd"], "disabled": []}})
    v2_config.register_directory(project, profile="web")

    layers = build_config_layers_with_profiles(project)
    assert len(layers) == 1
    layer_dir, _cfg, profile = layers[0]
    assert layer_dir == project.resolve()
    assert profile == {"name": "web", "skills": ["tdd"]}


def test_build_layers_falls_back_to_unregistered_local_config(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)

    project = tmp_path / "local-only"
    project.mkdir()
    v2_config.save_profile("local-prof", {"name": "local-prof", "hooks": ["guard.py"]})
    v2_config.save_dir_config(project, {"profile": "local-prof"})

    layers = build_config_layers_with_profiles(project)
    assert len(layers) == 1
    layer_dir, layer_cfg, profile = layers[0]
    assert layer_dir == project.resolve()
    assert layer_cfg.get("profile") == "local-prof"
    assert profile == {"name": "local-prof", "hooks": ["guard.py"]}


def test_build_resolver_dir_chain_returns_config_profile_pairs(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)

    project = tmp_path / "project"
    project.mkdir()
    v2_config.save_dir_config(project, {"skills": {"enabled": ["tdd"], "disabled": []}})

    chain = build_resolver_dir_chain(project)
    assert len(chain) == 1
    cfg, profile = chain[0]
    assert cfg["skills"]["enabled"] == ["tdd"]
    assert profile is None


def test_build_layers_keeps_empty_dir_config(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)

    project = tmp_path / "empty-config"
    project.mkdir()
    v2_config.save_dir_config(project, {})

    layers = build_config_layers_with_profiles(project)
    assert len(layers) == 1
    layer_dir, layer_cfg, profile = layers[0]
    assert layer_dir == project.resolve()
    assert layer_cfg == {}
    assert profile is None


def test_build_resolver_dir_chain_includes_unregistered_leaf_local_config(monkeypatch, tmp_path):
    _patch_config_paths(monkeypatch, tmp_path)

    root = tmp_path / "mono"
    child = root / "apps" / "web"
    child.mkdir(parents=True)

    v2_config.save_dir_config(root, {"skills": {"enabled": ["tdd"], "disabled": []}})
    v2_config.register_directory(root)
    v2_config.save_dir_config(child, {"skills": {"enabled": ["react"], "disabled": []}})

    chain = build_resolver_dir_chain(child)
    assert len(chain) == 2
    assert chain[0][0]["skills"]["enabled"] == ["tdd"]
    assert chain[1][0]["skills"]["enabled"] == ["react"]
