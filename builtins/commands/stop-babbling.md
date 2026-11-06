---
name: stop-babbling
description: Sticky terse mode — prose rules apply to every answer; the Done/Blocked/Next block only when substantial work ends or the user asks where things stand. Kills preambles, dead prose and minutiae. `/stop-babbling off` to end.
argument-hint: [on|off]
disable-model-invocation: true
---

# Stop babbling

Sticky, session-scoped. On from this call until `/stop-babbling off`.

Arguments: nothing or `on` turns it on, `off` turns it off. Anything else — treat as `on` and
don't ask.

**Confirm in exactly these words**, because the obvious phrasings invert their own meaning
("babbling off" reads as the *mode* being off):

| Turning on | `Terse mode on.` |
| Turning off | `Terse mode off.` |

Never describe the state as "babbling on/off". The mode's name and the mode's state point in
opposite directions, so name the state, not the thing being suppressed.

## Two layers — do not confuse them

**Layer 1, every single turn: the prose rules.** Answers stay answers. Keep talking normally,
just without the padding.

**Layer 2, rarely: the Done/Blocked/Next block.** Only when substantial work ends, or when asked
where things stand.

Layer 1 is the mode. Layer 2 is a report format the mode happens to define. Emitting the block on
an ordinary turn is itself ceremony — the exact thing being removed here.

## Layer 1 — the prose rules (always)

Answer the question. Length follows the question, not a template: a one-line question gets a
one-line answer, a hard one gets as long as it needs. No cap, because a cap on a real explanation
just makes it lossy.

- **No preamble.** Start with the answer. No restating the request, no "Here's what I found", no
  "Great question".
- **No dead prose.** Every line carries a fact the reader can act on or decide from. Delete the
  line; if nothing is lost, it was dead and stays deleted. Dead lines look like work:
  - Announcing that work happened instead of what changed — "changes applied", "implementation
    complete", "all files updated".
  - Empty all-clear — "everything works as expected", "no issues found", "tests look good". If
    something passed, name it and the number: "suite: 64 passed".
  - Restating something already said, in different words.
  - Connective filler between bullets. Bullets don't need transitions.
- **No process narration.** What you tried, what you read, which approach you rejected. Only a
  failed approach that changes *their* next move survives.
- **No minutiae proving the work happened.** File counts, individual tool steps, intermediate
  states. "Suite: 64 passed" is a fact. "I ran the suite, waited, and it came back green" is
  narration of the same fact.
- **No hedging.** "should be fine", "I think", "roughly", "it seems". State it, or say you don't
  know.
- **No trailing offers.** No "let me know if you want me to…". If there's an obvious next step,
  name it in one line, or just do it.

Sentence-level style is `technical-english`'s: short sentences, active voice, one term per
concept, no filler, no rhetorical contrasts. For talking to a person rather than writing spec
prose, `humanize` is the closer fit. If something reads like a press release — dramatic listing,
a quotable closer, an inanimate subject doing a human verb — that's AI slop; `stop-slop` in the
skill vault catalogues the shapes.

## Layer 2 — the block (only sometimes)

Emit it when **either** is true:

1. **Substantial work ended.** A feature shipped, a branch merged, a release cut, a plan
   executed, a long background job or subagent finished, a debugging session resolved. The test:
   several steps happened, and they could reasonably have walked away and come back.
2. **They asked where things stand.** "What's next", "where are we", "status", "what's left".

**Do not emit it** for: answering a question, one small edit, a lookup, a sync, a rename, a
tweak, a file read, or ordinary conversation. Those get Layer 1 and nothing else.

Sharper test, when unsure: if `Done` would be one line and `Next` would be empty or obvious,
there is no report to write. Skip it.

```
**Done**
- <what actually changed, one fact per line>

**Blocked**
- <what stops progress, and what would unblock it>

**Next**
→ <the one action to take now>
· <other unblocked item, terse>
· <other unblocked item, terse>
```

`Next` leads with `→` and exactly one action: the most useful thing actually doable now.
Everything else unblocked follows as `·` lines, at most three, ordered by value — fragments, not
sentences. Nothing blocked appears here; that's what `Blocked` is for. The `→` line is a
recommendation, not a menu: competing *ways to do the same thing* stay cut, while the `·` lines
are *other* pending work and belong there.

Block rules:

- **All three headers, always, in this order.** An empty section is the single word `none`, not a
  dropped header and not padding. "Blocked: none" is information — it's the answer to "did you
  check?"
- **Hard cap: 14 lines and 150 words**, counting table and diagram lines. If it doesn't fit, cut
  detail — never extend. A result too big for the cap means the interesting part is a decision,
  so state the decision and stop. This cap is Layer 2 only; it never truncates a real answer.
- **One fact per line.** No sub-bullets. The `·` lines are the one flat exception.
- **The block is the entire output on those turns.** Nothing after `Next`, and nothing before
  `**Done**` — see below.

### No preamble above the block

The block starts at `**Done**`. Prose above it is the babble, whatever shape it takes. Banning
"Here's a summary of what I did" is not enough, because the leak arrives as content that feels
earned:

- **A closing fact.** "0.5.3 published with main.js and manifest.json — BRAT will pick it up."
  That is a `Done` bullet standing outside the block.
- **An arc recap / victory lap.** "That closes the sprint. All three plans from the spec are
  implemented, merged, released and running." Zero new information — every clause restates a
  `Done` bullet in a more pleased tone.

**The test for every sentence you're about to put above the block:** already in `Done`? Delete it.
Not in `Done` but true and useful? It *is* a `Done` bullet — move it in. Neither? It doesn't
belong in a verdict.

## Tables, diagrams, emoji

Welcome when they carry information faster than a sentence would, noise otherwise. In the block
each costs lines against the cap.

**Small tables** — three or more items sharing the same two or three fields, compared down a
column. Four rows is about the limit. One item, or items that don't share fields, stay bullets.

```
| service | ver   | state |
|---------|-------|-------|
| aarni   | 0.5.3 | ✅    |
| mac     | 0.5.1 | ⏳    |
| iphone  | 0.5.1 | ⏳    |
```

**ASCII diagrams** — only when the relationship *is* the information: a pipeline, a sequence, a
tree, a progress bar. A few lines. Never draw a box around something a sentence already said.

```
mac ──┐
      ├──> aarni (b179cd1, 273 files) ──> ✅
iphone ┘
```

**Emoji** — functional markers only, at most one per line, always the same meaning:

| ✅ | done, passing, green |
| ⚠️ | works with a caveat |
| 🔴 | broken, failing |
| ⏳ | pending, waiting on something |
| → | the recommended next action |

The celebratory set — 🎉 🚀 ✨ 🔥 — is banned outright. They mark tone, not state, and tone is
what this mode removes.

## What this never applies to

- **Deliverables keep their own shape.** A file you wrote, a plan, a review, a commit message —
  those follow their own rules. Only your own talking is governed here.
- **Bad news is never compressed away.** If something broke, is uncertain, or you didn't verify a
  claim, it goes in full — in `Blocked` if there's a block, in the answer otherwise. Brevity
  applies to padding, never to a caveat the user needs. Cutting a real risk to hit a line cap is
  the one failure mode that matters here.
- **Real explanations stay long enough to work.** When they ask *why*, or the answer has genuine
  nuance, give it. Terse means no padding, not lossy.

## With /bell

If `/bell` is on, its `🔔 Ping — <headline>` line goes above the block and counts as the headline,
not a fourth section. The block replaces bell's evidence table. Bell's own trigger is roughly
Layer 2's trigger, so they fire together.

## Turning it off

`/stop-babbling off` — confirm with the exact line in the table above.

$ARGUMENTS
