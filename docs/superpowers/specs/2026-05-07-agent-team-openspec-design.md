# agent-team-openspec — Design

**Status:** Draft (MVP)
**Date:** 2026-05-07
**Owner:** Peter Kronström

## Purpose

A reusable Claude Code agent-team workflow for implementing an OpenSpec change end-to-end with parallel Sonnet implementers, an Opus advisor/lead, and an automated `/rev3` review pass at the end. Packaged as a hawk-hooks bundle so it can be deployed across projects.

## Non-goals (MVP)

The following are deliberately deferred to keep the first cut simple. They are recorded here so the implementation does not foreclose them.

- **Ext A — multi-plan orchestration.** One team handles one OpenSpec change at a time.
- **Ext B — same-task ganging.** Three implementers always work on three *different* tasks. No decomposition pass that splits one task into file-scoped subtasks.
- **Ext C — heterogeneous implementer pool.** No `implementer-codex` (Sonnet wrapping `codex exec`). Codex is used only inside the reviewer via `/rev3`.
- **Hooks-based quality gates.** `TaskCompleted` and `TeammateIdle` hooks are not used in the MVP; the lead drives transitions via prompt logic.

## Roles

| Role | Count | Model | Hawk component |
|---|---|---|---|
| Lead (taskmaster + advisor) | 1 | Opus | The user's session — not an agent def |
| Implementer | 3 | Sonnet | `agents/implementer-sonnet.md` |
| Reviewer | 1 | Sonnet | `agents/reviewer-rev3.md` |

The lead reads the orchestration playbook from `skills/agent-team-openspec/SKILL.md` and is invoked by the user via the `/agent-team-openspec start <change-id>` slash command.

### Lead responsibilities

- Preflight: verify OpenSpec installed, change exists, agent teams enabled, detect spec-flow.
- Worktree decision: ask user "worktree or current dir?" (default worktree).
- Seed the agent-team task list from `openspec/changes/<id>/tasks.md`, annotating each task with the files it may touch and `depends_on` relationships for file overlaps (Q9 = c — lead pre-partitions).
- Spawn implementers and the (idle) reviewer.
- Act as **advisor** for implementer escalations (Opus pattern, approximated via `SendMessage`).
- After all implementer tasks complete, run `verify:` commands from `openspec/.spec-flow.yaml` (or fall back to project conventions).
- File fix tasks if verify fails; loop back to implementers.
- Wake reviewer when verify passes (or earlier on suspicion — Q6 = a + c).
- Triage `/rev3` findings into fix tasks (one fix round only — Q5 = a).
- Present cumulative diff + summary to user; ask "merge to main + clean up worktree, or open a PR?" (Q10 = user-prompted).
- Invoke `/opsx:archive` (or instruct the user to) once the user confirms the change is shippable.

### Implementer responsibilities

- Self-claim from the team task list.
- For each claimed task:
  - Read `proposal.md`, `design.md`, relevant `specs/<capability>/spec.md` deltas, and the task entry from `tasks.md`.
  - Implement and commit on the worktree.
  - Mark task complete.
- **Escalation discipline (advisor pattern):**
  - **Design / judgment uncertainty** → message the lead with a specific question. Do not guess.
  - **Factual / coordination questions** ("did you finish X?", "are you in `src/foo.py` right now?") → may be sent peer-to-peer to other implementers.
- When blocked on a lead reply, claim the next ready task instead of stalling (Q8 = a).
- Commit own work; before staging, run `git status` and brief-retry if another commit is in flight (light prompt-level mutex; one worktree means contention is bounded to the 3 implementers).

### Reviewer responsibilities

- Idle until lead messages "run review."
- Invoke `/rev3` against the worktree's diff vs base branch (`/rev3` internally fans out to `/codex` gpt-5.5 + others).
- Return findings to the lead. Do not file tasks directly — the lead triages noise and decides which findings become fix tasks.

## Flow

```
1. /agent-team-openspec start <change-id>
2. Lead preflight
3. Lead reads OpenSpec change, summarizes scope
4. Lead asks user: worktree or current dir? (default worktree)
5. Lead creates worktree via using-git-worktrees skill (if chosen)
6. Lead annotates tasks.md entries with file footprints + dependencies
7. Lead seeds team task list
8. Lead spawns 3 implementers + 1 idle reviewer
9. Implementers self-claim → implement → commit → mark done
   - Escalate design/judgment to lead
   - Peer-message for coordination
   - On escalation, claim next ready task while waiting
10. All implementer tasks done → lead runs verify commands
11. Verify fails → file fix tasks → back to step 9
12. Verify passes (or lead suspects issues) → wake reviewer → run /rev3
13. Reviewer returns findings → lead triages → files fix tasks → implementers fix
14. Lead presents diff + summary; asks user: merge + clean up, or PR?
15. User approves; lead invokes /opsx:archive
```

## Worktree strategy

Default: a new worktree per run, branch named `agent-team/<change-id>`, located via the `superpowers:using-git-worktrees` skill conventions. The lead asks the user at kickoff whether to skip the worktree and run in the current directory (for trivial changes).

All three implementers and the reviewer share the **same** worktree. Per-implementer worktrees would introduce cross-worktree merge cost without solving any real conflict — the agent-team docs explicitly warn that two teammates editing the same file lose work, and the file-pre-partition (Q9) is the mitigation.

## Spec-flow integration

If the `spec-flow` skill is available in the user's environment, the lead **follows the spec-flow contract** rather than driving its own state machine:

- Single source of truth lives in `openspec/`.
- Verify commands come from `openspec/.spec-flow.yaml`.
- Roadmap entries are updated at the documented transitions (in-progress on kickoff, shipped on archive).
- Final action before declaring done is `/opsx:archive`.

If `spec-flow` is absent, the lead falls back to vanilla OpenSpec primitives (`/opsx:apply`, `/opsx:archive`) and uses project-default verify commands (e.g., test + lint scripts inferred from the repo).

The lead does **not** literally invoke `/spec-flow go` — that flow expects to drive the implementation itself, which conflicts with the team doing the work. The lead instead reads the spec-flow conventions document once and orchestrates accordingly.

## Hawk layout

Ships as a single bundled skill (subdir form) plus a thin slash command companion. The persona spawn-prompt files live **inside the skill directory**, not as separate top-level hawk agent components.

```
builtins/
├── skills/
│   └── agent-team-openspec/
│       ├── SKILL.md                          # orchestration playbook
│       └── agents/
│           ├── implementer-sonnet.md         # implementer spawn-prompt body
│           └── reviewer-rev3.md              # reviewer spawn-prompt body
└── commands/
    └── agent-team-openspec.md                # /agent-team-openspec slash kickoff
```

Why this shape: the personas are **roles inside this one workflow**, not standalone reusable agents. Bundling them inside the skill directory matches their actual scope and avoids polluting the top-level `agents/` namespace. The slash command must be a sibling because hawk's component scanner is type-by-top-level-dir, but it's a 3-line activator.

This shape sidesteps but does not resolve dodo `hawk-hooks_8f9eb2` task `0478e5c2` (hawk skills cannot declare deps on top-level companion components). Future skills that need *reusable* sibling agents will still hit that gap.

### `commands/agent-team-openspec.md`

Slash command `/agent-team-openspec start <change-id>` that bootstraps the lead by activating the `agent-team-openspec` skill and passing the change ID.

### `skills/agent-team-openspec/SKILL.md`

The orchestration playbook. Steps mirror the Flow section above. Includes:

- Preflight checklist
- Worktree prompt template
- Task-seeding logic (file-footprint annotation, dependency derivation from overlaps)
- Spawn invocations: lead reads `agents/implementer-sonnet.md` and `agents/reviewer-rev3.md` from this skill's base directory and uses each file's full content as the spawn prompt body
- Advisor reply patterns
- Verify command discovery (spec-flow vs fallback)
- Reviewer wake-up message template
- End-of-run user prompt ("merge or PR?") + archive trigger

### `skills/agent-team-openspec/agents/implementer-sonnet.md`

Plain-markdown spawn-prompt body (no frontmatter — this file is data consumed by the skill, not a registered hawk component). Covers:

- Self-claim discipline; one task at a time; mark done promptly
- Read OpenSpec change docs before implementing
- Commit on the worktree after each task
- Advisor escalation rule (design/judgment → lead) vs peer messaging (factual/coordination → other implementers)
- On escalation, claim next ready task instead of stalling
- Brief git-status mutex before staging

### `skills/agent-team-openspec/agents/reviewer-rev3.md`

Plain-markdown spawn-prompt body (no frontmatter). Covers:

- Idle until messaged by lead
- Run `/rev3` on the diff between current worktree state and the base branch (typically `main`)
- Return findings as a structured report; do not file tasks
- Do not write code

## Operational decisions reference

| Q | Decision |
|---|---|
| Q1 — MVP shape | A — single change, lead + 3 implementers + 1 reviewer; extensions deferred |
| Q2 — Ext B (same-task ganging) | Skip for now |
| Q3 — Codex implementer | Skip for now (codex used only via `/rev3`) |
| Q4 — Commits | b — implementers commit on the worktree |
| Q5 — Review rounds | 1 round |
| Q6 — Reviewer trigger | a + c — auto on verify-pass; lead may fire early on suspicion |
| Q7 — Kickoff surface | Slash command only |
| Q8 — Escalation while waiting | a — implementer claims next ready task |
| Q9 — File-edit serialization | c — lead pre-partitions tasks with file annotations + deps on overlap |
| Q10 — Final state | User-prompted at handoff: merge + clean up, or open PR |

## Risks & limitations

- **Coarse advisor escalation.** The blog's `advisor_20260301` server-side tool is API-only. Our `SendMessage`-based approximation depends on the implementer's prompt-following discipline. Some Sonnet teammates will guess instead of asking — accepted.
- **Git contention bounded but not eliminated.** Three concurrent implementers in one worktree mean `git add` / `git commit` races. The prompt-level mutex (`git status` check + brief retry) is best-effort. If it proves flaky in practice, fall back to Q4 = a (lead commits at checkpoints).
- **One review round only.** If `/rev3` surfaces a genuinely deep issue, the team will hand back to the user with that issue partially addressed. Acceptable for MVP — better than infinite loops.
- **Same-worktree means no parallel implementation isolation.** A divergent implementer can damage another's in-progress work. Mitigated by pre-partition + small task scope; not eliminated.
- **Token cost.** 3-5 active Sonnet teammates + Opus lead is significantly more expensive than a single Opus session. Worth it when the change has 8+ atomic tasks; overkill for small changes (the kickoff slash command should accept and forward this judgment to the user).
- **Agent teams are experimental.** Per Anthropic docs: session resumption with in-process teammates is broken; task status can lag; one team per session. The skill should warn the user at kickoff.

## Open questions deferred to plan

- Exact prompt templates for `implementer-sonnet.md` and `reviewer-rev3.md` (will be drafted in the plan).
- Whether the file-footprint annotation in Q9 is computed via static parsing of `tasks.md` headings or via lead heuristic / LLM judgment.
- Whether the verify commands fallback should attempt auto-detection (look for `make test`, `pnpm test`, `cargo test`, etc.) or require the user to declare them at kickoff.
- Whether `/opsx:archive` is invoked by the lead automatically after user approval or always handed off as an explicit user step.
