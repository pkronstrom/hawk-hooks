---
name: prime-context
description: Prime session with git history and project context
tools: [claude, gemini, codex]
---

# Prime Context

Load project context from git history and recent changes to orient the session.

## Process

1. **Get recent commits**:
   ```bash
   git log --oneline -20
   ```

2. **Get current status**:
   ```bash
   git status
   ```

3. **Get recent changes** (if any uncommitted):
   ```bash
   git diff --stat
   ```

4. **Read key project files**:
   - README.md
   - CLAUDE.md / AGENTS.md (if exists)
   - package.json / pyproject.toml / Cargo.toml

5. **Summarize context**:
   - What the project does
   - Recent work (last 5-10 commits)
   - Current state (uncommitted changes)
   - Active branches

## Output Format

```
Project: <name>
Description: <brief description>

Recent Activity:
- <commit 1 summary>
- <commit 2 summary>
- ...

Current State:
- Branch: <current branch>
- Status: <clean / X files modified>
- Uncommitted: <summary if any>

Ready to continue.
```
