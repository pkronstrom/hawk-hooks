---
name: antigravity
description: Leverage Google Gemini models for autonomous code implementation via Antigravity CLI (agy). Use when the user asks to invoke/call/run Antigravity, agy, or Gemini, use the agy CLI, mention Gemini models for implementation, or delegate coding tasks to Google models. Default model is gemini-3.6-flash-high.
tools: [claude, codex]
---

# Gemini (Antigravity CLI)

You are using **Antigravity CLI** (`agy`) in print mode for hands-off task execution.

Antigravity CLI replaced Gemini CLI, which Google shut down for free/Pro/Ultra tiers on 2026-06-18. The old `gemini` binary and its flags (`--approval-mode`, `--include-directories`, `-e none`) do not apply here.

## Defaults

```bash
agy --print --model gemini-3.6-flash-high --mode accept-edits "your task here"
```

Always pass `--model` explicitly. Left unset, `agy` picks its own default (Gemini 3.6 Flash at unspecified effort) rather than the `gemini-3.6-flash-high` this command recommends — pinning the slug is what makes runs reproducible.

## Prerequisites

```bash
agy --version
agy models     # fails until you sign in
```

Sign-in is an interactive OAuth flow — run bare `agy` once. On a headless box use the documented remote OAuth flow rather than an API-key env var.

## Handoff Strategy

Antigravity does **not** inherit the parent agent's reasoning context, and **it ignores piped stdin** — `cat diff | agy -p "..."` silently arrives with no diff attached. Hand context over by path or in the prompt body.

1. Use a short direct prompt for small, self-contained tasks.

```bash
agy --print --model gemini-3.6-flash-high --mode accept-edits "In src/auth/login.ts, validateToken throws on expired tokens instead of returning false. Fix it and run the relevant tests."
```

2. Write transient context to a file and reference it by path (this replaces stdin piping).

```bash
pytest -q tests/auth > /tmp/failures.txt 2>&1
agy --print --model gemini-3.6-flash-high --mode accept-edits --add-dir /tmp "Read /tmp/failures.txt, diagnose the failing tests, fix them, and rerun the same tests."
```

3. For long or reusable context, keep the findings file in the repo.

```bash
agy --print --model gemini-3.6-flash-high --mode accept-edits "Read docs/plans/gemini-findings.md, implement the requested changes, and run relevant verification commands."
```

Anything outside the working directory needs `--add-dir`, including `/tmp`.

## Models

`agy models` lists what your account can reach. Reasoning effort is **baked into the slug**, not a separate flag:

| Model | Use for |
|-------|---------|
| `gemini-3.6-flash-high` / `-medium` / `-low` | **Default.** Google's current best for coding — reviews, implementation, agentic loops |
| `gemini-3.1-pro-high` / `-low` | Older Pro generation; still useful for long-context reasoning, but 3.6 Flash beats it on coding |
| `gemini-3.5-flash-high` / `-medium` / `-low` | Previous flash generation |
| `claude-sonnet-4-6`, `claude-opus-4-6-thinking` | Anthropic models served through Antigravity |
| `gpt-oss-120b-medium` | Open-weights option |

**Don't assume Pro > Flash here.** There is no Gemini 3.6 Pro — 3.5 Pro has slipped repeatedly, so `gemini-3.1-pro` is a stale generation. Gemini 3.6 Flash (released 2026-07-21) beats 3.1 Pro on every coding and agentic benchmark Google published, while being cheaper and roughly twice as fast. Pick Flash unless you specifically need Pro's long-context behavior.

`--effort low|medium|high` works **only** with a bare slug that has effort variants. Combining it with an already-suffixed slug is a hard error, and non-Gemini slugs reject it outright:

```
Error: invalid model selection (--model "gemini-3.6-flash-high" --effort "low"): conflicts with --effort=low
Error: --effort is not supported for model "claude-sonnet-4-6"
```

Pick the suffixed slug and skip the flag.

## Useful Switches

- `--print` / `-p`: non-interactive single prompt
- `--mode accept-edits|plan`: autonomy level (`plan` is read-only; **omitting this hangs forever in CI** waiting on an approval prompt that never renders)
- `--model <slug>`: pick the model (effort included in the slug)
- `--output-format text|json|stream-json`: structured automation output
- `--json-schema <file|string>`: enforce structured output — **only honored by `gemini-*` models**; the claude/gpt-oss passthroughs ignore it and answer in prose
- `--add-dir <path>`: add a directory to the workspace (repeatable)
- `--sandbox`: run with terminal restrictions
- `--dangerously-skip-permissions`: auto-approve every tool request
- `--print-timeout <dur>`: raise the 5m default for long runs
- `--disable-slash-commands`: stop slash/skill expansion in print mode
- `--continue` / `-c`, `--conversation <id>`: resume prior work
- `--agent <name>`: use a named agent (`agy agents` to list)

`--output-format json` wraps the reply in a transport envelope — `{conversation_id, status, response, usage, duration_seconds, num_turns}`. Unwrap `.response` to get the model's actual output. The `usage` block is the only per-run token accounting agy exposes.

## When the quota runs out

`agy` runs on your Google subscription quota. When it is exhausted the run fails
instead of degrading — `agy` exits non-zero and reports the reason on **stdout**:

```
Print mode: run ended with error and no response: Individual quota reached.
Please upgrade your subscription to increase your limits. Resets in 124h23m43s.
```

The underlying error is `RESOURCE_EXHAUSTED (code 429)`, logged in
`~/.gemini/antigravity-cli/log/cli-*.log`. Match on `Individual quota reached`
or `RESOURCE_EXHAUSTED`; interactively the UI says `AI: Out of credits`.

**The limit is per account, not per model.** Dropping to a lower effort tier or a
different `gemini-*` slug does not get you back in — once it trips, every agy
model is blocked until the reset window elapses (it reports the exact remaining
time, and it is measured in *days*, not minutes). Do not retry in a loop.

**Ask before falling back. Do not switch silently.** `agy` costs subscription
quota; OpenRouter bills real money per token. The user decides whether this task
is worth cash. Say what failed, what the fallback would cost roughly, and wait.

The fallback is the *same model over a different transport* — OpenRouter serves
`google/gemini-3.6-flash`, which is what `gemini-3.6-flash-high` resolves to.
Route it through `pi`, which has the tool loop `agy` would have provided:

```bash
pi --provider openrouter --model google/gemini-3.6-flash:high -p "your task here"
```

Requires `OPENROUTER_API_KEY`. Flag mapping:

| `agy` | `pi` via OpenRouter |
|-------|---------------------|
| `--model gemini-3.6-flash-high` | `--model google/gemini-3.6-flash:high` (or `--thinking high`) |
| `--print` / `-p` | `--print` / `-p` |
| `--mode accept-edits` | default — pi has `edit`/`write` tools |
| `--mode plan` | `--tools read,grep,find,ls` (read-only), or `--no-tools` |
| `--add-dir <path>` | pi reads the cwd; hand files over as `@file` arguments |
| `--output-format json` | `--mode json` — no transport envelope to unwrap |
| `--json-schema <file>` | no equivalent; state the shape in the prompt and validate after |
| `--dangerously-skip-permissions` | `--approve` / `-a` |
| piped stdin (ignored by agy) | works normally |

Two things that differ in substance, not just spelling:

- **Effort moves out of the slug.** `agy` bakes it in (`…-flash-high`) and errors
  if you also pass `--effort`; pi takes `:high` on the model or `--thinking high`.
- **There is no Pro-tier equivalent at this generation.** OpenRouter carries no
  `gemini-3.6-pro` — it does not exist. If the task genuinely needed Pro,
  `google/gemini-3.1-pro-preview` is the nearest, and it is an older generation
  that 3.6 Flash beats on coding.

## Examples

```bash
# Read-only planning
agy --print --model gemini-3.6-flash-high --mode plan "Analyze the codebase structure and summarize the main modules."

# Standard implementation
agy --print --model gemini-3.6-flash-high --mode accept-edits "Implement the feature in src/foo.ts and run relevant tests."

# Structured CI output (unwrap the envelope)
agy --print --model gemini-3.6-flash-medium --mode plan --output-format json --json-schema ./schema.json "Run tests and summarize failures." \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['response'])"
```

## Best Practices

- Pin the slug with its effort suffix; never pass `--model …-high` together with `--effort`
- Always set `--mode` in automation — an unattended run without it blocks on approval
- Hand context over by path with `--add-dir`; stdin is silently dropped
- Use `gemini-*` slugs when you need `--json-schema` enforcement
- Keep handoff context minimal and explicit
- Raise `--print-timeout` before assuming a long task failed
- Use `--dangerously-skip-permissions` only in controlled environments
- On a quota failure, ask before falling back to OpenRouter — never spend the user's money unprompted
- Run relevant tests after making changes
