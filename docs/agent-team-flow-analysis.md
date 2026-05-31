# /agent-team + /rev3 Flow Analysis

Survey of 5 lead sessions and ~20 subagent transcripts (May 8–13, 2026) across `still-the-river-flows`, `turbollm`, and `hawk-hooks`.

## TL;DR — top issues ranked by impact

1. **`/rev3` hard-codes `gpt-5.4-codex`, which the OpenAI Codex CLI rejects with `invalid_request_error: 'gpt-5.4-codex' is not supported when using Codex with a ChatGPT account`** — observed in every single reviewer subagent (5/5). Reviewers then hallucinate fallback model names (`gpt-5.5`, `gpt-5.3-codex`, `gpt-4.1`, `gpt-4o`, `o4-mini`), most of which also fail before one accidentally works.
2. **The codex agents inside `/review-work` review the *wrong codebase state* because the `codex exec` calls don't pass `-C <worktree>`** — explicitly diagnosed by one reviewer ("the codex agents reviewed stale context from a different project"). Turns a deep review into noise that the lead then has to discard or hand-redo.
3. **`/rev3` looks like a hang to the lead's stream watchdog** — three parallel `codex exec` background processes don't stream to the parent agent, so after ~600 s the watchdog kills the reviewer even though it's alive. Lead's own narration: "Reviewer stalled out at the codex fan-out step — stream watchdog killed it." Forces ad-hoc fallback to `/rev1`.
4. **The Opus lead becomes a heavy implementer instead of a coordinator** — one lead session has 760 Edit/Write tool uses, indicating massive post-handoff fixup work. The skill explicitly forbids this in Step 7b ("Do not start implementing tasks yourself") but there is no mid-flight self-check.
5. **Implementer `swift test` / `pytest` runs that deadlock cause silent stalls + watchdog kills** — same 600 s stream timeout fires on implementer subagents running long-or-deadlocking verifies. Currently no advisory in the implementer persona about preempting hangs.

---

## Issue 1: Hard-coded `gpt-5.4-codex` in `/rev3` is rejected by Codex CLI

**What happens.** Every `/rev3` reviewer's first codex call returns:

```
ERROR: {"type":"error","status":400,"error":{"type":"invalid_request_error",
  "message":"The 'gpt-5.4-codex' model is not supported when using Codex with a ChatGPT account."}}
```

Counts of unsupported-model errors across the 5 reviewer transcripts I read:
- `gpt-5.4-codex`: 6 + 2 + 2 = 10 occurrences (in 3 distinct sessions)
- `gpt-4o`: 2 occurrences
- `o4-mini`: 2 occurrences

**Where in the flow.** Reviewer subagent (the `/rev3` ⇒ `/review-work` Step 3 dispatch).

**How often.** 100% of reviewer runs I checked. After the rejection, reviewers improvise — `codex exec -m` invocations I saw across the 5 reviewers: `gpt-5.5` (×8), `gpt-5.3-codex` (×31), `gpt-5.4-codex` (×17, all failing), `gpt-4.1` (×1), `gpt-4o` (×1), `o4-mini` (×3). Only `gpt-5.3-codex` consistently succeeds.

**Why it's happening.** `~/.claude/commands/rev3.md` line 7 hardcodes `gpt-5.4-codex`, and `~/.claude/commands/review-work.md` lines 41, 86–88 hardcode `gpt-5.3-codex`. They disagree, and the Codex CLI account this user has only authorizes `gpt-5.3-codex` (probably gpt-5 + gpt-5-codex effectively).

**Fix.**
- `~/.claude/commands/rev3.md` line 7: change `gpt-5.4-codex` to `gpt-5.3-codex` (or, better, drop the explicit model and let `/review-work`'s default apply — just say "Skip Step 2 — go directly with **Deep** mode."). Same fix applies to `rev1.md` and `rev2.md` if they hardcode similarly.
- `~/.claude/commands/review-work.md`: add a short "Codex model availability" note near line 41 telling the agent that if a model returns `invalid_request_error`, it should fall back to `gpt-5.3-codex` (the safest), not invent variants.

---

## Issue 2: Codex agents review the wrong project / stale context (missing `-C`)

**What happens.** Quote from reviewer transcript (`turbollm/391fae.../subagents/agent-afae.../jsonl`):

> "The agents reviewed a different diff (a previous unrelated project). They ignored the `git diff main..HEAD` argument and instead reviewed whatever was in context from the codex session. The output files contain findings about `client-web/src/main.ts` and engine-worker code — not the turbo-hud Swift files."

> "I now have read the actual diff. The codex agents reviewed stale context from a different project. I need to perform the review directly using my own analysis of the actual diff content I've now read."

The reviewer ended up doing the three-angle review *itself* in Claude, defeating the point of `/rev3`.

**Where in the flow.** Reviewer ⇒ `codex exec` dispatch. The actual command:

```
codex exec -m gpt-5.4-codex -s read-only -o /tmp/review-agent-1-quality.md "Review these recent code changes..."
```

Note the missing `-C <worktree>`. Compare with the working session at `still-the-river-flows/2886.../subagents/agent-a6bf...`, which *did* include `-C ~/Projects/still-the-river-flows/.worktrees/...` and got correct project output. The difference is undocumented — pure agent improvisation.

**How often.** 1/5 reviewer sessions explicitly failed this way; others got lucky because CWD inheritance happened to be correct.

**Why it's happening.** `/review-work.md` Step 3's command template (lines 83–88) doesn't include `-C $(pwd)` or a worktree path placeholder, and the reviewer persona doesn't pass the worktree path into the codex invocations. Codex inherits CWD from the parent agent; if that doesn't match the worktree, codex walks main repo at HEAD.

**Fix.**
- `~/.claude/commands/review-work.md` lines 83–88: change command template to `codex exec -C "$WORKTREE" -m gpt-5.3-codex -s read-only -o /tmp/review-agent-N-X.md "<prompt>"` and add: "When invoked from `/agent-team`'s reviewer, `$WORKTREE` is the worktree path from the reviewer's spawn prompt; otherwise default to `$(pwd)`."
- `~/.claude/skills/agent-team/agents/reviewer-rev3.md`: add an explicit instruction near the "Run /rev3" line: "Pass your worktree path through to `/rev3` so codex agents run with `-C <worktree>`. Without this, codex defaults to its own CWD and may review the wrong project."

---

## Issue 3: `/rev3` parallel codex fan-out looks like a hang

**What happens.** Quote from lead 5073 (`still-the-river-flows/5073...`):

> "Reviewer stalled out at the codex fan-out step — stream watchdog killed it. The agent was alive, but /rev3's parallel codex calls don't stream to the parent so it looks idle. Falling back: I'll respawn the reviewer with explicit [/rev1]..."

Reviewer durations I measured: 6.4 min, 8.2 min, 10.7 min, 11.7 min, plus one killed at ~600 s of silence then 1.3 min /rev1 fallback. The user-perceived hang is real *and* there's a literal kill signal (the harness's stream watchdog).

**Where in the flow.** Reviewer subagent during `/rev3` ⇒ 3 parallel `codex exec` background Bash calls. The reviewer is correctly using `run_in_background` but doesn't periodically print anything, so the parent agent gets no stream activity.

**How often.** 2/5 reviewers were interrupted or killed (one user-interrupted, one watchdog-killed and then user fell back to /rev1).

**Why it's happening.** `/review-work.md` instructs "Launch all agents simultaneously using parallel `run_in_background` Bash calls in a single response. After all complete, use the Read tool to read the `/tmp/review-agent-*.md` files." Between launch and Read, the agent has nothing to say. The stream watchdog interprets ≥600 s of no output as a stall.

**Fix.**
- `~/.claude/commands/review-work.md` Step 3: add a "keepalive" instruction after the parallel launch — e.g. "After launching, every 60–120 s emit a single status line (`Waiting on codex agents: 1-quality (running), 2-design (running), 3-arch (done)`) by checking the output file sizes. This keeps the stream watchdog happy and gives the lead useful progress."
- Better: add an explicit `Monitor` tool usage hint so the reviewer monitors the background bashes instead of going silent.
- `~/.claude/skills/agent-team/agents/reviewer-rev3.md`: add to the "Discipline" section: "If your `/rev3` exec runs >5 minutes with no output, print a one-line keepalive to the lead so the watchdog does not kill the run."

---

## Issue 4: Opus lead drifts into doing implementation itself

**What happens.** Lead Edit/Write counts across the 4 leads I measured: 16, 32, 70, **760**. The skill says (Step 7b): "Do not start implementing tasks yourself. Wait for teammates." And in Failure modes: "You drift into doing implementation yourself: stop. Re-read this skill. Send the work back to the implementer pool." But there's no in-flight self-check.

The 760 case is the `2886` session, which also had 7 auto-compact events — so the lead became both the implementer *and* a context-bloated one.

**Where in the flow.** Lead session, post-implementer-handoff and during the fix loop after `/rev3` findings.

**How often.** 3/4 leads had >30 Edit/Write ops; one was severe (760).

**Why it's happening.** Two pressures:
1. After `/rev3` returns critical findings, it feels faster for the lead to just patch a typo than to spawn `impl-fix`. The skill's Step 10 mandates "create a fix task" but offers no escape hatch for one-line fixes — so the lead either follows the heavy path or quietly improvises by editing directly.
2. When an implementer stalls (Issue 5 below), the lead "takes over directly" — lead's own words: "decide whether to spawn a fresh fix-impl-2 or take over directly." The skill should be explicit about which is right.

**Fix.**
- `~/.claude/skills/agent-team/SKILL.md` Step 10 (around line 380): add an explicit rule for trivial fixes: "If a finding's fix is ≤3 lines in one file, the lead may apply it directly and append a Decisions entry. Anything larger → fix task." This codifies what is already happening and prevents drift on harder fixes.
- Same file, Failure modes section (line 419): expand the "you drift into doing implementation yourself" item to give a measurable threshold — e.g. "If you've made >5 Edit/Write calls in a row without delegating, stop and spawn a fix-impl."

---

## Issue 5: Implementer test runs that deadlock kill the implementer

**What happens.** From `turbollm/04992.../subagents/agent-a55f4de3ea190e25b.jsonl` (the fix-impl that stalled): the implementer ran `swift test`, the test deadlocked (later root-caused by lead as a Phase-2 `bg.acquire()` re-entry into a cancelled MockAcquirer), and the parent watchdog killed the implementer after 600 s.

Lead's analysis afterward: "xctest is hung (9+ min, 1.47s CPU — alive but doing nothing) ... fix-impl's new SessionController task-group code most likely deadlocks ... they ran swift test and it hung, stream watchdog killed them."

**Where in the flow.** Implementer subagent's mutex-strategy verify step.

**How often.** 1/clear case observed; latent risk on any project with flaky tests.

**Why it's happening.** `implementer-sonnet.md` (lines 100–112) tells the implementer to wrap verify in `flock -x .team-buildlock <verify_cmd>` but says nothing about test-level timeouts. A deadlocked test under `flock` is indistinguishable from a slow test — implementer sits and waits.

**Fix.**
- `~/.claude/skills/agent-team/agents/implementer-sonnet.md` line 102–106: add a timeout wrapper, e.g.: `flock -x .team-buildlock timeout 300 <verify_cmd>` and document "If timeout fires, treat it as a test failure and escalate to the lead with the test name (do not retry — a hung test is almost always a real bug)."
- Same file, line 112 ("If verify is **slow**..."): extend with: "If verify exceeds 5 minutes once, do not just retry it — escalate. The watchdog will kill you at ~10 minutes of silence and the lead will lose your work."

---

## Issue 6 (lower-impact, but cheap to fix): Reviewer persona is inconsistent about what `/rev3` outputs

**What happens.** `reviewer-rev3.md` says (lines 11–14):

> "Wait for `/rev3` to complete. Extract the trailing fenced ```json block from its output — that is the canonical consensus report. **Return only the JSON object to the lead** via your final response."

But `/rev3` itself (via `/review-work` Step 4) returns BOTH a Markdown summary AND a JSON block — and the reviewer in 2886 returned the full Markdown report including human-readable findings, because the implementer-flavored prose in `/review-work` made the reviewer think the Markdown is the deliverable.

**Where in the flow.** Reviewer ⇒ lead handoff. The lead has to re-parse semantically what should have been a JSON read.

**Fix.**
- `~/.claude/commands/review-work.md` Step 4: tighten the "Print BOTH artifacts" instruction (line 233) — if called by `/rev3`, the consumer wants JSON only. Add a hint: "When invoked from `/agent-team`'s reviewer (caller is a subagent, not a human), print **only** the JSON block — skip the Markdown."
- Or, equivalently, fix at the persona side: `~/.claude/skills/agent-team/agents/reviewer-rev3.md` already says "Return only the JSON object" — strengthen to "Even if `/rev3` returns prose-plus-JSON, strip the prose. Do **not** forward the Markdown summary — the lead reads the JSON directly."

---

## Things I checked that are *not* problems

- **Implementer claim races / first-wave determinism** — claim board worked. Across all sessions only one cluster ever ended up `claim: <two-names>` and the lead caught it on the next progress tick.
- **Escalation discipline** — fewer than 5 `ESC` events total across 5 sessions. Implementers self-resolve correctly.
- **OpenSpec mode detection** — Step 1a works cleanly; no observed misclassification.
- **Worktree creation** — `superpowers:using-git-worktrees` invocations all succeeded.
