# v2 Code Review Fixes Plan

> **Status:** pending
> **Branch:** `v2`
> **Review date:** 2026-02-23
> **Review method:** 4-agent parallel review (code quality, design alignment, architecture, UI/UX) + independent second-opinion validation

## Context

Full review of the v2 branch (154 files, +26k/-10k lines, 30 commits) surfaced 43 findings. A second-opinion pass validated 16/20 sampled findings as TRUE, 3 as PARTIAL (overstated), and 1 as WONTFIX. This plan covers the confirmed, actionable issues organized into implementation phases.

## Validation Summary

| Finding | Verdict | Notes |
|---------|---------|-------|
| Shell injection in runner env exports | TRUE | Crafted metadata key injects shell |
| Profile path traversal | TRUE | No `../` containment |
| Scope-chain fallback incomplete | TRUE | Unregistered leaf dropped |
| Prune-only removals skip sync | TRUE | `any_changes` gate bypassed |
| Cache key collisions | TRUE | `/` and `\` both become `_` |
| MCP merge crash on malformed | TRUE | `.items()` without type guard |
| Gemini TOML body escaping | TRUE | `'''` in body breaks TOML |
| Hook metadata dropped without events | TRUE | Parsed fields lost on fallback |
| Autosync bypasses cache | TRUE | `force=True` defeats optimization |
| Unregistered local scope unsynced | PARTIAL | Auto-register mitigates in normal flow |
| Destructive item delete no confirm | PARTIAL | Package delete has confirm, item delete does not |
| Prompts-canonical incomplete | WONTFIX | Intentional backward compat |
| Resolver type-unsafe for lists | TRUE | Strings become char lists |
| Package update assumes type/name | TRUE | `KeyError` on malformed |
| Empty config treated as missing | TRUE | Falsiness check drops valid layer |
| Event aliases not normalized | TRUE | Raw tokens stored |
| Codex TOML path escaping | TRUE | Quotes/backslashes break TOML |
| OpenCode stdout hang | PARTIAL | Only with large output |
| Registry browser not wired | TRUE | Dead code |
| Private symbol leakage | WONTFIX | Internal reuse, not defect |

---

## Phase 1: Security & Data Integrity (HIGH — do first)

These can cause data loss, shell injection, or silent sync failures.

### Task 1.1: Sanitize runner env variable names
**Files:** `src/hawk_hooks/adapters/base.py:291`
**Problem:** `var_name` from hook metadata interpolated into `export {var_name}=...` without validation.
**Fix:** Validate `var_name` against `^[A-Za-z_][A-Za-z0-9_]*$` regex before interpolation. Reject or skip invalid names with a warning.
**Tests:** Add test with malicious `env=` metadata key containing shell metacharacters.

### Task 1.2: Contain profile path traversal
**Files:** `src/hawk_hooks/v2_config.py:135,:148`
**Problem:** Profile name joined as `{name}.yaml` with no `../` containment.
**Fix:** Validate profile names with the same `_validate_name()` pattern used by registry, or at minimum reject names containing `/`, `\`, `..`.
**Tests:** Add test attempting `../../../etc/passwd` as profile name.

### Task 1.3: Fix scope-chain fallback for unregistered leaf dirs
**Files:** `src/hawk_hooks/scope_resolution.py:53,:56`
**Problem:** When registered parent chain exists, unregistered local leaf config is dropped instead of appended.
**Fix:** After building registered chain, check if cwd has local `.hawk/config.yaml` and is not already in the chain — if so, append it as the innermost layer.
**Tests:** Add test: registered parent + unregistered child with local config → both appear in chain.

### Task 1.4: Trigger sync on prune-only package removals
**Files:** `src/hawk_hooks/package_service.py:202,:306,:321`
**Problem:** `any_changes` only set on add/update; prune-only removals don't trigger sync.
**Fix:** Set `any_changes = True` when prune removes items from registry.
**Tests:** Add test: prune removes a component → `sync_on_change` path is taken.

### Task 1.5: Fix sync cache key collisions
**Files:** `src/hawk_hooks/v2_sync.py:24`
**Problem:** Cache key normalization maps both `/` and `\` to `_`, so `/a/b` and `\a\b` (or `/a_b`) can collide.
**Fix:** Use URL-safe base64 or hex hash of the resolved path instead of character replacement.
**Tests:** Add test with two paths that would collide under current scheme → distinct cache keys.

### Task 1.6: Guard MCP merge against malformed config
**Files:** `src/hawk_hooks/adapters/base.py:508,:573`
**Problem:** Assumes `mcpServers` is a dict, calls `.items()` without type guard.
**Fix:** Add `isinstance(section, dict)` guard before `.items()` calls. Log warning and skip on non-dict.
**Tests:** Add test with `mcpServers: "not a dict"` → graceful skip, no crash.

---

## Phase 2: Correctness Bugs (HIGH — fix next)

These cause incorrect behavior but aren't security issues.

### Task 2.1: Fix Gemini TOML body escaping for triple-quotes
**Files:** `src/hawk_hooks/adapters/gemini.py:51`
**Problem:** `'''` in markdown body produces invalid TOML multi-line literal strings.
**Fix:** Switch to TOML basic multi-line strings (`"""..."""`) with proper escaping, or use a TOML library for serialization.
**Tests:** Add test with markdown body containing `'''` → valid TOML output that round-trips.

### Task 2.2: Preserve parsed hook metadata when events absent
**Files:** `src/hawk_hooks/hook_meta.py:62`
**Problem:** Parser falls through when `events` is empty, losing parsed timeout/env/deps/description.
**Fix:** Return `HookMeta` with all parsed fields regardless of whether events were found. Let callers decide how to handle event-less metadata.
**Tests:** Add test: hook with `timeout=30` but no `events=` → metadata.timeout == 30.

### Task 2.3: Fix autosync cache bypass
**Files:** `src/hawk_hooks/v2_interactive/dashboard.py:2050,:2072`
**Problem:** Dashboard sync always uses `force=True`, defeating cache optimization.
**Fix:** Only use `force=True` for explicit user-triggered sync actions. Auto-sync should use `force=False` to benefit from cache.
**Tests:** Add test: auto-sync with unchanged config → no adapter `sync()` calls.

### Task 2.4: Fix empty config falsiness in scope builder
**Files:** `src/hawk_hooks/scope_resolution.py:57`
**Problem:** `if not dir_config` treats empty dict `{}` as missing, dropping valid layer.
**Fix:** Change to `if dir_config is None`.
**Tests:** Add test: empty dir config `{}` → layer still included in chain.

### Task 2.5: Normalize event aliases in metadata parser
**Files:** `src/hawk_hooks/hook_meta.py:102`
**Problem:** Raw event tokens stored without normalizing aliases like `pre_tool` → `pre_tool_use`.
**Fix:** Apply `_normalize_hawk_event()` from `event_mapping.py` to each parsed event.
**Tests:** Add test: `events=pre_tool` → `meta.events == ["pre_tool_use"]`.

### Task 2.6: Fix Codex TOML notify path escaping
**Files:** `src/hawk_hooks/adapters/codex.py:665`
**Problem:** Raw command strings written into TOML without escaping quotes/backslashes.
**Fix:** Use `_escape_toml_string()` or equivalent for each notify command path.
**Tests:** Add test with path containing quotes → valid TOML output.

### Task 2.7: Fix resolver type safety for list fields
**Files:** `src/hawk_hooks/resolver.py:109`
**Problem:** `list()` applied to unchecked values; strings become char lists.
**Fix:** Wrap with type check: `val if isinstance(val, list) else []`.
**Tests:** Add test: config with `skills: "tdd"` (string, not list) → treated as empty, not `['t','d','d']`.

---

## Phase 3: Robustness (MEDIUM — can batch)

Defensive fixes for edge cases and malformed input.

### Task 3.1: Validate package item schema
**Files:** `src/hawk_hooks/package_service.py:115,:370`
**Problem:** Assumes every item has `type`/`name` keys; `KeyError` on malformed.
**Fix:** Add `.get()` with skip-and-warn for items missing required keys.
**Tests:** Add test: malformed package item without `type` → skipped with warning.

### Task 3.2: Handle non-dict config shapes in load_packages
**Files:** `src/hawk_hooks/v2_config.py:332`
**Problem:** Non-dict shape can crash downstream callers.
**Fix:** Add `isinstance` guard, return empty dict on non-dict.

### Task 3.3: Fix migration input validation
**Files:** `src/hawk_hooks/migration.py:53,:124`
**Problem:** Trusts v1 shapes without validation; I/O outside exception handling.
**Fix:** Add type guards for expected dict/list shapes. Wrap I/O in try/except.

### Task 3.4: Fix managed-config TOML for CRLF files
**Files:** `src/hawk_hooks/managed_config.py:51`
**Problem:** Regexes are LF-only; CRLF files won't match.
**Fix:** Normalize line endings before regex matching, or use `\r?\n` in patterns.

### Task 3.5: Handle OpenCode plugin stdout consumption
**Files:** `src/hawk_hooks/adapters/opencode.py:188`
**Problem:** Generated plugin pipes stdout but doesn't consume it; verbose hooks can hang.
**Fix:** Redirect stdout to `/dev/null` or consume it in the generated plugin code.

---

## Phase 4: UX Polish (MEDIUM-LOW — improve iteratively)

### Task 4.1: Add confirmation for item delete in toggle view
**Files:** `src/hawk_hooks/v2_interactive/dashboard.py:1477`
**Problem:** `d` key on item row deletes without confirmation (package delete has confirm but item delete doesn't).
**Fix:** Add y/N confirmation prompt before item deletion.

### Task 4.2: Wire registry browser into dashboard menu
**Files:** `src/hawk_hooks/v2_interactive/dashboard.py:266,:378,:395`
**Problem:** Handler exists but no menu action routes to it (dead code).
**Fix:** Add "Registry" option to `_build_menu_options()` and route it in the action handler.

### Task 4.3: Improve TUI import failure messaging
**Files:** `src/hawk_hooks/cli.py:1754`
**Problem:** Falls back to help text without explaining why TUI failed.
**Fix:** Print the actual import error before falling back.

### Task 4.4: Standardize keybinding hints across screens
**Files:** `src/hawk_hooks/v2_interactive/config_editor.py:111`, `toggle.py:395`
**Problem:** Inconsistent hints (some show `q` only, some show `Esc`, some omit nav keys).
**Fix:** Create shared hint constant/helper and apply across all TUI screens.

### Task 4.5: Use theme tokens consistently
**Files:** `src/hawk_hooks/v2_interactive/config_editor.py:42`, `wizard.py:46`, `uninstall_flow.py:84`
**Problem:** Several screens hardcode raw colors instead of semantic theme tokens.
**Fix:** Replace hardcoded color strings with theme helper calls.

### Task 4.6: Show missing component names in setup
**Files:** `src/hawk_hooks/v2_interactive/dashboard.py:1998,:2039`
**Problem:** Shows total count but not what is missing.
**Fix:** List the missing component names before asking repair/remove.

---

## Phase 5: Architecture (LOW — future work)

These are structural observations for longer-term improvement. Not blocking merge.

### Task 5.1: Extract dashboard action handlers
**Observation:** `dashboard.py` is 2298 lines handling 8+ concerns.
**Direction:** Extract package ops, codex consent, missing-component repair, environment settings into separate handler modules.

### Task 5.2: Break adapter base class responsibilities
**Observation:** `ToolAdapter` ABC owns orchestration, linking, runner gen, and MCP merge.
**Direction:** Extract runner generation and MCP merge into composable mixins or separate utilities.

### Task 5.3: Replace dashboard→CLI coupling with service calls
**Observation:** Dashboard calls `cmd_download` directly and catches `SystemExit`.
**Direction:** Extract download service (like `package_service.py`) and use from both CLI and TUI.

### Task 5.4: Clean up naming drift (v2_cli.py references)
**Observation:** Design docs reference `v2_cli.py` but implementation is in `cli.py`.
**Direction:** Update docs or rename file to match.

---

## Execution Notes

- Phases 1 and 2 should be completed before merging v2 to main
- Phase 3 can be done in the same session or immediately after merge
- Phase 4 is nice-to-have before merge, can be post-merge
- Phase 5 is post-merge refactoring work
- Run `python3 -m pytest tests/ --ignore=tests/test_cli.py -q` after each phase
- Each task is independently testable and should be committed separately
