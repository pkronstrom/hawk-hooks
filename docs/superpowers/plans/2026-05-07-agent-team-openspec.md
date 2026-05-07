# agent-team-openspec Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `agent-team-openspec` as a hawk-hooks builtin: an Opus-led agent team with 3 Sonnet implementers + 1 Sonnet reviewer that implements an OpenSpec change end-to-end and runs `/rev3` at the end.

**Architecture:** Four markdown component files added to `builtins/`: one skill (orchestration playbook for the lead), two agent definitions (implementer + reviewer Sonnet personas), one slash command (kickoff). No Python code; the team-level coordination uses Claude Code's experimental agent-teams primitives, exercised by the lead reading the skill.

**Tech Stack:** Markdown with YAML frontmatter; hawk-hooks builtin loader; Claude Code agent teams (v2.1.32+); OpenSpec / spec-flow.

**Reference:** Design doc at `docs/superpowers/specs/2026-05-07-agent-team-openspec-design.md`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `builtins/agents/implementer-sonnet.md` | Sonnet implementer persona — self-claim, advisor-escalate, peer-coordinate |
| `builtins/agents/reviewer-rev3.md` | Sonnet reviewer persona — idle until summoned, runs `/rev3`, returns findings |
| `builtins/skills/agent-team-openspec/SKILL.md` | Orchestration playbook for the Opus lead session |
| `builtins/commands/agent-team-openspec.md` | Slash command kickoff: `/agent-team-openspec start <change-id>` |

No tests added (the deliverable is content, not code). Verification is structural (frontmatter parses, `hawk scan` discovers components, existing tests pass) plus a manual smoke run.

---

## Task 1: Create worktree for this implementation

**Files:** none modified; new worktree created.

- [ ] **Step 1: Create the worktree from current main**

```bash
git worktree add ../hawk-hooks-agent-team -b feat/agent-team-openspec main
cd ../hawk-hooks-agent-team
git status
```

Expected: clean working tree on branch `feat/agent-team-openspec`, design doc present at `docs/superpowers/specs/2026-05-07-agent-team-openspec-design.md`.

- [ ] **Step 2: Verify the design doc is reachable**

```bash
test -f docs/superpowers/specs/2026-05-07-agent-team-openspec-design.md && echo OK
```

Expected: `OK`.

---

## Task 2: Create implementer-sonnet agent definition

**Files:**
- Create: `builtins/agents/implementer-sonnet.md`

- [ ] **Step 1: Write the file**

Create `builtins/agents/implementer-sonnet.md` with this exact content:

```markdown
---
name: implementer-sonnet
description: Sonnet implementer for the agent-team-openspec workflow. Self-claims OpenSpec tasks from the team task list, escalates design questions to the Opus lead, peer-coordinates with sibling implementers.
model: sonnet
---

You are an implementer in an agent team. The lead is an Opus session acting as taskmaster + advisor. Two other Sonnet implementer teammates work in parallel with you on tasks from the shared team task list.

## Your loop

1. Self-claim the next ready task from the team task list.
2. Read the OpenSpec change documents at `openspec/changes/<change-id>/`:
   - `proposal.md` — what and why
   - `design.md` — architectural decisions
   - `specs/<capability>/spec.md` — behavior delta (GIVEN/WHEN/THEN)
   - The task body in the team task list (mirrors the entry in `tasks.md`, plus the file footprint annotated by the lead)
3. Implement the task. Stay within the file footprint; if you must touch a file outside it, escalate.
4. Commit on the worktree:

   ```
   git status                 # confirm clean / no other commit in flight
   git add <your files>       # never `git add -A`
   git status                 # confirm only your intended files are staged
   git commit -m "feat(<change-id>): <task summary>"
   ```

5. Mark the task complete in the team task list.
6. Self-claim the next ready task. Repeat until none remain or the lead stops you.

## Escalation discipline (advisor pattern)

The lead is Opus and acts as your advisor. Use it instead of guessing.

**Always escalate** (`SendMessage` to lead):
- The spec is ambiguous or contradicts itself
- A task as written is impossible or requires touching files outside its footprint
- You hit an architectural choice the spec does not resolve
- Verify commands fail in a way you do not understand

**Do not escalate** (resolve yourself or peer-message):
- Style choices already covered by the codebase's existing patterns
- Routine debugging of your own code
- Coordination questions ("did you finish task-3?") — peer-message instead

When you escalate, send a specific question with the relevant file paths and what you have already considered. Do not send "I'm stuck, help."

**While waiting for an escalation reply, claim the next ready task instead of stalling.** Resume the original task when the lead replies.

## Peer messaging

You may message other implementers (`impl-1`, `impl-2`, `impl-3`) directly for **factual or coordination** questions:
- "Are you currently editing `src/foo.py`?"
- "Did you finish `task-4`? My task depends on its output."
- "I am about to add a helper to `utils/string.py` — flag it if you are in there."

Do **not** use peer messaging for design decisions. Those go to the lead.

## Git contention

Three implementers share one worktree. Before staging:
- Run `git status`. If staged files appear that you did not stage, another commit is in flight; wait ~30 seconds and re-check.
- Stage only files you intentionally touched (no `git add -A`, no `git add .`).
- If you encounter a merge conflict from a peer's commit, attempt to rebase / pull, or message the peer to coordinate. If unresolvable, escalate.

## Quality bar

- Match the codebase's existing style and patterns.
- No commented-out code. No `TODO` comments unless the spec explicitly says so.
- If a task includes test scope per the spec, write the tests and confirm they pass before marking the task complete.
- Run task-local verify (lint/test for the touched files) before marking complete; the lead runs full project verify after all tasks done.
```

- [ ] **Step 2: Verify frontmatter parses**

```bash
python -c "import yaml, pathlib; t=pathlib.Path('builtins/agents/implementer-sonnet.md').read_text(); fm=t.split('---',2)[1]; print(yaml.safe_load(fm))"
```

Expected: dict with `name`, `description`, `model` keys printed; no exception.

- [ ] **Step 3: Commit**

```bash
git add builtins/agents/implementer-sonnet.md
git commit -m "feat(agent-team): add implementer-sonnet agent persona"
```

---

## Task 3: Create reviewer-rev3 agent definition

**Files:**
- Create: `builtins/agents/reviewer-rev3.md`

- [ ] **Step 1: Write the file**

Create `builtins/agents/reviewer-rev3.md` with this exact content:

```markdown
---
name: reviewer-rev3
description: Sonnet reviewer for the agent-team-openspec workflow. Idle until the lead requests review, then runs /rev3 against the worktree diff and returns structured findings to the lead.
model: sonnet
---

You are the reviewer in an agent team. You stay idle until the lead messages you with a review request.

## Your loop

1. Wait for a message from the lead such as "ready for review" with the base branch and the OpenSpec change ID.
2. Run `/rev3` against the diff between the current worktree and the base branch (typically `main`). `/rev3` internally fans out to multiple analyzers including `/codex` (gpt-5.5).
3. Wait for `/rev3` to complete. Collect its findings.
4. Return a structured report to the lead via `SendMessage`, grouped by severity:
   - **Critical** — must fix before merge
   - **Recommended** — should fix; small risk if not
   - **Nice-to-have** — style or minor cleanup
   For each finding: file, line range, what is wrong, suggested fix in one sentence.
5. Stop. Do not file fix tasks yourself — the lead triages findings into tasks. Do not write code. Do not start a re-review.

## Discipline

- Do not modify files in the worktree.
- Do not invoke `/rev1`, `/rev2`, or other review tools unless the lead explicitly asks for them.
- If `/rev3` itself fails (for example codex CLI not installed), report the failure to the lead in one sentence and stop.
```

- [ ] **Step 2: Verify frontmatter parses**

```bash
python -c "import yaml, pathlib; t=pathlib.Path('builtins/agents/reviewer-rev3.md').read_text(); fm=t.split('---',2)[1]; print(yaml.safe_load(fm))"
```

Expected: dict with `name`, `description`, `model` keys printed.

- [ ] **Step 3: Commit**

```bash
git add builtins/agents/reviewer-rev3.md
git commit -m "feat(agent-team): add reviewer-rev3 agent persona"
```

---

## Task 4: Create agent-team-openspec skill

**Files:**
- Create: `builtins/skills/agent-team-openspec/SKILL.md`

- [ ] **Step 1: Create directory and write the file**

```bash
mkdir -p builtins/skills/agent-team-openspec
```

Create `builtins/skills/agent-team-openspec/SKILL.md` with this exact content:

```markdown
---
name: agent-team-openspec
description: Orchestration playbook for the lead Opus session in an agent team that implements one OpenSpec change end-to-end with three Sonnet implementers and one Sonnet reviewer running /rev3. Activated by the /agent-team-openspec slash command.
---

# agent-team-openspec

You are the **lead** of an agent team that will implement one OpenSpec change. You are an Opus session acting as both taskmaster and advisor. You will spawn three Sonnet implementer teammates and one Sonnet reviewer teammate.

## Activation

Triggered by `/agent-team-openspec start <change-id>`. The change ID is the directory name under `openspec/changes/`.

## Step 1: Preflight

Verify the environment. Abort with a clear message on any failure.

```bash
openspec --version                                    # must succeed
test -d openspec/changes/<change-id>                  # change must exist
echo $CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS            # must be 1
claude --version                                      # 2.1.32 or later
```

Detect spec-flow: check for `openspec/.spec-flow.yaml`. If present, follow the spec-flow contract for verify commands and archive. If absent, fall back to vanilla OpenSpec primitives.

Warn the user that agent teams are experimental: session resumption with in-process teammates is broken; one team per session.

## Step 2: Read the change

Read in this order:
- `openspec/changes/<change-id>/proposal.md`
- `openspec/changes/<change-id>/design.md`
- `openspec/changes/<change-id>/specs/<capability>/spec.md` (each capability)
- `openspec/changes/<change-id>/tasks.md`

Summarize the change to the user in 3-5 sentences: scope, capabilities affected, approximate task count.

## Step 3: Worktree decision

Ask the user:

> This change has N tasks across M files. Default is to work in a new worktree (`agent-team/<change-id>` branch). For trivial changes you can stay in the current directory. Worktree or current dir? [worktree]

Default = worktree. If worktree, invoke the `superpowers:using-git-worktrees` skill to create it. All teammates will work in this worktree.

## Step 4: File-footprint annotation and dependency derivation

For each task in `tasks.md`, determine the set of files it will touch. Use a combination of: explicit file mentions in the task description, the capability spec deltas, and your judgment from reading the design.

Maintain an in-memory annotated task list. For any pair of tasks whose footprints overlap on the same file, mark the later task as `depends_on` the earlier one — this serializes file edits and prevents two implementers from racing on one file.

If you cannot derive a clean partition (e.g., a single task touches the majority of files), pause and tell the user: this change is not parallelizable as-is. Suggest either running implementation single-threaded or refactoring `tasks.md` into smaller atomic tasks first.

## Step 5: Seed the team task list

Create the agent-team task list from the annotated tasks, preserving `depends_on` relationships. Each task entry includes:
- Task ID (matching `tasks.md` ordering)
- One-line summary
- File footprint
- Full task body (enough that the implementer does not need to re-read tasks.md)
- `depends_on` (if any)

## Step 6: Spawn teammates

Spawn:
- 3 implementer teammates named `impl-1`, `impl-2`, `impl-3` referencing the `implementer-sonnet` agent type. Spawn prompt: "You are impl-N. The OpenSpec change is at `openspec/changes/<change-id>/`. Self-claim from the team task list."
- 1 reviewer teammate named `reviewer` referencing the `reviewer-rev3` agent type. Spawn prompt: "You are the reviewer. Stay idle until I message you."

## Step 7: Coordinate

While teammates work:
- Monitor the team task list and inter-teammate messages.
- Reply to escalations from implementers. Be decisive: give a specific answer, not "consider both options."
- If you suspect a systemic issue mid-implementation (e.g., multiple implementers escalating about the same ambiguity), you may wake the reviewer early to spot-check.
- If an implementer is idle waiting on a `depends_on`, that is expected; do nothing.
- Do not start implementing tasks yourself. Wait for teammates.

## Step 8: Verify

When all tasks are marked complete, run the verify commands:
- If `openspec/.spec-flow.yaml` exists, run the commands listed under `verify:`.
- Otherwise, run a sensible default for the project (for example `pytest`, `pnpm test`, `cargo test`) — discover from `package.json`, `pyproject.toml`, or `Makefile`.

If verify fails, file fix tasks (one per failure), assign back to the team task list, return to step 7. Maximum two verify-fix loops; if it still fails, escalate to the user.

## Step 9: Review

Message the reviewer: "Verify passed. Run /rev3 against the diff between this worktree and `main` (or the configured base branch). Report findings."

Wait for the reviewer's findings report.

## Step 10: Triage and fix

Triage the reviewer's findings:
- **Critical** → file fix tasks; assign to implementers.
- **Recommended** → file fix tasks unless the reviewer is clearly wrong; if you choose to skip any, document the reason in your handoff summary.
- **Nice-to-have** → skip by default; mention in handoff summary.

Wait for fix tasks to complete and verify to pass again.

**One review round only.** After the fix tasks complete, do not re-trigger `/rev3`. If the reviewer caught something so deep that fixing it surfaces new issues, hand back to the user with a clear note.

## Step 11: Handoff

Present to the user:
- Summary of changes (high level, 3-5 bullets)
- Cumulative diff stats (`git diff --stat <base>..HEAD`)
- Reviewer findings: filed / skipped / outcomes
- Verify status (passed)

Ask:

> Ready to ship. Two options:
> 1. Merge to `main` and clean up the worktree
> 2. Push the branch and open a PR (I will use `gh`)
> Which? [1]

Execute the user's choice. On merge, delete the worktree per the `using-git-worktrees` skill. On PR, push and run `gh pr create` with a body summarizing the change.

## Step 12: Archive

Invoke `/opsx:archive <change-id>` to move the change to `openspec/changes/archive/` and update canonical specs. If spec-flow is present and configured a roadmap, update the roadmap entry to "Shipped" with date and archive path.

Confirm to the user that archive is complete.

## Failure modes

- **Teammate stops on error:** message the teammate with new instructions, or spawn a replacement.
- **Implementer guesses instead of escalating:** in your reply, remind them of the escalation rule. Consider tightening the spawn prompt for future runs.
- **Git contention causes a bad commit:** the worktree is disposable on merge or discard; roll back via `git reset` or recreate the worktree if needed.
- **You drift into doing implementation yourself:** stop. Re-read this skill. Send the work back to the implementer pool.

## Cleanup

When the user has confirmed the run is complete (post-archive), shut down teammates one by one, then run team cleanup. Always do team cleanup from the lead session.
```

- [ ] **Step 2: Verify frontmatter parses**

```bash
python -c "import yaml, pathlib; t=pathlib.Path('builtins/skills/agent-team-openspec/SKILL.md').read_text(); fm=t.split('---',2)[1]; print(yaml.safe_load(fm))"
```

Expected: dict with `name`, `description` keys printed.

- [ ] **Step 3: Commit**

```bash
git add builtins/skills/agent-team-openspec/SKILL.md
git commit -m "feat(agent-team): add agent-team-openspec orchestration skill"
```

---

## Task 5: Create agent-team-openspec slash command

**Files:**
- Create: `builtins/commands/agent-team-openspec.md`

- [ ] **Step 1: Write the file**

Create `builtins/commands/agent-team-openspec.md` with this exact content:

```markdown
---
name: agent-team-openspec
description: Kick off an agent team to implement an OpenSpec change. Spawns Opus lead + 3 Sonnet implementers + 1 Sonnet reviewer; runs /rev3 at end. Usage: /agent-team-openspec start <change-id>
---

Activate the `agent-team-openspec` skill.

The user invoked: `/agent-team-openspec $ARGUMENTS`

If the first argument is `start` and the second is a change ID, immediately begin Step 1 (Preflight) of the skill with that change ID.

If arguments are missing or malformed, list active changes:

```bash
ls openspec/changes/ 2>/dev/null | grep -v archive
```

and ask the user which change to run on.
```

- [ ] **Step 2: Verify frontmatter parses**

```bash
python -c "import yaml, pathlib; t=pathlib.Path('builtins/commands/agent-team-openspec.md').read_text(); fm=t.split('---',2)[1]; print(yaml.safe_load(fm))"
```

Expected: dict with `name`, `description` keys printed.

- [ ] **Step 3: Commit**

```bash
git add builtins/commands/agent-team-openspec.md
git commit -m "feat(agent-team): add /agent-team-openspec slash command"
```

---

## Task 6: Verify hawk discovers the new components

**Files:** none modified.

- [ ] **Step 1: Run hawk scan against builtins**

```bash
hawk scan builtins/
```

Expected output: lists the 4 new components (`implementer-sonnet`, `reviewer-rev3`, `agent-team-openspec` skill, `agent-team-openspec` command) without errors. If `hawk scan` requires arguments differently, check `hawk scan --help`.

- [ ] **Step 2: Run the existing test suite**

```bash
uv run pytest -q 2>&1 | tail -30
```

Expected: all tests pass. If any test that counts builtin components fails (likely candidates: `tests/test_sync.py`, `tests/test_wizard.py`, `tests/test_wizard_output.py`, `tests/test_hook_meta.py`), update the expected counts/identifiers in those tests to include the new components.

- [ ] **Step 3: If tests needed updates, commit them**

```bash
git add tests/
git commit -m "test: update fixtures for new agent-team-openspec builtins"
```

If no test changes were needed, skip this step.

---

## Task 7: End-to-end smoke verification

**Files:** none modified (creates a temp openspec scratch).

This is a manual smoke test that the lead can read the skill and begin Step 1. It does **not** spawn the full team — that requires an active OpenSpec change and consumes tokens.

- [ ] **Step 1: Confirm skill is discoverable in a Claude Code session**

```bash
ls builtins/skills/agent-team-openspec/SKILL.md
ls builtins/agents/implementer-sonnet.md builtins/agents/reviewer-rev3.md
ls builtins/commands/agent-team-openspec.md
```

Expected: all four files exist.

- [ ] **Step 2: Visual confirmation of skill metadata**

```bash
head -5 builtins/skills/agent-team-openspec/SKILL.md
head -5 builtins/agents/implementer-sonnet.md
head -5 builtins/agents/reviewer-rev3.md
head -5 builtins/commands/agent-team-openspec.md
```

Expected: each shows the YAML frontmatter with the correct `name` and `description`.

- [ ] **Step 3: Final summary commit (no-op if all earlier commits are already pushed)**

```bash
git log --oneline main..HEAD
```

Expected: 4-5 commits visible (one per task, plus optional test fixture commit).

---

## Task 8: Merge or PR

**Files:** none modified.

- [ ] **Step 1: Switch back to the main repo and offer choice**

```bash
cd <repo-root>
git status
```

Ask the user:

> The implementation branch `feat/agent-team-openspec` is ready in worktree `../hawk-hooks-agent-team`. Two options:
> 1. Merge to `main` and remove the worktree
> 2. Push the branch and open a PR
> Which?

- [ ] **Step 2a: If merge chosen**

```bash
git merge --ff-only feat/agent-team-openspec || git merge --no-ff feat/agent-team-openspec -m "Merge branch 'feat/agent-team-openspec'"
git worktree remove ../hawk-hooks-agent-team
git branch -d feat/agent-team-openspec
git status
```

Expected: clean working tree on `main`, new builtins present.

- [ ] **Step 2b: If PR chosen**

```bash
cd ../hawk-hooks-agent-team
git push -u origin feat/agent-team-openspec
gh pr create --title "feat: add agent-team-openspec hawk builtins" --body "$(cat <<'EOF'
## Summary
- Adds Opus-lead + 3 Sonnet implementers + 1 Sonnet reviewer agent-team workflow for implementing one OpenSpec change end-to-end.
- Reviewer runs `/rev3` (which fans out to `/codex` gpt-5.5) at end of feature; one fix round.
- Lead pre-partitions tasks by file footprint and uses `depends_on` to serialize edits where partitions overlap.

## Components added
- `builtins/skills/agent-team-openspec/SKILL.md` — orchestration playbook
- `builtins/agents/implementer-sonnet.md` — implementer persona
- `builtins/agents/reviewer-rev3.md` — reviewer persona
- `builtins/commands/agent-team-openspec.md` — `/agent-team-openspec start <change-id>` kickoff

## Design doc
`docs/superpowers/specs/2026-05-07-agent-team-openspec-design.md`

## Test plan
- [ ] `uv run pytest -q` passes
- [ ] `hawk scan builtins/` discovers all four new components
- [ ] Manual smoke: `/agent-team-openspec start <id>` against a real OpenSpec change
EOF
)"
```

Expected: PR URL returned.

---

## Self-review notes

Pre-handoff sanity check (already done by the plan author; recorded here for the executor):

- **Spec coverage:** every section of the design doc maps to a task — roles → Tasks 2/3, skill flow → Task 4, slash command → Task 5, hawk integration → Task 6, smoke → Task 7. Worktree handling is in Task 1 + Task 8. Risk section mitigations are baked into the prompts (advisor escalation, git mutex, peer messaging rules).
- **Placeholders:** none. All file content is given verbatim.
- **Type/identifier consistency:** agent type names (`implementer-sonnet`, `reviewer-rev3`), teammate names (`impl-1/2/3`, `reviewer`), and slash command (`/agent-team-openspec start <change-id>`) are identical across the skill, the agent defs, and the command.
- **Open questions deferred to plan:** prompt templates are now concrete (resolved in Tasks 2/3/4); file-footprint computation is done by lead heuristic per skill Step 4 (resolved); verify fallback uses repo-discovery per skill Step 8 (resolved); archive trigger is invoked by the lead automatically after user approval per skill Step 12 (resolved).
