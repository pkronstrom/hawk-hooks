"""Parse Hawk skill metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SkillRequires:
    agents: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    mcp: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SkillMeta:
    requires: SkillRequires = field(default_factory=SkillRequires)
    warnings: list[str] = field(default_factory=list)


_KEY_ALIASES = {
    "agent": ("agents", True),
    "agents": ("agents", False),
    "hook": ("hooks", True),
    "hooks": ("hooks", False),
    "prompt": ("prompts", True),
    "prompts": ("prompts", False),
    "command": ("prompts", True),
    "commands": ("prompts", False),
    "mcp": ("mcp", True),
}


def parse_skill_meta(skill_path: Path) -> SkillMeta:
    """Parse metadata from a skill directory or SKILL.md file."""
    skill_file = skill_path / "SKILL.md" if skill_path.is_dir() else skill_path
    try:
        text = skill_file.read_text(errors="replace")
    except OSError:
        return SkillMeta()

    frontmatter = _extract_frontmatter(text)
    if frontmatter is None:
        return SkillMeta()

    try:
        data = yaml.safe_load(frontmatter)
    except yaml.YAMLError as exc:
        return SkillMeta(warnings=[f"invalid skill frontmatter: {exc}"])

    if not isinstance(data, dict):
        return SkillMeta()

    requires = data.get("requires", {})
    if requires in (None, ""):
        return SkillMeta()
    if not isinstance(requires, dict):
        return SkillMeta(warnings=["requires expected a mapping"])

    buckets: dict[str, list[str]] = {"agents": [], "hooks": [], "prompts": [], "mcp": []}
    warnings: list[str] = []

    for raw_key, raw_value in requires.items():
        key = str(raw_key)
        alias = _KEY_ALIASES.get(key)
        if alias is None:
            warnings.append(f"requires.{key} is unsupported")
            continue
        target, allow_scalar = alias

        values = _as_string_list(raw_value, allow_scalar=allow_scalar)
        if values is None:
            warnings.append(f"requires.{target} expected a list or string")
            continue

        for value in values:
            if value not in buckets[target]:
                buckets[target].append(value)
        for entry in _non_string_entries(raw_value):
            warnings.append(f"requires.{target} ignored non-string entry {entry!r}")

    return SkillMeta(
        requires=SkillRequires(
            agents=buckets["agents"],
            hooks=buckets["hooks"],
            prompts=buckets["prompts"],
            mcp=buckets["mcp"],
        ),
        warnings=warnings,
    )


def _extract_frontmatter(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    return text[3:end].strip()


def _as_string_list(value: Any, *, allow_scalar: bool) -> list[str] | None:
    if isinstance(value, str):
        return [value] if allow_scalar else None
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, str)]


def _non_string_entries(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [item for item in value if not isinstance(item, str)]
