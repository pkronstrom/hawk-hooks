---
name: codex
description: Leverage OpenAI GPT models for autonomous code implementation via Codex CLI. Use when the user asks to invoke/call/run Codex, use codex CLI or codex exec, mention GPT-5 for implementation, or delegate coding tasks to Codex. Default model is gpt-5.6-terra.
tools: [claude, antigravity]
---

# Codex

You are operating in **codex exec** - a non-interactive automation mode for hands-off task execution.

## Invocation

You will usually be called as `/codex [model] [effort] [task]` — "sol high",
"terra subagent", "sol medium review the backup logic". Parse the leading words
as model and effort when they match; everything else is the task.

Expand the short name before it reaches the CLI. The bare word is what gets
spoken, but it is not a valid slug:

| Spoken | Pass to `-m` |
|--------|--------------|
| `sol` | `gpt-5.6-sol` |
| `terra` | `gpt-5.6-terra` |
| `luna` | `gpt-5.6-luna` |

`-m sol` fails with `Model metadata for 'sol' not found`, then HTTP 400 "The
'sol' model is not supported when using Codex with a ChatGPT account" — the run
dies after you have already backgrounded it, so the cost lands minutes later.

## Defaults

Use `gpt-5.6-terra` at `medium` by default.

```bash
codex exec -m gpt-5.6-terra -c model_reasoning_effort="medium" -s workspace-write "your task here"
```

Access other models with `-m <model>` or via `config.toml`.
Reasoning depth is a config override, not a flag: `-c model_reasoning_effort="high"`. There is no `--effort` flag in `codex exec`.

## Prerequisites

```bash
codex --version
```

If not installed: `npm i -g @openai/codex` or `brew install codex`.

If a run fails with `401 Unauthorized`, `token_invalidated`, or "Please try
signing in again", the ChatGPT auth token has expired. Nothing works until it is
renewed: run `codex login`, or ask the user whether to fall back to another
provider for this task.

## Running It

Codex runs for minutes, so launch it with `run_in_background: true` and then
**stop**. You are re-invoked when it completes; the notification carries the
output path. Do not `sleep` and peek — the harness refuses chained sleeps, so
polling costs a turn and buys nothing.

Give the prompt as a positional argument, and redirect stdin from `/dev/null`
unless you are deliberately piping into it:

```bash
codex exec -m gpt-5.6-terra -c model_reasoning_effort="medium" -s workspace-write \
  "your task here" < /dev/null
```

Without the redirect, a prompt that lands anywhere but the positional slot makes
codex print `Reading additional input from stdin...` and block. It exits cleanly
and writes nothing, so the failure reads as an empty result rather than an error.

## Handoff Strategy

Codex does **not** inherit the parent agent's reasoning context. Keep the handoff as small as possible.

1. Use a short direct prompt for small, self-contained tasks.

```bash
codex exec -m gpt-5.6-terra -c model_reasoning_effort="medium" -s workspace-write "In src/auth/login.ts, validateToken throws on expired tokens instead of returning false. Fix it and run the relevant tests."
```

2. Pipe stdin for transient generated context.

```bash
pytest -q tests/auth 2>&1 | codex exec -m gpt-5.6-terra -s workspace-write "Use the failing test output from stdin to diagnose and fix the issue. Run the same tests after the fix."
```

3. Write findings to a file when the context is long, structured, or reusable.

```bash
codex exec -m gpt-5.6-terra -s workspace-write "Read docs/plans/codex-findings.md, implement the requested changes, and run relevant verification commands."
```

Prefer short prompts over piping, and piping over files, unless reuse or prompt size makes a file clearer.

## Review Recipe

For a read-only review of work in a repo, this is the combination that works —
codex reads the repo, writes its verdict to a file you can read back, and cannot
touch the tree:

```bash
codex exec -m gpt-5.6-terra -c model_reasoning_effort="high" \
  -C <repo> -s read-only \
  --add-dir <scratchpad> -o <scratchpad>/review.md \
  "review <what>, focusing on <angle>" < /dev/null
```

`--add-dir` is what makes the scratchpad writable; without it `-o` fails when the
output path sits outside the workspace. Read the file back when the completion
notification arrives.

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

- `-s read-only|workspace-write|danger-full-access`: sandbox level. `workspace-write` is the everyday autonomous mode
- `-c model_reasoning_effort="high"`: increase effort
- `--json`: stream JSONL events
- `--output-schema <file>`: enforce structured final output
- `-o <file>`: write the final message to a file
- `--add-dir <path>`: allow writes in extra directories
- `--skip-git-repo-check`: allow non-git workspaces
- `--ephemeral`: do not persist session state
- `-p <profile>`: use a config profile

There is no single documented "no tools" switch in `codex exec`. Constrain Codex with a tighter prompt and `-s read-only`.

### Verified flag surface

The complete `codex exec` option list, verified against **codex-cli 0.152.0**:

```
-c --config       --enable          --disable        --strict-config
-i --image        -m --model        --oss            --local-provider
-p --profile      -s --sandbox      --approve-for-me -C --cd
--add-dir         --thread-source   --skip-git-repo-check
--ephemeral       --ignore-user-config  --ignore-rules
--output-schema   --color           --json           -o --output-last-message
```

Trust this list while `codex --version` still reports 0.152.0, and skip the
`--help` round-trip. On any other version, re-check with `codex exec --help`
before relying on a flag — the surface does move: `--full-auto` was a valid
alias for `-s workspace-write` through 0.150.x and is now rejected outright
(`error: unexpected argument '--full-auto' found`).

For which *models* the account can currently reach, use the `models_cache.json`
snippet in the Models section above rather than guessing. Two caveats it will not
tell you: only full slugs work (`gpt-5.6-sol`, never `sol`), and a ChatGPT-plan
account can refuse a model the cache lists, with HTTP 400 at run time.

## Examples

```bash
# Read-only investigation
codex exec -m gpt-5.6-terra -s read-only "Analyze the codebase structure and summarize the main modules."

# Standard implementation
codex exec -m gpt-5.6-terra -c model_reasoning_effort="medium" -s workspace-write "Implement the feature in src/foo.ts and run relevant tests."

# Fast, cheap pass
codex exec -m gpt-5.6-luna -s workspace-write "Rename the helper and update its callers."

# Complex bug hunting
codex exec -m gpt-5.6-sol -c model_reasoning_effort="xhigh" -s workspace-write "Diagnose the intermittent deadlock in the worker pool and fix it."

# Long-running agent work with subagent delegation
codex exec -m gpt-5.6-sol -c model_reasoning_effort="ultra" -s workspace-write "Work through the migration plan end-to-end."

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
