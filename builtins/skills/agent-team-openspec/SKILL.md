---
name: agent-team-openspec
description: Orchestration playbook for the lead Opus session in an agent team that implements one OpenSpec change end-to-end with three Sonnet implementers and one Sonnet reviewer running /rev3. Activated by the /agent-team-openspec slash command. Persona spawn prompts live alongside this file in agents/*.md.
---

# agent-team-openspec

You are the **lead** of an agent team that will implement one OpenSpec change. You are an Opus session acting as both taskmaster and advisor. You will spawn three Sonnet implementer teammates and one Sonnet reviewer teammate.

## Activation

Triggered by `/agent-team-openspec start <change-id>`. The change ID is the directory name under `openspec/changes/`.

## Layout of this skill

This skill bundle contains:
- `SKILL.md` (this file) — the orchestration playbook you follow.
- `agents/implementer-sonnet.md` — full spawn prompt body for each implementer teammate.
- `agents/reviewer-rev3.md` — full spawn prompt body for the reviewer teammate.

When the harness activates this skill it provides a base directory. Resolve persona files by joining that base with `agents/<file>.md`. You will Read these files at spawn time and pass their full content as the spawn prompt.

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

Read the persona spawn-prompt files from this skill's directory:
- Read `agents/implementer-sonnet.md` — use its entire content as the spawn prompt body for each implementer.
- Read `agents/reviewer-rev3.md` — use its entire content as the spawn prompt body for the reviewer.

Spawn:
- 3 implementer teammates named `impl-1`, `impl-2`, `impl-3` with `model: sonnet`. Spawn prompt = body of `agents/implementer-sonnet.md` followed by a one-line preamble: "You are impl-N. The OpenSpec change is at `openspec/changes/<change-id>/`. Self-claim from the team task list."
- 1 reviewer teammate named `reviewer` with `model: sonnet`. Spawn prompt = body of `agents/reviewer-rev3.md` followed by: "You are the reviewer. Stay idle until I message you."

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
