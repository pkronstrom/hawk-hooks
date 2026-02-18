#!/usr/bin/env python3
# Description: Detect repetitive action loops using transcript analysis + Haiku
# Deps: none

"""
Loop Detector - Analyzes the session transcript to detect if Claude is stuck
in a repetitive pattern (e.g., retrying the same failing action).

Uses the actual transcript file for accurate history, not temp file state.
"""

import json
import subprocess
import sys
from pathlib import Path

# Only evaluate for mutation tools (reads are fine to repeat)
MUTATION_TOOLS = {"Write", "Edit", "MultiEdit", "Bash", "NotebookEdit"}

# Minimum actions before checking for loops
MIN_ACTIONS_FOR_CHECK = 3

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

PROMPT_TEMPLATE = """You are a progress validator analyzing Claude's recent actions for repetitive patterns.

APPROVE if:
- Actions are meaningfully different from each other
- Claude is trying genuinely new approaches after failures
- Claude is making incremental progress on a multi-step task
- Repeated similar actions are intentional (e.g., editing multiple files)

BLOCK if:
- Claude is repeating the exact same action that just failed
- Claude is cycling through similar failing approaches without learning
- Claude keeps editing the same file with minor variations hoping it will work
- Claude is retrying without addressing the root cause of failure

Recent actions from transcript (newest last):
{recent_actions}

Current action about to be taken:
Tool: {tool_name}
Input: {tool_input}

Analyze whether this represents meaningful progress or a repetitive loop."""


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


def extract_tool_calls(messages: list[dict]) -> list[dict]:
    """Extract recent tool calls from transcript messages."""
    tool_calls = []

    for msg in messages:
        if msg.get("type") != "assistant":
            continue

        content = msg.get("message", {}).get("content", [])
        if isinstance(content, str):
            continue

        for block in content:
            if block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "tool": block.get("name", "unknown"),
                        "input": block.get("input", {}),
                    }
                )

    return tool_calls


def summarize_tool_call(tool: str, input_data: dict) -> str:
    """Create a concise summary of a tool call."""
    if tool == "Read":
        return f"Read: {input_data.get('file_path', '?')}"
    elif tool in ("Edit", "Write", "MultiEdit"):
        path = input_data.get("file_path", "?")
        return f"{tool}: {path}"
    elif tool == "Bash":
        cmd = input_data.get("command", "")[:80]
        return f"Bash: {cmd}"
    elif tool == "Grep":
        pattern = input_data.get("pattern", "?")
        return f"Grep: {pattern}"
    elif tool == "Glob":
        pattern = input_data.get("pattern", "?")
        return f"Glob: {pattern}"
    else:
        return f"{tool}: {json.dumps(input_data)[:60]}"


def evaluate_with_haiku(tool_name: str, tool_input: dict, recent_actions: list[str]) -> dict | None:
    """Call claude CLI with haiku to evaluate the action."""
    prompt = PROMPT_TEMPLATE.format(
        tool_name=tool_name,
        tool_input=json.dumps(tool_input, indent=2)[:1000],
        recent_actions="\n".join(f"- {a}" for a in recent_actions) or "(no recent actions)",
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

    # Get transcript path from session info
    transcript_path = data.get("session", {}).get("transcript_path")
    if not transcript_path or not Path(transcript_path).exists():
        return  # Can't analyze without transcript

    # Read and parse transcript
    messages = read_transcript(transcript_path)
    tool_calls = extract_tool_calls(messages)

    # Need enough history to detect patterns
    if len(tool_calls) < MIN_ACTIONS_FOR_CHECK:
        return

    # Get last N actions for context
    recent_actions = [summarize_tool_call(tc["tool"], tc["input"]) for tc in tool_calls[-10:]]

    # Quick heuristic: check if exact same action in last 3
    current_summary = summarize_tool_call(tool_name, tool_input)
    recent_summaries = recent_actions[-3:]
    if recent_summaries.count(current_summary) >= 2:
        # Likely loop - ask Haiku to confirm
        result = evaluate_with_haiku(tool_name, tool_input, recent_actions)

        if result and result.get("decision") == "block":
            print(
                json.dumps(
                    {
                        "decision": "block",
                        "reason": f"[Loop Detected] {result.get('reason', 'Repetitive action pattern')}",
                    }
                )
            )


if __name__ == "__main__":
    main()
