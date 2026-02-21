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
| Scan package updates | `package-grouping-design.md:270` | `hawk scan` records empty `url`/`commit`, so `hawk update` skips them |
| Migration schema | `migration.py:58` | Missing `prompts` key, only seeds 4 tools (defaults fill on load) |
| Cross-tool hooks (Gemini/Codex/others) | Phase E (below) | Claude + Gemini native, Codex bridge, OpenCode/Cursor/Antigravity explicit unsupported warnings |
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

### Phase C — Hook Discovery (1 agent, depends on nothing, completed 2026-02-21)

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

Status:
- Implemented in `src/hawk_hooks/downloader.py`
- Verified by `tests/test_downloader.py::TestClassifyFlatHooks::test_root_md_with_hawk_hook_metadata_is_hook_even_with_structured_dirs`
- Verified by `tests/test_downloader.py::TestScanDirectoryHooks::test_detects_root_md_with_hawk_hook_frontmatter`

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

### Phase E — Cross-Tool Hook Registration (completed 2026-02-21)

This phase plans hook support beyond Claude with a staged rollout:
- native integration where supported
- limited bridge mode where only partial APIs exist
- explicit unsupported reporting (no silent drops)

**Agent E1: Capability Matrix + Event Contract**
```
Files: docs/hawk-v2-research-and-design.md, src/hawk_hooks/event_mapping.py, tests/test_event_mapping.py
Task:
- Verify current hook capabilities for Claude, Gemini, Codex (and note optional tools)
- Freeze canonical event contract and per-tool mappings in event_mapping.py
- Mark each event as native / bridged / unsupported per tool
- Tests: add event mapping tests for supported + unsupported cases
```

**Agent E2: Gemini Native Hook Registration**
```
Files: src/hawk_hooks/adapters/gemini.py, src/hawk_hooks/event_mapping.py, tests/test_adapter_gemini.py
Task:
- Implement GeminiAdapter.register_hooks() using hawk runners + settings.json hook entries
- Map canonical hawk events to Gemini hook names (e.g. pre_tool_use -> BeforeTool)
- Preserve user-defined hooks; replace only hawk-managed entries
- Skip unsupported events with explicit sync warnings
- Tests: registration, update/cleanup, preservation, unsupported-event handling
```

**Agent E3: Codex Limited Hook Bridge**
```
Files: src/hawk_hooks/adapters/codex.py, src/hawk_hooks/event_mapping.py, tests/test_adapter_codex.py, docs/hawk-v2-research-and-design.md
Task:
- Implement minimal Codex hook support via the available notify-style callback path
- Bridge stop/notification-class events through hawk-generated runner(s)
- Keep unsupported Codex events explicit in sync output (not silently ignored)
- Tests: bridge install/update/remove and manual config preservation
```

**Agent E4 (Optional): Other adapters if low-friction**
```
Files: src/hawk_hooks/adapters/opencode.py, src/hawk_hooks/adapters/cursor.py, src/hawk_hooks/adapters/antigravity.py
Task:
- Add explicit capability flags + warning behavior for hooks
- Implement native registration only where API is stable and low-risk
- Tests: adapter-level smoke tests for hook registration behavior
```

Status:
- E1 complete: event contract + support levels in `src/hawk_hooks/event_mapping.py`
- E2 complete: Gemini hook registration in `src/hawk_hooks/adapters/gemini.py`
- E3 complete: Codex notify bridge in `src/hawk_hooks/adapters/codex.py`
- E4 complete: OpenCode/Cursor/Antigravity hook capability flags + explicit warning behavior

---

## Dependency Graph

```
Phase A (TUI Polish)          Phase B (Package Lifecycle)     Phase C (Hook Discovery)    Phase E (Cross-Tool Hooks)
  A1: Scope Detection           B1: Scan Source Tracking        C1: Metadata-Anywhere       E1: Event Contract
  A2: Registry Browser          B2: Migration Schema                                        E2: Gemini Native
                                                                                             E3: Codex Bridge
       |                             |                               |                       E4: Optional Others
       +-----------------------------+-------------------------------+------------------------------+
                                                                                                      |
                                                                                               Phase D (Pre-Merge)
                                                                                                D1: Reconciliation
```

A, B, C, and E can run in parallel by agent.
D runs after everything else lands.

## Execution Notes

- Each agent task is self-contained with file list, clear task, and test expectations
- Agents A1, A2, B1, B2, C1, E1, E2, E3 can run simultaneously (8 parallel agents; E4 optional)
- Or run as 4 phases: A (2 agents) || B (2 agents) || C (1 agent) || E (3-4 agents), then D
- After each phase, run `python3 -m pytest tests/ --ignore=tests/test_cli.py -q` to verify
- Cross-tool hook registration is now in scope under Phase E
