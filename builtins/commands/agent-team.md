---
name: agent-team
description: Kick off an agent team to implement a plan. Spawns Opus lead + up to 3 Sonnet implementers + 1 Sonnet reviewer; runs /rev3 at end. Works with OpenSpec changes or plain plan docs. Invoke with `/agent-team start <change-id-or-plan-path>`.
---

Activate the `agent-team` skill.

The user invoked: `/agent-team $ARGUMENTS`

If the first argument is `start` followed by a second argument, treat the second argument as the **plan source** and begin Step 1 (Preflight) of the skill. The plan source may be either:

- an OpenSpec change ID (a directory name under `openspec/changes/`), or
- a path to a plan dir (e.g. `docs/plans/my-feature/`) or a single plan file (e.g. `docs/plans/my-feature.md`).

The skill auto-detects which input mode applies (`openspec` vs `plain`) and adapts accordingly.

If arguments are missing or malformed, list candidate plan sources and ask the user which to run on:

```bash
ls openspec/changes/ 2>/dev/null | grep -v archive
ls docs/plans/ plans/ 2>/dev/null
```
