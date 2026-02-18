---
name: dodo-command
description: Use 'dodo' cli tool for tracking project and subagent tasks
tools: [claude, gemini, codex]
---

# Dodo Commands for AI Agents

## Use Case 1: Project Task Tracking

Track your own work as you go:

```bash
dodo add "Implement user auth"
dodo add "Write tests" -p high
dodo list -f jsonl                       # Machine-readable
dodo done <id>                           # Mark complete
```

Tasks persist in the project's `.dodo/` directory.

---

## Use Case 2: Agentic Workflow with Dependencies

Orchestrate parallel subagents with dependency-aware task distribution.

### Setup

```bash
dodo new workflow-abc --local -b sqlite
dodo plugins enable graph
```

### Bulk insert tasks

```bash
echo '{"text": "Setup database schema", "priority": "high", "tags": ["db"]}
{"text": "Implement user model", "tags": ["backend"]}
{"text": "Implement auth endpoints", "tags": ["backend"]}
{"text": "Write integration tests", "tags": ["test"]}' | dodo bulk add -d workflow-abc -q
```

Output (IDs only with `-q`):
```
a1b2c3
d4e5f6
g7h8i9
j0k1l2
```

### Add dependencies

```bash
echo '{"blocker": "d4e5f6", "blocked": "g7h8i9"}
{"blocker": "g7h8i9", "blocked": "j0k1l2"}' | dodo bulk dep -d workflow-abc
```

### Query ready tasks

```bash
dodo graph ready -d workflow-abc -f jsonl
```

### Subagent instructions

```
Track work with dodo:
- Get ready tasks: dodo graph ready -d workflow-abc -f jsonl
- Mark done: dodo done <id> -d workflow-abc

Only work on tasks from 'graph ready'. Blocked tasks auto-unblock when blockers complete.
```

### Cleanup

```bash
dodo destroy workflow-abc --local
```

---

## JSONL Schema

**bulk add** input:
```json
{"text": "Task description", "priority": "high", "tags": ["tag1", "tag2"]}
```

**bulk dep** input:
```json
{"blocker": "abc123", "blocked": "def456"}
```

**list -f jsonl** output:
```json
{"id": "abc123", "text": "Task", "status": "pending", "priority": "high", "tags": ["work"], "blocked_by": []}
```

---

## Quick Reference

```bash
# Core operations
dodo add "task" [-p priority] [-t tag]
dodo done <id>
dodo list -f jsonl

# Bulk (pipe JSONL to stdin, -q outputs IDs only)
echo '<jsonl>' | dodo bulk add [-q]
echo '<jsonl>' | dodo bulk dep

# Dependencies (requires: dodo plugins enable graph)
dodo graph ready [-f jsonl]              # Unblocked tasks
dodo graph blocked [-f jsonl]            # Blocked tasks
dodo dep add <blocker> <blocked>

# Target specific dodo
-d <name>                                # Use named dodo
-g                                       # Use global dodo
```

### Priority levels
`critical` > `high` > `normal` > `low` > `someday`
