from pathlib import Path

from hawk_hooks.skill_meta import SkillRequires, parse_skill_meta


def test_parse_skill_requires_plural_component_keys(tmp_path: Path):
    skill = tmp_path / "bundle" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(
        "---\n"
        "name: bundle\n"
        "description: Bundle skill\n"
        "requires:\n"
        "  agents:\n"
        "    - observer.md\n"
        "  hooks:\n"
        "    - observe.sh\n"
        "  prompts:\n"
        "    - instinct-status.md\n"
        "  mcp:\n"
        "    - dodo.json\n"
        "---\n\n"
        "# Bundle\n"
    )

    meta = parse_skill_meta(skill.parent)

    assert meta.requires == SkillRequires(
        agents=["observer.md"],
        hooks=["observe.sh"],
        prompts=["instinct-status.md"],
        mcp=["dodo.json"],
    )


def test_parse_skill_requires_accepts_aliases_and_dedupes(tmp_path: Path):
    skill = tmp_path / "bundle" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(
        "---\n"
        "name: bundle\n"
        "description: Bundle skill\n"
        "requires:\n"
        "  agent: observer.md\n"
        "  hook: [observe.sh, observe.sh]\n"
        "  commands:\n"
        "    - instinct-status.md\n"
        "---\n\n"
        "# Bundle\n"
    )

    meta = parse_skill_meta(skill.parent)

    assert meta.requires.agents == ["observer.md"]
    assert meta.requires.hooks == ["observe.sh"]
    assert meta.requires.prompts == ["instinct-status.md"]


def test_parse_skill_requires_ignores_malformed_values(tmp_path: Path):
    skill = tmp_path / "bundle" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(
        "---\n"
        "name: bundle\n"
        "description: Bundle skill\n"
        "requires:\n"
        "  agents:\n"
        "    - observer.md\n"
        "    - 12\n"
        "  hooks: nope\n"
        "  skills:\n"
        "    - other-skill\n"
        "---\n\n"
        "# Bundle\n"
    )

    meta = parse_skill_meta(skill.parent)

    assert meta.requires.agents == ["observer.md"]
    assert meta.requires.hooks == []
    assert meta.warnings == [
        "requires.agents ignored non-string entry 12",
        "requires.hooks expected a list or string",
        "requires.skills is unsupported",
    ]
