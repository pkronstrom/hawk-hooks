---
name: codex
description: Leverage OpenAI GPT models for autonomous code implementation via Codex CLI. Use when the user asks to invoke/call/run Codex, use codex CLI or codex exec, mention GPT-5 for implementation, or delegate coding tasks to Codex. Default model is gpt-5.4.
tools: [claude, gemini]
---

# Codex

You are operating in **codex exec** - a non-interactive automation mode for hands-off task execution.

## Defaults

Use `gpt-5.4` by default.

```bash
codex exec -m gpt-5.4 -c model_reasoning_effort="medium" --full-auto "your task here"
```

Access legacy models with `-m <model>` or via `config.toml`.
Use `-c model_reasoning_effort="high"` for deeper reasoning. There is no separate documented `--effort` flag in `codex exec`.

## Prerequisites

```bash
codex --version
```

If not installed: `npm i -g @openai/codex` or `brew install codex`.

## Handoff Strategy

Codex does **not** inherit the parent agent's reasoning context. Keep the handoff as small as possible.

1. Use a short direct prompt for small, self-contained tasks.

```bash
codex exec -m gpt-5.4 -c model_reasoning_effort="medium" --full-auto "In src/auth/login.ts, validateToken throws on expired tokens instead of returning false. Fix it and run the relevant tests."
```

2. Pipe stdin for transient generated context.

```bash
pytest -q tests/auth 2>&1 | codex exec -m gpt-5.4 --full-auto "Use the failing test output from stdin to diagnose and fix the issue. Run the same tests after the fix."
```

3. Write findings to a file when the context is long, structured, or reusable.

```bash
codex exec -m gpt-5.4 --full-auto "Read docs/plans/codex-findings.md, implement the requested changes, and run relevant verification commands."
```

Prefer short prompts over piping, and piping over files, unless reuse or prompt size makes a file clearer.

## Models

**IMPORTANT:** `gpt-5.4` does NOT have a `-codex` variant. The model name is just `gpt-5.4`. Do NOT use `gpt-5.4-codex` — that model does not exist and will error.

- `gpt-5.4`: default (no `-codex` suffix)
- `gpt-5.3-codex`: older Codex-tuned fallback
- `gpt-5.2-codex`: older agentic coding fallback
- `gpt-5.2`: broader general-purpose fallback
- `gpt-5.1-codex-max`: deep, slower reasoning
- `gpt-5.1-codex-mini`: fast, cheap, less capable

## Useful Switches

- `--full-auto`: default autonomous mode
- `-s read-only|workspace-write|danger-full-access`: sandbox level
- `-c model_reasoning_effort="high"`: increase effort
- `--json`: stream JSONL events
- `--output-schema <file>`: enforce structured final output
- `-o <file>`: write the final message to a file
- `--add-dir <path>`: allow writes in extra directories
- `--skip-git-repo-check`: allow non-git workspaces
- `--ephemeral`: do not persist session state
- `-p <profile>`: use a config profile

There is no single documented "no tools" switch in `codex exec`. Constrain Codex with a tighter prompt and `-s read-only`. Some flags visible in newer docs or interactive Codex surfaces may not exist in the installed `codex exec`; check `codex exec --help` before relying on them.

## Examples

```bash
# Read-only investigation
codex exec -m gpt-5.4 -s read-only "Analyze the codebase structure and summarize the main modules."

# Standard implementation
codex exec -m gpt-5.4 -c model_reasoning_effort="medium" --full-auto "Implement the feature in src/foo.ts and run relevant tests."

# Deep refactor
codex exec -m gpt-5.1-codex-max -c model_reasoning_effort="high" --full-auto "Refactor the module and preserve behavior."

# Structured CI output
codex exec -m gpt-5.4 --json --output-schema ./schema.json "Run tests and summarize failures."
```

## Best Practices

- Use `gpt-5.4` by default
- Keep handoff context minimal and explicit
- Choose short prompt vs stdin vs file intentionally
- Start with `-s read-only` for investigation tasks
- Use `--json` + `--output-schema` for CI integrations
- Check `codex exec --help` on the installed version before relying on newer flags not shown there
- Use `--dangerously-bypass-approvals-and-sandbox` only in isolated environments
- Run relevant tests after changes
