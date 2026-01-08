#!/usr/bin/env python3
# Description: Check if Claude verified info before editing (transcript analysis + Haiku)
# Deps: none

"""
Confidence Checker - Analyzes the session transcript to verify Claude has
read or researched a file before attempting to edit it.

Uses the actual transcript file for accurate history.
"""

import json
import subprocess
import sys
from pathlib import Path

# Only check for file mutation tools
MUTATION_TOOLS = {"Write", "Edit", "MultiEdit"}

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

PROMPT_TEMPLATE = """You are a confidence validator. Analyze if Claude has verified the file before editing.

APPROVE if:
- Claude read this exact file earlier in the session
- Claude used Grep/Glob to find and understand this file
- The file is being created new (Write to non-existent path)
- The edit is based on clear user instructions about the file
- Claude is editing a file it just created

BLOCK if:
- Claude is editing a file it never read or searched for
- Claude appears to be guessing at file contents or structure
- Claude is making assumptions without verification
- The file path doesn't appear anywhere in prior Read/Grep/Glob calls

File being edited: {file_path}
Tool: {tool_name}

Files Claude has read in this session:
{read_files}

Files Claude has searched for:
{searched_patterns}

Based on this evidence, has Claude verified this file before editing?"""


def read_transcript(path: str) -> list[dict]:
    """Read and parse the JSONL transcript file."""
    messages = []
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except (OSError, IOError):
        pass
    return messages


def extract_file_accesses(messages: list[dict]) -> tuple[set[str], set[str]]:
    """Extract files read and search patterns from transcript."""
    read_files = set()
    search_patterns = set()

    for msg in messages:
        if msg.get("type") != "assistant":
            continue

        content = msg.get("message", {}).get("content", [])
        if isinstance(content, str):
            continue

        for block in content:
            if block.get("type") == "tool_use":
                tool = block.get("name", "")
                input_data = block.get("input", {})

                if tool == "Read":
                    path = input_data.get("file_path", "")
                    if path:
                        read_files.add(path)
                elif tool == "Grep":
                    pattern = input_data.get("pattern", "")
                    path = input_data.get("path", "")
                    if pattern:
                        search_patterns.add(f"grep:{pattern} in {path or 'cwd'}")
                elif tool == "Glob":
                    pattern = input_data.get("pattern", "")
                    if pattern:
                        search_patterns.add(f"glob:{pattern}")
                elif tool == "Write":
                    # Track files we've created
                    path = input_data.get("file_path", "")
                    if path:
                        read_files.add(path)  # Created = known

    return read_files, search_patterns


def evaluate_with_haiku(
    tool_name: str, file_path: str, read_files: set[str], search_patterns: set[str]
) -> dict | None:
    """Call claude CLI with haiku to evaluate confidence."""
    prompt = PROMPT_TEMPLATE.format(
        tool_name=tool_name,
        file_path=file_path,
        read_files="\n".join(f"- {f}" for f in sorted(read_files)[-20:]) or "(none)",
        searched_patterns="\n".join(f"- {p}" for p in sorted(search_patterns)[-10:]) or "(none)",
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
                "--max-tokens",
                "200",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            response = json.loads(result.stdout)
            return response.get("result")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass

    return None


def main():
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "")

    # Gate: only check mutation tools
    if tool_name not in MUTATION_TOOLS:
        return

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path:
        return

    # Get transcript path
    transcript_path = data.get("session", {}).get("transcript_path")
    if not transcript_path or not Path(transcript_path).exists():
        return  # Can't analyze without transcript

    # Extract file access history
    messages = read_transcript(transcript_path)
    read_files, search_patterns = extract_file_accesses(messages)

    # Quick check: if file was explicitly read, it's fine
    if file_path in read_files:
        return

    # Check if parent directory was searched
    file_dir = str(Path(file_path).parent)
    file_name = Path(file_path).name

    for pattern in search_patterns:
        if file_name in pattern or file_dir in pattern:
            return  # Likely found via search

    # File not in read history - ask Haiku to evaluate
    result = evaluate_with_haiku(tool_name, file_path, read_files, search_patterns)

    if result and result.get("decision") == "block":
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": f"[Unverified] {result.get('reason', 'File not verified before editing')}",
                }
            )
        )


if __name__ == "__main__":
    main()
