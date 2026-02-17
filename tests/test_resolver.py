"""Tests for the resolver module."""

from hawk_hooks.resolver import resolve
from hawk_hooks.types import Tool


class TestResolveGlobalOnly:
    def test_basic(self):
        cfg = {
            "global": {
                "skills": ["tdd"],
                "hooks": ["block-secrets"],
                "commands": [],
                "agents": [],
                "mcp": ["github"],
            }
        }
        result = resolve(cfg)
        assert result.skills == ["tdd"]
        assert result.hooks == ["block-secrets"]
        assert result.mcp == ["github"]
        assert result.commands == []

    def test_empty_global(self):
        result = resolve({})
        assert result.skills == []
        assert result.hooks == []


class TestResolveWithProfile:
    def test_profile_adds(self):
        cfg = {"global": {"skills": ["tdd"], "hooks": [], "commands": [], "agents": [], "mcp": []}}
        profile = {"skills": ["react-patterns"], "hooks": ["lint-on-save"]}

        result = resolve(cfg, profile=profile)
        assert result.skills == ["tdd", "react-patterns"]
        assert result.hooks == ["lint-on-save"]

    def test_profile_deduplicates(self):
        cfg = {"global": {"skills": ["tdd"], "hooks": [], "commands": [], "agents": [], "mcp": []}}
        profile = {"skills": ["tdd", "react"]}

        result = resolve(cfg, profile=profile)
        assert result.skills == ["tdd", "react"]


class TestResolveWithDirConfig:
    def test_dir_enables(self):
        cfg = {"global": {"skills": ["tdd"], "hooks": [], "commands": [], "agents": [], "mcp": []}}
        dir_cfg = {"skills": {"enabled": ["local-skill"], "disabled": []}}

        result = resolve(cfg, dir_config=dir_cfg)
        assert result.skills == ["tdd", "local-skill"]

    def test_dir_disables(self):
        cfg = {
            "global": {
                "skills": ["tdd", "old-skill"],
                "hooks": [],
                "commands": [],
                "agents": [],
                "mcp": [],
            }
        }
        dir_cfg = {"skills": {"enabled": [], "disabled": ["old-skill"]}}

        result = resolve(cfg, dir_config=dir_cfg)
        assert result.skills == ["tdd"]
        assert "old-skill" not in result.skills

    def test_dir_simple_list_format(self):
        cfg = {"global": {"skills": [], "hooks": [], "commands": [], "agents": [], "mcp": []}}
        dir_cfg = {"skills": ["a", "b"]}

        result = resolve(cfg, dir_config=dir_cfg)
        assert result.skills == ["a", "b"]


class TestResolveWithToolOverrides:
    def test_per_tool_extra(self):
        cfg = {"global": {"skills": ["tdd"], "hooks": [], "commands": [], "agents": [], "mcp": []}}
        dir_cfg = {
            "tools": {
                "claude": {
                    "skills": {"extra": ["claude-only"]},
                }
            }
        }

        result = resolve(cfg, dir_config=dir_cfg, tool=Tool.CLAUDE)
        assert "claude-only" in result.skills
        assert "tdd" in result.skills

    def test_per_tool_exclude(self):
        cfg = {
            "global": {
                "skills": ["tdd", "generic"],
                "hooks": [],
                "commands": [],
                "agents": [],
                "mcp": [],
            }
        }
        dir_cfg = {
            "tools": {
                "gemini": {
                    "skills": {"exclude": ["generic"]},
                }
            }
        }

        result = resolve(cfg, dir_config=dir_cfg, tool=Tool.GEMINI)
        assert result.skills == ["tdd"]

    def test_tool_override_ignored_without_tool(self):
        cfg = {"global": {"skills": ["tdd"], "hooks": [], "commands": [], "agents": [], "mcp": []}}
        dir_cfg = {
            "tools": {
                "claude": {"skills": {"extra": ["claude-only"]}},
            }
        }

        result = resolve(cfg, dir_config=dir_cfg)
        # No tool specified, so tool overrides should not apply
        assert "claude-only" not in result.skills


class TestResolveFullStack:
    def test_all_layers(self):
        cfg = {
            "global": {
                "skills": ["tdd"],
                "hooks": ["block-secrets"],
                "commands": ["deploy"],
                "agents": [],
                "mcp": ["github"],
            }
        }
        profile = {
            "skills": ["react-patterns", "typescript"],
            "hooks": ["lint"],
            "mcp": ["postgres"],
        }
        dir_cfg = {
            "skills": {"enabled": ["local"], "disabled": ["typescript"]},
            "hooks": {"enabled": [], "disabled": ["lint"]},
            "tools": {
                "claude": {
                    "skills": {"extra": ["claude-special"]},
                }
            },
        }

        result = resolve(cfg, profile=profile, dir_config=dir_cfg, tool=Tool.CLAUDE)
        assert result.skills == ["tdd", "react-patterns", "local", "claude-special"]
        assert "typescript" not in result.skills
        assert result.hooks == ["block-secrets"]
        assert "lint" not in result.hooks
        assert result.mcp == ["github", "postgres"]
        assert result.commands == ["deploy"]
