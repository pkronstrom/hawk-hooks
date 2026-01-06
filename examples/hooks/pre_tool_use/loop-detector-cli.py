#!/usr/bin/env python3
# Description: Detect repetitive action loops using Haiku CLI evaluation
# Deps: none

import hashlib
import json
import subprocess
import sys
from pathlib import Path

# Track recent actions in temp file
STATE_FILE = Path("/tmp/captain-hook-actions.json")

# Only evaluate every Nth action or after errors
EVALUATION_INTERVAL = 5

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

PROMPT_TEMPLATE = """You are a progress validator. Analyze if Claude is making meaningful progress or stuck in a loop.

APPROVE if:
- This action is meaningfully different from recent actions
- Claude is trying a new approach after failure
- Claude is making incremental progress on a multi-step task

BLOCK if:
- Claude is repeating the same action that just failed
- Claude is cycling through similar failing approaches
- Claude keeps editing the same file with minor variations
- Claude is retrying without addressing the root cause

Recent actions (newest first):
{recent_actions}

Current action:
Tool: {tool_name}
Input summary: {tool_summary}

Respond with your decision."""


def load_state() -> dict:
    """Load state from file."""
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {"actions": [], "call_count": 0, "last_error": False}


def save_state(state: dict):
    """Save state to file."""
    STATE_FILE.write_text(json.dumps(state))


def action_hash(tool_name: str, tool_input: dict) -> str:
    """Create a short hash of an action for comparison."""
    content = f"{tool_name}:{json.dumps(tool_input, sort_keys=True)}"
    return hashlib.md5(content.encode()).hexdigest()[:8]


def summarize_input(tool_input: dict) -> str:
    """Create a brief summary of tool input."""
    if "file_path" in tool_input:
        return f"file={tool_input['file_path']}"
    if "command" in tool_input:
        cmd = tool_input["command"][:100]
        return f"cmd={cmd}"
    if "pattern" in tool_input:
        return f"pattern={tool_input['pattern']}"
    return json.dumps(tool_input)[:100]


def evaluate_with_haiku(tool_name: str, tool_input: dict, recent_actions: list) -> dict | None:
    """Call claude CLI with haiku to evaluate the action."""
    recent_str = (
        "\n".join([f"- {a['tool']}: {a['summary']}" for a in recent_actions[-10:]])
        if recent_actions
        else "(no recent actions)"
    )

    prompt = PROMPT_TEMPLATE.format(
        tool_name=tool_name,
        tool_summary=summarize_input(tool_input),
        recent_actions=recent_str,
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

    state = load_state()
    state["call_count"] += 1

    # Record this action
    current_action = {
        "tool": tool_name,
        "summary": summarize_input(tool_input),
        "hash": action_hash(tool_name, tool_input),
    }

    # Quick check: exact same action hash in last 3?
    recent_hashes = [a["hash"] for a in state["actions"][-3:]]
    repeat_count = recent_hashes.count(current_action["hash"])

    # Decide if we need Haiku evaluation
    should_evaluate = (
        repeat_count >= 2  # Same action 2+ times recently
        or state["call_count"] % EVALUATION_INTERVAL == 0  # Periodic check
        or state.get("last_error", False)  # After an error
    )

    if should_evaluate and state["actions"]:
        result = evaluate_with_haiku(tool_name, tool_input, state["actions"])

        if result and result.get("decision") == "block":
            print(
                json.dumps(
                    {
                        "decision": "block",
                        "reason": f"[Loop Detected] {result.get('reason', 'Repetitive action pattern detected')}",
                    }
                )
            )
            # Don't record blocked actions
            save_state(state)
            return

    # Record action and save
    state["actions"].append(current_action)
    state["actions"] = state["actions"][-20:]  # Keep last 20
    state["last_error"] = False
    save_state(state)


if __name__ == "__main__":
    main()
