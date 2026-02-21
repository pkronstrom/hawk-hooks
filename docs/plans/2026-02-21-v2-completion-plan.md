# v2 Completion Plan

## Current Status (2026-02-21)

Branch `v2` — 63 commits ahead of `main`, 476 tests passing.

### What's Done

| Area | Status | Key Files |
|------|--------|-----------|
| CLI commands | All wired: `sync`, `scan`, `download`, `packages`, `update`, `remove-package`, `new`, `deps`, `projects`, `migrate` | `v2_cli.py` |
| Config system | YAML, hierarchical (global → parent chain → cwd), package index, auto-register, prune | `v2_config.py` |
| Sync engine | Hash-based cache (names + content mtime/size), per-tool sync, clean ops | `v2_sync.py` |
| Resolver | N-layer dir_chain, per-tool overrides, all 6 component types | `resolver.py` |
| Registry | Add/remove/replace (atomic), list, clash detection | `registry.py` |
| Adapters | Claude (full), Gemini (toml commands, sidecar MCP), Codex, OpenCode, Cursor, Antigravity | `adapters/` |
| Hook format | Metadata parser (`hawk-hook:` headers), flat hooks, runner generation, Claude event registration | `hook_meta.py`, `adapters/base.py`, `adapters/claude.py` |
| Downloader | Flat hooks, legacy event dirs, hooks.json explosion, MCP fan-out, package manifests, path traversal sanitization | `downloader.py` |
| TUI | Dashboard, N-scope toggles, package grouping, wizard, config editor, select menu (view/open/sync) | `v2_interactive/` |
| Tests | 476 passing across all v2 modules | `tests/` |
| Security | Path traversal sanitization, atomic registry replace, sync cache content hashing, adapter hook contract fix | recent review commit |

### What's Incomplete

| Gap | Plan Reference | Current State |
|-----|---------------|---------------|
| TUI scope detection | `v2-tui-design.md:13` | Exact cwd match only, should walk ancestor registered dirs |
| TUI enabled counts | `v2-tui-design.md:52` | Approximate (global + local delta), not resolved-chain counts |
| Registry Browser | `v2-tui-design.md:111` | Not implemented — planned as TUI action |
| Hook metadata-anywhere discovery | `hawk-hook-format-design.md:82` | Scan classifies mainly by parent dir, not by header presence |
| Scan package updates | `package-grouping-design.md:270` | `hawk scan` records empty `url`/`commit`, so `hawk update` skips them |
| Migration schema | `migration.py:58` | Missing `prompts` key, only seeds 4 tools (defaults fill on load) |
| Non-Claude hooks | All non-Claude adapters | Return `[]` — correct, these tools don't support hooks natively yet |
| Builtins | `hawk-hook-format-plan.md:354` | Curated to 4 hooks (plan had 15) — intentional reduction |

---

## Phases

### Phase A — TUI Polish (2 parallel agents)

These are independent UI fixes, no shared state.

**Agent A1: Scope Detection & Counts**
```
Files: src/hawk_hooks/v2_interactive/dashboard.py, src/hawk_hooks/v2_config.py
Task:
- Update _detect_scope() to walk up from cwd checking registered dirs
  (v2_config.get_registered_dirs() already returns the list)
- Update dashboard component counts to use resolver.resolve() output
  instead of len(global_list) + len(local_list) approximation
- Tests: add test for nested subdir scope detection
```

**Agent A2: Registry Browser**
```
Files: src/hawk_hooks/v2_interactive/dashboard.py, src/hawk_hooks/v2_interactive/toggle.py
Task:
- Add "Registry" action to dashboard menu (after Packages)
- Shows all registry contents grouped by type (read-only browse)
- Each item shows: name, type, source package (if any), file size
- Enter on item opens it in $EDITOR (reuse existing view/open pattern)
- Tests: not needed for TUI (manual testing)
```

### Phase B — Package Lifecycle (2 parallel agents)

Independent package management improvements.

**Agent B1: Scan Package Source Tracking**
```
Files: src/hawk_hooks/v2_cli.py (cmd_scan), src/hawk_hooks/v2_config.py
Task:
- When hawk scan imports from a local directory, record source path in
  packages.yaml as `path` field (alongside existing `url` field)
- hawk update should check: if url is set, clone+update; if path is set,
  re-scan from path; if neither, print "local-only package, cannot update"
- hawk packages should show source type: [git], [local], [manual]
- Tests: test scan records path, test update with path-only package
```

**Agent B2: Migration Schema Completeness**
```
Files: src/hawk_hooks/migration.py, tests/test_migration.py
Task:
- Add "prompts": [] to generated global config in migrate_config()
- Add cursor and antigravity to tool_map initialization
- Ensure migrated config matches DEFAULT_GLOBAL_CONFIG shape exactly
- Tests: add test asserting migrated output has all keys from DEFAULT_GLOBAL_CONFIG
```

### Phase C — Hook Discovery (1 agent, depends on nothing)

**Agent C1: Metadata-Anywhere Hook Detection**
```
Files: src/hawk_hooks/downloader.py, src/hawk_hooks/hook_meta.py
Task:
- In classify()/scan_directory(), when a file doesn't match convention-based
  classification, check for hawk-hook: metadata header as fallback
- Files with valid hawk-hook: metadata should be classified as HOOK regardless
  of their directory location
- This enables repos with flat layouts (all files in root) to have hooks
  recognized by metadata alone
- Tests: add test for hook file in root dir with hawk-hook: header
```

### Phase D — Pre-Merge Cleanup (1 agent, after A+B+C)

**Agent D1: Plan Doc Reconciliation & Final Checks**
```
Files: docs/plans/*.md, CLAUDE.md
Task:
- Review each plan doc against final implementation
- Mark completed items, note intentional deviations (e.g., 4 builtins not 15)
- Update CLAUDE.md to reflect v2 as the primary architecture
- Run full test suite, verify 0 failures
- Check for any TODO/FIXME/HACK comments that need resolution
```

---

## Dependency Graph

```
Phase A (TUI Polish)          Phase B (Package Lifecycle)     Phase C (Hook Discovery)
  A1: Scope Detection           B1: Scan Source Tracking        C1: Metadata-Anywhere
  A2: Registry Browser          B2: Migration Schema
       |                             |                               |
       +-----------------------------+-------------------------------+
                                     |
                              Phase D (Pre-Merge)
                               D1: Reconciliation
```

A, B, C are fully parallel (no shared files between phases).
D runs after everything else lands.

## Execution Notes

- Each agent task is self-contained with file list, clear task, and test expectations
- Agents A1, A2, B1, B2, C1 can all run simultaneously (5 parallel agents)
- Or run as 3 phases: A (2 agents) || B (2 agents) || C (1 agent), then D
- After each phase, run `python3 -m pytest tests/ --ignore=tests/test_cli.py -q` to verify
- Non-Claude hook registration (Gemini/Codex/etc.) is intentionally out of scope — those tools don't support hooks natively
