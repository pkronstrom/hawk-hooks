---
hawk-hook:
  events: [stop]
  description: Verify task completion before stopping
---

Before stopping, please verify:

1. **All requested changes are complete** - Have you addressed everything the user asked for?

2. **Tests pass** - If you modified code with tests, did you run them?

3. **No obvious errors** - Did you check for syntax errors, typos, or broken imports?

4. **Clean state** - Are there any temporary files, debug statements, or TODO comments that should be removed?

If any of these are incomplete, continue working. If everything looks good, you may stop.
