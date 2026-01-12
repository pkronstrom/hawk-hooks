---
name: handoff-for-clear-context
description: Write a context handoff document for session continuation after context clear
tools: [claude, gemini, codex]
---

Write a context handoff document for session continuation after context clear.

## Purpose

Capture minimum viable context that took cycles to discover, enabling a fresh agent to resume without re-learning. The handoff should be dense but not bloated.

## What to Capture (High Value)

These are things that cost time to figure out:

- **Goal**: 1-2 sentences - the "why" of this session
- **State**: What's done, in progress, next, blocked
- **Key Discoveries**: Non-obvious learnings:
  - Architecture quirks, gotchas
  - Which file *actually* handles X (vs the obvious guess)
  - Failed approaches and why they failed
  - Critical dependencies or relationships
  - Environment/config issues encountered
- **Decision Rationale**: Why approach A over B (so fresh agent doesn't retry B)

## What to Skip (Quick to Rediscover)

Don't waste handoff space on:

- File contents (agent can re-read)
- Obvious project structure
- Standard patterns/conventions
- Conversation back-and-forth
- Things easily found with grep/glob

## Output

Create `.claude/handoffs/` directory if needed, then write to:
`.claude/handoffs/YYYY-MM-DD-HHMM-<topic-slug>.md`

Use this format:

```markdown
# Handoff: <Topic>

## Goal
[1-2 sentences - what we're trying to achieve]

## State
- Done: [completed items]
- Active: [current work]
- Next: [immediate next steps]
- Blocked: [if any, with reason]

## Key Discoveries
[Bullet points of non-obvious learnings that cost time to figure out]

## Critical Files
[3-5 most important files with brief context on why]

## Decisions Made
[Key choices and rationale, so fresh agent doesn't retry rejected approaches]

---

## Resume Prompt

Copy this to start a new session:

\`\`\`
[Ready-to-paste prompt that orients fresh agent and continues work]
\`\`\`
```

After writing the file, output the Resume Prompt section to stdout for easy copying.

## Quality Check

Before finalizing, verify:
- Is everything here hard-won knowledge? (not easily rediscovered)
- Would a fresh agent save significant time with this?
- Is the resume prompt specific enough to hit the ground running?
