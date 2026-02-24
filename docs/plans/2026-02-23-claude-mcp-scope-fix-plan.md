# Claude MCP Scope Fix Implementation Plan — DONE

> **Status:** Completed. All tasks implemented and tests passing.

**Goal:** Make Hawk-managed Claude MCP servers appear in normal Claude usage by writing to the correct config location for each scope.

**Architecture:** Keep Hawk's adapter-based sync flow unchanged, but make `ClaudeAdapter` resolve MCP config paths by scope instead of always using `target_dir/.mcp.json`. For global sync, write into user config (`~/.claude.json` `mcpServers`); for project sync, write to project root `.mcp.json`. Preserve manual entries and continue managing only Hawk-owned entries.

**Tech Stack:** Python 3.12, Hawk v2 adapter layer, pytest.

---

## Design Options

1. Direct JSON path fix in `ClaudeAdapter` (recommended)
- Global: `~/.claude.json`
- Project: `<project>/.mcp.json`
- Pros: minimal change, no subprocess dependency, aligns with existing adapter architecture.
- Cons: global updates touch a larger user config file.

2. Use `claude mcp add/remove` CLI for global scope
- Pros: follows Claude CLI behavior exactly.
- Cons: harder to diff/test deterministically, introduces subprocess/error handling complexity.

3. Keep current behavior and document limitation
- Pros: zero code risk.
- Cons: does not solve the bug; `hawk` reports enabled MCP but Claude does not see it in normal project use.

**Recommendation:** Option 1.

---

### Task 1: Lock In Expected Behavior With Failing Tests

**Files:**
- Modify: `tests/test_adapter_claude.py`

**Step 1: Add project-scope MCP path test**
- Add a test that calls `write_mcp_config()` with a target at `<tmp>/project/.claude` and asserts output in `<tmp>/project/.mcp.json`.

**Step 2: Add global-scope MCP path test**
- Add a test that patches `adapter.get_global_dir()` to `<tmp>/home/.claude`, calls `write_mcp_config()`, and asserts output in `<tmp>/home/.claude.json`.

**Step 3: Add read-path parity tests**
- Add read tests for both scopes so `read_mcp_config()` looks at the same resolved path logic.

**Step 4: Run targeted tests and confirm failure**
- Run: `uv run pytest -q tests/test_adapter_claude.py -k "mcp and (global or project or path)"`
- Expected: FAIL on current code because it always reads/writes `target_dir/.mcp.json`.

**Step 5: Commit failing-test checkpoint**
```bash
git add tests/test_adapter_claude.py
git commit -m "test: capture Claude MCP scope path expectations"
```

---

### Task 2: Implement Scope-Aware MCP Path Resolution

**Files:**
- Modify: `src/hawk_hooks/adapters/claude.py`
- Test: `tests/test_adapter_claude.py`

**Step 1: Add MCP path resolver helper**
- Add a private helper (for example `_mcp_config_path(target_dir: Path) -> Path`) with logic:
- If `target_dir.resolve() == get_global_dir().resolve()`: return `Path.home() / ".claude.json"`
- Else: return `target_dir.parent / ".mcp.json"`

**Step 2: Update write/read methods to use helper**
- `write_mcp_config()` should merge into `_mcp_config_path(target_dir)`.
- `read_mcp_config()` should read from `_mcp_config_path(target_dir)`.

**Step 3: Keep current merge semantics**
- Preserve manual entries.
- Replace only Hawk-managed entries.
- Keep marker behavior unchanged for now.

**Step 4: Run adapter tests**
- Run: `uv run pytest -q tests/test_adapter_claude.py`
- Expected: PASS.

**Step 5: Commit implementation checkpoint**
```bash
git add src/hawk_hooks/adapters/claude.py tests/test_adapter_claude.py
git commit -m "fix(claude): write MCP config to correct scope-specific paths"
```

---

### Task 3: Add Regression Coverage at Sync Layer

**Files:**
- Modify: `tests/test_v2_sync.py`

**Step 1: Add global sync regression test**
- Test that `sync_global()` with Claude enabled writes MCP into user scope location (via adapter behavior).

**Step 2: Add project sync regression test**
- Test that `sync_directory()` writes MCP to project root `.mcp.json` while hooks/settings remain under `.claude/`.

**Step 3: Run focused sync tests**
- Run: `uv run pytest -q tests/test_v2_sync.py -k "claude and mcp"`
- Expected: PASS.

**Step 4: Commit regression tests**
```bash
git add tests/test_v2_sync.py
git commit -m "test(sync): guard Claude MCP scope-specific output paths"
```

---

### Task 4: Verify End-to-End Locally

**Files:**
- No source changes unless defects are found.

**Step 1: Force Hawk sync and inspect files**
- Run: `hawk sync --global`
- Verify `~/.claude.json` contains Hawk-managed `mcpServers` entries.

**Step 2: Verify Claude sees server in normal project cwd**
- Run from a project dir (not `~/.claude`): `claude mcp list`
- Expected: includes `dodo`.

**Step 3: Verify no regressions in adapter suite**
- Run: `uv run pytest -q tests/test_adapter_claude.py tests/test_v2_sync.py`
- Expected: PASS.

**Step 4: Final commit (if Task 4 required fixes)**
```bash
git add <touched-files>
git commit -m "chore: finalize Claude MCP scope fix verification"
```

---

### Task 5: Documentation Update

**Files:**
- Modify: `docs/hawk-v2-research-and-design.md` (if stale)
- Modify: `README.md` (only if it mentions incorrect Claude MCP global path behavior)

**Step 1: Confirm docs match actual behavior**
- Ensure Claude MCP statement is explicit:
- Project scope: `.mcp.json` at project root.
- User scope: `~/.claude.json` `mcpServers`.

**Step 2: Update docs only if needed**
- Keep edits minimal and factual.

**Step 3: Run doc lint/check if configured**
- Run configured markdown checks if available.

**Step 4: Commit docs**
```bash
git add docs/hawk-v2-research-and-design.md README.md
git commit -m "docs: clarify Claude MCP user vs project scope paths"
```

---

## Verification Checklist

- `hawk status` shows `dodo` enabled under global MCP.
- `hawk sync --global` writes MCP to the user config scope used by Claude.
- `claude mcp get dodo` succeeds from a normal project working directory.
- Project-scoped sync writes `<project>/.mcp.json` and not `<project>/.claude/.mcp.json`.
- No failing tests in `tests/test_adapter_claude.py` and relevant `tests/test_v2_sync.py` cases.
