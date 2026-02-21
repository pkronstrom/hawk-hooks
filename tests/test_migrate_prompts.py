"""Tests for commands->prompts one-shot migration."""

from __future__ import annotations

from pathlib import Path

import yaml

from hawk_hooks import migrate_prompts, v2_config


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, sort_keys=False))


def test_check_reports_changes(tmp_path, monkeypatch):
    config_dir = tmp_path / "hawk-hooks"
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

    cfg = v2_config.load_global_config()
    cfg["global"]["commands"] = ["deploy.md"]
    v2_config.save_global_config(cfg)

    needs, summary = migrate_prompts.run_migrate_prompts(check_only=True, backup=False)

    assert needs is True
    assert "global.commands" in summary


def test_apply_rewrites_config_fields(tmp_path, monkeypatch):
    config_dir = tmp_path / "hawk-hooks"
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

    project = tmp_path / "proj"
    project.mkdir()

    cfg = v2_config.load_global_config()
    cfg["global"]["commands"] = ["a.md", "b.md"]
    cfg["global"]["prompts"] = ["b.md", "c.md"]
    cfg["directories"] = {str(project.resolve()): {}}
    cfg["tools"]["claude"]["commands"] = {"extra": ["x.md"], "exclude": ["y.md"]}
    v2_config.save_global_config(cfg)

    v2_config.save_dir_config(project, {
        "commands": {"enabled": ["local-a.md"], "disabled": ["local-b.md"]},
        "prompts": {"enabled": ["local-c.md"], "disabled": []},
    })

    changed, _ = migrate_prompts.run_migrate_prompts(check_only=False, backup=False)
    assert changed is True

    new_cfg = v2_config.load_global_config()
    assert new_cfg["global"]["prompts"] == ["b.md", "c.md", "a.md"]
    assert "commands" not in new_cfg["global"]
    assert new_cfg["tools"]["claude"]["prompts"] == {"extra": ["x.md"], "exclude": ["y.md"]}
    assert "commands" not in new_cfg["tools"]["claude"]

    dir_cfg = v2_config.load_dir_config(project)
    assert dir_cfg["prompts"]["enabled"] == ["local-c.md", "local-a.md"]
    assert dir_cfg["prompts"]["disabled"] == ["local-b.md"]
    assert "commands" not in dir_cfg


def test_apply_moves_registry_and_rewrites_packages(tmp_path, monkeypatch):
    config_dir = tmp_path / "hawk-hooks"
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

    cfg = v2_config.load_global_config()
    registry_path = config_dir / "registry"
    cfg["registry_path"] = str(registry_path)
    v2_config.save_global_config(cfg)

    commands_dir = registry_path / "commands"
    prompts_dir = registry_path / "prompts"
    commands_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / "deploy.md").write_text("# Deploy")

    v2_config.save_packages({
        "pkg": {
            "url": "https://example.com/repo.git",
            "commit": "abc123",
            "installed": "2026-02-21",
            "items": [
                {"type": "command", "name": "deploy.md", "hash": "11111111"},
                {"type": "agent", "name": "review.md", "hash": "22222222"},
            ],
        }
    })

    changed, _ = migrate_prompts.run_migrate_prompts(check_only=False, backup=False)
    assert changed is True

    assert not (commands_dir / "deploy.md").exists()
    assert (prompts_dir / "deploy.md").exists()

    packages = v2_config.load_packages()
    assert packages["pkg"]["items"][0]["type"] == "prompt"
    assert packages["pkg"]["items"][1]["type"] == "agent"


def test_registry_collision_keeps_existing_prompt_file(tmp_path, monkeypatch):
    config_dir = tmp_path / "hawk-hooks"
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

    cfg = v2_config.load_global_config()
    registry_path = config_dir / "registry"
    cfg["registry_path"] = str(registry_path)
    v2_config.save_global_config(cfg)

    commands_dir = registry_path / "commands"
    prompts_dir = registry_path / "prompts"
    commands_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    (commands_dir / "same.md").write_text("from-commands")
    (prompts_dir / "same.md").write_text("from-prompts")

    changed, summary = migrate_prompts.run_migrate_prompts(check_only=False, backup=False)
    assert changed is True

    assert not (commands_dir / "same.md").exists()
    assert (prompts_dir / "same.md").read_text() == "from-prompts"
    assert "collision" in summary


def test_apply_is_idempotent(tmp_path, monkeypatch):
    config_dir = tmp_path / "hawk-hooks"
    monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)

    cfg = v2_config.load_global_config()
    cfg["global"]["commands"] = ["x.md"]
    v2_config.save_global_config(cfg)

    changed1, _ = migrate_prompts.run_migrate_prompts(check_only=False, backup=False)
    changed2, summary2 = migrate_prompts.run_migrate_prompts(check_only=False, backup=False)

    assert changed1 is True
    assert changed2 is False
    assert "No changes" in summary2
