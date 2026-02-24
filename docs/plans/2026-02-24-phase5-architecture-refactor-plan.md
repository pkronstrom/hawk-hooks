# Phase 5: Architecture Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Break apart two oversized modules (dashboard.py ~2334 lines, base.py ~694 lines) into focused, testable units; extract a download service to eliminate CLI→TUI coupling; fix naming drift in docs.

**Architecture:** Extract concern-specific handler modules from the monolithic dashboard, compose adapter base from focused mixins, introduce a download service layer between CLI/TUI and git operations, and update stale doc references.

**Tech Stack:** Python 3, pathlib, YAML/JSON, pytest, existing hawk-hooks infrastructure

---

## Task 1: Extract dashboard action handlers into separate modules

**Files:**
- Create: `src/hawk_hooks/v2_interactive/handlers/__init__.py`
- Create: `src/hawk_hooks/v2_interactive/handlers/packages.py`
- Create: `src/hawk_hooks/v2_interactive/handlers/codex_consent.py`
- Create: `src/hawk_hooks/v2_interactive/handlers/missing_components.py`
- Create: `src/hawk_hooks/v2_interactive/handlers/environment.py`
- Create: `src/hawk_hooks/v2_interactive/handlers/registry_browser.py`
- Create: `src/hawk_hooks/v2_interactive/handlers/projects.py`
- Modify: `src/hawk_hooks/v2_interactive/dashboard.py`
- Test: `tests/test_dashboard_handlers.py` (smoke tests for imports + function signatures)

### Extraction Map

Each handler module gets the functions from dashboard.py that belong to its concern. The dashboard.py main loop (`run_dashboard`) and menu rendering stay in dashboard.py.

| New Module | Functions to Move | Dashboard Lines |
|---|---|---|
| `handlers/packages.py` | `_handle_packages` + all 10 nested helpers, `_confirm_registry_item_delete` | 266-274, 889-1506 |
| `handlers/codex_consent.py` | `_handle_codex_multi_agent_setup`, `_get_codex_multi_agent_consent`, `_is_codex_multi_agent_setup_required` | 164-185, 1720-1781 |
| `handlers/missing_components.py` | `_find_package_lock_path`, `_iter_lock_packages`, `_install_from_package_lock`, `_remove_names_from_section`, `_remove_missing_references`, `_handle_missing_components_setup`, `_compute_missing_components` | 188-213, 1784-2072 |
| `handlers/environment.py` | `_handle_uninstall_from_environment`, `_build_environment_menu_entries`, `_handle_environment`, `_handle_tools_toggle`, `_prune_disabled_tools` | 813-887, 2148-2220 |
| `handlers/registry_browser.py` | `_handle_registry_browser` | 277-343 |
| `handlers/projects.py` | `_handle_projects`, `_delete_project_scope`, `_prompt_delete_scope`, `_run_projects_tree` | 1509-1717 |

Functions that **stay** in dashboard.py (core orchestration):
- State management: `_detect_scope`, `_load_state`, `_count_enabled` (lines 60-161)
- UI utilities: `_human_size`, `_path_size`, `_run_editor_command` (lines 216-263)
- Menu rendering: `_build_header`, `_build_menu_options`, `_normalize_main_menu_cursor`, `_move_main_menu_cursor`, `_build_main_menu_display`, `_run_main_menu` (lines 346-509)
- Toggle core: `_build_toggle_scopes`, `_handle_component_toggle`, `_make_mcp_add_callback` (lines 512-810)
- Sync: `_sync_all_with_preflight`, `_handle_sync`, `_apply_auto_sync_if_needed` (lines 2075-2115)
- Download: `_handle_download` (lines 2118-2145) — moves to use download_service in Task 3
- Exit: `_prompt_sync_on_exit` (lines 2223-2260)
- Main loop: `run_dashboard` (lines 2262-2334)

### Step 1: Create handler module skeleton

Create `src/hawk_hooks/v2_interactive/handlers/__init__.py`:

```python
"""Dashboard action handler modules.

Each module owns one concern area previously inlined in dashboard.py.
Handlers receive the dashboard state dict and console, returning
a dirty flag (bool) when they modify config.
"""
```

### Step 2: Extract packages handler

Move `_handle_packages` (lines 889-1506) and `_confirm_registry_item_delete` (lines 266-274) into `handlers/packages.py`. Keep function signatures identical. Add necessary imports at the top of the new module.

The function references `_run_editor_command` and `_human_size` from dashboard — import these from dashboard or move them to a shared `handlers/_utils.py` if needed by multiple handlers.

```python
# handlers/packages.py
"""Package management accordion UI handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console

# Import shared utilities that stay in dashboard
from ..dashboard import _run_editor_command, _human_size, _path_size


def confirm_registry_item_delete(console: Console, name: str, comp_type: str) -> bool:
    """Ask for confirmation before deleting a registry item."""
    # ... moved from dashboard._confirm_registry_item_delete


def handle_packages(state: dict[str, Any], console: Console) -> bool:
    """Package management accordion UI. Returns True if config changed."""
    # ... moved from dashboard._handle_packages
    # All nested helpers move with it as local functions (they already are)
```

In dashboard.py, replace the moved functions with imports:

```python
from .handlers.packages import handle_packages, confirm_registry_item_delete
```

Update `run_dashboard` dispatch to call `handle_packages(state, console)` instead of `_handle_packages(state, console)`.

### Step 3: Extract remaining handlers

Repeat the same pattern for each handler module. Each gets:
- Its functions moved verbatim (drop leading `_` since they're now module-public)
- Required imports added
- Dashboard.py updated to import and dispatch to the new module

Order: `codex_consent.py`, `missing_components.py`, `environment.py`, `registry_browser.py`, `projects.py`.

### Step 4: Write smoke tests

```python
# tests/test_dashboard_handlers.py
"""Verify handler modules import correctly and expose expected functions."""

def test_packages_handler_imports():
    from hawk_hooks.v2_interactive.handlers.packages import handle_packages, confirm_registry_item_delete
    assert callable(handle_packages)
    assert callable(confirm_registry_item_delete)

def test_codex_consent_handler_imports():
    from hawk_hooks.v2_interactive.handlers.codex_consent import handle_codex_multi_agent_setup
    assert callable(handle_codex_multi_agent_setup)

def test_missing_components_handler_imports():
    from hawk_hooks.v2_interactive.handlers.missing_components import handle_missing_components_setup
    assert callable(handle_missing_components_setup)

def test_environment_handler_imports():
    from hawk_hooks.v2_interactive.handlers.environment import handle_environment
    assert callable(handle_environment)

def test_registry_browser_handler_imports():
    from hawk_hooks.v2_interactive.handlers.registry_browser import handle_registry_browser
    assert callable(handle_registry_browser)

def test_projects_handler_imports():
    from hawk_hooks.v2_interactive.handlers.projects import handle_projects
    assert callable(handle_projects)
```

### Step 5: Run tests to verify nothing broke

Run: `python3 -m pytest tests/ --ignore=tests/test_cli.py -q`
Expected: All existing tests pass (handler extraction is purely structural)

### Step 6: Commit

```bash
git add src/hawk_hooks/v2_interactive/handlers/ tests/test_dashboard_handlers.py src/hawk_hooks/v2_interactive/dashboard.py
git commit -m "refactor(dashboard): extract action handlers into focused modules"
```

---

## Task 2: Extract adapter base class into composable mixins

**Files:**
- Create: `src/hawk_hooks/adapters/mixins/__init__.py`
- Create: `src/hawk_hooks/adapters/mixins/runner.py`
- Create: `src/hawk_hooks/adapters/mixins/mcp.py`
- Modify: `src/hawk_hooks/adapters/base.py`
- Test: `tests/test_adapter_mixins.py`

### Mixin Extraction Map

Based on the analysis, base.py has these composable groups:

| Mixin Module | Methods | Base.py Lines | Coupling |
|---|---|---|---|
| `mixins/runner.py` → `HookRunnerMixin` | `_generate_runners()` | 237-369 | Metadata parsing + bash templating only |
| `mixins/mcp.py` → `MCPMixin` | `_load_mcp_servers()`, `_merge_mcp_json()`, `_read_mcp_json()`, `_merge_mcp_sidecar()` | 461-638 | JSON/YAML I/O only |

Methods that **stay** on `ToolAdapter`:
- Properties and abstract methods (lines 23-156)
- `sync()` orchestration (lines 158-235)
- `_sync_component()` and `_find_current_symlinks()` (lines 372-459)
- `_create_symlink()` and `_remove_link()` (lines 640-658)
- Hook diagnostics (lines 660-694)
- All component linking (lines 73-139) — could extract later but low value

### Step 1: Create mixin module skeleton

```python
# src/hawk_hooks/adapters/mixins/__init__.py
"""Composable mixins extracted from ToolAdapter base.

These mixins encapsulate self-contained responsibilities that were
previously inlined in the monolithic base adapter class.
"""
from .runner import HookRunnerMixin
from .mcp import MCPMixin
```

### Step 2: Extract HookRunnerMixin

Move `_generate_runners()` (lines 237-369) into `mixins/runner.py`:

```python
# src/hawk_hooks/adapters/mixins/runner.py
"""Hook runner generation mixin.

Generates per-event bash runner scripts from hook metadata.
"""
from __future__ import annotations

import shlex
import stat
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...hook_meta import HookMeta


class HookRunnerMixin:
    """Generates bash runner scripts for hook events."""

    def _generate_runners(
        self,
        hook_names: list[str],
        registry_path: Path,
        runners_dir: Path,
    ) -> dict[str, Path]:
        # ... moved verbatim from base.py lines 237-369
        ...
```

### Step 3: Extract MCPMixin

Move `_load_mcp_servers()`, `_merge_mcp_json()`, `_read_mcp_json()`, `_merge_mcp_sidecar()` (lines 461-638) into `mixins/mcp.py`:

```python
# src/hawk_hooks/adapters/mixins/mcp.py
"""MCP server configuration merge strategies.

Provides loading, inline-marker merge (Claude), and sidecar merge (Gemini).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


class MCPMixin:
    """MCP server loading and merge strategies."""

    @staticmethod
    def _load_mcp_servers(
        mcp_names: list[str],
        mcp_dir: Path,
    ) -> dict[str, dict[str, Any]]:
        # ... moved from base.py lines 461-500
        ...

    @staticmethod
    def _merge_mcp_json(
        config_path: Path,
        servers: dict[str, dict],
        server_key: str = "mcpServers",
    ) -> None:
        # ... moved from base.py lines 502-541
        ...

    @staticmethod
    def _read_mcp_json(
        config_path: Path,
        server_key: str = "mcpServers",
    ) -> dict[str, dict]:
        # ... moved from base.py lines 543-567
        ...

    @staticmethod
    def _merge_mcp_sidecar(
        config_path: Path,
        servers: dict[str, dict],
        server_key: str = "mcpServers",
    ) -> None:
        # ... moved from base.py lines 569-638
        ...
```

### Step 4: Update ToolAdapter to inherit mixins

```python
# base.py - change class declaration
from .mixins import HookRunnerMixin, MCPMixin

class ToolAdapter(HookRunnerMixin, MCPMixin, ABC):
    """Abstract base for AI CLI tool adapters."""
    # ... remaining methods stay here
    # Remove the methods that moved to mixins
```

### Step 5: Write mixin tests

```python
# tests/test_adapter_mixins.py
"""Test that adapter mixins work correctly in isolation."""

from hawk_hooks.adapters.mixins.runner import HookRunnerMixin
from hawk_hooks.adapters.mixins.mcp import MCPMixin


def test_runner_mixin_instantiable():
    """HookRunnerMixin can be instantiated standalone."""
    obj = HookRunnerMixin()
    assert hasattr(obj, "_generate_runners")


def test_mcp_mixin_instantiable():
    """MCPMixin can be instantiated standalone."""
    obj = MCPMixin()
    assert hasattr(obj, "_load_mcp_servers")
    assert hasattr(obj, "_merge_mcp_json")
    assert hasattr(obj, "_read_mcp_json")
    assert hasattr(obj, "_merge_mcp_sidecar")


def test_mcp_load_servers_missing_dir(tmp_path):
    """_load_mcp_servers handles missing registry dir gracefully."""
    result = MCPMixin._load_mcp_servers(["nonexistent"], tmp_path / "nope")
    assert result == {}


def test_mcp_merge_json_creates_file(tmp_path):
    """_merge_mcp_json creates config file if missing."""
    config = tmp_path / "config.json"
    MCPMixin._merge_mcp_json(config, {"test-server": {"command": "echo"}})
    import json
    data = json.loads(config.read_text())
    assert "test-server" in data["mcpServers"]
    assert data["mcpServers"]["test-server"]["__hawk_managed"] is True
```

### Step 6: Run tests

Run: `python3 -m pytest tests/ --ignore=tests/test_cli.py -q`
Expected: All pass — mixin inheritance preserves behavior

### Step 7: Commit

```bash
git add src/hawk_hooks/adapters/mixins/ src/hawk_hooks/adapters/base.py tests/test_adapter_mixins.py
git commit -m "refactor(adapters): extract runner and MCP mixins from base adapter"
```

---

## Task 3: Replace dashboard→CLI coupling with download service

**Files:**
- Create: `src/hawk_hooks/download_service.py`
- Modify: `src/hawk_hooks/v2_interactive/dashboard.py` (or `handlers/missing_components.py` if Task 1 done first)
- Modify: `src/hawk_hooks/v2_interactive/wizard.py`
- Modify: `src/hawk_hooks/cli.py`
- Test: `tests/test_download_service.py`

### Problem

Dashboard imports `cmd_download` from `cli.py` and catches `SystemExit` in two places (lines 1870 and 2140). Wizard does the same with `cmd_scan` (line 155). CLI functions use `sys.exit()` for error reporting, which the TUI must trap.

### Step 1: Write failing test for download service

```python
# tests/test_download_service.py
"""Tests for download_service — business logic without CLI/TUI coupling."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_download_and_install_returns_result(tmp_path):
    """download_and_install returns a DownloadResult, never raises SystemExit."""
    from hawk_hooks.download_service import download_and_install, DownloadResult

    # Mock git clone to avoid network
    with patch("hawk_hooks.download_service._clone_repo") as mock_clone:
        mock_clone.return_value = tmp_path / "cloned"
        (tmp_path / "cloned").mkdir()

        result = download_and_install(
            url="https://github.com/example/repo",
            registry_path=tmp_path / "registry",
            config_path=tmp_path / "config.yaml",
            select_all=True,
            replace=False,
        )
        assert isinstance(result, DownloadResult)
        assert not isinstance(result, SystemExit)


def test_download_and_install_error_returns_failure(tmp_path):
    """On clone failure, returns error result instead of SystemExit."""
    from hawk_hooks.download_service import download_and_install, DownloadResult

    with patch("hawk_hooks.download_service._clone_repo") as mock_clone:
        mock_clone.side_effect = RuntimeError("clone failed")

        result = download_and_install(
            url="https://github.com/example/repo",
            registry_path=tmp_path / "registry",
            config_path=tmp_path / "config.yaml",
            select_all=True,
            replace=False,
        )
        assert isinstance(result, DownloadResult)
        assert result.success is False
        assert "clone failed" in result.error
```

### Step 2: Run test to verify it fails

Run: `python3 -m pytest tests/test_download_service.py -v`
Expected: FAIL — `download_service` module doesn't exist

### Step 3: Implement download service

Extract the business logic from `cmd_download` (cli.py lines 598-700) into a service layer:

```python
# src/hawk_hooks/download_service.py
"""Download service — business logic for cloning and installing packages.

Extracted from cmd_download() in cli.py to eliminate SystemExit coupling.
Used by both CLI (with output formatting) and TUI (with state dict).
"""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .downloader import scan_local_path, classify_item
from .registry import Registry
from .v2_config import load_config, save_config

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Result of a download-and-install operation."""
    success: bool
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    clashes: list[str] = field(default_factory=list)
    error: str | None = None
    package_name: str | None = None


def _clone_repo(url: str, dest: Path) -> Path:
    """Shallow clone a git URL. Raises RuntimeError on failure."""
    import subprocess
    result = subprocess.run(
        ["git", "clone", "--depth=1", url, str(dest)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr.strip()}")
    return dest


def download_and_install(
    url: str,
    registry_path: Path,
    config_path: Path,
    *,
    select_all: bool = False,
    replace: bool = False,
    name: str | None = None,
    select_fn: callable | None = None,
) -> DownloadResult:
    """Clone a URL, classify components, install to registry.

    Args:
        url: Git URL to clone
        registry_path: Path to hawk registry
        config_path: Path to config.yaml
        select_all: Install all found components without prompting
        replace: Replace existing components on clash
        name: Override package name
        select_fn: Optional callback(items) -> selected_items for interactive selection.
                   If None and select_all is False, installs nothing.

    Returns:
        DownloadResult with success/failure and details
    """
    # ... extract core logic from cmd_download:
    # 1. Clone to tempdir
    # 2. Scan and classify
    # 3. Check clashes
    # 4. Install selected items to registry
    # 5. Record package in packages.yaml
    # 6. Return DownloadResult
    ...
```

### Step 4: Update CLI to use download service

In `cli.py`, refactor `cmd_download` to delegate to `download_service.download_and_install()`:

```python
def cmd_download(args):
    """CLI wrapper: calls download service, formats output, exits on error."""
    from .download_service import download_and_install

    result = download_and_install(
        url=args.url,
        registry_path=_get_registry_path(),
        config_path=_get_config_path(),
        select_all=getattr(args, "all", False),
        replace=getattr(args, "replace", False),
        name=getattr(args, "name", None),
        select_fn=_interactive_select_items if not getattr(args, "all", False) else None,
    )

    if not result.success:
        print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(1)

    # ... format output as before
    print(f"Added {len(result.added)} components")
    if result.skipped:
        print(f"Skipped {len(result.skipped)} (use --replace to overwrite)")
```

### Step 5: Update dashboard to use download service

Replace `cmd_download` imports with `download_service` calls. Remove `SystemExit` catches:

In `_install_from_package_lock` (dashboard.py or handlers/missing_components.py):

```python
# Before:
from ..cli import cmd_download
try:
    cmd_download(args)
    attempted += 1
except SystemExit:
    continue

# After:
from ..download_service import download_and_install
result = download_and_install(
    url=url,
    registry_path=registry_path,
    config_path=config_path,
    select_all=True,
    replace=False,
    name=name,
)
if result.success:
    attempted += 1
```

In `_handle_download` (dashboard.py):

```python
# Before:
from ..cli import cmd_download
try:
    cmd_download(args)
except SystemExit:
    pass

# After:
from ..download_service import download_and_install
result = download_and_install(
    url=url,
    registry_path=registry_path,
    config_path=config_path,
    select_all=False,
    replace=False,
)
if not result.success:
    console.print(f"[red]{result.error}[/red]")
```

### Step 6: Run tests

Run: `python3 -m pytest tests/ --ignore=tests/test_cli.py -q`
Expected: All pass

### Step 7: Commit

```bash
git add src/hawk_hooks/download_service.py src/hawk_hooks/cli.py src/hawk_hooks/v2_interactive/dashboard.py tests/test_download_service.py
git commit -m "refactor: extract download service to decouple TUI from CLI"
```

---

## Task 4: Fix naming drift in documentation

**Files:**
- Modify: `docs/plans/DONE-2026-02-21-v2-completion-plan.md`
- Modify: `docs/plans/DONE-2026-02-23-v2-architecture-refactor-plan.md`
- Modify: `docs/plans/DONE-2026-02-23-search-provider-plugin-system-plan.md`
- Modify: `CLAUDE.md`

### Problem

Design docs reference `src/hawk_hooks/v2_cli.py` but the actual implementation is `src/hawk_hooks/cli.py`. Similarly, `tests/test_v2_cli.py` exists and correctly imports from `cli.py`, but docs reference it inconsistently.

### Step 1: Fix references in completed plan docs

Search-and-replace `v2_cli.py` → `cli.py` in each doc file, but only for source path references (not the test file which is actually named `test_v2_cli.py`).

Specifically:
- `src/hawk_hooks/v2_cli.py` → `src/hawk_hooks/cli.py`
- Keep `tests/test_v2_cli.py` references as-is (file actually exists with that name)

### Step 2: Update CLAUDE.md architecture table

In CLAUDE.md, the primary architecture section lists `v2_cli.py`:

```markdown
# Before:
├── v2_cli.py               # Main CLI entry

# After:
├── cli.py                   # Main CLI entry (hawk + hawk-hooks commands)
```

### Step 3: Verify no runtime references to v2_cli

Run: `grep -r "v2_cli" src/` — should return zero matches (only docs and tests reference it).

### Step 4: Commit

```bash
git add docs/plans/ CLAUDE.md
git commit -m "docs: fix v2_cli.py naming drift — actual module is cli.py"
```

---

## Execution Order

Tasks are independent and can be done in any order. Recommended sequence:

1. **Task 4** (5 min) — pure docs, zero risk, quick win
2. **Task 2** (30 min) — mixin extraction is cleanly isolated
3. **Task 1** (45 min) — largest extraction, benefits from Task 2 being done
4. **Task 3** (45 min) — new service layer, most complex, do last

Tasks 1 and 2 can be parallelized since they touch different files.
Tasks 3 depends on knowing the final dashboard structure (Task 1).
