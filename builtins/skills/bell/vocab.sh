#!/usr/bin/env bash
# vocab.sh — the /bell voice snippet manifest.
#
# tts already caches synthesis by exact text (voice|speed|lang|text), so
# speaking the same short tag twice is already free. What's missing is
# visibility into what's already in that cache, since it's keyed by hash with
# no readable index. This is that index: a flat, deduped list of phrases
# /bell has spoken before, so the agent can prefer reuse over minting new
# wording — a cache hit *and* a consistent vocabulary the user learns by ear.
#
# Usage:
#   vocab.sh list              # one phrase per line, empty if none yet
#   vocab.sh has "<phrase>"    # exit 0 if already present, 1 otherwise
#   vocab.sh add "<phrase>"    # append if new; no-op (exit 0) if already present
#
# BELL_VOCAB overrides the manifest path (default: ~/.local/state/bell/voice-snippets.txt).
# Global on purpose — not per-project — so the vocabulary converges over time.

set -eu

VOCAB="${BELL_VOCAB:-$HOME/.local/state/bell/voice-snippets.txt}"

cmd="${1:-}"
shift || true

case "$cmd" in
  list)
    [ -f "$VOCAB" ] && cat "$VOCAB" || true
    ;;
  has)
    phrase="${1:-}"
    [ -n "$phrase" ] || { echo "usage: vocab.sh has \"<phrase>\"" >&2; exit 2; }
    [ -f "$VOCAB" ] && grep -qxF -- "$phrase" "$VOCAB"
    ;;
  add)
    phrase="${1:-}"
    [ -n "$phrase" ] || { echo "usage: vocab.sh add \"<phrase>\"" >&2; exit 2; }
    mkdir -p "$(dirname "$VOCAB")"
    touch "$VOCAB"
    grep -qxF -- "$phrase" "$VOCAB" || echo "$phrase" >> "$VOCAB"
    ;;
  *)
    echo "usage: vocab.sh {list|has <phrase>|add <phrase>}" >&2
    exit 2
    ;;
esac
