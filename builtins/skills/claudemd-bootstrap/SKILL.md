---
name: claudemd-bootstrap
description: Drop Karpathy's behavioral-guidelines CLAUDE.md into a project (or the user's global config). Fetches the current upstream copy, falls back to the bundled backup when offline. Never overwrites an existing CLAUDE.md.
---

# claudemd-bootstrap

Installs the behavioral-guidelines `CLAUDE.md` from
[multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) —
four sections (think before coding, simplicity first, surgical changes, goal-driven execution)
aimed at the common LLM coding failure modes.

## 1. Get the content

Try upstream first, since the bundled copy goes stale:

```bash
curl -fsSL --max-time 20 \
  https://raw.githubusercontent.com/multica-ai/andrej-karpathy-skills/main/CLAUDE.md \
  -o /tmp/karpathy-CLAUDE.md
```

Note the **raw** host — the GitHub `blob/` URL serves an HTML page, not the file.

On any failure (no network, non-zero exit, empty file, HTML instead of markdown) fall back to
`karpathy-CLAUDE.md` next to this file. **Say which source you used**, every time — "upstream"
or "bundled backup, last refreshed <date from git log>". Silently installing a stale copy is the
one way this skill misleads.

Sanity-check whichever you got: it starts with `# CLAUDE.md` and contains the four numbered
section headers. If not, stop and report — don't write a 404 page into their config.

## 2. Pick the destination

Match what the project already does rather than imposing a layout:

| Situation | Target |
|---|---|
| `./CLAUDE.md` exists | that file |
| `./.claude/CLAUDE.md` exists | that file |
| Neither, and it's a project | `./CLAUDE.md` |
| User said "global" / "everywhere" / "all projects" | `~/.claude/CLAUDE.md` |

Ambiguous between project and global — ask, one question. Don't guess: global changes every
session on the machine.

## 3. Write, or merge — never clobber

**If the target does not exist:** write the content verbatim. Done.

**If it exists:** it holds the user's own instructions and this file's own advice is "merge with
project-specific instructions as needed." Never overwrite. Read it first, then offer:

1. **Append** — add the guidelines as a clearly-marked section at the end. Safe default; costs
   some duplication if their file already covers the same ground.
2. **Merge** — fold in only the sections theirs doesn't already cover, and say which you skipped
   and why. Better result, needs their review.
3. **Side-by-side** — write to `CLAUDE.karpathy.md` and let them merge by hand.
4. **Skip.**

Recommend **merge** when their file is substantial, **append** when it's a stub. If their file
already contradicts a guideline (e.g. a project that mandates broad refactors against §3's
surgical-changes rule), name the conflict rather than stacking contradictory instructions — two
rules pointing opposite ways is worse than either alone.

## 4. Report

State the source (upstream or backup), the destination path, and the mode used (fresh write /
append / merge). If merging, list which sections were skipped as already-covered.

## Refreshing the bundled backup

The backup exists for offline use and will drift from upstream. To update it, fetch to
`karpathy-CLAUDE.md` in this skill's directory, then sync it through hawk (`hawk update
hawk-builtins --force && hawk sync`) so the installed copy matches. Mention the drift if the
backup is being used and is visibly old.
