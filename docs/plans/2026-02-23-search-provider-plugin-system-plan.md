# Search Provider Plugin System Implementation Plan

Status: undone

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a clean, opt-in search provider plugin system to Hawk so `hawk search` can aggregate results from enabled providers (for example PRPM and Playbooks), let users browse in Hawk UI, and choose whether to download/import into the registry.

**Architecture:** Keep provider integrations out of core command logic by introducing a small plugin boundary (`SearchProvider` protocol + provider manager + search service). Core Hawk only orchestrates provider lifecycle, normalization, and registry import; provider plugins own external CLI/API details. Use opt-in config and explicit install hints for missing plugins/tools.

**Tech Stack:** Python 3.10+, argparse CLI, Rich/simple-term-menu UI, existing `downloader`/`registry`/`v2_config`/`package_service`, pytest.

---

## Design principles (locked)

1. Provider integrations must not add provider-specific branching to core CLI/TUI flows.
2. `hawk search` reads only enabled providers from config and degrades gracefully.
3. Missing provider plugin and missing external CLI are separate states, each with explicit install command hints.
4. Search results are normalized to one schema before rendering.
5. Download/import is explicit user action; import does not auto-enable and does not auto-sync.
6. Download preview uses an ephemeral temp workspace, not persistent staging.
7. Package metadata remains backward-compatible with existing `url/path` entries.

## Provider model and plugin contract

1. New plugin group: `hawk.search_providers` via Python entry points.
2. Provider interface (protocol):

```python
@dataclass
class SearchHit:
    provider: str
    id: str
    name: str
    summary: str
    version: str | None
    homepage: str | None
    source_url: str | None
    tags: list[str]
    score: float | None
    raw: dict[str, Any]

@dataclass
class ProviderStatus:
    provider: str
    available: bool
    reason: str | None
    install_hint: str | None

@dataclass
class DownloadedArtifact:
    provider: str
    package_id: str
    version: str | None
    root_dir: Path
    source_ref: str

class SearchProvider(Protocol):
    provider_id: str
    display_name: str

    def status(self) -> ProviderStatus: ...
    def search(self, query: str, *, limit: int) -> list[SearchHit]: ...
    def download(self, hit: SearchHit, *, dest_dir: Path) -> DownloadedArtifact: ...
```

3. Each provider plugin maps native output (`json`/`jsonl`/text) into `SearchHit`.
4. Core never parses provider-native payload formats directly.

## Plugin interface behavior contract (explicit)

1. `status()` must not raise for expected runtime failures (missing CLI, bad auth, missing config). It must return `ProviderStatus(available=False, reason=..., install_hint=...)`.
2. `search(query, limit)` must be deterministic for same inputs, return normalized `SearchHit` objects, and never return provider-native dicts as top-level items.
3. `download(hit, dest_dir)` must place all fetched content under `dest_dir` and return `DownloadedArtifact.root_dir` inside that directory.
4. Providers must not write to Hawk registry/config directly. Only core Hawk imports into registry.
5. Provider errors must use typed exceptions so UI can map to user-safe status messages.
6. Provider subprocess/network calls must enforce timeouts and return actionable error messages.
7. `SearchHit.id` must be stable per provider; `provider + id + version` is used as import/reference identity.
8. `SearchHit.raw` may contain provider-native metadata, but UI uses normalized fields only.
9. Providers must support empty/no-result responses without treating that as an error.
10. Providers must document required runtime tools/env vars in plugin package README and return matching install hints.

## Config contract

Add to global config (`config.yaml`) with defaults:

```yaml
search:
  enabled: true
  default_limit: 25
  enabled_providers: []
  providers:
    prpm:
      enabled: false
    playbooks:
      enabled: false
```

Provider catalog (core constant) includes install hints even if plugin is missing:

```python
KNOWN_PROVIDER_HINTS = {
  "prpm": {
    "plugin_install": "uv pip install hawk-search-prpm",
    "runtime_install": "see provider docs for installing `prpm` CLI",
  },
  "playbooks": {
    "plugin_install": "uv pip install hawk-search-playbooks",
    "runtime_install": "see provider docs for installing `playbooks` CLI",
  },
}
```

## Data compatibility contract

1. Extend package entries with optional structured source block:

```yaml
packages:
  some-package:
    source:
      type: provider
      provider: prpm
      ref: "pkg-id@version"
```

2. Keep existing `url` and `path` semantics untouched for legacy entries.
3. `_package_source_type` should prefer `source.type` when present; otherwise fallback to legacy inference.

## Search UX contract (locked)

1. `hawk search <query>` shows a unified provider result list.
2. `space/enter` opens package details.
3. `d` downloads into an ephemeral temp workspace and opens import preview.
4. `v` views selected file content.
5. `o` opens local file/path.
6. `w` opens upstream website/source URL.
7. `i` imports selected items to registry.
8. `q/esc` returns/backs out.
9. No `D` shortcut in v1 of this flow.
10. Enable/disable/link and sync stay in existing Hawk menus/flows.

## UI implementation guidelines (match existing Hawk patterns)

1. Reuse existing TUI primitives (`rich.live.Live`, `readchar`, `TerminalMenu`, theme helpers) used in `dashboard.py` and `toggle.py`.
2. Keep navigation conventions identical: arrow keys + `j/k` move cursor; `space/enter` primary action; `q/esc` back.
3. Keep destructive semantics consistent across Hawk: `d` is not delete in search screens; use explicit confirmation for import operations that replace/conflict.
4. Keep status/footer style consistent with existing screens: dim hint line, concise action hints, and context-aware help text.
5. Use the same row model style as package/toggle views: selectable rows, separator rows, action rows, cursor skipping non-selectable rows.
6. Preserve scope awareness patterns: search/import screens must not mutate scope enabled lists implicitly.
7. Keep screen titles and section headers scoped and concise (`scoped_header`, `dim_separator`, theme color helpers).
8. Show provider/source badges in result rows (`[prpm]`, `[playbooks]`) but keep row density similar to package list.
9. Include a conflict preview before import, reusing existing clash language (`replace`, `skip`, owner package info).
10. Keep keymap discoverable at the bottom of each screen and aligned with current Hawk wording style.
11. Avoid introducing modal complexity beyond existing flows; one details screen + one import preview screen is sufficient for v1.
12. Follow existing action ordering in menus: inspect first, mutate second, exit/back last.

## Task 1: Add provider core interfaces and discovery manager

**Files:**
1. Create: `src/hawk_hooks/search_plugins/base.py`
2. Create: `src/hawk_hooks/search_plugins/manager.py`
3. Create: `src/hawk_hooks/search_plugins/catalog.py`
4. Create: `src/hawk_hooks/search_plugins/__init__.py`
5. Test: `tests/test_search_plugin_manager.py`

**Step 1: Write the failing tests**

```python
def test_manager_discovers_entrypoint_providers(monkeypatch):
    ...
    assert "prpm" in manager.list_available_ids()


def test_manager_reports_install_hint_for_missing_provider():
    status = manager.get_provider_status("playbooks")
    assert status.available is False
    assert "hawk-search-playbooks" in status.install_hint
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_search_plugin_manager.py -k "discovers_entrypoint or install_hint"`
Expected: FAIL with missing module/class errors.

**Step 3: Write minimal implementation**

```python
# manager.py
from importlib.metadata import entry_points

def load_providers() -> dict[str, SearchProvider]:
    providers = {}
    for ep in entry_points(group="hawk.search_providers"):
        provider_cls = ep.load()
        provider = provider_cls()
        providers[provider.provider_id] = provider
    return providers
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_search_plugin_manager.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/hawk_hooks/search_plugins tests/test_search_plugin_manager.py
git commit -m "feat(search): add provider plugin manager and contracts"
```

## Task 2: Add search config schema and backward-compatible package source typing

**Files:**
1. Modify: `src/hawk_hooks/v2_config.py`
2. Modify: `src/hawk_hooks/cli.py`
3. Modify: `src/hawk_hooks/package_service.py`
4. Test: `tests/test_v2_config.py`
5. Test: `tests/test_package_service.py`
6. Test: `tests/test_v2_cli.py`

**Step 1: Write the failing tests**

```python
def test_global_defaults_include_search_block(v2_env):
    cfg = v2_config.load_global_config()
    assert cfg["search"]["enabled"] is True
    assert cfg["search"]["enabled_providers"] == []


def test_package_source_type_prefers_structured_source():
    assert _package_source_type({"source": {"type": "provider"}}) == "provider"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_v2_config.py tests/test_package_service.py tests/test_v2_cli.py -k "search_block or source_type_prefers"`
Expected: FAIL because keys/functions do not support new shape.

**Step 3: Write minimal implementation**

```python
# v2_config.DEFAULT_GLOBAL_CONFIG
"search": {
    "enabled": True,
    "default_limit": 25,
    "enabled_providers": [],
    "providers": {},
}

# source typing helper
src = pkg_data.get("source", {})
if isinstance(src, dict) and src.get("type"):
    return str(src["type"])
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_v2_config.py tests/test_package_service.py tests/test_v2_cli.py -k "search_block or source_type_prefers"`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/hawk_hooks/v2_config.py src/hawk_hooks/cli.py src/hawk_hooks/package_service.py tests/test_v2_config.py tests/test_package_service.py tests/test_v2_cli.py
git commit -m "feat(search): add config defaults and source-type compatibility"
```

## Task 3: Build CLI adapter runner for provider-native output normalization

**Files:**
1. Create: `src/hawk_hooks/search_plugins/cli_runner.py`
2. Create: `src/hawk_hooks/search_plugins/normalize.py`
3. Test: `tests/test_search_cli_runner.py`

**Step 1: Write the failing tests**

```python
def test_parse_json_array_output_to_hits():
    raw = '[{"id":"a","name":"alpha"}]'
    hits = parse_provider_output(raw, mode="json", provider="prpm")
    assert hits[0].id == "a"


def test_parse_jsonl_output_to_hits():
    raw = '{"id":"a"}\n{"id":"b"}\n'
    hits = parse_provider_output(raw, mode="jsonl", provider="playbooks")
    assert [h.id for h in hits] == ["a", "b"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_search_cli_runner.py`
Expected: FAIL with missing parser/runner symbols.

**Step 3: Write minimal implementation**

```python
def run_cli_json(cmd: list[str], timeout_sec: int) -> Any:
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=True)
    return json.loads(completed.stdout)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_search_cli_runner.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/hawk_hooks/search_plugins/cli_runner.py src/hawk_hooks/search_plugins/normalize.py tests/test_search_cli_runner.py
git commit -m "feat(search): add cli runner and output normalization helpers"
```

## Task 4: Add search service orchestration (aggregate, browse, ephemeral preview, import)

**Files:**
1. Create: `src/hawk_hooks/search_service.py`
2. Modify: `src/hawk_hooks/downloader.py` (reuse import helpers only if required)
3. Modify: `src/hawk_hooks/v2_config.py` (`record_package` to accept `source` metadata)
4. Test: `tests/test_search_service.py`
5. Test: `tests/test_downloader.py` (regression for import behavior)

**Step 1: Write the failing tests**

```python
def test_search_service_aggregates_enabled_providers(monkeypatch):
    results = service.search("guard", providers=["prpm", "playbooks"])
    assert len(results.hits) == 2


def test_import_from_preview_does_not_auto_enable_or_sync(monkeypatch, tmp_path):
    preview = service.download_for_preview(hit)
    report = service.import_from_preview(preview, selected_items=preview.items, enable=False, sync=False)
    assert report.added_count > 0
    cfg = v2_config.load_global_config()
    assert cfg["global"]["skills"] == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_search_service.py -k "aggregates_enabled_providers or does_not_auto_enable_or_sync"`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
@dataclass
class SearchAggregate:
    hits: list[SearchHit]
    provider_status: list[ProviderStatus]


def search(query: str, *, enabled_provider_ids: list[str], limit: int) -> SearchAggregate:
    ...


def download_for_preview(hit: SearchHit) -> SearchPreview:
    # provider.download -> temp dir -> scan_directory -> build preview rows (items/conflicts/owners)
    ...


def import_from_preview(preview: SearchPreview, *, selected_items: list[...], replace: bool = False, enable: bool = False, sync: bool = False) -> ImportReport:
    # add_items_to_registry -> record_package(source=...)
    # must not auto-enable or auto-sync by default
    ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_search_service.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/hawk_hooks/search_service.py src/hawk_hooks/v2_config.py tests/test_search_service.py tests/test_downloader.py
git commit -m "feat(search): add provider search/import orchestration service"
```

## Task 5: Add `hawk search` CLI command and interactive browse/download flow

**Files:**
1. Modify: `src/hawk_hooks/cli.py`
2. Test: `tests/test_v2_cli.py`

**Step 1: Write the failing tests**

```python
def test_search_command_parsing():
    args = build_parser().parse_args(["search", "tdd"])
    assert args.command == "search"
    assert args.query == "tdd"


def test_cmd_search_prints_install_hint_for_missing_provider(monkeypatch, capsys):
    ...
    cmd_search(args)
    assert "uv pip install hawk-search-prpm" in capsys.readouterr().out
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_v2_cli.py -k "search_command_parsing or install_hint_for_missing_provider"`
Expected: FAIL due missing parser branch and handler.

**Step 3: Write minimal implementation**

```python
search_p = subparsers.add_parser("search", help="Search enabled providers for installable components")
search_p.add_argument("query", help="Search query")
search_p.add_argument("--provider", action="append", dest="providers")
search_p.add_argument("--limit", type=int, default=None)
search_p.add_argument("--json", action="store_true")
search_p.set_defaults(func=cmd_search)

# cmd_search key handling (interactive mode)
# enter/space details, d download preview, v view, o open path, w open website, i import, q/esc back
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_v2_cli.py -k "search_command_parsing or install_hint_for_missing_provider"`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/hawk_hooks/cli.py tests/test_v2_cli.py
git commit -m "feat(search): add hawk search command and install-hint UX"
```

## Task 6: Add TUI integration for search providers and provider opt-in settings

**Files:**
1. Modify: `src/hawk_hooks/v2_interactive/dashboard.py`
2. Modify: `src/hawk_hooks/v2_interactive/config_editor.py`
3. Test: `tests/test_v2_dashboard.py`
4. Create: `tests/test_v2_config_editor.py`

**Step 1: Write the failing tests**

```python
def test_build_menu_options_includes_search_entry():
    options = dashboard._build_menu_options(_minimal_state())
    assert any(action == "search" for _, action in options)


def test_environment_menu_shows_provider_status(monkeypatch):
    entries, _ = dashboard._build_environment_menu_entries(state)
    assert any("Search Providers" in entry for entry in entries)


def test_search_help_hints_use_d_for_download_not_delete():
    ...
    assert "d download preview" in help_line
    assert "D" not in help_line
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_v2_dashboard.py tests/test_v2_config_editor.py -k "search_entry or provider_status"`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
# dashboard menu options
options.append(("Search         Discover remote packages", "search"))

# environment entries
f"Search Providers  {enabled}/{total} enabled"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_v2_dashboard.py tests/test_v2_config_editor.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/hawk_hooks/v2_interactive/dashboard.py src/hawk_hooks/v2_interactive/config_editor.py tests/test_v2_dashboard.py tests/test_v2_config_editor.py
git commit -m "feat(search): add tui search entry and provider opt-in settings"
```

## Task 7: Add provider packages (`hawk-search-prpm`, `hawk-search-playbooks`) and contract tests

**Files:**
1. Create: `plugins/hawk-search-prpm/pyproject.toml`
2. Create: `plugins/hawk-search-prpm/src/hawk_search_prpm/provider.py`
3. Create: `plugins/hawk-search-playbooks/pyproject.toml`
4. Create: `plugins/hawk-search-playbooks/src/hawk_search_playbooks/provider.py`
5. Create: `tests/providers/test_prpm_provider_contract.py`
6. Create: `tests/providers/test_playbooks_provider_contract.py`

**Step 1: Write the failing tests**

```python
def test_prpm_provider_status_missing_cli(monkeypatch):
    provider = PrpmProvider()
    monkeypatch.setattr(shutil, "which", lambda _cmd: None)
    status = provider.status()
    assert status.available is False
    assert "install" in (status.install_hint or "")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/providers/test_prpm_provider_contract.py tests/providers/test_playbooks_provider_contract.py`
Expected: FAIL (provider packages not present).

**Step 3: Write minimal implementation**

```python
# pyproject entry point (plugin package)
[project.entry-points."hawk.search_providers"]
prpm = "hawk_search_prpm.provider:PrpmProvider"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/providers/test_prpm_provider_contract.py tests/providers/test_playbooks_provider_contract.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add plugins/hawk-search-prpm plugins/hawk-search-playbooks tests/providers
git commit -m "feat(search): add prpm and playbooks provider plugins"
```

## Task 8: Documentation and verification sweep

**Files:**
1. Modify: `README.md`
2. Create: `docs/search-providers.md`
3. Modify: `docs/CHANGELOG.md` (or `docs/CHANGELOG.md` equivalent used by repo)

**Step 1: Write failing doc/tests checks (if any)**

```bash
# If docs lint exists, add/enable it; otherwise skip and use manual validation.
```

**Step 2: Run full verification**

Run:
1. `uv run pytest -q tests/test_search_plugin_manager.py tests/test_search_cli_runner.py tests/test_search_service.py`
2. `uv run pytest -q tests/test_v2_cli.py tests/test_v2_config.py tests/test_package_service.py tests/test_v2_dashboard.py tests/test_v2_config_editor.py`
3. `uv run pytest -q tests/providers/test_prpm_provider_contract.py tests/providers/test_playbooks_provider_contract.py`

Expected: PASS.

**Step 3: Update docs**

Include:
1. how to install provider plugin package,
2. how to enable provider in settings,
3. how `hawk search` works,
4. missing tool install-hint behavior,
5. guarantee: import does not auto-enable tool integrations and does not auto-sync,
6. ephemeral preview workspace behavior (no persistent staging).

**Step 4: Commit**

```bash
git add README.md docs/search-providers.md docs/CHANGELOG.md
git commit -m "docs(search): document provider plugin install and hawk search workflow"
```

## Risk register

1. Provider output schema drift.
Mitigation: keep provider-specific normalization inside plugin packages and contract tests with fixtures.

2. CLI hangs/timeouts from external tools.
Mitigation: strict subprocess timeouts in `cli_runner`, surface non-fatal provider errors.

3. Package metadata regressions.
Mitigation: preserve legacy `url/path` behavior and add source-type compatibility tests.

4. UI complexity growth in dashboard.
Mitigation: isolate search UI handler and keep existing package/registry code paths unchanged.

5. Unclear Playbooks machine-readable output support.
Mitigation: implement provider contract around parser modes (`json/jsonl/text`) and lock with fixtures from actual command samples before release.

## TODO / Execution Checklist

- [ ] Task 1 complete
- [ ] Task 2 complete
- [ ] Task 3 complete
- [ ] Task 4 complete
- [ ] Task 5 complete
- [ ] Task 6 complete
- [ ] Task 7 complete
- [ ] Task 8 complete
