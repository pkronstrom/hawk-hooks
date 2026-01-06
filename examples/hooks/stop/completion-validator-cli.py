#!/usr/bin/env python3
# Description: Validate task completion using Haiku CLI evaluation
# Deps: none

import json
import subprocess
import sys

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

PROMPT_TEMPLATE = """You are a completion validator. Determine if Claude should stop or continue.

APPROVE stopping if:
- Requested tasks are genuinely complete
- Tests were run (or clear reason given why not)
- Changes were verified to work
- User's original request is satisfied

BLOCK stopping if:
- Claude claims completion without verification
- Tests exist but weren't run
- Implementation is partial or has TODOs
- Error handling was skipped
- User asked for X but only Y was done

Session context (truncated):
{context}

Respond with your decision."""


def evaluate_with_haiku(context: str) -> dict | None:
    """Call claude CLI with haiku to evaluate completion."""
    prompt = PROMPT_TEMPLATE.format(
        context=context[:4000]  # Limit context size
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

    # Get session context - stop hooks receive different data
    # Try various fields that might contain useful context
    context_parts = []

    if "stop_hook_active" in data:
        context_parts.append(f"Stop reason: {data.get('stop_reason', 'unknown')}")

    if "transcript" in data:
        context_parts.append(f"Transcript: {data['transcript']}")

    if "tool_results" in data:
        context_parts.append(f"Recent tool results: {json.dumps(data['tool_results'])}")

    # Fallback: dump all data
    if not context_parts:
        context_parts.append(json.dumps(data, indent=2))

    context = "\n".join(context_parts)

    result = evaluate_with_haiku(context)

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
