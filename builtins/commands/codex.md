---
name: codex
description: Leverage OpenAI GPT models for autonomous code implementation via Codex CLI. Use when the user asks to invoke/call/run Codex, use codex CLI or codex exec, mention GPT-5 for implementation, or delegate coding tasks to Codex. Default model is gpt-5.6-terra.
tools: [claude, antigravity]
---

# Codex

You are operating in **codex exec** - a non-interactive automation mode for hands-off task execution.

## Defaults

Use `gpt-5.6-terra` at `medium` by default.

```bash
codex exec -m gpt-5.6-terra -c model_reasoning_effort="medium" --full-auto "your task here"
```

Access other models with `-m <model>` or via `config.toml`.
Reasoning depth is a config override, not a flag: `-c model_reasoning_effort="high"`. There is no `--effort` flag in `codex exec`.

## Prerequisites

```bash
codex --version
```

If not installed: `npm i -g @openai/codex` or `brew install codex`.

## Handoff Strategy

Codex does **not** inherit the parent agent's reasoning context. Keep the handoff as small as possible.

1. Use a short direct prompt for small, self-contained tasks.

```bash
codex exec -m gpt-5.6-terra -c model_reasoning_effort="medium" --full-auto "In src/auth/login.ts, validateToken throws on expired tokens instead of returning false. Fix it and run the relevant tests."
```

2. Pipe stdin for transient generated context.

```bash
pytest -q tests/auth 2>&1 | codex exec -m gpt-5.6-terra --full-auto "Use the failing test output from stdin to diagnose and fix the issue. Run the same tests after the fix."
```

3. Write findings to a file when the context is long, structured, or reusable.

```bash
codex exec -m gpt-5.6-terra --full-auto "Read docs/plans/codex-findings.md, implement the requested changes, and run relevant verification commands."
```

Prefer short prompts over piping, and piping over files, unless reuse or prompt size makes a file clearer.

## Models

The GPT-5.6 family (Sol / Terra / Luna) is the current lineup:

| Model | Role | Relative token cost |
|-------|------|---------------------|
| `gpt-5.6-sol` | Frontier agentic coding — hardest bugs, security, ambiguous design work | 1× (baseline) |
| `gpt-5.6-terra` | **Default.** Balanced everyday coding and review work | ~0.4× Sol |
| `gpt-5.6-luna` | Fast and cheap — mechanical edits, renames, triage | ~0.04× Sol |

Previous generation, still selectable: `gpt-5.5` (frontier, defaults to `xhigh`), `gpt-5.4`, `gpt-5.4-mini`.

Verify what your account actually exposes — the CLI refreshes `~/.codex/models_cache.json` on each run:

```bash
python3 -c "
import json, os
p = os.path.expanduser('~/.codex/models_cache.json')
try:
    models = json.load(open(p)).get('models', [])
except (OSError, ValueError):
    raise SystemExit(f'no usable model cache at {p} — run any codex command first')
for m in models:
    print(m.get('slug'), [r.get('effort') for r in m.get('supported_reasoning_levels', [])])
"
```

The cache is written by the installed CLI version, so a stale entry means that version has not run yet, not that the model is unavailable.

## Reasoning Effort

`-c model_reasoning_effort="<level>"`. The ladder, cheapest first:

| Level | Use for | Sol | Terra | Luna |
|-------|---------|-----|-------|------|
| `low` | Mechanical, well-scoped edits | ✓ | ✓ | ✓ |
| `medium` | Default — everyday tasks | ✓ | ✓ | ✓ |
| `high` | Complex problems, reviews, audits | ✓ | ✓ | ✓ |
| `xhigh` | Deep debugging, architecture, hard reasoning | ✓ | ✓ | ✓ |
| `max` | Hardest problems, no time pressure | ✓ | ✓ | ✓ |
| `ultra` | Max reasoning + automatic subagent delegation | ✓ | ✓ | — |

`minimal` and `none` are accepted by the API but not advertised by these models.

**Cost model.** Effort does not change the per-token rate; it changes how many *reasoning output* tokens get generated, and output bills ~6× fresh input (cached input is ~1/10 of fresh input). So a level bump is a spend multiplier on the most expensive token class, and `ultra` multiplies again by spawning parallel subagents. On a metered account, prefer dropping a model tier over dropping effort: `terra` at `xhigh` typically costs far less than `sol` at `high` and reasons harder.

Codex's **Fast** (`priority`) service tier is a separate multiplier — more speed, more credits — and is unrelated to reasoning effort. Control it with `-c service_tier=...`; leave it off for batch and review work.

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
codex exec -m gpt-5.6-terra -s read-only "Analyze the codebase structure and summarize the main modules."

# Standard implementation
codex exec -m gpt-5.6-terra -c model_reasoning_effort="medium" --full-auto "Implement the feature in src/foo.ts and run relevant tests."

# Fast, cheap pass
codex exec -m gpt-5.6-luna --full-auto "Rename the helper and update its callers."

# Complex bug hunting
codex exec -m gpt-5.6-sol -c model_reasoning_effort="xhigh" --full-auto "Diagnose the intermittent deadlock in the worker pool and fix it."

# Long-running agent work with subagent delegation
codex exec -m gpt-5.6-sol -c model_reasoning_effort="ultra" --full-auto "Work through the migration plan end-to-end."

# Structured CI output
codex exec -m gpt-5.6-luna --json --output-schema ./schema.json "Run tests and summarize failures."
```

## Best Practices

- Use `gpt-5.6-terra` by default; drop to `gpt-5.6-luna` when speed/cost matters, escalate to `gpt-5.6-sol` for the genuinely hard work
- Raise effort deliberately — `high` for reviews and audits, `xhigh` for hard debugging, `max`/`ultra` only when a run is worth several times the tokens
- Keep handoff context minimal and explicit
- Choose short prompt vs stdin vs file intentionally
- Start with `-s read-only` for investigation tasks
- Use `--json` + `--output-schema` for CI integrations
- Check `codex exec --help` on the installed version before relying on newer flags not shown there
- Use `--dangerously-bypass-approvals-and-sandbox` only in isolated environments
- Run relevant tests after changes
