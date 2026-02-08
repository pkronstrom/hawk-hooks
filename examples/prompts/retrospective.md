---
name: retrospective
description: Review recently implemented features and suggest significant improvements across code, UI, architecture, and testing
tools: [claude, gemini, codex]
---

# Retrospective

Review recent work with a senior engineer's critical eye. Find the issues and enhancement opportunities that turn 80% quality into 99%.

## Goal

Perform a ruthlessly honest multi-dimensional review of recently implemented features, producing a prioritized action plan of concrete improvements.

## Process

### Step 1: Determine Scope

Identify what to review:

**Default scope** — examine recent git changes:
```bash
# Uncommitted + last 3 commits
git diff --name-only HEAD~3..HEAD
git diff --name-only
git diff --name-only --cached
```

**If the user provides arguments** (files, feature name, PR number), use that instead.

Present the list of changed files and confirm scope with the user before proceeding.

### Step 2: Read & Understand

Read all files in scope. Before reviewing, build context:

- **What was built**: Feature type (UI component, API endpoint, CLI command, library, infrastructure, etc.)
- **Tech stack**: Languages, frameworks, libraries in use
- **Existing patterns**: How does the rest of the codebase do things? What conventions exist?
- **Intent**: What problem was this solving? (Check commit messages, PR description, nearby docs)

### Step 3: Multi-Dimensional Review

Review across all applicable dimensions. **Skip dimensions that don't apply** to the changes (e.g., skip UI/UX for backend-only changes).

Also ask the user whether they'd like to use `codex` and/or `gemini` skills with subagents to run parallel reviews, or just run it here.

If yes, spawn the agent(s) with best thinking models available. Use the Skill tool:
- `/codex` with args: `-m o3 -s read-only "<review prompt with files and context>"`
- `/gemini` with args: `-m gemini-2.5-pro -s read-only "<review prompt with files and context>"`

#### Code Quality & Architecture
- DRY violations — copy-pasted logic, repeated patterns that should be abstracted
- Coupling — modules that know too much about each other, leaky abstractions
- Naming — unclear, misleading, or inconsistent names
- Separation of concerns — functions/classes doing too much, mixed responsibilities
- Error handling — swallowed errors, missing error cases, inconsistent patterns
- Unnecessary complexity — over-engineering, premature abstractions, dead code paths

#### UX/UI Polish (if frontend changes)
- Spacing & layout — inconsistent padding/margins, misaligned elements
- Accessibility — missing ARIA labels, keyboard navigation gaps, color contrast (WCAG AA)
- Responsiveness — broken layouts on mobile/tablet, missing breakpoints
- Modern UX patterns — loading states, error states, empty states, transitions
- Visual consistency — does it match the existing design system and patterns?

#### Testing & Reliability
- Missing test coverage — untested happy paths, edge cases, error scenarios
- Unhandled edge cases — null/undefined, empty arrays, concurrent access, race conditions
- Error states — what happens when the network fails, the API returns 500, the file doesn't exist?
- What could break in production — timing issues, data migration gaps, backwards compatibility

#### Security & Performance
- Input validation gaps — unsanitized user input, missing type checks at boundaries
- Auth issues — missing authorization checks, privilege escalation paths
- N+1 queries — database calls in loops, missing eager loading
- Bundle size / lazy loading — large imports that could be deferred, unused dependencies
- Caching opportunities — repeated expensive computations, missing memoization

### Step 4: Report Findings

For each applicable dimension, report:

```markdown
### [Dimension Name]

**Issues Found:**
- [Severity: high/medium/low] `file:line` — Description of the issue
- ...

**Enhancement Opportunities:**
- [Impact: high/medium/low] Description — concrete, actionable suggestion
- ...
```

Rules for reporting:
- Be specific — always include `file:line` references
- Focus on **patterns**, not nitpicks — "all 5 API handlers swallow errors" beats "line 42 swallows an error"
- Explain **why** it matters, not just what's wrong
- Every issue must have a concrete fix, not just a complaint

### Step 5: Prioritized Action Plan

Synthesize all findings into a ranked list:

```markdown
## Top Improvements (by impact/effort ratio)

| # | Issue | Severity | Effort | Files |
|---|-------|----------|--------|-------|
| 1 | [Description] | high | small | `file1.ts`, `file2.ts` |
| 2 | [Description] | high | medium | `file3.ts` |
| 3 | [Description] | medium | small | `file4.ts` |
| 4 | [Description] | medium | medium | `file5.ts`, `file6.ts` |
| 5 | [Description] | low | small | `file7.ts` |
```

Then ask the user:

1. **Implement all** — Work through improvements in order
2. **Pick and choose** — Let me select which ones to implement
3. **Just the report** — I'll handle it from here

## Persona

Adopt the mindset of a **senior engineer + product designer** doing a thorough code review:

- Be ruthlessly honest — the value is in catching real issues, not validating work
- Praise what's genuinely good, but don't sugarcoat problems
- Think about the user who will interact with the UI, the developer who will maintain the code, and the ops person who will debug it at 2am
- Consider what would embarrass you if a respected colleague saw it
- Patterns matter more than individual lines — systemic issues over one-off mistakes
