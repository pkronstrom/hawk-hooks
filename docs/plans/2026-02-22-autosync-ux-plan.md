# Auto-Sync UX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make enabled components auto-apply in interactive UX, classify unsupported sync outcomes as skipped (not errors), and ensure future tool capability changes re-trigger sync attempts.

**Architecture:** Keep config as source of truth, keep cache-based sync no-op optimization, and make cache identity capability-aware. Introduce typed sync diagnostics (`skipped`) so unsupported operations are visible but non-fatal.

**Tech Stack:** Python 3.11+, hawk v2 sync engine, tool adapters, pytest.

---

### Task 1: Add typed skipped diagnostics to sync result model

**Files:**
- Modify: `src/hawk_hooks/types.py`
- Modify: `src/hawk_hooks/v2_sync.py`
- Test: `tests/test_v2_sync.py`

**Step 1: Write failing test**

Add a test in `tests/test_v2_sync.py` asserting `format_sync_results(..., verbose=False)` includes skipped count when a result contains skipped items.

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_v2_sync.py -k format_skipped`
Expected: fail because `SyncResult` has no `skipped` and formatter has no skipped rendering.

**Step 3: Implement minimal code**

- Add `skipped: list[str] = field(default_factory=list)` to `SyncResult` in `src/hawk_hooks/types.py`.
- Update merge/format logic in `src/hawk_hooks/v2_sync.py`:
  - merge should carry `skipped`
  - compact formatter should include `~N skipped`
  - verbose formatter should render skipped lines (e.g. `~ hooks: ...`).

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_v2_sync.py -k format_skipped`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/hawk_hooks/types.py src/hawk_hooks/v2_sync.py tests/test_v2_sync.py
git commit -m "feat(v2): add skipped sync diagnostics"
```

### Task 2: Split hook diagnostics into skipped vs errors

**Files:**
- Modify: `src/hawk_hooks/adapters/base.py`
- Modify: `src/hawk_hooks/adapters/gemini.py`
- Modify: `src/hawk_hooks/adapters/codex.py`
- Modify: `src/hawk_hooks/adapters/opencode.py`
- Modify: `src/hawk_hooks/adapters/cursor.py`
- Modify: `src/hawk_hooks/adapters/antigravity.py`
- Test: `tests/test_adapter_codex.py`
- Test: `tests/test_adapter_gemini.py`

**Step 1: Write failing tests**

- Add tests asserting unsupported hook events are reported as skipped diagnostics, not errors.
- Keep tests asserting real conflicts (for example manual notify key collisions) remain errors.

**Step 2: Run tests to verify failure**

Run: `uv run pytest -q tests/test_adapter_codex.py tests/test_adapter_gemini.py -k unsupported or manual_notify`
Expected: FAIL on current error-channel behavior.

**Step 3: Implement minimal code**

- Introduce adapter hook diagnostic classification so unsupported capability warnings map to `result.skipped`.
- Keep operational/config conflict failures in `result.errors`.
- Update helper methods in base adapter to avoid overloading `errors` for informational skips.

**Step 4: Run tests to verify pass**

Run: `uv run pytest -q tests/test_adapter_codex.py tests/test_adapter_gemini.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/hawk_hooks/adapters/base.py src/hawk_hooks/adapters/gemini.py src/hawk_hooks/adapters/codex.py src/hawk_hooks/adapters/opencode.py src/hawk_hooks/adapters/cursor.py src/hawk_hooks/adapters/antigravity.py tests/test_adapter_codex.py tests/test_adapter_gemini.py
git commit -m "feat(v2): classify unsupported hook sync outcomes as skipped"
```

### Task 3: Make sync cache capability-aware

**Files:**
- Modify: `src/hawk_hooks/v2_sync.py`
- Modify: `src/hawk_hooks/adapters/base.py`
- Modify: `src/hawk_hooks/adapters/codex.py`
- Modify: `src/hawk_hooks/adapters/gemini.py`
- Test: `tests/test_v2_sync.py`

**Step 1: Write failing tests**

Add tests proving that:
- when desired state hash is unchanged but capability fingerprint changes, sync is not skipped by cache.
- capability unchanged still uses cache no-op.

**Step 2: Run test to verify failure**

Run: `uv run pytest -q tests/test_v2_sync.py -k capability`
Expected: FAIL because cache identity currently ignores capability.

**Step 3: Implement minimal code**

- Add adapter capability fingerprint surface (for example method/property on base adapter).
- Compute per-target cache identity from desired hash + capability fingerprint.
- Keep cache format backward-safe (if old cache exists, treat as miss and refresh).

**Step 4: Run test to verify pass**

Run: `uv run pytest -q tests/test_v2_sync.py -k capability`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/hawk_hooks/v2_sync.py src/hawk_hooks/adapters/base.py src/hawk_hooks/adapters/codex.py src/hawk_hooks/adapters/gemini.py tests/test_v2_sync.py
git commit -m "feat(v2): include tool capability fingerprint in sync cache"
```

### Task 4: Apply-on-leave auto-sync in interactive dashboard/config flows

**Files:**
- Modify: `src/hawk_hooks/v2_interactive/dashboard.py`
- Modify: `src/hawk_hooks/v2_interactive/config_editor.py`
- Modify: `src/hawk_hooks/v2_interactive/wizard.py` (if needed for consistency)
- Test: `tests/test_v2_sync.py`
- Test: `tests/test_v2_cli.py`

**Step 1: Write failing tests**

Add tests for interactive flow hooks (at minimum unit-level around trigger functions) asserting:
- leaving modified toggle/settings paths invokes sync without manual `Sync` action.
- dirty flag semantics remain correct.

**Step 2: Run test to verify failure**

Run: `uv run pytest -q tests/test_v2_sync.py tests/test_v2_cli.py -k autosync or sync_on_exit`
Expected: FAIL because manual sync is still a primary action.

**Step 3: Implement minimal code**

- Wire auto-sync calls on leave/exit where dirty changes exist.
- Demote/remove manual sync from primary TUI path (or keep as explicit optional action if needed during transition).
- Keep `sync_on_exit` preference behavior coherent with auto-sync triggers.

**Step 4: Run test to verify pass**

Run: `uv run pytest -q tests/test_v2_sync.py tests/test_v2_cli.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/hawk_hooks/v2_interactive/dashboard.py src/hawk_hooks/v2_interactive/config_editor.py src/hawk_hooks/v2_interactive/wizard.py tests/test_v2_sync.py tests/test_v2_cli.py
git commit -m "feat(v2): apply auto-sync on interactive leave/exit"
```

### Task 5: Update CLI output and docs for skipped diagnostics

**Files:**
- Modify: `src/hawk_hooks/v2_cli.py`
- Modify: `docs/plans/2026-02-22-autosync-ux-design.md` (if design deltas)
- Modify: `README.md` or relevant docs if sync output examples exist
- Test: `tests/test_v2_sync.py`

**Step 1: Write failing test**

Add/extend formatter expectations for compact + verbose sync outputs including skipped reasons.

**Step 2: Run test to verify failure**

Run: `uv run pytest -q tests/test_v2_sync.py -k skipped`
Expected: FAIL if output is incomplete.

**Step 3: Implement minimal code**

- Ensure CLI uses updated formatter output consistently.
- Keep non-verbose output compact but include skipped counts.

**Step 4: Run test to verify pass**

Run: `uv run pytest -q tests/test_v2_sync.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/hawk_hooks/v2_cli.py tests/test_v2_sync.py README.md docs/plans/2026-02-22-autosync-ux-design.md
git commit -m "docs(v2): clarify skipped sync diagnostics and auto-sync UX"
```

### Task 6: End-to-end verification and integration commit

**Files:**
- Verify only

**Step 1: Run focused suites**

Run:
- `uv run pytest -q tests/test_v2_sync.py tests/test_v2_cli.py`
- `uv run pytest -q tests/test_adapter_codex.py tests/test_adapter_gemini.py tests/test_adapter_opencode.py tests/test_adapter_cursor.py tests/test_adapter_antigravity.py`

Expected: all pass.

**Step 2: Run compile checks**

Run: `uv run python -m py_compile src/hawk_hooks/v2_sync.py src/hawk_hooks/v2_cli.py src/hawk_hooks/v2_interactive/dashboard.py src/hawk_hooks/adapters/base.py src/hawk_hooks/adapters/codex.py src/hawk_hooks/adapters/gemini.py`
Expected: exit 0.

**Step 3: Final commit if any staged leftovers**

```bash
git add -A
git commit -m "chore(v2): finalize auto-sync + capability-aware skipped behavior"
```

