"""Package update/remove operations shared by CLI and TUI."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import config
from .downloader import classify, get_head_commit, scan_directory, shallow_clone
from .registry import Registry
from .types import ComponentType


LogFn = Callable[[str], None]


class PackageServiceError(RuntimeError):
    """Base error for package service operations."""


class PackageNotFoundError(PackageServiceError):
    """Raised when an operation references an unknown package."""

    def __init__(self, package_name: str, installed: list[str]):
        self.package_name = package_name
        self.installed = installed
        super().__init__(f"Package not found: {package_name}")


class PackageUpdateFailedError(PackageServiceError):
    """Raised when one or more packages failed to update."""

    def __init__(self, failed_packages: list[str]):
        self.failed_packages = failed_packages
        super().__init__(
            f"Failed ({len(failed_packages)}): {', '.join(sorted(failed_packages))}"
        )


@dataclass
class PackageUpdateReport:
    """Summary of a package update operation."""

    any_changes: bool = False
    check_only: bool = False
    up_to_date: list[str] = field(default_factory=list)
    failed_packages: list[str] = field(default_factory=list)


@dataclass
class PackageRemoveReport:
    """Summary of a package removal operation."""

    package_name: str
    removed_items: int


@dataclass
class UngroupedRemoveReport:
    """Summary of removing ungrouped registry items."""

    removed_items: int
    removed_by_type: dict[str, int] = field(default_factory=dict)


def _noop(_msg: str) -> None:
    return


def _package_source_type(pkg_data: dict) -> str:
    """Infer package source type from package metadata."""
    if pkg_data.get("url"):
        return "git"
    if pkg_data.get("path"):
        return "local"
    return "manual"


def _iter_valid_package_items(
    items: object,
    *,
    log: LogFn,
    package_name: str,
) -> list[tuple[str, str, str]]:
    """Return valid (type, name, hash) tuples from package metadata items."""
    valid: list[tuple[str, str, str]] = []
    if not isinstance(items, list):
        log(f"{package_name}: malformed package items list; skipping")
        return valid
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            log(f"{package_name}: malformed package item at index {idx}; skipping")
            continue
        item_type = item.get("type")
        item_name = item.get("name")
        if not isinstance(item_type, str) or not isinstance(item_name, str):
            log(
                f"{package_name}: malformed package item at index {idx} (missing type/name); skipping"
            )
            continue
        item_hash = item.get("hash", "")
        valid.append((item_type, item_name, item_hash if isinstance(item_hash, str) else ""))
    return valid


def update_packages(
    package: str | None = None,
    *,
    check: bool = False,
    force: bool = False,
    prune: bool = False,
    sync_on_change: bool = True,
    log: LogFn | None = None,
) -> PackageUpdateReport:
    """Update tracked packages from their source locations."""
    logf = log or _noop
    report = PackageUpdateReport(check_only=check)

    packages = config.load_packages()
    if not packages:
        logf("No packages installed.")
        return report

    registry = Registry(config.get_registry_path())
    registry.ensure_dirs()

    if package:
        if package not in packages:
            raise PackageNotFoundError(package, sorted(packages.keys()))
        to_update = {package: packages[package]}
    else:
        to_update = packages

    any_changes = False
    up_to_date: list[str] = []
    failed_packages: list[str] = []

    for pkg_name, pkg_data in sorted(to_update.items()):
        source_type = _package_source_type(pkg_data)
        old_items = {
            (item_type, item_name): item_hash
            for item_type, item_name, item_hash in _iter_valid_package_items(
                pkg_data.get("items", []),
                log=logf,
                package_name=pkg_name,
            )
        }
        registry_path = config.get_registry_path()

        if source_type == "manual":
            logf(f"{pkg_name}: local-only package, cannot update")
            continue

        if source_type == "git":
            url = pkg_data.get("url", "")
            logf(f"\n{pkg_name}:")
            logf(f"  Cloning {url}...")

            clone_dir: Path | None = None
            try:
                clone_dir = shallow_clone(url)
            except Exception as e:  # pragma: no cover - defensive parity with existing behavior
                logf(f"  Error cloning: {e}")
                failed_packages.append(pkg_name)
                continue

            try:
                new_commit = get_head_commit(clone_dir)
                old_commit = pkg_data.get("commit", "")

                if new_commit == old_commit and not force:
                    up_to_date.append(pkg_name)
                    logf(f"  Up to date ({new_commit[:7]})")
                    continue

                if check:
                    logf(f"  Update available: {old_commit[:7]} -> {new_commit[:7]}")
                    any_changes = True
                    continue

                repo_name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
                content = classify(clone_dir, repo_name=repo_name)

                new_pkg_items = []
                added_count = 0
                updated_count = 0

                for item in content.items:
                    item_key = (item.component_type.value, item.name)

                    try:
                        if registry.detect_clash(item.component_type, item.name):
                            registry.replace(item.component_type, item.name, item.source_path)
                        else:
                            registry.add(item.component_type, item.name, item.source_path)
                    except (FileNotFoundError, FileExistsError, OSError) as e:
                        logf(f"  ! {item.name}: {e}")
                        continue

                    item_path = registry_path / item.component_type.registry_dir / item.name
                    new_hash = config.hash_registry_item(item_path)

                    new_pkg_items.append({
                        "type": item.component_type.value,
                        "name": item.name,
                        "hash": new_hash,
                    })

                    old_hash = old_items.get(item_key, "")
                    if not old_hash:
                        logf(f"  + {item.name} (added)")
                        added_count += 1
                    elif old_hash != new_hash:
                        logf(f"  ~ {item.name} (updated)")
                        updated_count += 1
                    else:
                        logf(f"  = {item.name} (unchanged)")

                new_keys = {(i["type"], i["name"]) for i in new_pkg_items}
                for (t, n), _ in old_items.items():
                    if (t, n) in new_keys:
                        continue
                    if prune:
                        try:
                            ct = ComponentType(t)
                        except ValueError:
                            logf(f"  ! malformed package item type '{t}' for {n}; skipping prune")
                            continue
                        if registry.remove(ct, n):
                            any_changes = True
                        logf(f"  - {n} (pruned)")
                    else:
                        logf(f"  ? {n} (removed upstream, kept locally)")

                config.record_package(
                    pkg_name, url, new_commit, new_pkg_items, path=str(pkg_data.get("path", ""))
                )

                parts = []
                if updated_count:
                    parts.append(f"{updated_count} updated")
                if added_count:
                    parts.append(f"{added_count} new")
                if parts:
                    logf(f"  {', '.join(parts)}")
                    any_changes = True
            finally:
                if clone_dir is not None:
                    shutil.rmtree(clone_dir, ignore_errors=True)
            continue

        local_path = Path(str(pkg_data.get("path", ""))).expanduser()
        logf(f"\n{pkg_name}:")

        if not local_path.exists():
            logf(f"  local source path not found: {local_path}")
            logf("  Path moved? Re-import: hawk scan /new/path --all --replace")
            logf(f"  Removed intentionally? hawk remove-package {pkg_name}")
            logf(f"  Temporarily unavailable? Reconnect and run: hawk update {pkg_name}")
            failed_packages.append(pkg_name)
            continue

        content = scan_directory(local_path.resolve())
        if not content.items:
            logf(f"  no components found at {local_path.resolve()}")
            logf("  Fix: verify path, increase scan depth if needed, or re-import")
            logf("  Example: hawk scan /correct/path --depth 8 --all --replace")
            failed_packages.append(pkg_name)
            continue

        new_pkg_items = []
        added_count = 0
        updated_count = 0
        unchanged_count = 0

        for item in content.items:
            item_key = (item.component_type.value, item.name)

            if check:
                new_hash = config.hash_registry_item(item.source_path)
            else:
                try:
                    if registry.detect_clash(item.component_type, item.name):
                        registry.replace(item.component_type, item.name, item.source_path)
                    else:
                        registry.add(item.component_type, item.name, item.source_path)
                except (FileNotFoundError, FileExistsError, OSError) as e:
                    logf(f"  ! {item.name}: {e}")
                    continue

                item_path = registry_path / item.component_type.registry_dir / item.name
                new_hash = config.hash_registry_item(item_path)

            new_pkg_items.append({
                "type": item.component_type.value,
                "name": item.name,
                "hash": new_hash,
            })

            old_hash = old_items.get(item_key, "")
            if not old_hash:
                added_count += 1
            elif old_hash != new_hash:
                updated_count += 1
            else:
                unchanged_count += 1

        new_keys = {(i["type"], i["name"]) for i in new_pkg_items}
        removed_count = 0
        for (t, n), _ in old_items.items():
            if (t, n) in new_keys:
                continue
            removed_count += 1
            if check:
                continue
            if prune:
                try:
                    ct = ComponentType(t)
                except ValueError:
                    logf(f"  ! malformed package item type '{t}' for {n}; skipping prune")
                    continue
                if registry.remove(ct, n):
                    any_changes = True
                logf(f"  - {n} (pruned)")
            else:
                logf(f"  ? {n} (removed upstream, kept locally)")

        if check:
            if added_count or updated_count or removed_count:
                parts = []
                if updated_count:
                    parts.append(f"{updated_count} updated")
                if added_count:
                    parts.append(f"{added_count} new")
                if removed_count:
                    parts.append(f"{removed_count} removed upstream")
                logf(f"  Would update: {', '.join(parts)}")
                any_changes = True
            else:
                up_to_date.append(pkg_name)
                logf("  Up to date (local)")
            continue

        config.record_package(
            pkg_name, "", "", new_pkg_items, path=str(local_path.resolve())
        )

        parts = []
        if updated_count:
            parts.append(f"{updated_count} updated")
        if added_count:
            parts.append(f"{added_count} new")
        if parts:
            logf(f"  {', '.join(parts)}")
            any_changes = True
        elif unchanged_count and not removed_count:
            up_to_date.append(pkg_name)
            logf("  Up to date (local)")

    if up_to_date:
        logf(f"\nAll packages up to date: {', '.join(up_to_date)}")

    if any_changes and not check and sync_on_change:
        from .sync import sync_all

        logf("\nSyncing...")
        sync_all(force=True)
        logf("Done.")

    report.any_changes = any_changes
    report.up_to_date = up_to_date
    report.failed_packages = sorted(failed_packages)

    if failed_packages:
        logf(
            f"\nFailed ({len(failed_packages)}): {', '.join(sorted(failed_packages))}"
        )
        raise PackageUpdateFailedError(sorted(failed_packages))

    return report


def remove_package(
    package_name: str,
    *,
    sync_after: bool = True,
    log: LogFn | None = None,
) -> PackageRemoveReport:
    """Remove a package and all its items from registry + config."""
    logf = log or _noop

    packages = config.load_packages()
    if package_name not in packages:
        raise PackageNotFoundError(package_name, sorted(packages.keys()))

    pkg_data = packages[package_name]
    items = pkg_data.get("items", [])
    valid_items = _iter_valid_package_items(items, log=logf, package_name=package_name)
    registry = Registry(config.get_registry_path())

    removed = 0
    for item_type, item_name, _ in valid_items:
        try:
            ct = ComponentType(item_type)
            if registry.remove(ct, item_name):
                removed += 1
                logf(f"  Removed {item_type}/{item_name}")
        except ValueError:
            logf(f"{package_name}: malformed package item type '{item_type}' for {item_name}; skipping")
            continue

    item_names_by_field: dict[str, set[str]] = {}
    for item_type, item_name, _ in valid_items:
        try:
            field = ComponentType(item_type).registry_dir
        except ValueError:
            logf(f"{package_name}: malformed package item type '{item_type}' for {item_name}; skipping")
            continue
        item_names_by_field.setdefault(field, set()).add(item_name)
    _remove_names_from_global_and_dir_enabled_lists(item_names_by_field)

    config.remove_package(package_name)

    logf(f"\nRemoved package '{package_name}' ({removed} items)")

    if sync_after:
        from .sync import sync_all

        logf("Syncing...")
        sync_all(force=True)
        logf("Done.")

    return PackageRemoveReport(package_name=package_name, removed_items=removed)


def _remove_names_from_global_and_dir_enabled_lists(
    item_names_by_field: dict[str, set[str]],
) -> None:
    """Remove names from global and directory enabled lists by component field."""
    cfg = config.load_global_config()
    global_section = cfg.get("global", {})

    for field, names in item_names_by_field.items():
        enabled = global_section.get(field, [])
        if isinstance(enabled, list):
            new_enabled = [n for n in enabled if n not in names]
            if len(new_enabled) != len(enabled):
                global_section[field] = new_enabled

    cfg["global"] = global_section
    config.save_global_config(cfg)

    for dir_path_str in config.get_registered_directories():
        dir_cfg = config.load_dir_config(Path(dir_path_str))
        if not dir_cfg:
            continue
        dir_changed = False
        for field, names in item_names_by_field.items():
            section = dir_cfg.get(field, {})
            if not isinstance(section, dict):
                continue
            enabled = section.get("enabled", [])
            new_enabled = [n for n in enabled if n not in names]
            if len(new_enabled) != len(enabled):
                section["enabled"] = new_enabled
                dir_cfg[field] = section
                dir_changed = True
        if dir_changed:
            config.save_dir_config(Path(dir_path_str), dir_cfg)


def remove_ungrouped_items(
    *,
    sync_after: bool = True,
    log: LogFn | None = None,
) -> UngroupedRemoveReport:
    """Remove all package-menu ungrouped items from registry and enabled config lists."""
    logf = log or _noop
    packages = config.load_packages()
    registry = Registry(config.get_registry_path())

    managed_types = [
        ComponentType.SKILL,
        ComponentType.HOOK,
        ComponentType.PROMPT,
        ComponentType.AGENT,
        ComponentType.MCP,
    ]
    field_by_type = {ct: ct.registry_dir for ct in managed_types}

    owned_by_field: dict[str, set[str]] = {field: set() for field in field_by_type.values()}
    for _pkg_name, pkg_data in packages.items():
        for item in pkg_data.get("items", []):
            item_type = item.get("type")
            item_name = item.get("name")
            if not isinstance(item_type, str) or not isinstance(item_name, str):
                continue
            try:
                ct = ComponentType(item_type)
            except ValueError:
                continue
            field = field_by_type.get(ct)
            if field:
                owned_by_field[field].add(item_name)

    contents = registry.list()
    removed_by_type: dict[str, int] = {ct.value: 0 for ct in managed_types}
    item_names_by_field: dict[str, set[str]] = {}
    removed_total = 0

    for ct in managed_types:
        field = field_by_type[ct]
        owned_names = owned_by_field.get(field, set())
        for name in contents.get(ct, []):
            if name in owned_names:
                continue
            if registry.remove(ct, name):
                removed_total += 1
                removed_by_type[ct.value] = removed_by_type.get(ct.value, 0) + 1
                item_names_by_field.setdefault(field, set()).add(name)
                logf(f"  Removed {ct.value}/{name}")

    if removed_total <= 0:
        logf("\nNo ungrouped items found.")
        return UngroupedRemoveReport(removed_items=0, removed_by_type={})

    _remove_names_from_global_and_dir_enabled_lists(item_names_by_field)
    logf(f"\nRemoved {removed_total} ungrouped item(s)")

    if sync_after:
        from .sync import sync_all

        logf("Syncing...")
        sync_all(force=True)
        logf("Done.")

    compact_counts = {k: v for k, v in removed_by_type.items() if v > 0}
    return UngroupedRemoveReport(
        removed_items=removed_total,
        removed_by_type=compact_counts,
    )
