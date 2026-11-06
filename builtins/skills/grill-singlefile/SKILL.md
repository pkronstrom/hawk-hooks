---
name: grill-singlefile
description: "Grilling interview to exhaustion, packaged as one self-contained HTML file the user answers async. /grill-singlefile."
---

# grill-singlefile

`grilling` (the vault's relentless-interview skill) is designed for a live, round-by-round
back-and-forth: ask the frontier, stop, wait for answers, recompute, ask again. That's right
when the user is at the keyboard with you. It's wrong when they want to think it over on the
train, or when the tree is wide enough that live rounds would take all afternoon.

This skill runs the same interview to completion **without stopping for the user**, then hands
back one HTML file — every open question, grouped, each option its own radio, the recommendation
starred and already selected — so they can answer offline and paste a summary back. It's
`grilling` plus `singlefile`, composed.

## 1. Grill to exhaustion, not to the first round

Load the `grilling` skill (`Skill` tool) for the interview mechanic — the design-tree/frontier
model, the recommendation format, the "facts are your job, decisions are theirs" rule. Load
`domain-modeling` too if the interview is about codebase terminology or will produce an ADR.

**The difference from a live grill: don't stop after round 1.** Keep computing the frontier and
generating recommendations across every round, dispatching sub-agents for every fact-findable
prerequisite exactly as `grilling` prescribes — but instead of pausing for the user's answer
before continuing, treat every question as provisionally answered **in the direction of your
recommendation** and move on to whatever the next frontier would be. That's what lets the whole
tree, not just the first frontier, end up in the file.

**Except when a question is a real fork.** If your recommendation for one question would
completely change the *shape* of downstream questions (not just their details), grilling on under
an assumption produces a file full of questions that don't apply under the other branch. When
you hit one of those, either:

- pick the branch you'd actually recommend and grill it out, saying so plainly in the file's
  intro copy, or
- stop and ask that one question live before generating anything — and when you do, or when
  acknowledging any answer, pair the question's id with its short title ("on **Q7** (token
  model)"), never the bare number. Same rule as `grilling` itself.

Most trees don't fork this way, so this should be rare rather than the default reason to fall
back to a live round.

## 2. Every question needs a defensible recommendation

The file **pre-selects** your recommendation, which changes the stakes: a lazy recommendation is
now a silent default the user may never look at, not merely a suggestion they ignore.

- `recommend` is required on every question, and must be a valid index into `opts`. There is no
  "no recommendation" state, by design. A question you can't recommend on is one you haven't
  finished thinking about — either find the fact that settles it (your job, per `grilling`) or
  reshape it into a question you can answer.
- **Never order the options so the recommendation is always first.** Keep whatever order is
  natural (status quo first, cheapest first, whatever the domain suggests). The ★ marks it; its
  position shouldn't.
- `why` explains why the ★ option beats the others, and renders **inside the starred row**,
  directly under that option (and under its own `note`, if it has one). Reasoning about an option
  sits with the option; stranding it after the whole group separates it from what it justifies.
- Per-option `note` is optional and belongs on options that need a specific caveat ("one leak
  exposes every vault"), not on all of them for symmetry. An option whose note just restates its
  label should have no note.
- **`note` and `why` on the recommended option stack, so don't say the same thing twice.** They
  land two lines apart in the same tinted block. `note` is a fact about that option; `why` is why
  it wins. If the note only re-argues the recommendation, drop the note and keep `why`.

## 3. Package it per `singlefile`

Load the `singlefile` skill for the non-negotiables (no `<script type="module">`, no network at
runtime, data-block-first, escape user data with `textContent`, the `</script` trap, the
definition-of-done checklist). This skill's `template.html` already follows all of them — start
from it, don't write one from scratch.

1. Copy `template.html` (this skill's directory) to the output path.
2. Fill in the data block: `title` (becomes the page `<h1>` and `<title>`); leave `answers` as
   `{}`.
3. Set `APP_ID` to something unique to this run (slugified title plus a short date or session
   id) — **not** the literal placeholder. Two files sharing an `APP_ID` share a localStorage key
   and clobber each other's answers.
4. Replace the empty `QUESTIONS` array with the flattened set from §1, in the shape the comment
   above it documents:

   ```js
   { g: "Multi-vault", id: "Q5", t: "Token model",
     ctx: "The path names the vault. What authorises it?",
     opts: [
       { t: "Per-vault tokens, mismatch gives 403",
         note: "GET /v1/vaults then returns only the vaults your token opens." },
       { t: "One server token for everything",
         note: "One leak exposes every vault." },
       "Tokens carrying a set of vaults"
     ],
     recommend: 0,
     why: "Gives the picker and the authorisation check from one mechanism, and is the only option that keeps isolation when an agent token leaks." }
   ```

   Group by **topic, not round number** — the reader doesn't care which live round would have
   produced a question. Order groups the way the tree branched so related questions stay together.
5. Run `grep -c '</script' <file>` — must equal 2. If not, something in a title, context, option,
   note, or rationale spelled the sequence; find it before shipping.
6. Open it and check: every question renders, each option is its own radio, the ★ row is tinted
   and pre-selected, the counter reads `0 / N reviewed`, changing an option updates the summary
   live, Copy works. `singlefile`'s full definition-of-done applies.

**Do not add a "Clear answers" (or "clear notes") button, here or next to Copy, ever.** It was
deliberately left out of `template.html`. Copy is the button the user reaches for constantly, and
a destructive action beside the one clicked most eventually gets misclicked. A reset is a devtools
`localStorage.removeItem(APP_ID)` away. Don't reintroduce it because it "seems useful" or because
another single-file app in this ecosystem has one.

## 4. Hand it off and resume

Tell the user where the file is: open it, and because every recommendation is already selected,
they only need to touch the questions they disagree with. Answers autosave as they go, so closing
the tab loses nothing. Then copy the summary and paste it back.

The summary distinguishes three states per question, and the distinction is the point:

| `— confirmed ★` | they actively selected the recommendation |
| `— ★ default, not reviewed` | they never touched it |
| `— CHANGED from ★` / `SOMETHING ELSE` | they decided differently |

Treat `confirmed` as settled. Treat `CHANGED` / `SOMETHING ELSE` (plus its note) as the real
decision. **Treat `not reviewed` as weaker than agreement** — it means the recommendation stands
by default, so if a `not reviewed` question turns out to be load-bearing for what you're about to
build, say so and confirm it before relying on it. Don't silently re-ask everything either; the
file exists so they don't have to answer twice.
