"""Download and install operations shared by CLI and TUI."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Callable

from . import config
from .downloader import ClassifiedContent, add_items_to_registry, check_clashes, classify, get_head_commit, shallow_clone
from .registry import Registry


LogFn = Callable[[str], None]

# SelectFn: (items, registry, *, package_name, packages) -> selected_items or (selected_items, action)
SelectFn = Callable[..., "list | tuple[list, str | None]"]


def get_interactive_select_fn() -> SelectFn:
    """Return the interactive item selector from the CLI module.

    Provides a clean import path so TUI callers don't reach into cli internals.
    """
    from .cli import _interactive_select_items

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


def _noop(_msg: str) -> None:
    return


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
            pkg = content.package_meta.name if content.package_meta else ""
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

        clashes = check_clashes(selected_items, registry)
        clash_names = [f"{item.component_type.value}/{item.name}" for item in clashes]
        if clashes:
            logf("\nClashes with existing registry entries:")
            for item in clashes:
                logf(f"  {item.component_type.value}/{item.name}")

        if clashes and not replace:
            logf("\nUse --replace to overwrite existing entries.")
            clash_keys = {(c.component_type, c.name) for c in clashes}
            items_to_add = [
                i for i in selected_items if (i.component_type, i.name) not in clash_keys
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

        if added:
            logf("\nRun 'hawk sync' to apply changes.")

        return DownloadResult(
            success=True,
            added=added,
            skipped=skipped,
            clashes=clash_names,
            package_name=package_name,
        )
    except Exception as exc:  # pragma: no cover - defensive parity with CLI behavior
        err = str(exc)
        logf(f"Error: {err}")
        return DownloadResult(success=False, error=err)
    finally:
        shutil.rmtree(clone_dir, ignore_errors=True)
