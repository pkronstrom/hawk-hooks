# Skill Bundles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Hawk skill declare and ship required companion agents, hooks, prompts, and MCP servers so enabling the skill activates the complete working bundle instead of silently syncing an incomplete setup.

**Architecture:** Keep `skill` as the canonical component type and add dependency semantics around it. A new `skill_meta` module parses `requires:` from `SKILL.md`; resolver/sync expands active skills into required companion components and reports missing requirements; scanner/import supports skill directories that contain typed companion subdirectories such as `agents/` and `hooks/`.

**Tech Stack:** Python 3.10+, PyYAML frontmatter parsing, existing `ResolvedSet`/registry/sync pipeline, pytest.

**Reference:** Dodo `hawk-hooks_8f9eb2` item `0478e5c2`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `src/hawk_hooks/skill_meta.py` | Parse skill frontmatter and normalize `requires:` into component-field lists. |
| `src/hawk_hooks/resolver.py` | Expand resolved active skills with companion requirements. |
| `src/hawk_hooks/sync.py` | Use dependency-expanded resolved sets for cache identity, dry-run, and adapter sync; surface dependency warnings. |
| `src/hawk_hooks/downloader.py` | Scan typed companion directories inside a skill directory without treating arbitrary skill resources as components. |
| `tests/test_skill_meta.py` | Unit tests for `requires:` parsing and malformed metadata handling. |
| `tests/test_resolver.py` | Unit tests for dependency expansion and missing-component diagnostics. |
| `tests/test_sync.py` | Sync/cache tests proving required companions are linked and warnings surface. |
| `tests/test_downloader.py` | Scanner tests for skill-bundle directory layout. |
| `builtins/skills/hawk-new/skill-guide.md` | Authoring docs for `requires:` and bundle layout. |
| `README.md` | User-facing summary of skill bundles. |

## Accepted Skill Metadata

Use this YAML frontmatter form in `SKILL.md`:

```yaml
---
name: continuous-learning-v2
description: Observes sessions and turns patterns into instincts.
requires:
  agents:
    - observer.md
  hooks:
    - observe.sh
  prompts:
    - instinct-status.md
  mcp:
    - dodo.json
---
```

Singular keys are accepted as aliases (`agent`, `hook`, `prompt`). `commands` is accepted as a legacy alias for `prompts`. `skills` is not supported inside `requires:` in this plan; recursive skill dependency graphs add ordering and cycle handling that this feature does not need yet.

## Accepted Bundle Layout

For local scans and archives, a skill bundle may be a single directory:

```text
continuous-learning-v2/
  SKILL.md
  agents/
    observer.md
  hooks/
    observe.sh
  prompts/
    instinct-status.md
  mcp/
    dodo.json
  scripts/
    internal-helper.py
```

The scanner imports the skill plus the typed companion directories. It does not import `scripts/` as hooks, because those are skill-local resources unless explicitly placed in `hooks/`.

---

## Task 1: Add skill metadata parser

**Files:**
- Create: `src/hawk_hooks/skill_meta.py`
- Create: `tests/test_skill_meta.py`

- [ ] **Step 1: Write failing parser tests**

Create `tests/test_skill_meta.py`:

```python
from pathlib import Path

from hawk_hooks.skill_meta import SkillRequires, parse_skill_meta


def test_parse_skill_requires_plural_component_keys(tmp_path: Path):
    skill = tmp_path / "bundle" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(
        "---\n"
        "name: bundle\n"
        "description: Bundle skill\n"
        "requires:\n"
        "  agents:\n"
        "    - observer.md\n"
        "  hooks:\n"
        "    - observe.sh\n"
        "  prompts:\n"
        "    - instinct-status.md\n"
        "  mcp:\n"
        "    - dodo.json\n"
        "---\n\n"
        "# Bundle\n"
    )

    meta = parse_skill_meta(skill.parent)

    assert meta.requires == SkillRequires(
        agents=["observer.md"],
        hooks=["observe.sh"],
        prompts=["instinct-status.md"],
        mcp=["dodo.json"],
    )


def test_parse_skill_requires_accepts_aliases_and_dedupes(tmp_path: Path):
    skill = tmp_path / "bundle" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(
        "---\n"
        "name: bundle\n"
        "description: Bundle skill\n"
        "requires:\n"
        "  agent: observer.md\n"
        "  hook: [observe.sh, observe.sh]\n"
        "  commands:\n"
        "    - instinct-status.md\n"
        "---\n\n"
        "# Bundle\n"
    )

    meta = parse_skill_meta(skill.parent)

    assert meta.requires.agents == ["observer.md"]
    assert meta.requires.hooks == ["observe.sh"]
    assert meta.requires.prompts == ["instinct-status.md"]


def test_parse_skill_requires_ignores_malformed_values(tmp_path: Path):
    skill = tmp_path / "bundle" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(
        "---\n"
        "name: bundle\n"
        "description: Bundle skill\n"
        "requires:\n"
        "  agents:\n"
        "    - observer.md\n"
        "    - 12\n"
        "  hooks: nope\n"
        "  skills:\n"
        "    - other-skill\n"
        "---\n\n"
        "# Bundle\n"
    )

    meta = parse_skill_meta(skill.parent)

    assert meta.requires.agents == ["observer.md"]
    assert meta.requires.hooks == []
    assert meta.warnings == [
        "requires.agents ignored non-string entry 12",
        "requires.hooks expected a list or string",
        "requires.skills is unsupported",
    ]
```

- [ ] **Step 2: Run parser tests to verify they fail**

Run:

```bash
uv run pytest tests/test_skill_meta.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hawk_hooks.skill_meta'`.

- [ ] **Step 3: Implement `skill_meta.py`**

Create `src/hawk_hooks/skill_meta.py`:

```python
"""Parse Hawk skill metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SkillRequires:
    agents: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    mcp: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SkillMeta:
    requires: SkillRequires = field(default_factory=SkillRequires)
    warnings: list[str] = field(default_factory=list)


_KEY_ALIASES = {
    "agent": "agents",
    "agents": "agents",
    "hook": "hooks",
    "hooks": "hooks",
    "prompt": "prompts",
    "prompts": "prompts",
    "command": "prompts",
    "commands": "prompts",
    "mcp": "mcp",
}


def parse_skill_meta(skill_path: Path) -> SkillMeta:
    """Parse metadata from a skill directory or SKILL.md file."""
    skill_file = skill_path / "SKILL.md" if skill_path.is_dir() else skill_path
    try:
        text = skill_file.read_text(errors="replace")
    except OSError:
        return SkillMeta()

    frontmatter = _extract_frontmatter(text)
    if frontmatter is None:
        return SkillMeta()

    try:
        data = yaml.safe_load(frontmatter)
    except yaml.YAMLError as exc:
        return SkillMeta(warnings=[f"invalid skill frontmatter: {exc}"])

    if not isinstance(data, dict):
        return SkillMeta()

    requires = data.get("requires", {})
    if requires in (None, ""):
        return SkillMeta()
    if not isinstance(requires, dict):
        return SkillMeta(warnings=["requires expected a mapping"])

    buckets: dict[str, list[str]] = {"agents": [], "hooks": [], "prompts": [], "mcp": []}
    warnings: list[str] = []

    for raw_key, raw_value in requires.items():
        key = str(raw_key)
        target = _KEY_ALIASES.get(key)
        if target is None:
            warnings.append(f"requires.{key} is unsupported")
            continue

        values = _as_string_list(raw_value)
        if values is None:
            warnings.append(f"requires.{target} expected a list or string")
            continue

        for value in values:
            if value not in buckets[target]:
                buckets[target].append(value)
        for entry in _non_string_entries(raw_value):
            warnings.append(f"requires.{target} ignored non-string entry {entry!r}")

    return SkillMeta(
        requires=SkillRequires(
            agents=buckets["agents"],
            hooks=buckets["hooks"],
            prompts=buckets["prompts"],
            mcp=buckets["mcp"],
        ),
        warnings=warnings,
    )


def _extract_frontmatter(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    return text[3:end].strip()


def _as_string_list(value: Any) -> list[str] | None:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, str)]


def _non_string_entries(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [item for item in value if not isinstance(item, str)]
```

- [ ] **Step 4: Run parser tests to verify they pass**

Run:

```bash
uv run pytest tests/test_skill_meta.py -q
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/hawk_hooks/skill_meta.py tests/test_skill_meta.py
git commit -m "feat(skills): parse skill bundle requirements"
```

---

## Task 2: Expand resolved skills into companion dependencies

**Files:**
- Modify: `src/hawk_hooks/resolver.py`
- Modify: `tests/test_resolver.py`

- [ ] **Step 1: Write failing resolver tests**

Append to `tests/test_resolver.py`:

```python
from pathlib import Path

from hawk_hooks.resolver import expand_skill_dependencies
from hawk_hooks.types import ResolvedSet


def test_expand_skill_dependencies_adds_existing_required_components(tmp_path: Path):
    registry = tmp_path / "registry"
    skill = registry / "skills" / "bundle"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\n"
        "name: bundle\n"
        "description: Bundle\n"
        "requires:\n"
        "  agents: [observer.md]\n"
        "  hooks: [observe.sh]\n"
        "  prompts: [instinct-status.md]\n"
        "  mcp: [dodo.json]\n"
        "---\n\n"
        "# Bundle\n"
    )
    (registry / "agents").mkdir()
    (registry / "agents" / "observer.md").write_text("# Observer\n")
    (registry / "hooks").mkdir()
    (registry / "hooks" / "observe.sh").write_text("#!/bin/sh\n")
    (registry / "prompts").mkdir()
    (registry / "prompts" / "instinct-status.md").write_text("# Status\n")
    (registry / "mcp").mkdir()
    (registry / "mcp" / "dodo.json").write_text('{"command":"dodo"}\n')

    expanded, warnings = expand_skill_dependencies(
        ResolvedSet(skills=["bundle"]),
        registry,
    )

    assert expanded.skills == ["bundle"]
    assert expanded.agents == ["observer.md"]
    assert expanded.hooks == ["observe.sh"]
    assert expanded.prompts == ["instinct-status.md"]
    assert expanded.mcp == ["dodo.json"]
    assert warnings == []


def test_expand_skill_dependencies_reports_missing_components(tmp_path: Path):
    registry = tmp_path / "registry"
    skill = registry / "skills" / "bundle"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\n"
        "name: bundle\n"
        "description: Bundle\n"
        "requires:\n"
        "  agents: [observer.md]\n"
        "  hooks: [observe.sh]\n"
        "---\n\n"
        "# Bundle\n"
    )

    expanded, warnings = expand_skill_dependencies(
        ResolvedSet(skills=["bundle"]),
        registry,
    )

    assert expanded.agents == []
    assert expanded.hooks == []
    assert warnings == [
        "skill bundle requires missing agent observer.md",
        "skill bundle requires missing hook observe.sh",
    ]
```

- [ ] **Step 2: Run resolver tests to verify they fail**

Run:

```bash
uv run pytest tests/test_resolver.py -q
```

Expected: FAIL with `ImportError` for `expand_skill_dependencies`.

- [ ] **Step 3: Implement dependency expansion**

Modify `src/hawk_hooks/resolver.py`:

```python
from pathlib import Path

from .registry import _validate_name
from .skill_meta import parse_skill_meta
```

Add this function near the bottom of the file:

```python
def expand_skill_dependencies(
    resolved: ResolvedSet,
    registry_path: Path,
) -> tuple[ResolvedSet, list[str]]:
    """Add companion components required by active skills.

    Missing requirements are returned as warnings and are not added.
    """
    expanded = ResolvedSet(
        skills=list(resolved.skills),
        hooks=list(resolved.hooks),
        commands=list(resolved.commands),
        agents=list(resolved.agents),
        mcp=list(resolved.mcp),
        prompts=list(resolved.prompts),
    )
    warnings: list[str] = []

    field_dirs = {
        "agents": "agents",
        "hooks": "hooks",
        "prompts": "prompts",
        "mcp": "mcp",
    }
    singular = {
        "agents": "agent",
        "hooks": "hook",
        "prompts": "prompt",
        "mcp": "mcp",
    }

    for skill_name in resolved.skills:
        try:
            _validate_name(skill_name)
        except ValueError as exc:
            warnings.append(f"skill {skill_name!r} has invalid name: {exc}")
            continue

        skill_path = registry_path / "skills" / skill_name
        meta = parse_skill_meta(skill_path)
        warnings.extend(f"skill {skill_name}: {warning}" for warning in meta.warnings)

        for field_name, dir_name in field_dirs.items():
            current = getattr(expanded, field_name)
            for requirement in getattr(meta.requires, field_name):
                try:
                    _validate_name(requirement)
                except ValueError as exc:
                    warnings.append(
                        f"skill {skill_name} requires invalid {singular[field_name]} "
                        f"{requirement!r}: {exc}"
                    )
                    continue
                if not (registry_path / dir_name / requirement).exists():
                    warnings.append(
                        f"skill {skill_name} requires missing "
                        f"{singular[field_name]} {requirement}"
                    )
                    continue
                if requirement not in current:
                    current.append(requirement)

    return expanded, warnings
```

- [ ] **Step 4: Run resolver tests to verify they pass**

Run:

```bash
uv run pytest tests/test_resolver.py -q
```

Expected: all resolver tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/hawk_hooks/resolver.py tests/test_resolver.py
git commit -m "feat(skills): expand skill bundle dependencies"
```

---

## Task 3: Use expanded dependencies during sync and cache checks

**Files:**
- Modify: `src/hawk_hooks/sync.py`
- Modify: `tests/test_sync.py`

- [ ] **Step 1: Write failing sync tests**

Append to `tests/test_sync.py`:

```python
from pathlib import Path

from hawk_hooks import config
from hawk_hooks.sync import sync_directory
from hawk_hooks.types import Tool


def test_sync_directory_links_skill_required_agent(tmp_path: Path, monkeypatch):
    registry = tmp_path / "registry"
    skill = registry / "skills" / "bundle"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\n"
        "name: bundle\n"
        "description: Bundle\n"
        "requires:\n"
        "  agents: [observer.md]\n"
        "---\n\n"
        "# Bundle\n"
    )
    (registry / "agents").mkdir()
    (registry / "agents" / "observer.md").write_text("---\nname: observer\n---\n\nObserve.\n")
    for dirname in ("hooks", "prompts", "mcp"):
        (registry / dirname).mkdir(exist_ok=True)

    project = tmp_path / "project"
    project.mkdir()
    config.save_dir_config(project, {"skills": {"enabled": ["bundle"]}})

    cfg = config.DEFAULT_GLOBAL_CONFIG.copy()
    cfg["registry_path"] = str(registry)
    cfg["tools"] = {"claude": {"enabled": True}}
    monkeypatch.setattr(config, "load_global_config", lambda: cfg)
    monkeypatch.setattr(config, "get_enabled_tools", lambda _cfg=None: [Tool.CLAUDE])

    results = sync_directory(project, tools=[Tool.CLAUDE], force=True)

    assert not results[0].errors
    assert (project / ".claude" / "skills" / "bundle").is_symlink()
    assert (project / ".claude" / "agents" / "observer.md").is_symlink()


def test_sync_directory_warns_about_missing_skill_requirement(tmp_path: Path, monkeypatch):
    registry = tmp_path / "registry"
    skill = registry / "skills" / "bundle"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\n"
        "name: bundle\n"
        "description: Bundle\n"
        "requires:\n"
        "  agents: [observer.md]\n"
        "---\n\n"
        "# Bundle\n"
    )
    for dirname in ("agents", "hooks", "prompts", "mcp"):
        (registry / dirname).mkdir(exist_ok=True)

    project = tmp_path / "project"
    project.mkdir()
    config.save_dir_config(project, {"skills": {"enabled": ["bundle"]}})

    cfg = config.DEFAULT_GLOBAL_CONFIG.copy()
    cfg["registry_path"] = str(registry)
    cfg["tools"] = {"claude": {"enabled": True}}
    monkeypatch.setattr(config, "load_global_config", lambda: cfg)
    monkeypatch.setattr(config, "get_enabled_tools", lambda _cfg=None: [Tool.CLAUDE])

    results = sync_directory(project, tools=[Tool.CLAUDE], force=True)

    assert any(
        "skill bundle requires missing agent observer.md" in item
        for item in results[0].skipped
    )
```

- [ ] **Step 2: Run sync tests to verify they fail**

Run:

```bash
uv run pytest tests/test_sync.py -q
```

Expected: first new test fails because `.claude/agents/observer.md` is not linked; second fails because no warning is surfaced.

- [ ] **Step 3: Add a sync helper and wire it into sync paths**

Modify imports in `src/hawk_hooks/sync.py`:

```python
from .resolver import expand_skill_dependencies, resolve
```

Add helper near `_cache_identity`:

```python
def _expand_for_sync(
    resolved: ResolvedSet,
    registry_path: Path,
) -> tuple[ResolvedSet, list[str]]:
    return expand_skill_dependencies(resolved, registry_path)
```

In `count_unsynced_targets`, call `_expand_for_sync` before computing `hash_key` for both global and project scopes:

```python
resolved_global, _ = _expand_for_sync(resolve(cfg), registry.path)
global_hash = resolved_global.hash_key(registry_path=registry.path)
```

For project scope:

```python
resolved_project = (
    resolve(cfg, dir_chain=dir_chain, tool=tool)
    if dir_chain
    else resolve(cfg, tool=tool)
)
resolved_project, _ = _expand_for_sync(resolved_project, registry.path)
project_hash = resolved_project.hash_key(registry_path=registry.path)
```

In `sync_directory`, after resolving and before dry-run/cache:

```python
resolved, dependency_warnings = _expand_for_sync(resolved, registry.path)
```

After `adapter.sync(...)`:

```python
result.skipped.extend(f"dependencies: {warning}" for warning in dependency_warnings)
```

In `sync_global`, mirror the same expansion and warning append:

```python
resolved = resolve(cfg)
resolved, dependency_warnings = _expand_for_sync(resolved, registry.path)
```

After `adapter.sync(...)`:

```python
result.skipped.extend(f"dependencies: {warning}" for warning in dependency_warnings)
```

For dry-runs, use expanded `resolved` in `_compute_would_link`.

- [ ] **Step 4: Run sync tests to verify they pass**

Run:

```bash
uv run pytest tests/test_sync.py -q
```

Expected: all sync tests pass.

- [ ] **Step 5: Run focused adapter tests**

Run:

```bash
uv run pytest tests/test_adapter_claude.py tests/test_adapter_codex.py -q
```

Expected: all selected adapter tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/hawk_hooks/sync.py tests/test_sync.py
git commit -m "feat(sync): activate skill bundle dependencies"
```

---

## Task 4: Scan bundled companion directories inside skill directories

**Files:**
- Modify: `src/hawk_hooks/downloader.py`
- Modify: `tests/test_downloader.py`

- [ ] **Step 1: Write failing scanner tests**

Append to `tests/test_downloader.py`:

```python
def test_scan_directory_imports_skill_bundle_companions(tmp_path):
    bundle = tmp_path / "continuous-learning-v2"
    bundle.mkdir()
    (bundle / "SKILL.md").write_text(
        "---\n"
        "name: continuous-learning-v2\n"
        "description: Bundle\n"
        "requires:\n"
        "  agents: [observer.md]\n"
        "  hooks: [observe.sh]\n"
        "---\n\n"
        "# Bundle\n"
    )
    (bundle / "agents").mkdir()
    (bundle / "agents" / "observer.md").write_text("# Observer\n")
    (bundle / "hooks").mkdir()
    (bundle / "hooks" / "observe.sh").write_text("#!/usr/bin/env bash\n")
    (bundle / "scripts").mkdir()
    (bundle / "scripts" / "helper.py").write_text("print('skill resource')\n")

    content = scan_directory(tmp_path)

    found = {(item.component_type, item.name) for item in content.items}
    assert (ComponentType.SKILL, "continuous-learning-v2") in found
    assert (ComponentType.AGENT, "observer.md") in found
    assert (ComponentType.HOOK, "observe.sh") in found
    assert (ComponentType.HOOK, "helper.py") not in found


def test_scan_directory_tags_skill_bundle_companions_with_package(tmp_path):
    (tmp_path / "hawk-package.yaml").write_text(
        "name: learning-pack\n"
        "description: Learning bundle\n"
        'version: "1.0.0"\n'
    )
    bundle = tmp_path / "continuous-learning-v2"
    bundle.mkdir()
    (bundle / "SKILL.md").write_text("---\nname: continuous-learning-v2\ndescription: Bundle\n---\n")
    (bundle / "agents").mkdir()
    (bundle / "agents" / "observer.md").write_text("# Observer\n")

    content = scan_directory(tmp_path)

    assert {
        (item.component_type, item.name, item.package)
        for item in content.items
    } >= {
        (ComponentType.SKILL, "continuous-learning-v2", "learning-pack"),
        (ComponentType.AGENT, "observer.md", "learning-pack"),
    }
```

- [ ] **Step 2: Run downloader tests to verify they fail**

Run:

```bash
uv run pytest tests/test_downloader.py -q
```

Expected: first new test fails because `_walk` returns immediately after detecting `SKILL.md`.

- [ ] **Step 3: Implement companion scanning**

Modify `_walk` in `src/hawk_hooks/downloader.py`. Replace the current skill-directory block:

```python
        if entry_names & _SKILL_MARKERS:
            if path not in seen_paths:
                seen_paths.add(path)
                content.items.append(ClassifiedItem(
                    component_type=ComponentType.SKILL,
                    name=path.name,
                    source_path=path,
                    package=pkg_name,
                ))
            return  # Don't recurse into skill dirs
```

with:

```python
        if entry_names & _SKILL_MARKERS:
            if path not in seen_paths:
                seen_paths.add(path)
                content.items.append(ClassifiedItem(
                    component_type=ComponentType.SKILL,
                    name=path.name,
                    source_path=path,
                    package=pkg_name,
                ))
            _scan_skill_bundle_companions(path, content, pkg_name, seen_paths)
            return  # Do not recurse into arbitrary skill resources
```

Add helper functions after `scan_directory`:

```python
def _scan_skill_bundle_companions(
    skill_dir: Path,
    content: ClassifiedContent,
    package_name: str,
    seen_paths: set[Path],
) -> None:
    """Scan typed companion directories inside a skill directory."""
    typed = [
        ("agents", ComponentType.AGENT),
        ("hooks", ComponentType.HOOK),
        ("commands", ComponentType.PROMPT),
        ("prompts", ComponentType.PROMPT),
    ]
    for dir_name, component_type in typed:
        _scan_skill_bundle_typed_dir(
            skill_dir / dir_name,
            component_type,
            content,
            package_name,
            seen_paths,
        )
    _scan_skill_bundle_mcp_dir(skill_dir / "mcp", content, package_name, seen_paths)


def _scan_skill_bundle_typed_dir(
    directory: Path,
    component_type: ComponentType,
    content: ClassifiedContent,
    package_name: str,
    seen_paths: set[Path],
) -> None:
    if not directory.is_dir():
        return
    for entry in sorted(directory.iterdir()):
        if entry.name.startswith(".") or entry.is_symlink():
            continue
        if entry.is_file() and entry.name in _NON_COMPONENT_FILES:
            continue
        if component_type == ComponentType.HOOK and entry.is_file() and not _is_hook_file(entry):
            continue
        if entry.is_file() or entry.is_dir():
            if entry in seen_paths:
                continue
            seen_paths.add(entry)
            content.items.append(ClassifiedItem(
                component_type=component_type,
                name=entry.name,
                source_path=entry,
                package=package_name,
            ))


def _scan_skill_bundle_mcp_dir(
    directory: Path,
    content: ClassifiedContent,
    package_name: str,
    seen_paths: set[Path],
) -> None:
    if not directory.is_dir():
        return
    for entry in sorted(directory.iterdir()):
        if entry.is_symlink() or not entry.is_file() or entry.suffix not in (".yaml", ".yml", ".json"):
            continue
        exploded = _explode_mcp_file(entry)
        if exploded:
            for item in exploded:
                if item.source_path in seen_paths:
                    continue
                seen_paths.add(item.source_path)
                item.package = package_name
                content.items.append(item)
            continue
        if entry in seen_paths:
            continue
        seen_paths.add(entry)
        content.items.append(ClassifiedItem(
            component_type=ComponentType.MCP,
            name=entry.name,
            source_path=entry,
            package=package_name,
        ))
```

- [ ] **Step 4: Run downloader tests to verify they pass**

Run:

```bash
uv run pytest tests/test_downloader.py -q
```

Expected: all downloader tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/hawk_hooks/downloader.py tests/test_downloader.py
git commit -m "feat(scan): import skill bundle companion components"
```

---

## Task 5: Document authoring and UX behavior

**Files:**
- Modify: `builtins/skills/hawk-new/skill-guide.md`
- Modify: `README.md`
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: Update `hawk-new` skill guide**

Add this section to `builtins/skills/hawk-new/skill-guide.md` after the existing skill frontmatter example:

```markdown
## Skill Bundles

A skill can declare companion Hawk components that must be active for the skill to work:

```yaml
---
name: continuous-learning-v2
description: Observes sessions and turns patterns into instincts.
requires:
  agents:
    - observer.md
  hooks:
    - observe.sh
  prompts:
    - instinct-status.md
  mcp:
    - dodo.json
---
```

When the skill is enabled, `hawk sync` also activates the required agents, hooks, prompts, and MCP servers if they exist in the registry. If a required component is missing, sync reports a dependency warning.

For archives and local scans, companion components may live inside the skill directory:

```text
my-skill/
  SKILL.md
  agents/
    observer.md
  hooks/
    observe.sh
  prompts/
    status.md
  mcp/
    dodo.json
```

Only typed companion directories are imported. Files under `scripts/`, `references/`, or other skill resource directories stay inside the skill.
```
```

- [ ] **Step 2: Update README component model**

In `README.md`, add this paragraph near the component type overview:

```markdown
Skills can also be bundles. A skill's `SKILL.md` may declare `requires:` for companion agents, hooks, prompts, and MCP servers. Enabling the skill activates those companions during sync, and local scans can import typed companion directories nested inside the skill.
```

- [ ] **Step 3: Update changelog**

Add under the unreleased/top section in `docs/CHANGELOG.md`:

```markdown
- Added skill bundle support: `SKILL.md` may declare `requires:` for companion agents, hooks, prompts, and MCP servers, and local scans can import typed companion directories nested inside a skill directory.
```

- [ ] **Step 4: Commit**

```bash
git add builtins/skills/hawk-new/skill-guide.md README.md docs/CHANGELOG.md
git commit -m "docs: describe skill bundle authoring"
```

---

## Task 6: Full verification

**Files:** none modified.

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest tests/test_skill_meta.py tests/test_resolver.py tests/test_sync.py tests/test_downloader.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Manual scan smoke test**

Create a temporary bundle outside the repo:

```bash
tmpdir="$(mktemp -d)"
mkdir -p "$tmpdir/my-bundle/agents" "$tmpdir/my-bundle/hooks"
cat > "$tmpdir/my-bundle/SKILL.md" <<'EOF'
---
name: my-bundle
description: Test bundle
requires:
  agents: [observer.md]
  hooks: [observe.sh]
---

# My Bundle
EOF
cat > "$tmpdir/my-bundle/agents/observer.md" <<'EOF'
---
name: observer
description: Observer
---

Observe.
EOF
cat > "$tmpdir/my-bundle/hooks/observe.sh" <<'EOF'
#!/usr/bin/env bash
# hawk-hook: events=stop description="Observe session"
exit 0
EOF
hawk scan "$tmpdir" --select my-bundle,observer.md,observe.sh --replace
hawk list skill | grep my-bundle
hawk list agent | grep observer.md
hawk list hook | grep observe.sh
```

Expected: all three `grep` commands print the imported component name.

- [ ] **Step 4: Commit any verification fixes**

If verification required fixes:

```bash
git add <fixed files>
git commit -m "fix(skills): stabilize skill bundle support"
```

If no fixes were needed, do not create an empty commit.

---

## Self-Review

- Spec coverage: the plan covers dependency metadata, missing-dependency warnings, companion activation, scan/import of nested companion components, and authoring docs.
- Placeholder scan: no placeholders or deferred implementation notes remain.
- Scope check: this is one coherent subsystem around skill bundle dependency semantics; Codex prompt-to-skill conversion is intentionally excluded and should be planned separately.
