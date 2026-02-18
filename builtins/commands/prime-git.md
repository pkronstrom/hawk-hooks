---
name: prime-git
description: Context Prime - understand project context with git history
tools: [claude, gemini, codex]
---

# Context Prime (--git, --git-full)

Understand the context of the project. Add --git or --git-full for additional git changes.

## Process

1. Always run `eza . --tree --git-ignore` for context (or `tree` if eza not available)
2. If --git is present, run `git log main..HEAD` for changes in branch
3. If --git-full is present, run `git log main..HEAD -p` for commits with diffs
4. Read README.md and any CLAUDE.md/AGENTS.md if present

## Output

Summarize:
- Project structure overview
- Key files and their purposes
- Recent changes (if --git or --git-full)
- Ready to assist with the project
