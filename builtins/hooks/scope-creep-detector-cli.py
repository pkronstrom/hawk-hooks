#!/usr/bin/env python3
# hawk-hook: events=pre_tool_use
# hawk-hook: description=Detect scope creep using transcript analysis + Haiku

"""
Scope Creep Detector - Analyzes the session transcript to verify Claude's
actions align with the user's original request.

Uses the actual transcript file to extract the original user request.
"""

import json
import subprocess
import sys
from pathlib import Path

# Only evaluate for mutation tools
MUTATION_TOOLS = {"Write", "Edit", "MultiEdit", "Bash", "NotebookEdit"}

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

PROMPT_TEMPLATE = """You are a scope validator. Determine if Claude's action aligns with the user's request.

APPROVE if:
- Action directly serves the user's stated goal
- Action is a reasonable prerequisite (reading files, searching codebase)
- User explicitly asked for comprehensive or related changes
- Action is part of a logical sequence toward the goal

BLOCK if:
- Claude is refactoring unrelated code "while we're here"
- Claude is adding features the user didn't request
- Claude is "improving" things beyond the specific task
- Claude is fixing unrelated issues it noticed
- Claude is making stylistic changes outside the requested scope

User's original request:
{user_request}

Current action:
Tool: {tool_name}
Input summary: {tool_summary}

Does this action stay within the scope of the user's request?"""


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


def extract_user_request(messages: list[dict]) -> str:
    """Extract the original user request from transcript."""
    # Find the first substantial user message
    for msg in messages:
        if msg.get("type") != "user":
            continue

        content = msg.get("message", {}).get("content", "")

        # Handle content as string or list
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = " ".join(text_parts)

        # Skip very short messages (like "yes", "ok", "continue")
        if len(content) > 20:
            return content[:2000]  # Limit size

    return "(no user request found)"


def summarize_tool_input(tool_name: str, tool_input: dict) -> str:
    """Create a concise summary of the tool input."""
    if tool_name == "Bash":
        return f"command: {tool_input.get('command', '')[:200]}"
    elif tool_name in ("Edit", "Write", "MultiEdit"):
        path = tool_input.get("file_path", "")
        old = tool_input.get("old_string", "")[:100] if "old_string" in tool_input else ""
        new = tool_input.get("new_string", "")[:100] if "new_string" in tool_input else ""
        if old and new:
            return f"file: {path}, replacing '{old}...' with '{new}...'"
        return f"file: {path}"
    else:
        return json.dumps(tool_input)[:300]


def evaluate_with_haiku(tool_name: str, tool_input: dict, user_request: str) -> dict | None:
    """Call claude CLI with haiku to evaluate scope."""
    prompt = PROMPT_TEMPLATE.format(
        tool_name=tool_name,
        tool_summary=summarize_tool_input(tool_name, tool_input),
        user_request=user_request,
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

    # Gate: only evaluate mutation tools
    if tool_name not in MUTATION_TOOLS:
        return

    tool_input = data.get("tool_input", {})

    # Get transcript path
    transcript_path = data.get("session", {}).get("transcript_path")
    if not transcript_path or not Path(transcript_path).exists():
        return  # Can't analyze without transcript

    # Extract user's original request
    messages = read_transcript(transcript_path)
    user_request = extract_user_request(messages)

    if user_request == "(no user request found)":
        return  # Can't validate without knowing the request

    # Evaluate with Haiku
    result = evaluate_with_haiku(tool_name, tool_input, user_request)

    if result and result.get("decision") == "block":
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": f"[Scope Creep] {result.get('reason', 'Action expands beyond requested scope')}",
                }
            )
        )


if __name__ == "__main__":
    main()
