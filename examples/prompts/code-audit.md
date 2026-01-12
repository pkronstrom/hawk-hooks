---
name: code-audit
description: Perform a comprehensive code audit to identify technical debt and quality issues
tools: [claude, gemini, codex]
---

Perform a comprehensive code audit to identify technical debt, code smells, and quality issues.

## Goal

Get the codebase to "not ashamed to show the code to professional developers" quality.

## Process

### Step 1: Determine Scope

Ask the user what to audit:

1. **Whole codebase** - Scan everything
2. **Specific directories/files** - User specifies paths
3. **Recent commits** - Files changed in last N commits
4. **Uncommitted changes** - Staged and unstaged changes
5. **Other** - User specifies custom scope

Also ask the user whether it would like to use `codex` and/or `gemini` skills with subagents
to do the analysis, or just run it here.

If yes, spawn the agent(s) with best thinking models available to perform the audit.

### Step 2: Analyze Code

Review the scoped code like a senior developer would, checking for:

**Dead Code**
- Unreachable code paths
- Unused functions, variables, imports
- Commented-out code blocks
- Orphaned files

**Code Smells**
- Long functions (doing too much)
- Deep nesting (arrow code)
- Magic numbers/strings
- God objects/files
- Primitive obsession

**DRY Violations**
- Copy-pasted logic
- Repeated patterns that should be abstracted
- Duplicated validation/error handling

**Coupling & Modularity**
- Tight coupling between modules
- Circular dependencies
- Leaky abstractions
- Poor separation of concerns

**Clarity & Maintainability**
- Unclear naming
- Missing/misleading abstractions
- Complex conditionals
- Inconsistent patterns

**Error Handling**
- Swallowed errors
- Missing error cases
- Inconsistent error patterns

### Step 3: Write Audit Document

Create `docs/plans/` directory if needed. Write findings to:
`docs/plans/YYYY-MM-DD-<project>-audit.md`

Use this format:

```markdown
# Code Audit: <Project Name>

**Date**: YYYY-MM-DD
**Scope**: [What was audited]
**Health Score**: [Good / Needs Work / Significant Issues]

## Executive Summary

[2-4 sentences: Overall state, biggest concerns, quick wins available]

## Findings by Category

### Dead Code
[Pattern-level findings - why it matters, what to do about it]

### Code Smells
[Pattern-level findings]

### DRY Violations
[Pattern-level findings]

### Coupling & Modularity
[Pattern-level findings]

### Clarity & Maintainability
[Pattern-level findings]

### Error Handling
[Pattern-level findings]

## Priority Matrix

| Category | Severity | Effort | Recommended Action |
|----------|----------|--------|-------------------|
| [Issue]  | High/Med/Low | Small/Medium/Large | [What to do] |

## Recommended Cleanup Plan

### Phase 1: Quick Wins (Low effort, high impact)
- [Items]

### Phase 2: Core Improvements
- [Items]

### Phase 3: Architectural Changes
- [Items]
```

### Step 4: Present Summary

After writing the document, summarize:

```
Audit complete. Found:
- X dead code areas
- X code smells
- X DRY violations
- X coupling issues
- X clarity problems
- X error handling gaps

Quick wins available: X items
Document written to: docs/plans/YYYY-MM-DD-<project>-audit.md
```

### Step 5: Offer Implementation Path

Ask the user:

**Ready to create an implementation plan?**
1. Yes, full cleanup (all phases)
2. Yes, quick wins only (Phase 1)
3. No, just the audit document for now

## Quality Standards

Think like a senior developer who:
- Values DRY (Don't Repeat Yourself)
- Creates readable, self-documenting code
- Builds easily extensible systems
- Maintains modular architecture
- Writes code they'd be proud to show others

## Important Notes

- Focus on patterns, not specific line numbers (those change)
- Explain WHY something is a problem, not just WHAT
- Prioritize actionable improvements over nitpicks
- Consider the effort/impact ratio when recommending fixes
