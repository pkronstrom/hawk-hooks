# Team notes — <plan-slug>

Lead-authored coordination doc for the Sonnet implementer team. The
`<task_source>` file (named in the header below) is the canonical work
spec; this file adds the dep graph, file footprints, cluster bundling,
and the claim board.

**Plan mode:** `openspec | plain`
**Plan dir:** `<plan_dir>`
**Task source:** `<task_source>` (the file with `- [ ]` checkboxes)
**Worktree:** `<absolute-path-to-worktree>`
**Branch:** `agent-team/<plan-slug>` (off `<base-branch>` `<base-sha>`)
**Verify strategy:** `mutex | lead-only`
**Verify command:** `<verify_cmd or (none)>`

## Status

_Refreshed by the lead on each progress-loop tick._

```
(pending — team not yet spawned)
```

Once running, this block holds something like:

```
📊 T+12:34 since spawn
Tasks:    14/20 sub-tasks done (70%)  |  Clusters: 6/10 complete
impl-1:   T-7    (started 07:53Z, 4 commits)
impl-2:   T-12   (started 07:55Z, 1 commit)
impl-3:   idle — waiting on T-9 (impl-1)
Escalations pending: 0
Last commit: a4f9c21 "feat(<id>): add protocol types" (impl-1, 2m ago)
```

## How to use this file

1. Read your assigned cluster below. Read the corresponding sub-tasks in
   the `<task_source>` for the full spec body.
2. Read the proposal, design, and spec files in this directory for context.
3. Before starting, update the `claim:` line under your cluster from
   `claim: (open)` to `claim: <your-name>, started: <wall-clock UTC>`.
   Use `date -u +%FT%TZ`, not any in-process clock.
4. Work through the sub-tasks. Commit each sub-task or coherent group;
   tick the matching `- [ ]` line in the `<task_source>` to `- [x]` per sub-task.
5. Run the verify command (under `flock` when strategy is `mutex`) before
   marking the cluster complete.
6. When the cluster is done, set
   `claim: <your-name>, completed: <wall-clock UTC>`, then pick the next
   ready cluster.

A cluster is "ready" when every cluster in its `after:` list is `completed:`.

If a sub-task's footprint suggests editing a file outside the cluster's
listed footprint, **escalate to the lead**. Do not silently expand scope.

## Dep graph

```
T-1 ──┬── T-5
      └── T-6 ── T-9
T-2 (independent)
T-3 ──── T-7 ── T-9
T-4 ──── T-8
```

## Clusters

### T-1 — <short summary>
- **after:** (none — first wave)
- **claim:** (open)
- **footprint:**
  - NEW `path/to/new-file.ext`
  - MOD `path/to/existing-file.ext`
- **sub-tasks:** 1.1, 1.2 (see the `<task_source>`)
- **notes:** <anything the implementer needs that is not in the task source / plan body>

### T-2 — <short summary>
- **after:** (none — independent)
- **claim:** (open)
- **footprint:** …
- **sub-tasks:** …
- **notes:** …

<!-- Repeat per cluster. For ≤15 atomic tasks, one cluster per task is fine. -->

## Escalations

_Implementers append a one-liner here when they SendMessage the lead, and
the lead appends the resolution. Keeps the audit trail in one place._

- (none yet)

## Decisions

_Lead-authored ledger of judgment calls made during this run. Append one
entry per non-routine decision. These flow into the Step 11 handoff /
PR description so the user sees why the team did what it did._

Append a decision when:
- Step 4b rewrote a task body because it contradicted the spec
- An escalation was resolved with a non-obvious answer
- A reviewer finding was skipped (`recommended` or `nice-to-have` not actioned)
- The verify strategy was switched mid-flight
- A cluster's footprint was expanded after escalation

Do **not** log routine choices (which file to edit first, which cluster
to claim, standard formatting fixes).

### Entry format

```
- **D-N** (<wall-clock UTC>) — <one-line summary>
  - **Why:** <one or two sentences>
  - **Alternatives:** <what was rejected, one line>
```

Example:

```
- **D-1** (2026-05-12T07:42Z) — Expanded T-5 footprint to include `chrome/*` files
  - **Why:** Spec requires zero `wasm-shim` imports on the main thread; tasks.md only listed `main.ts`. Rewrote per Step 4b "spec wins."
  - **Alternatives:** Narrow the proposal to keep a main-thread shim — rejected; would defer the win this change exists to deliver.
```
