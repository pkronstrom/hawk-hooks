---
name: dodo-command
description: Use 'dodo' cli tool for tracking project and subagent tasks
tools: [claude, gemini, codex]
---

## Use Case 1: Project Task Tracking

Track your own work in the project's `.dodo/` at git root:

```bash
# Track progress as you work
dodo add "Implement user auth"
dodo add "Write tests" -P high
dodo list -f jsonl                       # Machine-readable status
dodo done <id>                           # Mark complete
```

Simple, persistent. Tasks live with the project.

---

## Use Case 2: Agentic Workflow with Subagents

Orchestrate parallel subagents with dependency-aware task distribution.

### Step 1: Create ephemeral dodo

```bash
dodo new workflow-abc --local -b sqlite
```

### Step 2: Bulk insert tasks with dependencies

```bash
# Add all tasks
echo '{"text": "Setup database schema", "priority": "high", "tags": ["db"]}
{"text": "Implement user model", "tags": ["backend"]}
{"text": "Implement auth endpoints", "tags": ["backend"]}
{"text": "Write integration tests", "tags": ["test"]}' | dodo add-bulk -d workflow-abc -q > task_ids.txt

# Add dependencies (auth depends on user model, tests depend on auth)
echo '{"blocker": "<user-model-id>", "blocked": "<auth-endpoints-id>"}
{"blocker": "<auth-endpoints-id>", "blocked": "<integration-tests-id>"}' | dodo dep add-bulk -d workflow-abc
```

### Step 3: Dispatch subagents with ready tasks

Pass these instructions to each subagent:

```
Track your work with dodo:
- See ready tasks: dodo ready -d workflow-abc
- Mark done when complete: dodo done <id> -d workflow-abc

Only work on tasks shown by 'dodo ready'. Dependencies are tracked automatically.
```

Subagents pull ready tasks, complete them, and blocked tasks become unblocked.

### Step 4: Cleanup when done

```bash
dodo destroy workflow-abc
```

Ephemeral dodos prevent stale task accumulation.

---

## JSONL Schema

**add-bulk** fields:
- `text` (required): Todo text
- `priority`: critical/high/normal/low/someday
- `tags`: ["tag1", "tag2"]

**dep add-bulk** fields:
- `blocker` (required): ID of blocking todo
- `blocked` (required): ID of blocked todo

## Command Reference

```bash
# Single operations
dodo add "task" [-d name] [-g] [-P priority] [-t tags]
dodo list [-d name] [-g] [-f jsonl]
dodo done <id> [-d name] [-g]
dodo rm <id> [-d name] [-g]

# Dependencies (requires graph plugin)
dodo ready [-d name]                         # Tasks with no blockers
dodo dep add <blocker> <blocked> [-d name]
dodo dep add-bulk [-d name] [-q]             # JSONL stdin
dodo dep rm <blocker> <blocked> [-d name]
dodo dep list [-d name] [-t]                 # -t for tree view

# Bulk operations
dodo add-bulk [-d name] [-g] [-q]            # JSONL stdin

# Dodo management
dodo new <name> [--local] [-b sqlite|markdown]
dodo destroy <name>
```

### Flags

- `-d, --dodo`: Target specific dodo by name
- `-g, --global`: Use global dodo (~/.config/dodo/)
- `-q, --quiet`: Minimal output (IDs only for bulk ops)
- `-f, --format`: Output format (table/jsonl/tree)
- `-P, --priority`: Priority level
- `-t, --tags`: Comma-separated tags (add) or tree view (dep list)
