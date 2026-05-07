---
name: agent-team-openspec
description: Kick off an agent team to implement an OpenSpec change. Spawns Opus lead + 3 Sonnet implementers + 1 Sonnet reviewer; runs /rev3 at end. Invoke with `/agent-team-openspec start <change-id>`.
---

Activate the `agent-team-openspec` skill.

The user invoked: `/agent-team-openspec $ARGUMENTS`

If the first argument is `start` and the second is a change ID, immediately begin Step 1 (Preflight) of the skill with that change ID.

If arguments are missing or malformed, list active changes:

```bash
ls openspec/changes/ 2>/dev/null | grep -v archive
```

and ask the user which change to run on.
