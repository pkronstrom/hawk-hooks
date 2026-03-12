---
name: gemini
description: Leverage Google Gemini models for autonomous code implementation via Gemini CLI. Use when the user asks to invoke/call/run Gemini, use gemini CLI, mention Gemini for implementation, or delegate coding tasks to Gemini. Default model routing is auto; with preview enabled this can use Gemini 3 models.
tools: [claude, codex]
---

# Gemini

You are using **Gemini CLI** in non-interactive mode for hands-off task execution.

## Defaults

Use `--model auto` by default.

With preview features enabled, `auto` or `pro` can route to Gemini 3 models.

```bash
gemini -p --model auto --approval-mode auto_edit "your task here"
```

## Prerequisites

```bash
gemini --version
```

If not installed, see the [Gemini CLI documentation](https://github.com/google-gemini/gemini-cli).

## Handoff Strategy

Gemini does **not** inherit the parent agent's reasoning context. Keep the handoff as small as possible.

1. Use a short direct prompt for small, self-contained tasks.

```bash
gemini -p --model auto --approval-mode auto_edit "In src/auth/login.ts, validateToken throws on expired tokens instead of returning false. Fix it and run the relevant tests."
```

2. Pipe stdin for transient generated context.

```bash
pytest -q tests/auth 2>&1 | gemini -p --model auto --approval-mode auto_edit "Use the failing test output from stdin to diagnose and fix the issue. Run the same tests after the fix."
```

3. Write findings to a file when the context is long, structured, or reusable.

```bash
gemini -p --model auto --approval-mode auto_edit "Read docs/plans/gemini-findings.md, implement the requested changes, and run relevant verification commands."
```

Prefer short prompts over piping, and piping over files, unless reuse or prompt size makes a file clearer.

## Models

- `auto`: default routing
- `pro`: deeper reasoning
- `flash`: faster coding loop
- `flash-lite`: fastest, least capable

## Useful Switches

- `--approval-mode default|auto_edit|yolo`: autonomy level
- `-s, --sandbox`: run inside the Gemini sandbox
- `--output-format json|stream-json`: structured automation output
- `--include-directories <dir1,dir2,...>`: multi-directory workspace context
- `--resume [session]`: continue a previous session
- `-e none`: disable extensions for the session

There is no single documented "no tools" switch. `-e none` disables extensions, not built-in tools. To constrain Gemini, prefer `--approval-mode default` plus sandboxing over vague prompting alone.

## Examples

```bash
# Read-only planning
gemini -p --model auto --approval-mode default -s "Analyze the codebase structure and summarize the main modules."

# Standard implementation
gemini -p --model auto --approval-mode auto_edit "Implement the feature in src/foo.ts and run relevant tests."

# Structured CI output
gemini -p --model auto --approval-mode auto_edit --output-format json "Run tests and summarize failures."
```

## Best Practices

- Default to `--model auto` unless you have a strong reason to pin
- Keep handoff context minimal and explicit
- Choose short prompt vs stdin vs file intentionally
- Prefer `--approval-mode default` for investigation and `auto_edit` for practical automation
- Use `--include-directories` instead of overloading the prompt with cross-repo context
- Use `-e none` when you want to suppress extensions or MCP-based extras
- Use `--output-format json` or `stream-json` for automation
- Use `--approval-mode yolo` only in controlled environments
- Run relevant tests after making changes
