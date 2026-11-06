---
name: grill-docs-singlefile
description: "Like grill-singlefile, but also writes a CONTEXT.md glossary and ADRs from the answers. /grill-docs-singlefile."
---

# grill-docs-singlefile

`grill-singlefile` with the documentation discipline of `domain-modeling` folded in — the async
counterpart to the vault's `grill-with-docs`.

**Load both skills first**: `grill-singlefile` (interview mechanics, the HTML template, the
recommendation rules) and `domain-modeling` (glossary discipline, `CONTEXT.md` format, when an
ADR is warranted). Everything in `grill-singlefile` applies unchanged, including its
`template.html` — use that file, do not write a second copy here. Two templates drift.

This skill adds only what changes.

## The one structural difference: docs are drafted, not written

Live `grill-with-docs` updates `CONTEXT.md` the moment a term is resolved, because the user is
right there to confirm it. Here they are not, so **nothing lands on disk while generating the
file.** A glossary entry written from an unconfirmed assumption is worse than no entry: it reads
as settled vocabulary and gets cited later.

Instead, draft the docs, put their approval *in* the file as questions, and write them when the
user pastes their answers back.

## Extra question groups

Both new kinds fit the existing radio-plus-notes shape, so the template needs no changes.

**Glossary questions** — group them under `Glossary`. Use `domain-modeling`'s triggers: a term
that conflicts with the existing `CONTEXT.md`, a fuzzy or overloaded term, or a term the code and
the user seem to disagree about. Options are the candidate canonical terms; `recommend` is your
pick; `why` carries the evidence, especially any contradiction you found in the code.

```js
{ g: "Glossary", id: "G1", t: "\"account\" — Customer or User?",
  ctx: "CONTEXT.md has no entry. src/billing/ uses `account` for the paying entity; src/auth/ uses it for the login.",
  opts: [
    { t: "Customer (paying entity), rename the auth usage to User",
      note: "Touches 14 call sites in src/auth/." },
    { t: "User (login), rename the billing usage to Payer" },
    "Keep both, disambiguate by module"
  ],
  recommend: 0,
  why: "Billing's meaning is the one that appears in your invoices and in customer-facing copy, so it is the one with an external contract. The auth rename is mechanical." }
```

**ADR questions** — group them under `Decisions to record`. `domain-modeling`'s bar still
applies, all three: hard to reverse, surprising without context, and the result of a real
trade-off. Miss any one and there is no ADR, so most sessions produce zero to two of these. Do
not pad the group to look thorough.

Give each proposed ADR its title and one-line consequence in `ctx`, then:

```js
{ g: "Decisions to record", id: "A1", t: "ADR: per-vault tokens for authorisation",
  ctx: "Hard to reverse (every client re-issues tokens), surprising (most servers use one token), real trade-off (isolation vs. simplicity).",
  opts: ["Record as drafted", "Record with changes (say what in notes)", "Don't record — not worth an ADR"],
  recommend: 0,
  why: "It meets all three ADR tests and a future reader will otherwise ask why there isn't a single server token." }
```

Put the drafted ADR body in the question's `ctx` only if it is short. A long draft belongs in the
`why`, or summarize the decision and consequences and write the full body on resume — the file is
for deciding, not for reviewing prose.

## Ordering

`Glossary` first, then the design-decision groups from `grill-singlefile`, then
`Decisions to record` last. Vocabulary settles before the decisions that use it, and an ADR only
makes sense once the decision it records has been confirmed above it.

## On resume — write the docs

When the summary comes back, apply `grill-singlefile`'s three states (`confirmed ★`,
`★ default not reviewed`, `CHANGED` / `SOMETHING ELSE`), then:

1. **Glossary** — write confirmed and changed terms into `CONTEXT.md` in `domain-modeling`'s
   `CONTEXT-FORMAT.md` format. Create the file if absent. Keep it a glossary and nothing else:
   no implementation detail, no spec, no scratch notes.
2. **ADRs** — write one file per approved ADR under `docs/adr/`, numbered in sequence after the
   highest existing number, using `ADR-FORMAT.md`. "Record with changes" means apply the note
   before writing. "Don't record" means write nothing, and don't argue with it in the report.
3. **`not reviewed` glossary terms are not confirmed vocabulary.** A term the user never looked at
   still goes in, because the recommendation stands by default — but say which entries arrived
   that way, so they know what to re-read. This matters more for a glossary than for a design
   decision: vocabulary written down starts getting cited as if it were agreed.
4. Report the files written and the entries skipped, per `grill-singlefile`'s handoff step.

If a repo has a `CONTEXT-MAP.md`, it has multiple contexts — put each term in the right one per
`domain-modeling`'s file-structure rules rather than dumping everything at the root.
