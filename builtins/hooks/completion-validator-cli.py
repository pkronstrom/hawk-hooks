#!/usr/bin/env python3
# hawk-hook: events=stop
# hawk-hook: description=Validate task completion using transcript analysis + Haiku

"""
Completion Validator - Analyzes the session transcript to verify Claude
has genuinely completed the task before stopping.

Uses the actual transcript file to extract context.
"""

import json
import subprocess
import sys
from pathlib import Path

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

PROMPT_TEMPLATE = """You are a completion validator. Determine if Claude should stop or continue working.

APPROVE stopping if:
- The user's request has been fully addressed
- Tests were run and passed (if applicable)
- Changes were verified to work
- Claude provided a clear summary of what was done
- No obvious next steps were left unaddressed

BLOCK stopping if:
- Claude claims completion without verification
- Tests exist but weren't run
- Implementation appears partial or has TODOs
- Error handling was skipped
- User asked for X but Claude only did part of it
- Claude is stopping due to uncertainty rather than completion

User's original request:
{user_request}

Recent actions taken:
{recent_actions}

Claude's final message (if any):
{final_message}

Should Claude be allowed to stop, or should it continue working?"""


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
    for msg in messages:
        if msg.get("type") != "user":
            continue

        content = msg.get("message", {}).get("content", "")

        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = " ".join(text_parts)

        if len(content) > 20:
            return content[:2000]

    return "(no user request found)"


def extract_recent_actions(messages: list[dict]) -> list[str]:
    """Extract recent tool calls from transcript."""
    actions = []

    for msg in messages[-20:]:  # Last 20 messages
        if msg.get("type") != "assistant":
            continue

        content = msg.get("message", {}).get("content", [])
        if isinstance(content, str):
            continue

        for block in content:
            if block.get("type") == "tool_use":
                tool = block.get("name", "unknown")
                input_data = block.get("input", {})

                # Summarize the action
                if tool == "Bash":
                    cmd = input_data.get("command", "")[:60]
                    actions.append(f"Bash: {cmd}")
                elif tool in ("Edit", "Write"):
                    path = input_data.get("file_path", "?")
                    actions.append(f"{tool}: {path}")
                elif tool == "Read":
                    path = input_data.get("file_path", "?")
                    actions.append(f"Read: {path}")
                else:
                    actions.append(f"{tool}")

    return actions[-15:]  # Last 15 actions


def extract_final_message(messages: list[dict]) -> str:
    """Extract Claude's final text message before stopping."""
    for msg in reversed(messages):
        if msg.get("type") != "assistant":
            continue

        content = msg.get("message", {}).get("content", [])
        if isinstance(content, str):
            return content[:1000]

        for block in content:
            if block.get("type") == "text":
                text = block.get("text", "")
                if len(text) > 50:  # Skip very short messages
                    return text[:1000]

    return "(no final message)"


def evaluate_with_haiku(
    user_request: str, recent_actions: list[str], final_message: str
) -> dict | None:
    """Call claude CLI with haiku to evaluate completion."""
    prompt = PROMPT_TEMPLATE.format(
        user_request=user_request,
        recent_actions="\n".join(f"- {a}" for a in recent_actions) or "(no actions recorded)",
        final_message=final_message,
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

    # Get transcript path
    transcript_path = data.get("session", {}).get("transcript_path")
    if not transcript_path or not Path(transcript_path).exists():
        return  # Can't analyze without transcript

    # Extract context from transcript
    messages = read_transcript(transcript_path)

    if len(messages) < 3:
        return  # Not enough context to validate

    user_request = extract_user_request(messages)
    recent_actions = extract_recent_actions(messages)
    final_message = extract_final_message(messages)

    # Evaluate with Haiku
    result = evaluate_with_haiku(user_request, recent_actions, final_message)

    if result and result.get("decision") == "block":
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": f"[Incomplete] {result.get('reason', 'Task may not be fully complete')}",
                }
            )
        )


if __name__ == "__main__":
    main()
