---
name: cleanup-claude-sessions
description: Clean up old Claude Code session files to reclaim disk space
tools: [claude]
---

Clean up old Claude Code session files to reclaim disk space.

## Purpose

Claude Code stores session data in `~/.claude/projects/`. Over time, this can accumulate significantly. This command helps identify and remove old sessions.

## Session File Structure

```
~/.claude/projects/<project-path-with-dashes>/
├── 30de850c-180f-41a0-b968-af89b2ce6a5c.jsonl  # Main session (UUID)
├── agent-051c9047.jsonl                         # Subagent session (agent-*)
└── ...
```

- **Main sessions**: UUID format, user-initiated conversations
- **Subagent sessions**: `agent-*` prefix, spawned by Task tool (typically 2:1 ratio vs main)

Related directories that may also need cleanup:
- `~/.claude/session-env/` - Session environment data
- `~/.claude/todos/` - Todo list storage

## Process

### Step 1: Ask Cleanup Scope

Ask the user:
- **Age threshold**: How old should sessions be to delete? (default: 14 days)
- **What to clean**: Sessions only, or also session-env/todos?
- **Dry run first?**: Show what would be deleted before actually deleting

### Step 2: Analyze Current State

Use `fd` if available, fall back to `find`:

```bash
# Using fd (preferred - faster)
fd -e jsonl . ~/.claude/projects --type f | wc -l                    # Total sessions
fd -e jsonl . ~/.claude/projects --type f --changed-before 14d | wc -l  # Old sessions

# Using find (fallback - macOS compatible)
find ~/.claude/projects -name "*.jsonl" -type f | wc -l              # Total sessions
find ~/.claude/projects -name "*.jsonl" -type f -mtime +14 | wc -l   # Older than 14 days
```

### Step 3: Preview (Dry Run)

If user wants preview, show sample of files to be deleted:

```bash
find ~/.claude/projects -name "*.jsonl" -type f -mtime +14 | head -20
```

### Step 4: Execute Cleanup

After user confirmation:

```bash
find ~/.claude/projects -name "*.jsonl" -type f -mtime +14 -delete
```

### Step 5: Report Results

```
Cleanup complete:
- Deleted: X session files
- Space freed: ~Y MB
- Remaining: Z sessions
```

## Safety Notes

- **Always dry-run first** when unsure
- **Session files are not recoverable** once deleted
- Subagent sessions are typically safe to delete (ephemeral by nature)
- Main sessions may contain useful context - consider using `/prime-context-from-claude` before cleanup

## Quick Cleanup (One-liner)

```bash
# Delete all sessions older than 2 weeks
find ~/.claude/projects -name "*.jsonl" -type f -mtime +14 -delete
```
