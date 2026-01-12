---
name: write-agents-md
description: Analyze this codebase and create/update AI assistant instruction files
tools: [claude, gemini, codex]
---

Analyze this codebase and create/update AI assistant instruction files.

## Detection Phase

1. Check for existing instruction files:
   - Claude: `CLAUDE.md`, `.claude/CLAUDE.md`
   - Cursor: `.cursorrules`, `.cursor/rules/*.md`
   - Copilot: `.github/copilot-instructions.md`
   - Windsurf: `.windsurfrules`
   - Generic: `AGENTS.md`

2. If found: ask user whether to update existing or create additional format
3. If none: ask which format(s) to create (default to tool-native format)

## Analysis Phase

Examine codebase for:
- **Stack**: Languages, frameworks, key dependencies
- **Structure**: Monorepo? Key directories? Entry points?
- **Commands**: Build/test/lint (package.json, Makefile, Cargo.toml, etc.)
- **Conventions**: Naming patterns, architecture style, existing standards
- **Gotchas**: Non-obvious behaviors (check README, CONTRIBUTING, docs/)

## Writing Guidelines (Critical)

### The Cardinal Rule: BREVITY

**Shorter is always better.** Every line competes for the agent's attention.

- **Under 100 lines ideal**, absolute max 300
- Only include what agents NEED to do work correctly
- Reference external docs, don't duplicate them
- If something is "nice to know" but not essential, cut it

### Structure: WHAT / WHY / HOW
- **WHAT**: Tech stack, project structure, key files
- **WHY**: Project purpose (1-2 sentences max)
- **HOW**: Essential commands, verification steps

### Constraints
- **Universal only** - no task-specific content
- **Specific > vague** - "Use 2-space indentation" not "format code properly"
- **Pointers > copies** - `src/auth/middleware.ts:45` not code blocks that go stale
- **Reference, don't embed** - "See docs/architecture.md" not inline explanations

### Anti-patterns (Avoid)
- Style rules (use linters, not LLM instructions)
- Database schemas or implementation details
- Auto-generated fluff - manually craft every line
- Code snippets that will go stale
- Anything Claude/Cursor/etc already knows

### Good Example
```markdown
## Stack
TypeScript, Next.js 14 (app router), Prisma, PostgreSQL

## Commands
- `pnpm dev` - Start dev server
- `pnpm test` - Run vitest
- `pnpm db:migrate` - Run migrations

## Key Files
- `src/lib/auth.ts` - Auth utilities, session handling
- `src/app/api/` - API routes (app router convention)

## Conventions
- Use server actions for mutations, not API routes
- Colocate components with their routes in app/
```

## When Updating Existing Files

**Resist the urge to expand.** When updating:

1. **Surgical updates only** - Change what's wrong or outdated, nothing else
2. **Don't "improve" by adding** - More content is rarely an improvement
3. **Ask: "Will the agent fail without this?"** - If no, don't add it
4. **Trim while you're there** - If you see bloat, cut it

The goal is maintenance, not enhancement. A good update often makes the file shorter.
