---
name: post-work-review
description: Run parallel codex + gemini subagents to review recent code changes with context-aware criteria
tools: [claude, codex, gemini]
---

# Post-Work Review

Run dual AI reviewers (codex + gemini) in parallel to audit recent code changes, adapting criteria to the project's nature and spirit.

## Goal

Catch issues before they solidify - code smell, coupling, magic values, and deviations from the project's design philosophy.

## Process

### Step 1: Determine Scope

Identify what to review:

```bash
# Recent uncommitted changes
git diff --name-only HEAD

# Or recent commits (if already committed)
git diff --name-only HEAD~3..HEAD
```

Ask user if scope is unclear:
1. **Uncommitted changes** - What I just worked on
2. **Last N commits** - Recent committed work
3. **Specific files** - User specifies

### Step 2: Analyze Project Context

Before reviewing, understand the project to adapt criteria:

```bash
# Check for plugin system
find . -type d -name "plugin*" -o -name "backend*" -o -name "extension*" 2>/dev/null | head -5
grep -r "register.*plugin\|load.*plugin\|Plugin" --include="*.py" --include="*.ts" -l 2>/dev/null | head -3

# Check if CLI tool (startup time matters)
grep -l "typer\|click\|argparse\|commander\|yargs" *.toml package.json pyproject.toml 2>/dev/null

# Check for lazy loading patterns
grep -r "import.*inside\|lazy\|deferred" --include="*.py" --include="*.ts" -l 2>/dev/null | head -3

# Read project description
head -50 README.md 2>/dev/null || head -20 pyproject.toml 2>/dev/null
```

Build a mental model:
- **Project type**: CLI tool, web app, library, service?
- **Has plugin system?**: Backends, extensions, plugins directory?
- **Performance-sensitive?**: CLI startup, hot paths, lazy loading needed?
- **Core philosophy**: What makes this project "this project"?

### Step 3: Launch Parallel Reviews

Use the `/codex` and `/gemini` skills to spawn parallel subagents. Invoke both simultaneously using the Skill tool.

Build the review prompt with the gathered context:

```
Review these recent code changes for quality issues.

FILES CHANGED:
<list files from Step 1>

PROJECT CONTEXT:
<summary from Step 2>

ALWAYS CHECK:
- Code smell (long functions, deep nesting, god objects)
- DRY violations (copy-paste, repeated patterns)
- Magic values (hardcoded strings/numbers that should be constants)
- Unclear naming or misleading abstractions
- Tight coupling between modules

CONTEXT-SPECIFIC (if applicable):
- Plugin modularity: Can plugins be removed without breaking core? Are plugin interfaces clean?
- Lazy loading: Are heavy imports deferred for CLI startup performance?
- Spirit alignment: Do changes fit the project's design philosophy?

Output a structured report with:
1. Issues found (severity: high/medium/low)
2. Whether changes align with project spirit
3. Specific recommendations
```

**Invoke both in parallel:**

Use the Skill tool twice in a single response:
- `/codex` with args: `-m gpt-5.3-codex -s read-only "<review prompt>"`
- `/gemini` with args: `-m gemini-3-flash-preview -s read-only "<review prompt>"`

**Fallback if skills unavailable:**

If `/codex` or `/gemini` skills are not available, fall back to direct CLI:
```bash
codex exec -m gpt-5.3-codex -s read-only "<review prompt>"
gemini exec -m gemini-3-flash-preview -s read-only "<review prompt>"
```

### Step 4: Synthesize Results

Combine findings from both reviewers:

```markdown
## Post-Work Review Summary

**Scope**: [files reviewed]
**Project Context**: [CLI tool with plugin system / web service / etc.]

### Consensus Issues (both reviewers flagged)
[These are high-confidence problems]

### Codex-Only Findings
[Review for validity]

### Gemini-Only Findings
[Review for validity]

### Spirit Check
[Do changes align with project philosophy?]

### Recommended Actions
1. [Prioritized list]
```

### Step 5: Offer Next Steps

Ask user:
1. **Fix issues now** - Address findings before committing/merging
2. **Create TODO** - Track for later
3. **Acknowledge and proceed** - Findings noted, moving on

## Adaptive Criteria Reference

| Project Signal | Add This Criterion |
|----------------|-------------------|
| `typer`, `click`, `argparse` in deps | Check lazy loading, startup performance |
| `plugins/`, `backends/`, `extensions/` dir | Check plugin modularity, interface cleanliness |
| Heavy deps (AI libs, DB clients) | Check deferred imports |
| Config files, `.env` patterns | Check for hardcoded values that should be config |
| Protocol/ABC classes | Check interface consistency |

## Spirit Alignment Examples

**CLI tool spirit**: Fast startup, composable commands, Unix philosophy
**Library spirit**: Clean API, minimal dependencies, good defaults
**Plugin system spirit**: Core doesn't know about specific plugins, clean interfaces
**Web app spirit**: Request isolation, proper error handling, security

The reviewers should flag changes that fight against these principles.
