---
name: agy
description: Shorthand for /antigravity — run Google models via Antigravity CLI (agy). Default model is gemini-3.6-flash-high.
tools: [claude, codex]
---

Alias for `/antigravity`. Follow that command's playbook verbatim — same CLI (`agy`), same defaults, same caveats (effort lives in the model slug, stdin is ignored, `--json-schema` binds `gemini-*` only), and the same quota-failure rule: ask before falling back to OpenRouter via `pi`.
