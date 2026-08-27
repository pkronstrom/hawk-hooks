---
name: bell
description: Toggle an end-of-work "🔔 Ping" notification for this session, or set a custom watch condition (e.g. "me when comments on pr") to ping on instead of the default. Optional voice narration via /bell voice.
---

# bell

A session-scoped habit, not a hook — the instruction lives in this conversation and applies
from the moment you call `/bell` until `/bell off`. No config beyond the voice-snippet manifest
below: just do it, every turn, until told to stop.

## Default mode — `/bell` with no arguments

Turn it on: from this point in the session forward, whenever a genuine unit of work concludes —
not every trivial reply, but the moments that actually warrant "come look" (a task finishes, a
blocker resolves, tests pass, a PR becomes mergeable, a long-running background command or
subagent completes) — do both of these before ending that turn:

1. Call the `PushNotification` tool with a one-line summary of what finished.
2. Lead the chat response with `🔔 Ping — <one-line summary>`, in the style below.

### The style (from actual use)

> 🔔 Ping — the blockers are resolved.
>
> **PR #722 is now mergeable and CI is running for the first time.**
>
> | | |
> |---|---|
> | Branch | 32 commits, rebased onto `main`, 0 behind, no merge commits |
> | Local suite | **64 passed** |
> | Mergeable | `MERGEABLE` — was `CONFLICTING` |
> | CI | `E2E` + `CI` running |

Decisive headline first, then whatever compact evidence backs it up — a table when there are
several facts worth stating, plain sentences when there's one. Never a bare "🔔 Ping — done."
with nothing behind it.

**Applies to background completions too.** A `<task-notification>`, or a backgrounded Bash
command or subagent finishing, counts as "work ending" — treat the turn where you report it the
same as any other trigger, not as a status line to skim past.

**Confirm out loud when turning it on** — one line, no ceremony: "🔔 Bell on — I'll ping you
when work finishes."

## Voice / narrated — `/bell voice`

Stacks on top of whichever mode is already active (default or a custom condition) — it changes
**how** the ping reaches the user, not what triggers it. Say so when toggling it: "🔔 Bell:
voice on" / "🔔 Bell: voice off".

With voice on, every ping also calls `tts` (the skill — load it) to say a **short spoken tag,
1–5 words**, naming where things landed, not restating the finding: `"verdict ready"`, `"tests
pass"`, `"questions pending"`, `"CI green"`, `"comment landed"`. The chat message and
`PushNotification` still carry the real detail per the format above — the voice line is a cue
to go look, not the report itself. Pick words that match what actually happened; don't recycle a
fixed phrase regardless of outcome, and don't narrate failure as if it were success (`"tests
failing"`, not `"tests pass"`, when they didn't).

`/bell voice off` turns narration back off without touching whatever's being watched for.

### Reusing snippets — the vocabulary manifest

`tts` already caches every synthesis it does by the exact text spoken, so speaking the *same*
short tag twice is already an instant replay with no new synthesis. `vocab.sh`, next to this
file, is the readable index into that vocabulary — the cache itself is keyed by hash and has no
such index.

**Before wording a ping**, list what's already in use:

```bash
<skill-dir>/vocab.sh list
```

Empty or missing on first use — that's fine, proceed straight to minting wording. Otherwise,
prefer an existing line if one genuinely fits what just happened: reusing `"tests pass"`
verbatim is both a cache hit and a consistent vocabulary the user learns to recognize by ear.

Only mint new wording when nothing in the list fits — 1–5 words, same register as the existing
entries.

**Record every time you speak, reused phrase or new — never only "when it's new."** That
condition is the failure mode: it makes recording a second thing to remember *after* the
notification already landed, and the step that isn't load-bearing for the ping itself is exactly
the one that gets silently dropped. `vocab.sh add` is idempotent, so there's no cost to calling
it unconditionally. Pair it with every `tts` call, same turn, not as a follow-up:

```bash
<skill-dir>/vocab.sh add "verdict ready" && <tts call>
```

Never reuse a phrase for an outcome it doesn't match just to hit the cache — accuracy over
snippet economy every time. The manifest is global across sessions and projects on purpose: the
vocabulary is meant to converge over time, not restart per project.

## Turning it off — `/bell off`

Stop doing both default-mode actions for the rest of the session. If a custom watch condition
(below) is active, cancel it too: `ScheduleWakeup({stop: true})`. Voice, if on, turns off with
it — a fresh `/bell` later starts from silent. Confirm: "🔔 Bell off."

## Custom condition — `/bell <description>`

Anything after `/bell` that isn't `off` or `voice`/`voice off` replaces **what counts as done**,
not the notification mechanism — everything above about *how* to ping (including voice, if it's
on) still applies.

Examples: `/bell me when comments on pr`, `/bell when the deploy finishes`, `/bell when CI goes
green`.

1. Restate the condition back in one line so you both know what's being watched for.
2. If it resolves inside the current turn — you can just check it right now (CI is already
   green, the comment is already there) — fire the Ping immediately per the default-mode format,
   say the condition is already satisfied, and ask whether to keep bell on for future
   completions or turn it off.
3. Otherwise (the common case — a PR comment, a deploy, a CI run that hasn't finished) it needs
   checking **later**, not guessed at now:
   - Use `ScheduleWakeup` to re-check on an interval sized to how fast the condition can actually
     change (a CI run: single-digit minutes; a PR comment: tens of minutes) — follow that tool's
     own guidance for picking `delaySeconds`, and don't poll faster than the thing being watched
     could plausibly change.
   - Each wake, check the **real** condition (`gh pr view --json comments`, `gh run view`,
     whatever the description implies) — never assume or fabricate a result to close the loop
     early.
   - The moment it's true, fire the Ping (`PushNotification` + chat message, `tts` too if voice
     is on) and stop the wakeup loop (`ScheduleWakeup({stop: true})`).
4. Only one watch condition is active at a time. A new `/bell <description>` replaces whatever
   was being watched before — say so when it does.

## Examples

```
/bell                          # on: ping on real work-completion moments
/bell off                      # off — cancels any custom watch and voice too
/bell me when comments on pr   # watch this PR, ping when a comment lands
/bell voice                    # add narration to whichever mode is active
/bell voice off                # narration off, watch/default mode unchanged
```
