# Hawk Hook Format Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace event-directory hook layout with flat files carrying `hawk-hook:` metadata headers, enabling multi-event hooks, cross-tool portability, and self-describing hook files.

**Architecture:** New `hook_meta.py` module parses `hawk-hook:` comment headers (scripts) or YAML frontmatter (.md/.txt). `_generate_runners()` in `base.py` switches from `event/filename` splitting to metadata-driven grouping. Builtins are restructured to flat layout with headers. Config uses plain filenames.

**Tech Stack:** Python 3, dataclasses, PyYAML (already a dependency), pytest

**Design doc:** `docs/plans/2026-02-18-hawk-hook-format-design.md`

---

### Task 1: Create `hook_meta.py` — metadata parser

**Files:**
- Create: `src/hawk_hooks/hook_meta.py`
- Test: `tests/test_hook_meta.py`

**Step 1: Write the failing tests**

Create `tests/test_hook_meta.py`:

```python
"""Tests for hawk-hook metadata parsing."""
from dataclasses import field
from pathlib import Path

import pytest

from hawk_hooks.hook_meta import HookMeta, parse_hook_meta


class TestParseCommentHeaders:
    """Parse hawk-hook: comment headers from scripts."""

    def test_single_event(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]

    def test_multiple_events(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# hawk-hook: events=stop,notification\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["stop", "notification"]

    def test_all_fields(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text(
            "#!/usr/bin/env python3\n"
            "# hawk-hook: events=pre_tool_use\n"
            "# hawk-hook: description=Block bad files\n"
            "# hawk-hook: deps=requests\n"
            "# hawk-hook: env=DESKTOP=true\n"
            "# hawk-hook: env=NTFY_ENABLED=false\n"
            "import sys\n"
        )
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]
        assert meta.description == "Block bad files"
        assert meta.deps == "requests"
        assert meta.env == ["DESKTOP=true", "NTFY_ENABLED=false"]

    def test_bash_script(self, tmp_path):
        f = tmp_path / "hook.sh"
        f.write_text("#!/usr/bin/env bash\n# hawk-hook: events=pre_tool_use\n# hawk-hook: description=Block dangerous commands\nset -euo pipefail\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]
        assert meta.description == "Block dangerous commands"

    def test_no_header_returns_empty_events(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# Description: old style\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == []

    def test_stops_at_non_comment_line(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# hawk-hook: events=stop\nimport sys\n# hawk-hook: events=notification\n")
        meta = parse_hook_meta(f)
        # Should only find the header before code starts
        assert meta.events == ["stop"]


class TestParseFrontmatter:
    """Parse hawk-hook YAML frontmatter from .md/.txt files."""

    def test_markdown_frontmatter(self, tmp_path):
        f = tmp_path / "hook.md"
        f.write_text("---\nhawk-hook:\n  events: [stop]\n  description: Check completion\n---\nContent here\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["stop"]
        assert meta.description == "Check completion"

    def test_txt_frontmatter(self, tmp_path):
        f = tmp_path / "hook.txt"
        f.write_text("---\nhawk-hook:\n  events: [user_prompt_submit]\n---\nContent here\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["user_prompt_submit"]

    def test_no_hawk_hook_key_in_frontmatter(self, tmp_path):
        f = tmp_path / "hook.md"
        f.write_text("---\nname: my-command\ndescription: A command\n---\nContent\n")
        meta = parse_hook_meta(f)
        assert meta.events == []

    def test_no_frontmatter(self, tmp_path):
        f = tmp_path / "hook.md"
        f.write_text("# Just a markdown file\nNo frontmatter here.\n")
        meta = parse_hook_meta(f)
        assert meta.events == []

    def test_frontmatter_with_all_fields(self, tmp_path):
        f = tmp_path / "hook.md"
        f.write_text("---\nhawk-hook:\n  events: [stop, notification]\n  description: Notify\n  deps: requests\n  env:\n    - DESKTOP=true\n---\nContent\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["stop", "notification"]
        assert meta.deps == "requests"
        assert meta.env == ["DESKTOP=true"]


class TestDirectoryFallback:
    """Fall back to parent directory name for event inference."""

    def test_parent_is_known_event(self, tmp_path):
        event_dir = tmp_path / "pre_tool_use"
        event_dir.mkdir()
        f = event_dir / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# Description: old style\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]

    def test_parent_is_unknown(self, tmp_path):
        other_dir = tmp_path / "random"
        other_dir.mkdir()
        f = other_dir / "hook.py"
        f.write_text("#!/usr/bin/env python3\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == []

    def test_header_takes_priority_over_parent(self, tmp_path):
        event_dir = tmp_path / "pre_tool_use"
        event_dir.mkdir()
        f = event_dir / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# hawk-hook: events=stop,notification\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["stop", "notification"]

    def test_stdout_md_no_header_uses_parent(self, tmp_path):
        event_dir = tmp_path / "stop"
        event_dir.mkdir()
        f = event_dir / "check.stdout.md"
        f.write_text("# Check things\nDo stuff\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["stop"]
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_hook_meta.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hawk_hooks.hook_meta'`

**Step 3: Write minimal implementation**

Create `src/hawk_hooks/hook_meta.py`:

```python
"""Parse hawk-hook metadata from hook files.

Supports two formats:
- Comment headers in scripts: # hawk-hook: events=pre_tool_use,stop
- YAML frontmatter in .md/.txt: hawk-hook: {events: [stop]}

Fallback: infer events from parent directory name if it matches a known event.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .events import EVENTS

# Matches: # hawk-hook: key=value
_COMMENT_RE = re.compile(r"^#\s*hawk-hook:\s*(\w+)=(.+)$")

# Matches YAML frontmatter delimiters
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass
class HookMeta:
    """Metadata parsed from a hawk hook file."""

    events: list[str] = field(default_factory=list)
    description: str = ""
    deps: str = ""
    env: list[str] = field(default_factory=list)


def parse_hook_meta(path: Path) -> HookMeta:
    """Parse hawk-hook metadata from a file.

    Tries in order:
    1. hawk-hook: comment headers (scripts)
    2. YAML frontmatter with hawk-hook key (.md/.txt)
    3. Parent directory fallback (if parent is a known event name)

    Returns HookMeta with events=[] if no metadata found and no fallback applies.
    """
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return HookMeta()

    suffix = path.suffix.lower()

    # Try comment headers for scripts
    if suffix in (".py", ".sh", ".js", ".ts"):
        meta = _parse_comment_headers(text)
        if meta.events:
            return meta

    # Try YAML frontmatter for markdown/text
    if suffix in (".md", ".txt"):
        meta = _parse_frontmatter(text)
        if meta.events:
            return meta

    # Also try frontmatter for .stdout.md / .stdout.txt
    if path.name.endswith((".stdout.md", ".stdout.txt")):
        meta = _parse_frontmatter(text)
        if meta.events:
            return meta

    # Fallback: parent directory name
    return _fallback_from_parent(path)


def _parse_comment_headers(text: str) -> HookMeta:
    """Parse # hawk-hook: key=value lines from script header."""
    meta = HookMeta()
    found_any = False

    for line in text.splitlines():
        stripped = line.strip()

        # Skip shebang
        if stripped.startswith("#!"):
            continue

        # Stop at first non-comment, non-empty line
        if stripped and not stripped.startswith("#"):
            break

        m = _COMMENT_RE.match(stripped)
        if m:
            key, value = m.group(1), m.group(2).strip()
            found_any = True
            if key == "events":
                meta.events = [e.strip() for e in value.split(",") if e.strip()]
            elif key == "description":
                meta.description = value
            elif key == "deps":
                meta.deps = value
            elif key == "env":
                meta.env.append(value)

    return meta if found_any else HookMeta()


def _parse_frontmatter(text: str) -> HookMeta:
    """Parse YAML frontmatter with hawk-hook key."""
    import yaml

    m = _FRONTMATTER_RE.match(text)
    if not m:
        return HookMeta()

    try:
        data = yaml.safe_load(m.group(1))
    except Exception:
        return HookMeta()

    if not isinstance(data, dict):
        return HookMeta()

    hawk = data.get("hawk-hook")
    if not isinstance(hawk, dict):
        return HookMeta()

    events_raw = hawk.get("events", [])
    if isinstance(events_raw, str):
        events = [e.strip() for e in events_raw.split(",") if e.strip()]
    elif isinstance(events_raw, list):
        events = [str(e) for e in events_raw]
    else:
        events = []

    env_raw = hawk.get("env", [])
    if isinstance(env_raw, str):
        env = [env_raw]
    elif isinstance(env_raw, list):
        env = [str(e) for e in env_raw]
    else:
        env = []

    return HookMeta(
        events=events,
        description=str(hawk.get("description", "")),
        deps=str(hawk.get("deps", "")),
        env=env,
    )


def _fallback_from_parent(path: Path) -> HookMeta:
    """Infer events from parent directory name if it's a known event."""
    parent_name = path.parent.name
    if parent_name in EVENTS:
        return HookMeta(events=[parent_name])
    return HookMeta()
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_hook_meta.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/hawk_hooks/hook_meta.py tests/test_hook_meta.py
git commit -m "feat: add hook_meta.py for parsing hawk-hook metadata headers"
```

---

### Task 2: Restructure builtins to flat layout with hawk-hook headers

**Files:**
- Modify: all files under `builtins/hooks/`
- Delete: `builtins/hooks/{pre_tool_use,post_tool_use,stop,notification,user_prompt_submit,session_start,session_end,pre_compact,subagent_stop}/`

**Important:** `notification/notify.py` and `stop/notify.py` are **not** duplicates. They have different logic:
- `stop/notify.py` — handles `stop_reason`, sends "Task completed" etc.
- `notification/notify.py` — handles `tool_name`, sends "Needs permission: X"

They must become two separate files with different names.

**Step 1: Move files to flat layout and add headers**

For each file, move from `event_dir/filename` to `builtins/hooks/filename` and add `hawk-hook:` header. Rename where needed to avoid clashes.

Files to move (15 files, skipping .keep files):

| From | To | hawk-hook header |
|------|----|-----------------|
| `pre_tool_use/file-guard.py` | `file-guard.py` | `events=pre_tool_use` |
| `pre_tool_use/dangerous-cmd.sh` | `dangerous-cmd.sh` | `events=pre_tool_use` |
| `pre_tool_use/confidence-checker-cli.py` | `confidence-checker-cli.py` | `events=pre_tool_use` |
| `pre_tool_use/git-commit-guide.sh` | `git-commit-guide.sh` | `events=pre_tool_use` |
| `pre_tool_use/loop-detector-cli.py` | `loop-detector-cli.py` | `events=pre_tool_use` |
| `pre_tool_use/scope-creep-detector-cli.py` | `scope-creep-detector-cli.py` | `events=pre_tool_use` |
| `pre_tool_use/shell-lint.sh` | `shell-lint.sh` | `events=pre_tool_use` |
| `post_tool_use/python-format.py` | `python-format.py` | `events=post_tool_use` |
| `post_tool_use/python-lint.py` | `python-lint.py` | `events=post_tool_use` |
| `stop/notify.py` | `notify-stop.py` | `events=stop` |
| `stop/completion-check.stdout.md` | `completion-check.md` | frontmatter `events: [stop]` |
| `stop/completion-validator-cli.py` | `completion-validator-cli.py` | `events=stop` |
| `stop/docs-update.sh` | `docs-update.sh` | `events=stop` |
| `notification/notify.py` | `notify-permission.py` | `events=notification` |
| `user_prompt_submit/context-primer.stdout.md` | `context-primer.md` | frontmatter `events: [user_prompt_submit]` |

For each script, replace the old `# Description:` line with `# hawk-hook:` lines. Keep `# Deps:` and `# Env:` as `# hawk-hook: deps=` and `# hawk-hook: env=`.

Example for `file-guard.py`:
```python
#!/usr/bin/env python3
# hawk-hook: events=pre_tool_use
# hawk-hook: description=Block modifications to sensitive files
```

Example for `completion-check.md` (renamed from `.stdout.md`):
```markdown
---
hawk-hook:
  events: [stop]
  description: Verify task completion before stopping
---

Before stopping, please verify:
...
```

**Step 2: Delete empty event directories**

```bash
rm -rf builtins/hooks/pre_tool_use builtins/hooks/post_tool_use builtins/hooks/stop builtins/hooks/notification builtins/hooks/user_prompt_submit builtins/hooks/session_start builtins/hooks/session_end builtins/hooks/pre_compact builtins/hooks/subagent_stop
```

**Step 3: Verify hook_meta parses all new files**

Write a quick test that scans `builtins/hooks/` and verifies every file has events:

Add to `tests/test_hook_meta.py`:

```python
class TestBuiltins:
    """Verify all bundled hooks have valid hawk-hook metadata."""

    def test_all_builtins_have_events(self):
        builtins_dir = Path(__file__).parent.parent / "builtins" / "hooks"
        if not builtins_dir.exists():
            # Editable install
            builtins_dir = Path(__file__).parent.parent / "builtins" / "hooks"

        # Find the builtins path (try both locations)
        for candidate in [
            Path(__file__).parent.parent / "builtins" / "hooks",
            Path(__file__).parent.parent / "src" / "hawk_hooks" / "builtins" / "hooks",
        ]:
            if candidate.exists():
                builtins_dir = candidate
                break
        else:
            pytest.skip("builtins/hooks not found")

        for f in sorted(builtins_dir.iterdir()):
            if f.name.startswith(".") or f.is_dir():
                continue
            meta = parse_hook_meta(f)
            assert meta.events, f"{f.name} has no events in hawk-hook metadata"
            assert meta.description, f"{f.name} has no description in hawk-hook metadata"
```

Run: `python3 -m pytest tests/test_hook_meta.py::TestBuiltins -v`
Expected: PASS

**Step 4: Commit**

```bash
git add builtins/hooks/
git commit -m "refactor: restructure builtins/hooks to flat layout with hawk-hook headers"
```

---

### Task 3: Update `_generate_runners()` in base adapter

**Files:**
- Modify: `src/hawk_hooks/adapters/base.py:216-318`
- Test: `tests/test_adapter_base.py`

**Step 1: Write failing tests**

Add to `tests/test_adapter_base.py`:

```python
class TestGenerateRunnersWithMeta:
    """Test _generate_runners with hawk-hook metadata (flat files)."""

    def test_groups_by_metadata_events(self, tmp_path, base_adapter):
        """Hook with hawk-hook header groups by declared events."""
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        # Create hook with metadata
        hook = hooks_dir / "guard.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")

        runners = base_adapter._generate_runners(["guard.py"], registry, runners_dir)
        assert "pre_tool_use" in runners
        assert runners["pre_tool_use"].exists()
        content = runners["pre_tool_use"].read_text()
        assert "guard.py" in content

    def test_multi_event_hook(self, tmp_path, base_adapter):
        """Hook targeting multiple events appears in multiple runners."""
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "notify.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=stop,notification\nimport sys\n")

        runners = base_adapter._generate_runners(["notify.py"], registry, runners_dir)
        assert "stop" in runners
        assert "notification" in runners

    def test_content_hook_with_frontmatter(self, tmp_path, base_adapter):
        """Markdown hook with frontmatter generates cat call."""
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "check.md"
        hook.write_text("---\nhawk-hook:\n  events: [stop]\n---\nVerify completion.\n")

        runners = base_adapter._generate_runners(["check.md"], registry, runners_dir)
        assert "stop" in runners
        content = runners["stop"].read_text()
        assert "cat" in content.lower() or "check.md" in content

    def test_hook_without_metadata_skipped(self, tmp_path, base_adapter):
        """Hook with no hawk-hook header and no event dir fallback is skipped."""
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"

        hook = hooks_dir / "random.py"
        hook.write_text("#!/usr/bin/env python3\nimport sys\n")

        runners = base_adapter._generate_runners(["random.py"], registry, runners_dir)
        assert runners == {}

    def test_stale_runners_cleaned(self, tmp_path, base_adapter):
        """Runners for events no longer in use are deleted."""
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)
        runners_dir = tmp_path / "runners"
        runners_dir.mkdir(parents=True)

        # Create a stale runner
        stale = runners_dir / "old_event.sh"
        stale.write_text("#!/bin/bash\nexit 0\n")

        hook = hooks_dir / "guard.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")

        base_adapter._generate_runners(["guard.py"], registry, runners_dir)
        assert not stale.exists()
```

Note: the `base_adapter` fixture should already exist in the test file. If not, add:

```python
@pytest.fixture
def base_adapter():
    """Create a concrete adapter for testing base class methods."""
    # Use existing ConcreteAdapter from the test file, or create one
    ...
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_adapter_base.py::TestGenerateRunnersWithMeta -v`
Expected: FAIL (current `_generate_runners` expects `event/filename` format)

**Step 3: Rewrite `_generate_runners()` in `base.py`**

Replace the method at `src/hawk_hooks/adapters/base.py:216-318`. The new version:
- Takes plain filenames (not `event/filename`)
- Parses each hook's metadata via `hook_meta.parse_hook_meta()`
- Groups by events from metadata
- Generates runners as before

```python
def _generate_runners(
    self,
    hook_names: list[str],
    registry_path: Path,
    runners_dir: Path,
) -> dict[str, Path]:
    """Generate bash runners from hook files using hawk-hook metadata.

    Hook names are plain filenames (e.g. "file-guard.py").
    Each hook's metadata declares which events it targets.
    One runner is generated per event, chaining all hooks for that event.

    Returns dict of {event_name: runner_path}.
    """
    from collections import defaultdict
    import shlex
    from ..generator import _get_interpreter_path, _atomic_write_executable
    from ..hook_meta import parse_hook_meta

    # Resolve hooks and group by event
    hooks_by_event: dict[str, list[Path]] = defaultdict(list)
    hooks_dir = registry_path / "hooks"
    for name in hook_names:
        hook_path = hooks_dir / name
        if not hook_path.is_file():
            continue
        meta = parse_hook_meta(hook_path)
        for event in meta.events:
            hooks_by_event[event].append(hook_path)

    runners: dict[str, Path] = {}
    runners_dir.mkdir(parents=True, exist_ok=True)

    for event, scripts in hooks_by_event.items():
        calls: list[str] = []
        for script in scripts:
            safe_path = shlex.quote(str(script))
            suffix = script.suffix

            # Content hooks: cat the file
            if script.name.endswith((".stdout.md", ".stdout.txt")) or suffix in (".md", ".txt"):
                try:
                    cat_path = _get_interpreter_path("cat")
                except FileNotFoundError:
                    cat_path = "cat"
                calls.append(f'[[ -f {safe_path} ]] && {cat_path} {safe_path}')
            elif suffix == ".py":
                calls.append(
                    f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | python3 {safe_path} || exit $?; }}'
                )
            elif suffix == ".sh":
                try:
                    bash_path = _get_interpreter_path("bash")
                except FileNotFoundError:
                    bash_path = "bash"
                calls.append(
                    f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {bash_path} {safe_path} || exit $?; }}'
                )
            elif suffix == ".js":
                try:
                    node_path = _get_interpreter_path("node")
                except FileNotFoundError:
                    node_path = "node"
                calls.append(
                    f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {node_path} {safe_path} || exit $?; }}'
                )
            elif suffix == ".ts":
                try:
                    bun_path = _get_interpreter_path("bun")
                except FileNotFoundError:
                    bun_path = "bun"
                calls.append(
                    f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {bun_path} run {safe_path} || exit $?; }}'
                )
            else:
                calls.append(
                    f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {safe_path} || exit $?; }}'
                )

        hook_calls_str = "\n".join(calls)
        content = f"""#!/usr/bin/env bash
# Auto-generated by hawk v2 - do not edit manually
# Event: {event}
# Regenerate with: hawk sync --force

set -euo pipefail

INPUT=$(cat)

{hook_calls_str}

exit 0
"""
        runner_path = runners_dir / f"{event}.sh"
        _atomic_write_executable(runner_path, content)
        runners[event] = runner_path

    # Clean up stale runners for events that no longer have hooks
    for existing in runners_dir.iterdir():
        if existing.suffix == ".sh" and existing.stem not in hooks_by_event:
            existing.unlink()

    return runners
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_adapter_base.py -v`
Expected: All PASS (both old and new tests)

**Step 5: Commit**

```bash
git add src/hawk_hooks/adapters/base.py tests/test_adapter_base.py
git commit -m "refactor: _generate_runners uses hawk-hook metadata instead of event/filename"
```

---

### Task 4: Update Claude adapter `register_hooks()`

**Files:**
- Modify: `src/hawk_hooks/adapters/claude.py:38-97`
- Test: `tests/test_adapter_claude.py`

**Step 1: Write failing test**

Add to `tests/test_adapter_claude.py`:

```python
class TestRegisterHooksWithMeta:
    """Test Claude register_hooks with plain filenames (hawk-hook metadata)."""

    def test_registers_hook_by_metadata(self, tmp_path):
        adapter = ClaudeAdapter()
        registry = tmp_path / "registry"
        hooks_dir = registry / "hooks"
        hooks_dir.mkdir(parents=True)

        # Create hook with metadata
        hook = hooks_dir / "guard.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")

        target_dir = tmp_path / "claude"
        target_dir.mkdir()

        registered = adapter.register_hooks(["guard.py"], target_dir, registry_path=registry)
        assert "guard.py" in registered

        # Check settings.json has PreToolUse entry
        settings = json.loads((target_dir / "settings.json").read_text())
        hook_entries = settings.get("hooks", [])
        matchers = [h["matcher"] for h in hook_entries]
        assert "PreToolUse" in matchers
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_adapter_claude.py::TestRegisterHooksWithMeta -v`
Expected: FAIL (current code splits on `/` expecting `event/filename`)

**Step 3: Update `register_hooks()` in `claude.py`**

The method needs to:
- Accept plain filenames (no `event/filename`)
- Return plain filenames that were successfully registered (not `event/filename`)

```python
def register_hooks(self, hook_names: list[str], target_dir: Path, registry_path: Path | None = None) -> list[str]:
    """Register hooks via bash runners in Claude's settings.json."""
    from ..events import EVENTS
    from .. import v2_config

    runners_dir = v2_config.get_config_dir() / "runners"

    if not hook_names or registry_path is None:
        self._remove_hawk_hooks(target_dir)
        if runners_dir.exists():
            for f in runners_dir.iterdir():
                if f.suffix == ".sh":
                    f.unlink()
        return []

    # Generate runners (uses hawk-hook metadata internally)
    runners = self._generate_runners(hook_names, registry_path, runners_dir)

    # Load settings.json
    settings_path = target_dir / "settings.json"
    settings = self._load_json(settings_path)

    # Remove existing hawk-managed hook entries
    existing_hooks = settings.get("hooks", [])
    user_hooks = [h for h in existing_hooks if not self._is_hawk_hook(h)]

    # Add new hawk entries for each runner
    hawk_entries = []
    for event_name, runner_path in sorted(runners.items()):
        event_def = EVENTS.get(event_name)
        matcher = event_def.claude_name if event_def else event_name

        hawk_entries.append({
            "matcher": matcher,
            "hooks": [{
                "type": "command",
                "command": str(runner_path),
                _HAWK_HOOK_MARKER: True,
            }],
        })

    settings["hooks"] = user_hooks + hawk_entries
    self._save_json(settings_path, settings)

    # Return hook names that ended up in at least one runner
    from ..hook_meta import parse_hook_meta
    hooks_dir = registry_path / "hooks"
    registered = []
    for name in hook_names:
        hook_path = hooks_dir / name
        if hook_path.is_file():
            meta = parse_hook_meta(hook_path)
            if any(event in runners for event in meta.events):
                registered.append(name)
    return registered
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_adapter_claude.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/hawk_hooks/adapters/claude.py tests/test_adapter_claude.py
git commit -m "refactor: Claude register_hooks uses plain filenames with hawk-hook metadata"
```

---

### Task 5: Update downloader to handle flat hooks

**Files:**
- Modify: `src/hawk_hooks/downloader.py:126-158` (`_scan_typed_dir`) and `352-388` (`_classify_file`)
- Test: `tests/test_downloader.py`

**Step 1: Write failing tests**

Add to `tests/test_downloader.py`:

```python
class TestClassifyFlatHooks:
    """Test classify() with flat hook files (hawk-hook headers)."""

    def test_flat_hook_with_header(self, tmp_path):
        """File directly in hooks/ with hawk-hook header is classified as hook."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook = hooks_dir / "guard.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")

        content = classify(tmp_path)
        hook_items = [i for i in content.items if i.component_type == ComponentType.HOOK]
        assert len(hook_items) == 1
        assert hook_items[0].name == "guard.py"

    def test_legacy_event_dir_still_works(self, tmp_path):
        """Files in hooks/event_name/ dirs still classified as hooks."""
        hooks_dir = tmp_path / "hooks" / "pre_tool_use"
        hooks_dir.mkdir(parents=True)
        hook = hooks_dir / "guard.py"
        hook.write_text("#!/usr/bin/env python3\nimport sys\n")

        content = classify(tmp_path)
        hook_items = [i for i in content.items if i.component_type == ComponentType.HOOK]
        assert len(hook_items) >= 1

    def test_md_with_frontmatter_is_hook(self, tmp_path):
        """Markdown file in hooks/ with hawk-hook frontmatter is classified as hook."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook = hooks_dir / "check.md"
        hook.write_text("---\nhawk-hook:\n  events: [stop]\n---\nContent\n")

        content = classify(tmp_path)
        hook_items = [i for i in content.items if i.component_type == ComponentType.HOOK]
        assert len(hook_items) == 1
        assert hook_items[0].name == "check.md"

    def test_md_without_frontmatter_not_hook(self, tmp_path):
        """Plain markdown in hooks/ without hawk-hook frontmatter is NOT classified."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        readme = hooks_dir / "README.md"
        readme.write_text("# My Hooks\nDocumentation here.\n")

        content = classify(tmp_path)
        hook_items = [i for i in content.items if i.component_type == ComponentType.HOOK]
        # README.md should not be a hook
        assert not any(i.name == "README.md" for i in hook_items)


class TestScanDirectoryHooks:
    """Test scan_directory() hook detection with hawk-hook headers."""

    def test_detects_hawk_hook_header(self, tmp_path):
        """scan_directory finds scripts with hawk-hook headers."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook = hooks_dir / "notify.py"
        hook.write_text("#!/usr/bin/env python3\n# hawk-hook: events=stop\nimport sys\n")

        content = scan_directory(tmp_path)
        hook_items = [i for i in content.items if i.component_type == ComponentType.HOOK]
        assert any(i.name == "notify.py" for i in hook_items)
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_downloader.py::TestClassifyFlatHooks -v`
Expected: FAIL

**Step 3: Update `_scan_typed_dir()` and `_classify_file()`**

In `_scan_typed_dir()`: when scanning `hooks/`, treat flat files as hooks if they have a hawk-hook header or are scripts. Also still recurse into event subdirs for backward compat.

In `_classify_file()`: add hawk-hook header detection for hooks.

Update `_scan_typed_dir()`:

```python
def _scan_typed_dir(
    directory: Path,
    component_type: ComponentType,
    content: ClassifiedContent,
) -> None:
    """Scan a typed subdirectory for components."""
    if not directory.exists() or not directory.is_dir():
        return

    for entry in sorted(directory.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_symlink():
            continue

        if entry.is_dir():
            if component_type == ComponentType.HOOK:
                # Legacy event-dir layout: recurse one level into event dirs
                for sub in sorted(entry.iterdir()):
                    if sub.name.startswith(".") or sub.is_symlink() or not sub.is_file():
                        continue
                    content.items.append(
                        ClassifiedItem(
                            component_type=component_type,
                            name=sub.name,
                            source_path=sub,
                        )
                    )
            else:
                # Directory-style component (e.g., skill with multiple files)
                content.items.append(
                    ClassifiedItem(
                        component_type=component_type,
                        name=entry.name,
                        source_path=entry,
                    )
                )
        elif entry.is_file():
            if component_type == ComponentType.HOOK:
                # For hooks: check if file is a valid hook
                if _is_hook_file(entry):
                    content.items.append(
                        ClassifiedItem(
                            component_type=component_type,
                            name=entry.name,
                            source_path=entry,
                        )
                    )
            else:
                content.items.append(
                    ClassifiedItem(
                        component_type=component_type,
                        name=entry.name,
                        source_path=entry,
                    )
                )
```

Add helper `_is_hook_file()`:

```python
def _is_hook_file(path: Path) -> bool:
    """Check if a file is a valid hook (script, .stdout.*, or has hawk-hook header)."""
    suffix = path.suffix.lower()

    # Scripts are always valid hooks
    if suffix in (".py", ".sh", ".js", ".ts"):
        return True

    # .stdout.* files are always content hooks
    if path.name.endswith((".stdout.md", ".stdout.txt")):
        return True

    # .md/.txt only if they have hawk-hook frontmatter
    if suffix in (".md", ".txt"):
        try:
            from .hook_meta import parse_hook_meta
            meta = parse_hook_meta(path)
            return bool(meta.events)
        except Exception:
            return False

    return False
```

Update `_classify_file()` to also check for hawk-hook headers:

```python
def _classify_file(path: Path, parent_dir_name: str) -> ClassifiedItem | None:
    """Classify a single file based on its extension and parent directory."""
    suffix = path.suffix.lower()
    name = path.name

    # MCP configs
    if parent_dir_name == "mcp" and suffix in (".yaml", ".yml", ".json"):
        return ClassifiedItem(ComponentType.MCP, name, path)

    # Commands
    if parent_dir_name == "commands" and suffix == ".md":
        return ClassifiedItem(ComponentType.COMMAND, name, path)

    # Agents
    if parent_dir_name == "agents" and suffix == ".md":
        return ClassifiedItem(ComponentType.AGENT, name, path)

    # Prompts
    if parent_dir_name == "prompts" and suffix == ".md":
        return ClassifiedItem(ComponentType.PROMPT, name, path)

    # Hooks — scripts in hooks/ dir
    if parent_dir_name == "hooks" and suffix in (".py", ".sh", ".js", ".ts"):
        return ClassifiedItem(ComponentType.HOOK, name, path)

    # Hooks — .stdout.* in hooks/
    if parent_dir_name == "hooks" and name.endswith((".stdout.md", ".stdout.txt")):
        return ClassifiedItem(ComponentType.HOOK, name, path)

    # Hooks — .md/.txt in hooks/ with hawk-hook frontmatter
    if parent_dir_name == "hooks" and suffix in (".md", ".txt"):
        if _is_hook_file(path):
            return ClassifiedItem(ComponentType.HOOK, name, path)
        return None  # Skip plain markdown in hooks/

    # Check for hawk-hook header anywhere (not just in hooks/ dir)
    if suffix in (".py", ".sh", ".js", ".ts", ".md", ".txt"):
        try:
            from .hook_meta import parse_hook_meta
            meta = parse_hook_meta(path)
            if meta.events:
                return ClassifiedItem(ComponentType.HOOK, name, path)
        except Exception:
            pass

    # Markdown with frontmatter → try to classify as command
    if suffix == ".md":
        try:
            head = path.read_text(errors="replace")[:500]
            if head.startswith("---"):
                if "name:" in head and "description:" in head:
                    return ClassifiedItem(ComponentType.COMMAND, name, path)
        except OSError:
            pass

    return None
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_downloader.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/hawk_hooks/downloader.py tests/test_downloader.py
git commit -m "feat: downloader handles flat hook files with hawk-hook metadata"
```

---

### Task 6: Update wizard enable logic

**Files:**
- Modify: `src/hawk_hooks/v2_interactive/wizard.py:174-184`

The wizard's `_offer_builtins_install()` appends `component_type/name` strings from `add_items_to_registry()`. For hooks, this produces `hook/file-guard.py`. The config field is `hooks` and the value appended is the name part after the `/`. Since hook names are now plain filenames, this already works correctly — `item_str.split("/", 1)` gives `("hook", "file-guard.py")` and appends `"file-guard.py"` to the `hooks` list.

**No code change needed.** The wizard logic is already correct for flat filenames.

**Step 1: Verify with a test**

Run: `python3 -m pytest tests/ --ignore=tests/test_cli.py -q`
Expected: All pass

**Step 2: Commit (skip — no changes)**

---

### Task 7: Run full test suite and fix any breakage

**Step 1: Run all tests**

```bash
python3 -m pytest tests/ --ignore=tests/test_cli.py -q
```

**Step 2: Fix any failures**

Existing tests in `test_adapter_base.py` that use `event/filename` format need updating to use plain filenames with hawk-hook headers. Look for test methods that create hooks as `event_dir/filename` and update them to create flat files with `# hawk-hook: events=event_name` headers.

Similarly, `test_adapter_claude.py` tests that pass `["pre_tool_use/guard.py"]` style names need updating.

**Step 3: Run full suite again**

```bash
python3 -m pytest tests/ --ignore=tests/test_cli.py -q
```
Expected: All pass

**Step 4: Commit**

```bash
git add -A
git commit -m "test: update existing tests for flat hook format"
```

---

### Task 8: Final verification and cleanup

**Step 1: Verify builtins are scannable**

```bash
python3 -c "
from hawk_hooks.downloader import classify
from pathlib import Path
content = classify(Path('builtins'))
hooks = [i for i in content.items if str(i.component_type) == 'hook']
print(f'Found {len(hooks)} hooks:')
for h in hooks:
    print(f'  {h.name}')
"
```

Expected: Lists all 15 hook files.

**Step 2: Verify hook_meta parses all builtins**

```bash
python3 -c "
from hawk_hooks.hook_meta import parse_hook_meta
from pathlib import Path
for f in sorted(Path('builtins/hooks').iterdir()):
    if f.is_file() and not f.name.startswith('.'):
        meta = parse_hook_meta(f)
        print(f'{f.name}: events={meta.events} desc={meta.description[:40]}')
"
```

Expected: All hooks show events and descriptions.

**Step 3: Run full suite one more time**

```bash
python3 -m pytest tests/ --ignore=tests/test_cli.py -q
```

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: hawk hook format - flat files with hawk-hook metadata headers"
```
