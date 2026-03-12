"""Download and install operations shared by CLI and TUI."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Callable

from . import config
from .downloader import ClassifiedContent, add_items_to_registry, check_clashes, classify, get_head_commit, scan_directory, shallow_clone
from .registry import Registry


LogFn = Callable[[str], None]

# SelectFn: (items, registry, *, package_name, packages) -> selected_items or (selected_items, action)
SelectFn = Callable[..., "list | tuple[list, str | None]"]


def _interactive_select_items(items, registry=None, package_name: str = "",
                              packages: list | None = None,
                              collapsed: bool = False, select_all: bool = False):
    """Interactive item picker backed by run_picker."""
    from .interactive.toggle import (
        run_picker,
        ACTION_SAVE_ENABLE,
    )
    from .interactive.handlers.packages import (
        _ORDERED_COMPONENT_FIELDS,
    )

    if not items:
        return [], "cancel"

    # Build package_tree: {pkg: {field: [names]}}
    package_tree: dict[str, dict[str, list[str]]] = {}
    for item in items:
        pkg = getattr(item, "package", "") or package_name or "Components"
        field = item.component_type.registry_dir
        package_tree.setdefault(pkg, {}).setdefault(field, []).append(item.name)

    # Dedupe names within each field bucket (preserve order)
    for pkg_fields in package_tree.values():
        for field in pkg_fields:
            seen: set[str] = set()
            deduped: list[str] = []
            for name in pkg_fields[field]:
                if name not in seen:
                    seen.add(name)
                    deduped.append(name)
            pkg_fields[field] = deduped

    package_order = sorted(package_tree.keys())

    field_labels = {f: label for f, label, _ in _ORDERED_COMPONENT_FIELDS}

    # Pre-select all items (clashes are handled via rename after save)
    enabled: set[tuple[str, str]] = {
        (item.component_type.registry_dir, item.name)
        for item in items
    }

    # Detect items that already exist in registry (for "(exists)" hints)
    existing: set[tuple[str, str]] | None = None
    if registry:
        existing = {
            (item.component_type.registry_dir, item.name)
            for item in items
            if registry.has(item.component_type, item.name)
        }
        if not existing:
            existing = None

    scopes = [{"key": "select", "label": "Select components", "enabled": enabled}]

    final_scopes, changed, chosen_action = run_picker(
        package_name or "Components",
        package_tree,
        package_order,
        field_labels,
        scopes=scopes,
        action_label="Save",
        secondary_action_label="Save & Enable",
        existing_items=existing,
    )

    if not changed:
        return [], "cancel"

    selected = final_scopes[0]["enabled"]
    selected_items = [
        item for item in items
        if (item.component_type.registry_dir, item.name) in selected
    ]

    if chosen_action == ACTION_SAVE_ENABLE:
        return selected_items, "save_enable"
    return selected_items, "save"


def get_interactive_select_fn() -> SelectFn:
    """Return the interactive item selector.

    Provides a clean import path so TUI callers don't reach into cli internals.
    """
    return _interactive_select_items


@dataclass
class DownloadResult:
    """Summary of a download/install operation."""

    success: bool
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    clashes: list[str] = field(default_factory=list)
    error: str | None = None
    package_name: str | None = None
    enable: bool = False


def _noop(_msg: str) -> None:
    return


def _clash_prefix(name: str | None, content, url: str) -> str:
    """Derive a short prefix for renaming clashing items."""
    pkg_name = (
        name
        or (content.package_meta.name if content.package_meta else None)
        or config.package_name_from_url(url)
    )
    if not pkg_name:
        return ""
    # Use last segment: "obra/superpowers" -> "superpowers"
    return pkg_name.split("/")[-1] if "/" in pkg_name else pkg_name


def _prefixed_name(prefix: str, original: str) -> str:
    """Add a package prefix to a filename: 'code-reviewer.md' -> 'superpowers-code-reviewer.md'."""
    return f"{prefix}-{original}"


def _build_pkg_items(items, registry, package_name: str = "", added_keys: set[str] | None = None):
    """Build package items list from selected items and current registry contents.

    Includes existing entries that clash and were not replaced, so package
    ownership can include both newly-added and pre-existing components.
    """
    added_keys = added_keys or set()

    owner_map: dict[tuple[str, str], str] = {}
    packages = config.load_packages()
    for pkg_name, pkg_data in packages.items():
        pkg_items = pkg_data.get("items", []) if isinstance(pkg_data, dict) else []
        if not isinstance(pkg_items, list):
            continue
        for it in pkg_items:
            if not isinstance(it, dict):
                continue
            t = it.get("type")
            n = it.get("name")
            if isinstance(t, str) and isinstance(n, str):
                owner_map[(t, n)] = pkg_name

    pkg_items = []
    for item in items:
        item_path = registry.get_path(item.component_type, item.name)
        if not item_path:
            continue

        item_key_str = f"{item.component_type}/{item.name}"
        if item_key_str not in added_keys:
            key = (item.component_type.value, item.name)
            owner = owner_map.get((item.component_type.value, item.name))
            if owner and owner != package_name:
                continue

            # For unowned clashes not added this run, only claim when scanned
            # source content matches current registry content.
            if not owner and item_key_str not in added_keys:
                source_path = item.source_path
                if source_path is None or not source_path.exists():
                    continue
                source_hash = config.hash_registry_item(source_path)
                registry_hash = config.hash_registry_item(item_path)
                if source_hash != registry_hash:
                    continue

        item_hash = config.hash_registry_item(item_path)
        pkg_items.append(
            {
                "type": item.component_type.value,
                "name": item.name,
                "hash": item_hash,
            }
        )
    return pkg_items


def _merge_package_items(
    existing_items: list[dict[str, str]] | None,
    new_items: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Merge package items by (type,name), with new items overwriting existing ones."""
    merged: dict[tuple[str, str], dict[str, str]] = {}
    for item in existing_items or []:
        item_type = item.get("type")
        item_name = item.get("name")
        if isinstance(item_type, str) and isinstance(item_name, str):
            merged[(item_type, item_name)] = {
                "type": item_type,
                "name": item_name,
                "hash": str(item.get("hash", "")),
            }

    for item in new_items:
        item_type = item.get("type")
        item_name = item.get("name")
        if isinstance(item_type, str) and isinstance(item_name, str):
            merged[(item_type, item_name)] = item

    return sorted(merged.values(), key=lambda i: (i["type"], i["name"]))


@dataclass
class ScanResult:
    """Summary of a scan-and-install operation."""

    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def scan_and_install(
    scan_path: "Path",
    *,
    replace: bool = False,
    enable: bool = False,
    max_depth: int = 5,
    log: LogFn | None = None,
) -> ScanResult:
    """Scan a local directory for components and install to registry.

    This is the service-layer function that ``cmd_scan`` (CLI) and
    ``_offer_builtins_install`` (wizard) both delegate to.
    """
    from pathlib import Path

    logf = log or _noop

    scan_path = Path(scan_path).resolve()
    registry = Registry(config.get_registry_path())
    registry.ensure_dirs()

    content = scan_directory(scan_path, max_depth=max_depth)
    if not content.items:
        logf("No components found.")
        return ScanResult()

    selected_items = content.items

    # Check clashes — skip clashing items (caller can use replace=True to overwrite)
    clashes = check_clashes(selected_items, registry)
    if clashes and not replace:
        # Use object identity so only the flagged duplicates are removed,
        # not the first valid occurrence that shares the same (type, name) key.
        clash_ids = {id(c) for c in clashes}
        items_to_add = [i for i in selected_items if id(i) not in clash_ids]
    else:
        items_to_add = selected_items

    if not items_to_add and not content.packages:
        logf("No new components to add.")
        return ScanResult()

    if items_to_add:
        added, skipped = add_items_to_registry(items_to_add, registry, replace=replace)
    else:
        added, skipped = [], []

    # Record packages
    if content.packages:
        existing_packages = config.load_packages()

        # Reject source-type conflicts (e.g. overwriting a git package with local scan)
        selected_pkg_names = {
            item.package or (content.package_meta.name if content.package_meta else "")
            for item in selected_items
        }
        blocked_pkgs: set[str] = set()
        for pn in sorted(n for n in selected_pkg_names if n):
            existing = existing_packages.get(pn)
            if not existing:
                continue
            existing_url = existing.get("url")
            existing_path = existing.get("path")
            existing_source = "git" if existing_url else ("local" if existing_path else "manual")
            if existing_source != "local":
                logf(
                    f"Package '{pn}' already exists with source [{existing_source}], "
                    "skipping metadata update."
                )
                blocked_pkgs.add(pn)

        items_by_pkg: dict[str, list] = {}
        for item in selected_items:
            pkg_name = item.package or (
                content.package_meta.name if content.package_meta else ""
            )
            if pkg_name:
                items_by_pkg.setdefault(pkg_name, []).append(item)
        pkg_meta_by_name = {p.name: p for p in content.packages}
        for pkg_name, pkg_item_list in items_by_pkg.items():
            if pkg_name in blocked_pkgs:
                continue
            pkg_items = _build_pkg_items(pkg_item_list, registry, pkg_name, set(added))
            if pkg_items:
                existing_items = existing_packages.get(pkg_name, {}).get("items", [])
                merged_items = _merge_package_items(existing_items, pkg_items)
                config.record_package(
                    pkg_name, "", "", merged_items,
                    path=str(scan_path),
                )
                meta = pkg_meta_by_name.get(pkg_name)
                logf(f"Package: {pkg_name}")
                if meta and meta.description:
                    logf(f"  {meta.description}")

    # Enable in global config
    if added and enable:
        newly = config.enable_items_in_config(added)
        if newly:
            logf(f"Enabled {len(newly)} component(s) in global config.")

    if added:
        logf(f"Added {len(added)} component(s).")
    if skipped:
        logf(f"Skipped {len(skipped)}.")

    return ScanResult(added=added, skipped=skipped)


def download_and_install(
    url: str,
    *,
    select_all: bool = False,
    replace: bool = False,
    name: str | None = None,
    select_fn: SelectFn | None = None,
    select_names: set[str] | None = None,
    log: LogFn | None = None,
) -> DownloadResult:
    """Download components from git and install to registry.

    Never raises SystemExit and never calls sys.exit().
    """
    logf = log or _noop

    registry = Registry(config.get_registry_path())
    registry.ensure_dirs()

    logf(f"Cloning {url}...")
    try:
        clone_dir = shallow_clone(url)
    except Exception as exc:  # pragma: no cover - parity with current CLI behavior
        err = f"Error cloning: {exc}"
        logf(err)
        return DownloadResult(success=False, error=err)

    try:
        commit_hash = get_head_commit(clone_dir)
        repo_name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        content = classify(clone_dir, repo_name=repo_name)
        if not content.items:
            logf("No components found in repository.")
            return DownloadResult(success=True)

        logf(f"\nFound {len(content.items)} component(s):")
        for item in content.items:
            logf(f"  [{item.component_type.value}] {item.name}")

        # Filter by --select names if provided
        if select_names is not None:
            filtered = [i for i in content.items if i.name in select_names]
            unknown = select_names - {i.name for i in content.items}
            if unknown:
                logf(f"\nWarning: not found in repo: {', '.join(sorted(unknown))}")
            if not filtered:
                logf("\nNo matching components found.")
                return DownloadResult(success=True)
            content = ClassifiedContent(
                items=filtered,
                package_meta=content.package_meta,
                packages=content.packages,
            )

        if select_all:
            selected_items = content.items
        else:
            pkg = (
                name
                or (content.package_meta.name if content.package_meta else None)
                or config.package_name_from_url(url)
            )
            if select_fn is None:
                selected_items = content.items
                action = None
            else:
                selection = select_fn(
                    content.items,
                    registry,
                    package_name=pkg,
                    packages=content.packages,
                )
                action = None
                if isinstance(selection, tuple):
                    selected_items = selection[0]
                    if len(selection) > 1:
                        action = selection[1]
                else:
                    selected_items = selection

            if not selected_items or action == "cancel":
                logf("\nNo components selected.")
                return DownloadResult(success=True)

        # Resolve clashes: rename clashing items with package prefix
        clashes = check_clashes(selected_items, registry)
        clash_names = [f"{item.component_type.value}/{item.name}" for item in clashes]
        if clashes and not replace:
            pkg_prefix = _clash_prefix(name, content, url)
            if pkg_prefix:
                for item in clashes:
                    old_name = item.name
                    new_name = _prefixed_name(pkg_prefix, old_name)
                    if not registry.detect_clash(item.component_type, new_name):
                        item.name = new_name
                        logf(f"  Renamed {old_name} -> {new_name} (clash with existing)")
                    else:
                        logf(f"  Skipping {old_name} (clash even after rename)")
            else:
                # No package context for renaming — skip clashing items
                logf("\nClashes with existing registry entries:")
                for item in clashes:
                    logf(f"  {item.component_type.value}/{item.name}")
                logf("\nUse --replace to overwrite existing entries.")

        # Re-check after renames: skip any remaining clashes
        if not replace:
            items_to_add = [
                i for i in selected_items
                if not registry.detect_clash(i.component_type, i.name)
            ]
        else:
            items_to_add = selected_items

        if not items_to_add:
            logf("\nNo new components to add.")
            return DownloadResult(success=True, clashes=clash_names)

        added, skipped = add_items_to_registry(items_to_add, registry, replace=replace)

        package_name: str | None = None
        if added:
            package_name = (
                name
                or (content.package_meta.name if content.package_meta else None)
                or config.package_name_from_url(url)
            )
            pkg_items = _build_pkg_items(selected_items, registry, package_name, set(added))
            if pkg_items:
                config.record_package(package_name, url, commit_hash, pkg_items)
                logf(f"\nRecorded package: {package_name} ({len(pkg_items)} items)")

        if added:
            logf(f"\nAdded {len(added)} component(s):")
            for item_name in added:
                logf(f"  + {item_name}")
        if skipped:
            logf(f"\nSkipped {len(skipped)}:")
            for item_name in skipped:
                logf(f"  - {item_name}")

        enable_requested = action == "save_enable" if not select_all else False

        if added and not enable_requested:
            logf("\nRun 'hawk enable <name>' to activate, then 'hawk sync' to apply.")

        return DownloadResult(
            success=True,
            added=added,
            skipped=skipped,
            clashes=clash_names,
            package_name=package_name,
            enable=enable_requested,
        )
    except Exception as exc:  # pragma: no cover - defensive parity with CLI behavior
        err = str(exc)
        logf(f"Error: {err}")
        return DownloadResult(success=False, error=err)
    finally:
        shutil.rmtree(clone_dir, ignore_errors=True)
