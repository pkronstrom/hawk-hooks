---
name: commit
description: Generate a concise commit message following best practices
---

# Commit

Generate a concise, conventional commit message for staged changes.

## Step 1: Ground in Actual State

Before reasoning about the commit, gather real project state:

```bash
!git status --short
!git diff --cached --stat
!git log --oneline -5
```

This ensures the commit message reflects what's actually staged, not assumptions.

## Step 2: Analyze and Draft

1. Run `git diff --cached` to see the full staged diff
2. Analyze the nature of changes (feat, fix, refactor, docs, test, chore)
3. Check recent commit messages (`git log`) to match the project's existing style
4. Write a commit message following conventional commits format

## Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

## Types

- **feat**: New feature
- **fix**: Bug fix
- **refactor**: Code change that neither fixes a bug nor adds a feature
- **docs**: Documentation only changes
- **test**: Adding missing tests or correcting existing tests
- **chore**: Changes to build process or auxiliary tools

## Guidelines

- First line should be 50 characters or less
- Use imperative mood ("add" not "added" or "adds")
- Don't end with a period
- Body should explain what and why, not how
- Reference issues/PRs when relevant

## Example

```
feat(auth): add OAuth2 login support

Implement Google and GitHub OAuth providers.
Includes token refresh and session management.

Closes #123
```
