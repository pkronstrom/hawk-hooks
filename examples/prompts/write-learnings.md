---
name: write-learnings
description: Summarize learnings from this session into a structured document
tools: [claude, gemini, codex]
---

# Write Learnings

Summarize key learnings from the current session into a structured document.

## Process

1. Review the conversation history for:
   - Problems solved
   - Solutions discovered
   - Patterns learned
   - Tools/techniques used
   - Mistakes made and corrections

2. Create a structured document at `docs/learnings/YYYY-MM-DD-<topic>.md`

## Format

```markdown
# Learnings: <Topic>

**Date**: YYYY-MM-DD
**Context**: [Brief description of what was being worked on]

## Key Takeaways

1. **[Takeaway title]**
   - What: [What was learned]
   - Why it matters: [Why this is useful]
   - Example: [Code or command example if applicable]

## Problems Solved

### [Problem 1]
- **Symptom**: [What went wrong]
- **Root cause**: [Why it happened]
- **Solution**: [How it was fixed]

## Useful Commands/Patterns

```bash
# [Description]
[command]
```

## References

- [Links to docs, articles, etc.]

## Future Considerations

- [Things to watch out for]
- [Potential improvements]
```

## Guidelines

- Focus on reusable knowledge, not session-specific details
- Include concrete examples and commands
- Note any gotchas or edge cases discovered
- Link to relevant documentation
