# Prompts-Canonical Schema (v3) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate hawk to a prompts-canonical schema (breaking change) with a one-shot upgrader that rewrites config/registry/package state safely.

**Architecture:** Introduce an isolated migration module and CLI entrypoint (`hawk migrate-prompts`) that rewrites legacy `commands` state to canonical `prompts`. Update runtime modules (v2 and legacy v1) to consume prompts-only schema. Keep adapter-specific destination mapping behavior while removing `commands` as a first-class runtime concept.

**Tech Stack:** Python 3.12+, argparse CLI, pytest, YAML/JSON config IO, filesystem migration utilities.

---

### Task 1: Add Failing Tests for One-Shot Upgrader Interface

**Files:**
- Create: `tests/test_migrate_prompts.py`
- Modify: `src/hawk_hooks/v2_cli.py`

**Step 1: Write the failing test**

```python
def test_migrate_prompts_check_reports_changes(cli_runner, monkeypatch, tmp_path):
    # Arrange test config with global.commands + registry/commands item
    # Act: run `hawk migrate-prompts --check`
    # Assert: output contains "would migrate" and exit code 0
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_migrate_prompts.py::test_migrate_prompts_check_reports_changes -q`
Expected: FAIL (command not recognized or function missing)

**Step 3: Write minimal implementation**

- Add parser wiring in `build_parser()` for `migrate-prompts`.
- Add stub `cmd_migrate_prompts()` that calls migration module.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_migrate_prompts.py::test_migrate_prompts_check_reports_changes -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_migrate_prompts.py src/hawk_hooks/v2_cli.py
git commit -m "test+feat: add migrate-prompts CLI entrypoint"
```

### Task 2: Implement Config Rewrites (Global/Dir/Tool Overrides)

**Files:**
- Create: `src/hawk_hooks/migrate_prompts.py`
- Modify: `src/hawk_hooks/v2_config.py`
- Test: `tests/test_migrate_prompts.py`

**Step 1: Write the failing test**

```python
def test_apply_rewrites_commands_fields_to_prompts(tmp_path, monkeypatch):
    # Arrange config with global.commands and dir commands.enabled/disabled
    # Act: apply migration
    # Assert: prompts fields populated, commands removed
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_migrate_prompts.py::test_apply_rewrites_commands_fields_to_prompts -q`
Expected: FAIL (rewrites missing)

**Step 3: Write minimal implementation**

- Implement migration helpers that:
  - move `global.commands -> global.prompts`
  - move `commands.enabled/disabled -> prompts.enabled/disabled`
  - move `tools.<tool>.commands.extra/exclude -> tools.<tool>.prompts.extra/exclude`
- Deduplicate while preserving order.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_migrate_prompts.py::test_apply_rewrites_commands_fields_to_prompts -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/hawk_hooks/migrate_prompts.py src/hawk_hooks/v2_config.py tests/test_migrate_prompts.py
git commit -m "feat: migrate config command fields to prompts"
```

### Task 3: Implement Registry + Packages Migration Semantics

**Files:**
- Modify: `src/hawk_hooks/migrate_prompts.py`
- Test: `tests/test_migrate_prompts.py`

**Step 1: Write the failing tests**

```python
def test_apply_moves_registry_commands_into_prompts(tmp_path, monkeypatch):
    ...

def test_apply_rewrites_packages_item_type_command_to_prompt(tmp_path, monkeypatch):
    ...

def test_registry_collision_keeps_existing_prompt_item(tmp_path, monkeypatch):
    ...
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_migrate_prompts.py -k "registry or packages or collision" -q`
Expected: FAIL

**Step 3: Write minimal implementation**

- Move files from `registry/commands` to `registry/prompts`.
- On collision, keep existing prompt copy and report skip.
- Rewrite `packages.yaml` entries of type `command` to `prompt`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_migrate_prompts.py -k "registry or packages or collision" -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/hawk_hooks/migrate_prompts.py tests/test_migrate_prompts.py
git commit -m "feat: migrate registry and package metadata to prompts"
```

### Task 4: Make Runtime v2 Prompts-Canonical

**Files:**
- Modify: `src/hawk_hooks/types.py`
- Modify: `src/hawk_hooks/resolver.py`
- Modify: `src/hawk_hooks/v2_config.py`
- Modify: `src/hawk_hooks/v2_sync.py`
- Modify: `src/hawk_hooks/v2_cli.py`
- Modify: `src/hawk_hooks/v2_interactive/dashboard.py`
- Test: `tests/test_v2_types.py`, `tests/test_resolver.py`, `tests/test_v2_sync.py`, `tests/test_v2_cli.py`

**Step 1: Write failing tests**

```python
def test_v2_status_outputs_prompts_not_commands(...):
    ...

def test_resolver_uses_prompts_field(...):
    ...
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_v2_types.py tests/test_resolver.py tests/test_v2_sync.py tests/test_v2_cli.py -q`
Expected: FAIL (old commands model still referenced)

**Step 3: Write minimal implementation**

- Remove first-class `commands` runtime field usage.
- Ensure resolver/sync/status/TUI lists include `prompts` as canonical slash concept.
- Keep adapters’ destination behavior unchanged.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_v2_types.py tests/test_resolver.py tests/test_v2_sync.py tests/test_v2_cli.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/hawk_hooks/types.py src/hawk_hooks/resolver.py src/hawk_hooks/v2_config.py src/hawk_hooks/v2_sync.py src/hawk_hooks/v2_cli.py src/hawk_hooks/v2_interactive/dashboard.py tests/test_v2_types.py tests/test_resolver.py tests/test_v2_sync.py tests/test_v2_cli.py
git commit -m "refactor: make v2 runtime prompts-canonical"
```

### Task 5: Migrate Legacy v1 Runtime to Prompts Terminology

**Files:**
- Modify: `src/hawk_hooks/config.py`
- Modify: `src/hawk_hooks/sync.py`
- Modify: `src/hawk_hooks/prompt_scanner.py`
- Modify: `src/hawk_hooks/interactive/prompts.py`
- Modify: `src/hawk_hooks/interactive/__init__.py`
- Test: `tests/test_config_destinations.py`, `tests/test_sync.py`, `tests/test_prompt_scanner.py`, `tests/test_integration_prompts.py`

**Step 1: Write failing tests**

```python
def test_destinations_use_prompts_key_for_slash_items(...):
    ...

def test_legacy_menu_labels_show_prompts_not_commands(...):
    ...
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config_destinations.py tests/test_sync.py tests/test_prompt_scanner.py tests/test_integration_prompts.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

- Rename v1 destination key usage from `commands` to `prompts`.
- Update labels/UI wording to prompts terminology.
- Preserve agent behavior.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config_destinations.py tests/test_sync.py tests/test_prompt_scanner.py tests/test_integration_prompts.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/hawk_hooks/config.py src/hawk_hooks/sync.py src/hawk_hooks/prompt_scanner.py src/hawk_hooks/interactive/prompts.py src/hawk_hooks/interactive/__init__.py tests/test_config_destinations.py tests/test_sync.py tests/test_prompt_scanner.py tests/test_integration_prompts.py
git commit -m "refactor: align legacy v1 runtime with prompts terminology"
```

### Task 6: Wire Upgrader into CLI and Cache Invalidations

**Files:**
- Modify: `src/hawk_hooks/v2_cli.py`
- Modify: `src/hawk_hooks/migrate_prompts.py`
- Modify: `src/hawk_hooks/v2_sync.py`
- Test: `tests/test_migrate_prompts.py`, `tests/test_v2_cli.py`

**Step 1: Write failing tests**

```python
def test_migrate_prompts_apply_clears_resolved_cache(...):
    ...

def test_migrate_prompts_is_idempotent(...):
    ...
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_migrate_prompts.py tests/test_v2_cli.py -k "migrate_prompts or idempotent or cache" -q`
Expected: FAIL

**Step 3: Write minimal implementation**

- Complete CLI UX for `migrate-prompts` (`--check`, `--apply`, `--no-backup`).
- Clear resolved cache after successful apply.
- Ensure repeat runs are no-op.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_migrate_prompts.py tests/test_v2_cli.py -k "migrate_prompts or idempotent or cache" -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/hawk_hooks/v2_cli.py src/hawk_hooks/migrate_prompts.py src/hawk_hooks/v2_sync.py tests/test_migrate_prompts.py tests/test_v2_cli.py
git commit -m "feat: finalize migrate-prompts oneshot workflow"
```

### Task 7: Add Deprecation Inventory and Verify Full Suite

**Files:**
- Create: `docs/DEPRECATE.md`
- Modify: `docs/plans/2026-02-21-prompts-canonical-schema-v3-design.md`

**Step 1: Write doc changes**

```markdown
# Deprecation Inventory

| Module/Feature | Status | Replacement | Target Removal | Notes |
|---|---|---|---|---|
```

**Step 2: Run full verification**

Run: `uv run pytest tests/ --ignore=tests/test_cli.py -q`
Expected: all tests pass

**Step 3: Commit**

```bash
git add docs/DEPRECATE.md docs/plans/2026-02-21-prompts-canonical-schema-v3-design.md
git commit -m "docs: add deprecation inventory for v1 and legacy schema"
```

