---
name: whats-next
description: Where the work actually stands — the unfinished thing in front of you first, the epic plan second, and an explicit line when the current work isn't in the plan at all. Verifies the plan against the repo instead of trusting its checkboxes. `plan` or `here` to force one scope.
argument-hint: [plan|here]
---

# What's next

Two different questions share this name, and answering the wrong one is why this command has
felt useless:

| **near** | what's next in the thing I'm doing *right now* — uncommitted work, this branch, this session |
| **far** | what's next in the epic — the plan doc |

**Default: answer near first, far second.** The near scope is what the user can act on in the
next five minutes; the epic is context around it. Argument `here` means near only, `plan` means
far only. Anything else, ignore and use the default.

## Step 1 — read the working state before anything else

Cheap signals, one batch, no file reads yet:

```bash
git status --short && git branch --show-current && git log --oneline -10
```

Add whatever else is nearly free and relevant: a running dev server, a failing test you already
saw this session, an open worktree. Your own conversation is a signal too — a task in progress
in this session counts as in flight even with nothing on disk yet.

**Do not open source files to reconstruct what a diff already tells you.** Filenames plus the
branch name usually identify the work; read a file only when they genuinely don't.

## Step 2 — read the plan cheaply, not wholly

Find the big-picture doc: `docs/`, `specs/`, `plans/`, `TODO.md`, `ROADMAP.md`, or an issue
tracker. Ask the user only after looking.

**Never read a masterplan end to end.** They run to hundreds of lines and most of it is settled
history that will crowd out the actual question. Instead:

```bash
grep -nE '^#{1,3} |^\s*- \[[ x]\]' <plan>      # headings + checkboxes, with line numbers
git log -1 --format=%cr -- <plan>              # how stale is it?
```

That skeleton is usually the whole answer. Read one section in full only when it's the section
the current work touches. Cite `file:line`, don't paste blocks.

If no plan doc exists, say so and skip the **Plan** section — don't invent one.

## Step 3 — verify before you believe the doc

A checkbox is a claim, not a fact. The doc is only as fresh as the last person who remembered to
edit it — which is why this command used to hand back stale epics with confidence.

Check only the items you're about to report, and only cheaply: `git log --oneline` since the
doc's last commit, the file or endpoint an item claims exists, `docker ps` for a service. Report
drift in both directions — pending items already built, done items with nothing behind them.
Where a check would cost more than it's worth, say the item is unverified rather than guessing.

## Step 4 — report

```
**In flight**
- <the unfinished work, one line each — branch, files, what state it's in>

**Next**
→ <the one action that moves the in-flight work>
· <other unblocked item, terse>

**Plan** — <path>, last touched <age>
- ✅ <verified done phase>   ⚠️ <claimed done, unconfirmed>
- <next plan item, by lowest-hanging value that delivers something real — not doc order>
```

Rules:

- **Say when the current work isn't in the plan.** One line: *"the archivist token rotation isn't
  a plan item — unplanned."* Silence here is the original bug; unplanned work was invisible, so
  the epic looked like a description of what you were doing.
- **In flight beats Plan.** If the two disagree about priority, the thing already half-built
  usually wins, and finishing it is the recommendation.
- Nothing in flight? Say so in one line and let **Plan** carry the answer — that's the case the
  old version handled, and it's the rarer one.
- One fact per line, no padding. Under 20 lines total.

$ARGUMENTS
