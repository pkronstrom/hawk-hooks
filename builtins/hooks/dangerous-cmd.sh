#!/usr/bin/env bash
# hawk-hook: events=pre_tool_use
# hawk-hook: description=Block dangerous shell commands
# hawk-hook: deps=jq

set -euo pipefail

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')

if [[ "$TOOL_NAME" != "Bash" ]]; then
    exit 0
fi

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Dangerous patterns
DANGEROUS_PATTERNS=(
    "rm -rf /"
    "rm -rf ~"
    "rm -rf \$HOME"
    ":(){:|:&};:"  # Fork bomb
    "mkfs"
    "dd if=/dev/"
    "> /dev/sd"
    "chmod -R 777 /"
    "curl.*| *sh"
    "wget.*| *sh"
    "curl.*| *bash"
    "wget.*| *bash"
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
    if [[ "$COMMAND" == *"$pattern"* ]]; then
        echo "{\"decision\": \"block\", \"reason\": \"Dangerous command pattern detected: $pattern\"}"
        exit 0
    fi
done

# Block sudo with certain commands
if [[ "$COMMAND" == sudo\ rm* ]] || [[ "$COMMAND" == sudo\ chmod* ]] || [[ "$COMMAND" == sudo\ chown* ]]; then
    echo "{\"decision\": \"block\", \"reason\": \"Sudo with potentially destructive command - requires manual approval\"}"
    exit 0
fi

exit 0
