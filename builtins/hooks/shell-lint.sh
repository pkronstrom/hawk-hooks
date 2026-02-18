#!/usr/bin/env bash
# hawk-hook: events=pre_tool_use
# hawk-hook: description=Lint shell scripts with shellcheck
# hawk-hook: deps=shellcheck,jq

set -euo pipefail

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')

if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" && "$TOOL_NAME" != "MultiEdit" ]]; then
    exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# Only check shell scripts
if [[ "$FILE_PATH" != *.sh ]] && [[ "$FILE_PATH" != *.bash ]]; then
    exit 0
fi

# Check if file exists (for Edit operations)
if [[ ! -f "$FILE_PATH" ]]; then
    exit 0
fi

# Run shellcheck
if ! shellcheck -f gcc "$FILE_PATH" 2>/dev/null; then
    echo "Shellcheck found issues in $FILE_PATH" >&2
    # Don't block, just warn
    # exit 2  # Uncomment to block on lint errors
fi

exit 0
