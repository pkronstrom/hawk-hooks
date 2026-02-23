# v2 Architecture Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce high-risk architectural coupling in v2 by removing dashboard→CLI command coupling, centralizing scope-chain/profile resolution, and tightening package lifecycle boundaries.

**Architecture:** Introduce two reusable service modules: (1) scope resolution builder used by sync/status/dashboard, and (2) package operations service used by both CLI and TUI. Keep CLI user-facing behavior stable by using thin command wrappers that translate service errors into exit codes.

**Tech Stack:** Python 3, rich/simple-term-menu TUI, existing hawk v2 config/resolver/registry APIs, pytest.

---

## Constraints & invariants

1. No behavior regression in existing command UX (`hawk update`, `hawk remove-package`).
2. Dashboard package actions must not import or call CLI command functions.
3. Shared scope-chain/profile logic must be single-source and reused by v2 sync + status + dashboard state load.
4. Preserve existing registry/config data formats.
5. Avoid touching unrelated uncommitted work already present in repo.

## Task 1: Add shared scope-chain/profile resolution module

**Files:**
1. Create: `src/hawk_hooks/scope_resolution.py`
2. Modify: `src/hawk_hooks/v2_sync.py`
3. Modify: `src/hawk_hooks/cli.py`
4. Modify: `src/hawk_hooks/v2_interactive/dashboard.py`
5. Test: `tests/test_scope_resolution.py` (new)
6. Test: `tests/test_v2_sync.py`

**Implementation:**
1. Add helper to resolve profile for a directory layer (`dir config` then global directory index fallback).
2. Add helper to build `(dir_config, profile)` chain from `project_dir`, including fallback when dir has local `.hawk/config.yaml` but is not globally registered.
3. Replace duplicated dir-chain/profile code in `v2_sync.count_unsynced_targets` and `v2_sync.sync_directory` with shared helper.
4. Replace private helper import from `cmd_status` (`from .v2_sync import _load_profile_for_dir`) with new shared helper.
5. Replace dashboard `_load_state` active-resolution chain building with new shared helper.

**Verification:**
1. Add focused tests for chain/profile fallback semantics.
2. Run: `uv run pytest -q tests/test_scope_resolution.py tests/test_v2_sync.py`

## Task 2: Extract package update/remove service layer

**Files:**
1. Create: `src/hawk_hooks/package_service.py`
2. Modify: `src/hawk_hooks/cli.py`
3. Test: `tests/test_package_service.py` (new)
4. Test: `tests/test_v2_cli.py`

**Implementation:**
1. Create typed service API for package update and package removal that returns structured outcomes and never calls `sys.exit`.
2. Move package mutation logic from `cmd_update`/`cmd_remove_package` to service functions with minimal behavior change.
3. Add service-level error classes (e.g., package not found, update failures) for caller-controlled handling.
4. Keep CLI commands as wrappers that:
   - parse args,
   - call service,
   - print equivalent summary,
   - convert service failures to `SystemExit(1)` where appropriate.

**Verification:**
1. Keep existing CLI tests passing.
2. Add service tests for local-path-missing update failure and remove-package happy path.
3. Run: `uv run pytest -q tests/test_package_service.py tests/test_v2_cli.py`

## Task 3: Decouple dashboard package menu from CLI commands

**Files:**
1. Modify: `src/hawk_hooks/v2_interactive/dashboard.py`
2. Test: `tests/test_v2_dashboard.py`

**Implementation:**
1. Replace `from ..cli import cmd_update/cmd_remove_package` calls with direct `package_service` calls.
2. Remove `SystemExit` swallowing around package actions.
3. Keep same UX interactions:
   - `U` updates all packages,
   - `u` updates selected package,
   - `d/x` removes selected package (after confirm).
4. Show concise service failure message in TUI status/console and continue safely.

**Verification:**
1. Add/adjust tests to ensure dashboard package operations do not rely on CLI wrappers.
2. Run: `uv run pytest -q tests/test_v2_dashboard.py`

## Task 4: DRY component-order constants in dashboard package/toggle views

**Files:**
1. Modify: `src/hawk_hooks/v2_interactive/dashboard.py`
2. Test: `tests/test_v2_dashboard.py`

**Implementation:**
1. Replace duplicated component-order lists with a single canonical constant and derived helper mappings.
2. Reuse this in `_handle_component_toggle` and `_handle_packages`.

**Verification:**
1. Run: `uv run pytest -q tests/test_v2_dashboard.py`

## Task 5: Full focused verification and regression sweep

**Files:**
1. No new files (verification only)

**Verification commands:**
1. `uv run pytest -q tests/test_scope_resolution.py tests/test_package_service.py`
2. `uv run pytest -q tests/test_v2_sync.py tests/test_v2_cli.py tests/test_v2_dashboard.py`

## Risks & mitigations

1. Risk: subtle behavior drift in CLI output wording.
   - Mitigation: keep wrappers printing current summary strings; assert with existing tests.
2. Risk: scope-chain fallback edge cases for unregistered local `.hawk` configs.
   - Mitigation: explicit tests in new scope-resolution suite.
3. Risk: large dashboard function complexity causing accidental regressions.
   - Mitigation: refactor only action call sites and constants in this pass.

## Execution checklist

- [x] Task 1 complete
- [x] Task 2 complete
- [x] Task 3 complete
- [x] Task 4 complete
- [x] Task 5 complete
