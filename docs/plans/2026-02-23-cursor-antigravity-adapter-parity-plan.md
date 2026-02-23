# Cursor + Antigravity Adapter Parity Plan

Date: 2026-02-23
Owner: hawk-hooks
Status: undone (in progress, Phase 1 completed)

## Terminology (recommended)

Use these words consistently in code/docs/UI:

1. `Canonical Component Model`
   - Hawk's source model: `skills`, `hooks`, `prompts`, `agents`, `mcp`.
2. `Adapter Mapping`
   - How one canonical component maps to a tool-native artifact.
3. `Capability Matrix`
   - Per tool/component status: `native`, `bridge`, `unsupported`.
4. `Projection`
   - Materialized output files/config generated for a tool.
5. `Bridge Driver`
   - Adapter logic that emulates missing native support.
6. `Managed Unit`
   - Hawk-owned config block/file with ownership markers.

## Goal

Bring Cursor and Antigravity adapters to explicit, tested parity with the canonical component model by:

1. implementing missing real integrations where tool support exists,
2. marking unsupported areas as explicit `unsupported` or `bridge` (never implicit),
3. documenting exact mapping behavior in tests and user diagnostics.

## Current Baseline

Cursor:
1. Skills -> `.cursor/rules/` (native-ish mapping).
2. Hooks -> `unsupported`.
3. Prompts -> default base path behavior (not explicit native mapping).
4. Agents -> placeholder filesystem mapping.
5. MCP -> `mcp.json` merge works.

Antigravity:
1. Skills -> `~/.gemini/antigravity/skills` mapping.
2. Hooks -> `unsupported`.
3. Prompts -> default base path behavior (not explicit native mapping).
4. Agents -> placeholder filesystem mapping.
5. MCP -> `mcp_config.json` sidecar merge works.

## Scope

In scope:
1. Cursor adapter parity work.
2. Antigravity adapter parity work.
3. Event/capability matrix updates.
4. Tests for all new mappings and unsupported semantics.
5. Short docs/changelog update for user-facing behavior.

Out of scope:
1. New tool adapters.
2. Reworking v2 registry model.
3. UI redesign beyond capability labels/messages.

## Strategy

Two-lane execution to avoid speculative integrations:

1. `Verified Lane`
   - Implement only behavior validated by official docs/tool behavior.
2. `Guarded Lane`
   - If a capability is not validated, keep `unsupported` with explicit diagnostics and TODO markers.

No "silent filesystem drops" for unsupported features.

## Phase 1: Capability Verification Gate

Objective:
1. Confirm Cursor and Antigravity native support for prompts/hooks/agents.
2. Record evidence in adapter comments and tests.

Tasks:
1. Add a small capability note block at top of each adapter with source references.
2. Confirm Cursor custom prompt path and hook/event mechanism.
3. Confirm Antigravity prompt/agent/hook extension points (if any).
4. Decide per component: `native`, `bridge`, `unsupported`.

Exit criteria:
1. No ambiguous mapping behavior remains.
2. Every component for both tools has an explicit support classification.

## Phase 2: Cursor Mapping Upgrade

Objective:
Implement Cursor-native or bridge mappings proven in Phase 1.

Planned mappings (target):
1. Skills -> keep `.cursor/rules/`.
2. Prompts -> explicit mapping to Cursor custom prompt location (if supported).
3. Hooks -> bridge driver only for verified events, else explicit unsupported skips.
4. Agents -> either native mapping (if supported) or intentional bridge strategy.
5. MCP -> keep `mcp.json` merge behavior.

Files:
1. Modify: `src/hawk_hooks/adapters/cursor.py`
2. Modify: `src/hawk_hooks/event_mapping.py` (if hook bridge events are added)
3. Modify/Add tests:
   - `tests/test_adapter_cursor.py`
   - `tests/test_event_mapping.py` (if mapping changes)

Acceptance:
1. Cursor adapter has explicit prompt/agent behavior (native/bridge/unsupported).
2. Hook behavior is no longer generic unsupported unless truly unsupported.
3. All Cursor tests pass.

## Phase 3: Antigravity Mapping Upgrade

Objective:
Implement Antigravity-native or bridge mappings proven in Phase 1.

Planned mappings (target):
1. Skills -> keep current native mapping.
2. Prompts -> explicit mapping if supported, otherwise explicit unsupported warning path.
3. Hooks -> bridge/native only if verified; otherwise explicit unsupported.
4. Agents -> explicit native/bridge/unsupported behavior.
5. MCP -> keep sidecar merge unless verified native format requires different ownership model.

Files:
1. Modify: `src/hawk_hooks/adapters/antigravity.py`
2. Modify: `src/hawk_hooks/event_mapping.py` (if hook bridge events are added)
3. Modify/Add tests:
   - `tests/test_adapter_antigravity.py`
   - `tests/test_event_mapping.py` (if mapping changes)

Acceptance:
1. Antigravity adapter contains no implicit defaults for prompts/agents.
2. Unsupported areas emit actionable skipped diagnostics.
3. All Antigravity tests pass.

## Phase 4: Cross-Adapter Contract Tightening

Objective:
Make adapter behavior predictable across all tools.

Tasks:
1. Ensure all adapters declare `HOOK_SUPPORT` accurately.
2. Ensure unsupported features always route to `result.skipped`, not `result.errors`.
3. Ensure projection cleanup removes stale generated files for bridges.
4. Add regression tests for stale cleanup behavior.

Files:
1. Modify: `src/hawk_hooks/adapters/base.py` (only if helper extensions are needed)
2. Modify tests:
   - `tests/test_adapter_cursor.py`
   - `tests/test_adapter_antigravity.py`
   - optional: `tests/test_v2_sync.py`

Acceptance:
1. Bridge projection files are removed when features are disabled.
2. Unsupported behavior is consistent across tools.

## Test Plan

Target commands:

1. `uv run pytest -q tests/test_adapter_cursor.py tests/test_adapter_antigravity.py tests/test_event_mapping.py`
2. `uv run pytest -q tests/test_v2_sync.py`
3. `uv run pytest -q tests/test_adapter_codex.py tests/test_adapter_gemini.py tests/test_adapter_opencode.py`

New/updated test cases:

1. Cursor:
   - explicit prompt mapping behavior test
   - explicit agent mapping behavior test
   - hook bridge or unsupported diagnostics test
2. Antigravity:
   - explicit prompt mapping behavior test
   - explicit agent mapping behavior test
   - hook bridge or unsupported diagnostics test
3. Event mapping:
   - cursor/antigravity support levels for any newly supported events

## Risks

1. Tool docs/features may be in flux.
   - Mitigation: Phase 1 verification gate before implementation.
2. Over-bridging unsupported behavior creates false confidence.
   - Mitigation: default to explicit `unsupported` unless verified.
3. Config ownership collisions with user-managed files.
   - Mitigation: preserve manual entries and surface clear skip/errors.

## TODO / Execution Checklist

- [x] Phase 1 capability verification complete.
- [ ] Cursor mapping decisions finalized.
- [ ] Cursor adapter updates implemented.
- [ ] Cursor tests added/updated and passing.
- [ ] Antigravity mapping decisions finalized.
- [ ] Antigravity adapter updates implemented.
- [ ] Antigravity tests added/updated and passing.
- [ ] Event mapping updated (if needed) with tests.
- [ ] Regression suite passes.
- [ ] Changelog/docs note added.
