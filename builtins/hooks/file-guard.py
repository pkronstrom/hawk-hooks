#!/usr/bin/env python3
# hawk-hook: events=pre_tool_use
# hawk-hook: description=Block modifications to sensitive files

import json
import sys

# Files/patterns to protect
PROTECTED_PATTERNS = [
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "secrets.yaml",
    "secrets.yml",
    ".ssh/",
    "id_rsa",
    "id_ed25519",
    ".aws/credentials",
    ".npmrc",
    ".pypirc",
]


def main():
    data = json.load(sys.stdin)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Write", "Edit", "MultiEdit", "Bash"):
        return

    tool_input = data.get("tool_input", {})

    # Check file path for file tools
    file_path = tool_input.get("file_path", "")
    for pattern in PROTECTED_PATTERNS:
        if pattern in file_path:
            print(json.dumps({
                "decision": "block",
                "reason": f"Protected file: {file_path} matches pattern '{pattern}'",
            }))
            sys.exit(0)

    # Check bash commands for file operations on protected files
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        for pattern in PROTECTED_PATTERNS:
            # Simple check - could be made more sophisticated
            if pattern in command and any(op in command for op in [">", "rm ", "mv ", "cp "]):
                print(json.dumps({
                    "decision": "block",
                    "reason": f"Command may modify protected file matching '{pattern}'",
                }))
                sys.exit(0)


if __name__ == "__main__":
    main()
