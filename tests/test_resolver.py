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


class TestResolveWithDirChain:
    """Tests for hierarchical dir_chain resolution."""

    def test_single_layer_chain(self):
        cfg = {"global": {"skills": ["tdd"], "hooks": [], "commands": [], "agents": [], "mcp": []}}
        dir_chain = [
            ({"skills": {"enabled": ["react"], "disabled": []}}, None),
        ]
        result = resolve(cfg, dir_chain=dir_chain)
        assert result.skills == ["tdd", "react"]

    def test_multi_layer_chain_outermost_first(self):
        cfg = {"global": {"skills": ["tdd"], "hooks": [], "commands": [], "agents": [], "mcp": []}}
        dir_chain = [
            # Outermost: monorepo root
            ({"skills": {"enabled": ["typescript"], "disabled": []}}, None),
            # Innermost: packages/frontend
            ({"skills": {"enabled": ["react"], "disabled": ["typescript"]}}, None),
        ]
        result = resolve(cfg, dir_chain=dir_chain)
        assert result.skills == ["tdd", "react"]
        assert "typescript" not in result.skills

    def test_chain_with_profiles(self):
        cfg = {"global": {"skills": ["tdd"], "hooks": [], "commands": [], "agents": [], "mcp": []}}
        profile_root = {"skills": ["shared-lint"], "hooks": ["format"]}
        profile_child = {"skills": ["react-patterns"]}
        dir_chain = [
            ({"skills": {"enabled": [], "disabled": []}}, profile_root),
            ({"skills": {"enabled": ["local"], "disabled": []}}, profile_child),
        ]
        result = resolve(cfg, dir_chain=dir_chain)
        assert result.skills == ["tdd", "shared-lint", "react-patterns", "local"]
        assert result.hooks == ["format"]

    def test_chain_with_tool_overrides(self):
        cfg = {"global": {"skills": ["tdd"], "hooks": [], "commands": [], "agents": [], "mcp": []}}
        dir_chain = [
            (
                {
                    "skills": {"enabled": ["mono-skill"], "disabled": []},
                    "tools": {"claude": {"skills": {"extra": ["claude-root"]}}},
                },
                None,
            ),
            (
                {
                    "skills": {"enabled": ["child-skill"], "disabled": []},
                    "tools": {"claude": {"skills": {"exclude": ["mono-skill"]}}},
                },
                None,
            ),
        ]
        result = resolve(cfg, dir_chain=dir_chain, tool=Tool.CLAUDE)
        assert "tdd" in result.skills
        assert "claude-root" in result.skills
        assert "child-skill" in result.skills
        assert "mono-skill" not in result.skills

    def test_dir_chain_overrides_dir_config_param(self):
        """When dir_chain is provided, dir_config and profile params are ignored."""
        cfg = {"global": {"skills": ["tdd"], "hooks": [], "commands": [], "agents": [], "mcp": []}}
        profile = {"skills": ["ignored-profile-skill"]}
        dir_config = {"skills": {"enabled": ["ignored-dir-skill"], "disabled": []}}
        dir_chain = [
            ({"skills": {"enabled": ["chain-skill"], "disabled": []}}, None),
        ]
        result = resolve(cfg, profile=profile, dir_config=dir_config, dir_chain=dir_chain)
        assert "chain-skill" in result.skills
        assert "ignored-profile-skill" not in result.skills
        assert "ignored-dir-skill" not in result.skills

    def test_empty_chain_equals_global_only(self):
        cfg = {"global": {"skills": ["tdd"], "hooks": ["h"], "commands": [], "agents": [], "mcp": []}}
        result_chain = resolve(cfg, dir_chain=[])
        result_plain = resolve(cfg)
        assert result_chain.skills == result_plain.skills
        assert result_chain.hooks == result_plain.hooks

    def test_backward_compat_unchanged(self):
        """Existing single dir_config + profile usage still works."""
        cfg = {"global": {"skills": ["tdd"], "hooks": [], "commands": [], "agents": [], "mcp": []}}
        profile = {"skills": ["react"]}
        dir_config = {"skills": {"enabled": ["local"], "disabled": ["react"]}}
        result = resolve(cfg, profile=profile, dir_config=dir_config)
        assert result.skills == ["tdd", "local"]


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
