#!/usr/bin/env python3
# Description: Check if Claude has verified info before acting (Haiku CLI)
# Deps: none

import json
import subprocess
import sys
from pathlib import Path

# Only evaluate for mutation tools
MUTATION_TOOLS = {"Write", "Edit", "MultiEdit"}

# Track recent reads in temp file
STATE_FILE = Path("/tmp/captain-hook-reads.json")

JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["approve", "block"]},
            "reason": {"type": "string"},
        },
        "required": ["decision", "reason"],
    }
)

PROMPT_TEMPLATE = """You are a confidence validator. Analyze if Claude has verified the information it's acting on.

APPROVE if:
- Claude read the file before editing it
- Claude searched/grepped before making claims about code
- Action is based on user-provided information
- This appears to be an informed edit

BLOCK if:
- Claude is editing a file it likely hasn't read
- Claude assumes file structure without checking
- Claude makes claims about code without evidence
- Claude is guessing at file locations or contents

Tool: {tool_name}
File: {file_path}
Recent reads: {recent_reads}

Respond with your decision."""


def load_recent_reads() -> list[str]:
    """Load recently read files from state."""
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            return data.get("reads", [])[-20:]  # Keep last 20
    except (json.JSONDecodeError, OSError):
        pass
    return []


def record_read(file_path: str):
    """Record a file read."""
    reads = load_recent_reads()
    if file_path not in reads:
        reads.append(file_path)
    STATE_FILE.write_text(json.dumps({"reads": reads[-20:]}))


def evaluate_with_haiku(tool_name: str, file_path: str, recent_reads: list[str]) -> dict | None:
    """Call claude CLI with haiku to evaluate the action."""
    prompt = PROMPT_TEMPLATE.format(
        tool_name=tool_name,
        file_path=file_path,
        recent_reads=", ".join(recent_reads[-10:]) if recent_reads else "(none recorded)",
    )

    try:
        result = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--model",
                "haiku",
                "--output-format",
                "json",
                "--json-schema",
                JSON_SCHEMA,
                "--tools",
                "",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            response = json.loads(result.stdout)
            return response.get("structured_output") or response.get("result")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass

    return None


def main():
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    # Track reads for future reference
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        if file_path:
            record_read(file_path)
        return

    # Gate: only evaluate mutation tools
    if tool_name not in MUTATION_TOOLS:
        return

    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    recent_reads = load_recent_reads()

    # Quick check: if file was recently read, likely OK
    if file_path in recent_reads:
        return

    # File not in recent reads - ask Haiku to evaluate
    result = evaluate_with_haiku(tool_name, file_path, recent_reads)

    if result and result.get("decision") == "block":
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": f"[Confidence] {result.get('reason', 'File not verified before editing')}",
                }
            )
        )


if __name__ == "__main__":
    main()
