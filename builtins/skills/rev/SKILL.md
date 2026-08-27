---
name: rev
description: Use when the user invokes /rev to review code changes and supplies a depth or cross-vendor mode such as 1, 2, 3, x, xflash, xhigh, or xultra.
---

# Rev

Route a compact review invocation to the installed `review-work` skill. Do not
reimplement its dispatcher or change its backend routing.

## Invocation

`/rev [mode] [panel-roster arguments]`

| Mode | Delegate to | Review configuration |
| --- | --- | --- |
| `1` | `/rev1` | One Terra code-quality reviewer at `high` |
| `2` | `/rev2` | Terra code-quality + design-alignment reviewers at `xhigh` |
| `3` | `/rev3` | Three Sol reviewers: code quality, design alignment, architecture |
| `x` | `/revx` | Standard four-vendor panel |
| `xflash` | `/revxflash` | Fast, low-cost four-vendor panel |
| `xhigh` | `/revxhigh` | Strong four-vendor panel |
| `xultra` | `/revxultra` | Six-agent maximum-coverage panel |

With no mode, ask the user to choose one. Reject an unknown mode and show the
valid values.

For panel modes, pass all text after the mode unchanged as the roster argument
string. This preserves the existing bare-name and `+model`/`-model` grammar.

## Execution

Read the sibling `review-work/SKILL.md` and follow the selected shortcut's
configuration. Detect the diff and produce the review exactly as that skill
specifies.

The dispatcher selects the backend by lane: use `codex exec` for Codex lanes and
`claude --print` for Anthropic lanes. Never run an Anthropic reviewer through
Codex.
