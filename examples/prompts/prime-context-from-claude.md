---
name: prime-context-from-claude
description: Prime the current session with context from a previous Claude session
tools: [claude]
---

Prime the current session with context from a previous Claude session.

## Purpose

Load knowledge from earlier sessions to avoid re-discovering hard-won learnings. Useful when resuming work, switching contexts, or building on previous discoveries.

## Tools

Use `rg` (ripgrep), `fd` (fd-find), and `jq` for fast searching through Claude's data structures.

## Claude Data Location

Context is stored in `~/.claude/`:
- `history.jsonl` - Global prompt index with project paths, timestamps, sessionIds
- `projects/<encoded-path>/*.jsonl` - Full session transcripts
- `plans/*.md` - Saved plan documents

Project paths are encoded with dashes (e.g., `/Users/foo/bar` -> `-Users-foo-bar`).

## Process

### Step 1: Ask What to Find

Ask the user what context they want to load:
- **Project name**: e.g., "captain-hook", "my-api"
- **Keywords**: e.g., "docker networking", "auth implementation"
- **Recent activity**: e.g., "last session", "yesterday", "this morning"

### Step 2: Search for Matches

```bash
# Find projects matching a name
fd . ~/.claude/projects --type d | rg "<project-name>"

# Search history for keywords
rg "<keywords>" ~/.claude/history.jsonl

# Find recent sessions
fd . ~/.claude/projects --type f -e jsonl --changed-within 1d

# Get user messages from a session file
jq -r 'select(.message.role=="user") | .message.content' <session>.jsonl | head -20
```

### Step 3: Narrow Down (if multiple matches)

If multiple sessions match, extract differentiating information:
- First few user messages (topic/goal)
- Files mentioned
- Approximate duration
- How it ended

Present options:
```
Found 3 sessions for "captain-hook":

1. Jan 8, 22:25 - "Refactored hook dispatching, added parallel execution"
2. Jan 9, 09:41 - "Fixed test failures in event handler module"
3. Jan 9, 14:25 - "Added Docker support, debugging container networking"

Pick one (1-3), or narrow search with more keywords:
```

### Step 4: Extract Context

Once identified, extract:

**Summary:**
- Project path/name
- Session date and approximate duration
- Goal (what the user was trying to achieve)
- Key topics discussed
- Outcome (completed, in progress, blocked)

**Detailed context:**
- Key decisions made and why
- Discoveries/learnings (non-obvious findings)
- Approaches tried (what worked, what didn't)
- Current state (if work was in progress)

### Step 5: Present and Offer Options

```
Context loaded from session [date] ([project]):

Goal: [extracted goal]
State: [outcome/current state]
Key discovery: [most important learning]

How would you like to proceed?
1. Continue where this left off
2. Save as handoff document
3. Context loaded - I'll tell you what I need next
```
