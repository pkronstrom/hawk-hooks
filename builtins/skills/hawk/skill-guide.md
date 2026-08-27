# Skill Guide

Skills are directory-based components that can include a main instruction file plus supporting reference files, templates, or guides. Use a skill instead of a command when the component needs multiple files.

## Format

- Directory named after the skill
- Must contain `SKILL.md` (the main instruction file)
- Can include any number of supporting files (guides, templates, examples, data)
- Can bundle companion `agents/`, `hooks/`, `prompts/`, `commands/`, or `mcp/` directories
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

## Skill Bundles

A skill bundle is a skill directory that ships companion hawk components next to `SKILL.md`. Use this when the skill's workflow depends on a subagent, hook, prompt, or MCP server.

```
continuous-learning/
├── SKILL.md
├── agents/
│   └── observer.md
├── hooks/
│   └── capture.sh
├── prompts/
│   └── summarize.md
└── scripts/
    └── helper.py      # Resource only; not imported as a hook
```

When scanned or downloaded, hawk imports the skill plus components in these typed directories:

| Directory | Imported as |
|-----------|-------------|
| `agents/` | Agents |
| `hooks/` | Hooks |
| `prompts/` | Prompts |
| `commands/` | Prompts |
| `mcp/` | MCP servers |

Other directories stay private to the skill as supporting resources.

## Frontmatter Fields (SKILL.md)

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Skill identifier |
| `description` | yes | One-line summary |
| `requires` | no | Companion components to enable whenever the skill is enabled |

`requires` accepts singular keys (`agent`, `hook`, `prompt`, `command`, `mcp`) and plural keys (`agents`, `hooks`, `prompts`, `commands`). `commands` are resolved as prompts.

```yaml
---
name: continuous-learning
description: Capture learnings and summarize them across sessions
requires:
  agents:
    - observer.md
  hooks:
    - capture.sh
  prompts:
    - summarize.md
---
```

## When to Use a Skill vs a Command

| | Command | Skill |
|---|---------|-------|
| Files | Single `.md` | Directory with multiple files |
| Attachments | No | Yes — guides, templates, data |
| Use case | Simple slash-command prompt | Rich workflow with reference material |
| Invocation | Tool slash command where supported | Tool skill syntax, for example `$skill-name` in Codex |

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
