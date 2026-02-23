# TUI Packages/Registry Unification Plan

Date: 2026-02-23
Owner: hawk-hooks
Status: undone (partially implemented)

## Objective

Implement one package-first management screen in TUI, while keeping top-level component toggles (`Skills`, `Hooks`, `Prompts`, `Agents`, `MCP Servers`) unchanged.

## In Scope

1. Main menu/header polish.
2. Replace separate `Registry` interaction with a unified `Packages` tree view.
3. Group components by package, then by component type, with per-item actions.
4. Add `Ungrouped` synthetic package for registry items with no package ownership.

## Out of Scope

1. Changing underlying registry/package storage model.
2. Changing non-TUI CLI semantics (`hawk download`, `hawk sync`, etc.).
3. Reworking existing component toggle screens (`Skills/Hooks/Prompts/Agents/MCP`).

## Locked Product Decisions

1. Keep top-level component entries directly visible in main menu.
2. Keep one-time setup as conditional separate block.
3. Do not show standalone top-level `Registry` entry after migration.
4. `Packages` becomes the only installed-components management screen.

## File/Function Touchpoints

Primary:
1. `src/hawk_hooks/v2_interactive/dashboard.py`
   - `_build_header`
   - `_build_menu_options`
   - `_handle_packages`
   - `_handle_package_toggle` (may be replaced/refactored)
   - `_handle_registry_browser` (remove from menu path; keep helper only if still reused)
   - `run_dashboard` action dispatch
2. `src/hawk_hooks/v2_config.py`
   - `load_packages`
   - `get_package_for_item`
3. `src/hawk_hooks/registry.py`
   - read/list/get-path utilities (already present; no format change expected)

Tests:
1. `tests/test_v2_dashboard.py`
2. `tests/test_v2_sync.py` (regression)
3. `tests/test_adapter_codex.py` (regression)
4. Add new targeted package-view tests (in `tests/test_v2_dashboard.py` unless file split is needed)

## Target IA and Menu Contract

Main menu order must remain:
1. `Skills`
2. `Hooks`
3. `Prompts`
4. `Agents`
5. `MCP Servers`
6. Conditional `One-time setup` block (only when unresolved setup items exist)
7. `Download`
8. `Packages`
9. `Environment`
10. `Exit`

One-time block placement decision:
1. Keep `One-time setup` directly below component rows and above utility rows.
2. Do not move it above components by default (avoids shifting primary navigation muscle memory).
3. Keep warning styling (`yellow`) so it stays visible without stealing top position.

Remove direct `Registry` entry from `main menu`.

## Header Contract

`_build_header` output rules:
1. Line 1: `hawk <version>` plus compact summary (no noisy counts unless useful).
2. Line 2: scope (`Global` or scoped project path/name).
3. Line 3 (conditional): sync status only when unsynced > 0.
4. Codex setup warning stays in menu block, not as noisy repeated header text.

## Unified Packages View Spec

## Row Kinds

Implement a single row model with explicit row kinds:
1. `ROW_PACKAGE`
2. `ROW_TYPE`
3. `ROW_ITEM`
4. `ROW_SEPARATOR`
5. `ROW_ACTION`

Minimum row payload schema:
1. `kind`
2. `package_name` (for package/type/item rows)
3. `component_type` (for type/item rows)
4. `item_name` (for item rows)
5. `is_collapsed` (for package/type rows)
6. `is_ungrouped` (for package rows)

## Tree Construction Algorithm

For each render/rebuild:
1. Read registry items from `state["contents"]` across:
   - `skill`, `hook`, `prompt`, `agent`, `mcp`
2. Build ownership map from `load_packages()`:
   - key: `(component_type, item_name)` -> `package_name`
3. Partition registry items:
   - owned items under their package
   - unknown/unowned items under package `Ungrouped`
4. Within each package, group by component type in fixed order:
   - `Skills`, `Hooks`, `Prompts`, `Agents`, `MCP Servers`
5. Sort item names alphabetically within each type group.
6. Build flat render rows from current collapse state.

## Interaction Contract

Global keys:
1. `↑/↓`, `j/k`: move cursor
2. `q`, `Esc`: back
3. `Ctrl+C`: back/cancel (same as `q`/`Esc`)
4. `U`: update all packages

Package row:
1. `Enter` or `Space`: collapse/expand package
2. `u`: update selected package (no-op on `Ungrouped`, show status msg)
3. `x`/`d`: remove selected package (no-op on `Ungrouped`, show status msg)

Type row:
1. `Enter` or `Space`: collapse/expand type

Item row:
1. `Enter` or `Space`: enable/disable item in active scope
2. `e`: open source in editor/view
3. `d`: remove item from registry

Consistency rule for `Enter` vs `Space`:
1. For selectable/toggle rows, `Enter` and `Space` are equivalent primary actions.
2. Letter keys (`e`, `u`, `d`, `x`) are row-specific secondary actions.
3. Do not make `Enter` and `Space` diverge inside the same screen.

Status/help line:
1. Always dim.
2. Must be context-sensitive:
   - package selected vs item selected actions.

## State Mutation Rules

1. Item toggle must reuse existing scope-aware config write path used by current toggles.
2. Package update/remove must call existing CLI-backed handlers (same behavior as current `Packages` menu).
3. Registry item removal must refresh `state["contents"]` immediately and keep cursor stable where possible.
4. Any mutating action sets local `dirty=True`, then runs existing `_apply_auto_sync_if_needed(...)`.

## Implementation Phases with Exit Criteria

## Phase 1: Main menu and header polish

Tasks:
1. Finalize header copy in `_build_header`.
2. Keep one-time block placement and style.
3. Remove `Registry` entry from `_build_menu_options`.
4. Remove `registry` action branch from `run_dashboard`.

Exit criteria:
1. Main menu contains no `Registry` row.
2. One-time block appears only when required.
3. Existing codex-setup UX unchanged.

## Phase 2: Build unified package row model

Tasks:
1. Create private helpers in `dashboard.py`:
   - ownership map builder
   - grouped package tree builder
   - row flattening/render helper
2. Introduce persistent collapse state dicts:
   - `collapsed_packages`
   - `collapsed_types[(package_name, component_type)]`
3. Render tree with Rich `Live`.

Exit criteria:
1. `Packages` screen shows package accordions + `Ungrouped`.
2. Per-package type accordions present in fixed order.
3. Item lists are stable and sorted.

## Phase 3: Wire actions and mutations

Tasks:
1. Package actions (`u`, `x/d`) use existing logic and refresh tree.
2. Item actions (toggle/open/delete) wired and reflected immediately.
3. Add clear status messages for invalid actions on `Ungrouped`.

Exit criteria:
1. All key actions work for intended row kind.
2. `Ungrouped` package never offers destructive package-level operations.
3. Dirty/sync behavior remains consistent.

## Phase 4: Testing and regression

Tasks:
1. Add dashboard tests for:
   - menu composition without `Registry`
   - one-time block visibility
   - grouping to `Ungrouped`
   - row-kind action guardrails
2. Run full target regression suites.

Exit criteria:
1. `tests/test_v2_dashboard.py` pass.
2. `tests/test_v2_sync.py` pass.
3. `tests/test_adapter_codex.py` pass.
4. Manual TUI smoke test in narrow terminal passes.

## Test Cases to Add (Concrete)

1. `test_main_menu_no_registry_entry`
2. `test_packages_grouping_builds_ungrouped_bucket`
3. `test_package_actions_disabled_for_ungrouped`
4. `test_item_toggle_from_packages_updates_scope_config`
5. `test_package_remove_refreshes_contents`
6. `test_one_time_setup_block_only_when_required`

## TODO / Execution Checklist

- [x] Update `_build_header` copy contract.
- [x] Remove top-level `Registry` option and dispatcher branch.
- [x] Implement package ownership map builder.
- [x] Implement grouped package tree (`package -> type -> items`).
- [x] Implement collapse state management.
- [x] Implement row flatten + render.
- [x] Wire row-kind key handling and action dispatch.
- [x] Add `Ungrouped` guardrails (`u`, `x/d` no-op with message).
- [x] Ensure dirty + auto-sync integration after mutating actions.
- [ ] Add/adjust tests listed above.
- [ ] Run: `uv run pytest -q tests/test_v2_dashboard.py tests/test_v2_sync.py tests/test_adapter_codex.py`.
- [ ] Manual TUI verification (global + local scope).

## Risks and Mitigations

1. Navigation regressions in nested rows.
   - Mitigation: keep explicit row kinds and cursor-skip helpers.
2. Ownership mismatch between registry and packages.
   - Mitigation: compute `Ungrouped` as set difference on each rebuild.
3. Overloaded keymap confusion.
   - Mitigation: context-sensitive help footer and status messages.
