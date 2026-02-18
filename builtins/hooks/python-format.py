#!/usr/bin/env python3
# hawk-hook: events=post_tool_use
# hawk-hook: description=Auto-format Python files with ruff
# hawk-hook: deps=ruff

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

    # Run ruff format (auto-fixes)
    subprocess.run(
        ["ruff", "format", "--quiet", file_path],
        capture_output=True,
    )

    # Run ruff check with auto-fix
    subprocess.run(
        ["ruff", "check", "--fix", "--quiet", file_path],
        capture_output=True,
    )


if __name__ == "__main__":
    main()
