#!/usr/bin/env bash
# Description: Git commit best practices guidance
# Deps: jq

set -euo pipefail

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')

# Only intercept Bash tool calls
if [[ "$TOOL_NAME" != "Bash" ]]; then
    exit 0
fi

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Check if this is a git commit command
if [[ "$COMMAND" == *"git commit"* ]]; then
    cat << 'EOF'
Git commit best practices:
- Use conventional commits: type(scope): description
- Types: feat, fix, docs, style, refactor, test, chore
- Keep subject line under 50 chars
- Use imperative mood: "Add feature" not "Added feature"
- Separate subject from body with blank line
- Body explains what and why, not how
EOF
fi

exit 0
