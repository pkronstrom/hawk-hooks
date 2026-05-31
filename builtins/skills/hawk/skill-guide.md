# Skill Guide

Skills are directory-based components that can include a main instruction file plus supporting reference files, templates, or guides. Use a skill instead of a command when the component needs multiple files.

## Format

- Directory named after the skill
- Must contain `SKILL.md` (the main instruction file)
- Can include any number of supporting files (guides, templates, examples, data)
- YAML frontmatter in `SKILL.md` with `name` and `description`
- Placed in `skills/` directory

## Structure

```
my-skill/
├── SKILL.md           # Main instructions (required)
├── guide-one.md       # Supporting reference
├── template.py        # Template file
└── examples/          # Subdirectories are fine
    └── example.md
```

## Frontmatter Fields (SKILL.md)

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Skill identifier |
| `description` | yes | One-line summary |

## When to Use a Skill vs a Command

| | Command | Skill |
|---|---------|-------|
| Files | Single `.md` | Directory with multiple files |
| Attachments | No | Yes — guides, templates, data |
| Use case | Simple slash-command prompt | Rich workflow with reference material |
| Invocation | `/command-name` | `/skill-name` or loaded as context |

## Tips

- SKILL.md should be the entry point — it can reference other files in the directory
- Use `Read` tool references in SKILL.md to point the agent at supporting files
- Keep SKILL.md concise — put detailed reference material in separate files
- Name supporting files descriptively so the agent knows what to read

## Template

### SKILL.md

```markdown
---
name: my-skill
description: Brief description of what this skill helps with
---

# My Skill

Overview of what this skill does.

## Workflow

1. [First step]
2. Read `detail-guide.md` from this skill directory for specifics
3. [Action step]
4. Present results to user
```

### Supporting File (detail-guide.md)

```markdown
# Detail Guide

Detailed reference material the agent reads when needed.

## Section One

[Content]

## Section Two

[Content]
```
