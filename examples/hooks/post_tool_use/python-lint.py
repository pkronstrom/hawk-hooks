#!/usr/bin/env python3
# Description: Run ruff linter on modified Python files
# Deps: ruff

import json
import subprocess
import sys


def main():
    data = json.load(sys.stdin)

    # Only run on file write/edit tools
    tool_name = data.get("tool_name", "")
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        return

    # Get the file path
    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path.endswith(".py"):
        return

    # Run ruff check
    result = subprocess.run(
        ["ruff", "check", "--output-format=concise", file_path],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Ruff found issues in {file_path}:", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        # Don't block, just warn
        # sys.exit(2)  # Uncomment to block on lint errors


if __name__ == "__main__":
    main()
