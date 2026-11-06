---
name: eng-converge
description: Sticky engineering standard — simplest thing that works, YAGNI, invariants over duplicated state, names over comments. Every substantial task ends in exactly one of three states; no patching without convergence. Output stays short and readable. `off` to end.
argument-hint: [on|off]
disable-model-invocation: true
---

# Converge

Sticky, session-scoped. On from this call until `/eng-converge off`.

Arguments: nothing or `on` turns it on, `off` turns it off. Anything else — treat as `on` and
don't ask.

Confirm with `Converge mode on.` / `Converge mode off.` and nothing else.

## In session chat

Fewest precise words. Direct. Lead with the answer.

Identifiers, numbers and caveats survive the cut — everything else is negotiable. Full rules in
`humanize` (talking to a peer) and `technical-english` (docs and instructions); this mode assumes
them without restating them.

## In the code

Simplicity in the system *and* in the mental model needed to hold it. The second one is the one
that gets forgotten: a clever mechanism that saves ten lines and costs a paragraph of explanation
is a loss.

- **YAGNI.** No guardrails for failures that haven't happened, no caching before something is
  measurably slow, no abstraction with one caller, no configurability nobody asked for.
- **One invariant beats two places that agree.** Prefer a single source of truth over duplicated
  logic, duplicated conditionals, or derived state kept in sync by hand. If the same condition is
  checked twice, one of the checks is a future bug.
- **No redundant work.** Recomputing, re-fetching, re-validating what the caller already
  established.
- **Names instead of comments.** A comment explaining *what* the code does is a naming failure.
  Comments earn their place only for *why*: the non-obvious constraint, the reason the obvious
  approach fails. Never restate the line below.

Reach for what already exists, stopping at the first that holds: the standard library, then a
native platform feature (a DB constraint, a CSS rule, an HTML input type), then a dependency
already installed, then your own few lines. A new dependency needs a reason bigger than the code
it saves.

## Boundaries

The interface is the expensive part to change; internals are cheap. Design the call site first,
then make the inside serve it.

- **Narrow.** Every exported name is a promise you maintain. Publish the fewest that let the real
  use case be expressed.
- **Expressive.** The correct call is the obvious one, and a wrong one is hard to spell. Prefer a
  type that cannot hold a bad state over a comment saying don't.
- **Compact.** If describing the module needs an "and", it's two modules.
- **No behaviour-changing boolean flags.** Take the meaning, not the switch: `timeout=None`, not
  `retry=True`.
- **One word per concept**, the same word in function names, parameters, errors and docs. A
  synonym reads as a second concept.
- **Effects at the edges, plain data through the middle.** Ownership — who opens, who closes — is
  stated at the boundary, not left to convention.
- **Callers never need the internals to use it correctly.** If they do, the boundary is in the
  wrong place: move it, or inline the thing and stop pretending it's an abstraction.

## Where simplicity stops

Never simplify away validation at a trust boundary, error handling that prevents data loss,
security, accessibility basics, or anything explicitly asked for. Avoiding unnecessary guardrails
means the unnecessary ones; a check on untrusted input is not one.

Non-trivial logic leaves one runnable check behind — the smallest thing that fails if the logic
breaks. Not a suite, not fixtures: one check.

A deliberate shortcut with a known ceiling gets a comment naming the ceiling and the way out
(`# global lock; per-account locks if throughput matters`). That is a why, so it earns its place.

## Ending a task

Every substantial task ends in exactly one of these, stated plainly:

1. **Success** — the real motivating case works. Not the test, not a simplified version: the
   thing that prompted the work.
2. **Meaningful progression** — one blocker is removed and the next is isolated, with evidence
   for what it is. Say what the evidence was.
3. **Honest stop** — going further would cost excessive scope, debt, brittleness, or tangled
   logic. Say which one, and what you'd need to proceed.

Do not continue patching without convergence. Two failed fixes on the same symptom means the
model of the problem is wrong; stop and say so rather than trying a third.

Partial work is left cleaner, clearer, and easier to diagnose than it was found — no dead
scaffolding, no half-renamed identifiers, no debug output.

## Related

- `ponytail` — the same instinct applied as a one-shot review. This is the standing mode.
- `stop-babbling` — governs the shape of a wrap-up. Composes with this.

$ARGUMENTS
