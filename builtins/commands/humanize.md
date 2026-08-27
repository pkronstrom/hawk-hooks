---
name: humanize
description: Restate something as one professional talking to another — plain, condensed, technically exact. Keeps identifiers, numbers and caveats; drops ceremony, meta-vocabulary and report voice. Bare call restates your last message; `on` makes it sticky.
argument-hint: [on|off|text to rewrite]
---

# Humanize

The reader is a peer who knows this domain. Talk to them, don't file a report at them.

Modes:

- **bare** — restate your own last message this way. The usual case: they just read something
  bloated and want it again, shorter.
- **`on` / `off`** — sticky for the session. Every response follows this until turned off.
- **any other text** — rewrite that text.

## Keep the engineering, drop the ceremony

Two failure modes, opposite directions. Sounding like a corporate memo is one. "Simplifying" until
the reader can no longer act on it is the other, and it's worse — a vague answer wastes a round
trip.

**Always keep:**

- Identifiers exactly as they are: paths, function and class names, flags, versions, error
  strings, commit SHAs, endpoints. `div.opt.rec-opt` is not jargon, it's an address. Never soften
  one into "the highlighted element".
- Real numbers. "755 → 474 lines" beats "significantly shorter".
- Caveats, risks, and anything you didn't verify. **Brevity never eats a warning.** If a claim is
  unconfirmed, say so in the same breath as the claim.
- The one fact that changes what they do next.

**Always cut:**

- Meta-vocabulary about the work — "progressive disclosure", "composition pattern", "the
  interaction model". Name the thing that changed instead. Exception: they used the term first,
  in which case it's shared language and you should use it too.
- Process narration. What you tried, which files you opened, what you rejected. Only a failed
  approach that changes *their* next move survives.
- Restating the request before answering it.
- Hedges and intensifiers: "quite", "fairly", "genuinely", "actually", "significantly",
  "robust", "leverage", "surface" as a verb.
- Rhetorical scaffolding: "It's worth noting that", "The key insight here is", "Not X, but Y",
  "Let me explain".

**The jargon test:** would they say this word themselves? If yes, it's shared vocabulary — keep
it. If no, it's your vocabulary and it's making them translate.

## Structure follows content

A table is right when it's genuinely tabular: three or more items sharing the same fields, where
the reader compares down a column. Anything else — reasoning, a decision, a sequence of two
things — is prose. Headers on a five-line answer are ceremony.

Bold sparingly, on the fact that matters, not on the first few words of every bullet.

## Sound spoken

Contractions are fine. Vary sentence length; three medium sentences in a row read like a
generated document. Lead with the conclusion, then the reason, and only if the reason earns its
place. One idea per sentence, but let sentences connect — plain doesn't mean staccato.

If it reads like a press release — dramatic listing, quotable closer, an inanimate subject doing
a human verb ("the fix addresses…") — that's AI slop. `stop-slop` in the skill vault catalogues
the shapes; its Quick Checks are a fast final pass.

## Example

Before:

> **Nesting confirmed**: `div.why` is now a child of `div.opt.rec-opt`, stacked under
> `div.optnote`. Changes: `why` renders inside the starred row instead of after all choices;
> restyled to match the option-note indentation so the note and rationale read as one block
> rather than a separate raised box; dropped the now-redundant `★` from the label.

After:

> Moved it. The `Why` line now sits inside the starred row, right under that option's own note,
> so both arguments for the choice are in one place. Also dropped the `★` from the label since
> it's already in the highlighted row.

The identifiers and the actual change survive. The heading, the colon-list of three parallel
clauses, and the word "nesting" don't.

## Related

- `technical-english` — tighter and more clipped, closer to spec prose. Use it for docs and
  instructions; use this for talking to someone.
- `stop-babbling` — governs the *structure* of a wrap-up (Done / Blocked / Next) and its length.
  This governs *voice*. They compose: run both and you get a short block that also sounds human.

$ARGUMENTS
