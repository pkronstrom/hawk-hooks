"""v2 CLI interface for hawk-hooks.

New command structure for multi-tool management.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .types import ComponentType, Tool


_console = None


def _print(msg: str = "") -> None:
    """Print with Rich markup support. Falls back to plain print."""
    global _console
    if _console is None:
        try:
            from rich.console import Console
            _console = Console(highlight=False)
        except ImportError:
            _console = False
    if _console:
        _console.print(msg)
    else:
        print(msg)


def cmd_init(args):
    """Initialize a directory for hawk management."""
    from . import v2_config
    from .v2_sync import sync_directory

    project_dir = Path(args.dir).resolve() if args.dir else Path.cwd().resolve()

    if not project_dir.is_dir():
        print(f"Error: Not a directory: {project_dir}")
        sys.exit(1)

    config_path = v2_config.get_dir_config_path(project_dir)
    if config_path.exists() and not args.force:
        print(f"Already initialized: {config_path}")
        print("Use --force to reinitialize.")
        return

    # Build dir config
    dir_config: dict = {}
    if args.profile:
        profile = v2_config.load_profile(args.profile)
        if profile is None:
            print(f"Error: Profile not found: {args.profile}")
            sys.exit(1)
        dir_config["profile"] = args.profile

    # Save dir config
    v2_config.save_dir_config(project_dir, dir_config)

    # Register in global index
    v2_config.register_directory(project_dir, profile=args.profile)

    # Ensure registry dirs exist
    v2_config.ensure_v2_dirs()

    # Sync
    results = sync_directory(project_dir)

    # Summary
    print(f"Initialized: {config_path}")
    if args.profile:
        print(f"Profile: {args.profile}")
    print(f"Registered in global index.")

    total_linked = sum(len(r.linked) for r in results)
    if total_linked:
        print(f"\nSynced {total_linked} component(s):")
        for r in results:
            if r.linked:
                print(f"  {r.tool}: {', '.join(r.linked)}")

    print("\nNext steps:")
    print("  hawk add skill <path>   # Add skills to registry")
    print("  hawk sync               # Re-sync after changes")
    print("  hawk status             # View current state")


def cmd_sync(args):
    """Sync components to tools."""
    from . import v2_config
    from .v2_sync import format_sync_results, sync_all, sync_directory, sync_global

    # Auto-register + prune on each sync
    v2_config.auto_register_if_needed(Path.cwd())
    v2_config.prune_stale_directories()

    tools = [Tool(args.tool)] if args.tool else None

    force = args.force

    if args.dir:
        project_dir = Path(args.dir).resolve()
        results = sync_directory(project_dir, tools=tools, dry_run=args.dry_run, force=force)
        formatted = format_sync_results({str(project_dir): results})
    elif args.globals_only:
        results = sync_global(tools=tools, dry_run=args.dry_run, force=force)
        formatted = format_sync_results({"global": results})
    else:
        all_results = sync_all(tools=tools, dry_run=args.dry_run, force=force)
        formatted = format_sync_results(all_results)

    if args.dry_run:
        print("Dry run (no changes applied):")
    print(formatted or "  No changes.")


def cmd_status(args):
    """Show current status."""
    from . import v2_config
    from .adapters import get_adapter
    from .registry import Registry
    from .resolver import resolve

    cfg = v2_config.load_global_config()
    registry = Registry(v2_config.get_registry_path(cfg))

    # Show registry contents
    contents = registry.list()
    total = sum(len(names) for names in contents.values())
    print(f"Registry: {total} component(s)")
    for ct, names in contents.items():
        if names:
            print(f"  {ct.registry_dir}: {', '.join(names)}")

    # Show resolved set (global or directory-scoped)
    if args.dir:
        project_dir = Path(args.dir).resolve()

        # Show config chain
        config_chain = v2_config.get_config_chain(project_dir)
        if config_chain:
            chain_labels = ["global"] + [str(d) for d, _ in config_chain]
            print(f"\nChain: {' -> '.join(chain_labels)}")

            # Show per-layer breakdown
            global_section = cfg.get("global", {})
            for field in ["skills", "hooks", "commands", "agents", "mcp"]:
                g_items = global_section.get(field, [])
                if g_items:
                    print(f"  global:  {', '.join(g_items)}")
                    break
            # Show each layer's contributions
            for chain_dir, chain_config in config_chain:
                parts: list[str] = []
                for field in ["skills", "hooks", "commands", "agents", "mcp"]:
                    section = chain_config.get(field, {})
                    if isinstance(section, dict):
                        enabled = section.get("enabled", [])
                        disabled = section.get("disabled", [])
                        if enabled:
                            parts.extend(f"+{e}" for e in enabled)
                        if disabled:
                            parts.extend(f"-{d}" for d in disabled)
                    elif isinstance(section, list) and section:
                        parts.extend(f"+{e}" for e in section)
                if parts:
                    dir_name = Path(chain_dir).name if isinstance(chain_dir, str) else chain_dir.name
                    print(f"  {dir_name}:  {', '.join(parts)}")

            # Build dir_chain for resolve
            from .v2_sync import _load_profile_for_dir
            dir_chain: list[tuple[dict, dict | None]] = []
            for chain_dir, chain_config in config_chain:
                profile_name = _load_profile_for_dir(chain_config, chain_dir, cfg)
                profile = v2_config.load_profile(profile_name) if profile_name else None
                dir_chain.append((chain_config, profile))
            resolved = resolve(cfg, dir_chain=dir_chain)
        else:
            dir_config = v2_config.load_dir_config(project_dir)
            profile_name = dir_config.get("profile") if dir_config else None
            profile = v2_config.load_profile(profile_name) if profile_name else None
            resolved = resolve(cfg, profile=profile, dir_config=dir_config)

        print(f"\nResolved for {project_dir}:")
    else:
        resolved = resolve(cfg)
        print(f"\nGlobal active:")
    for field in ["skills", "hooks", "commands", "agents", "mcp"]:
        items = getattr(resolved, field)
        if items:
            print(f"  {field}: {', '.join(items)}")

    # Show tool status
    print(f"\nTools:")
    for tool in Tool.all():
        adapter = get_adapter(tool)
        installed = adapter.detect_installed()
        tool_cfg = cfg.get("tools", {}).get(str(tool), {})
        enabled = tool_cfg.get("enabled", True)
        status_parts = []
        if installed:
            status_parts.append("installed")
        else:
            status_parts.append("not found")
        if enabled:
            status_parts.append("enabled")
        else:
            status_parts.append("disabled")
        print(f"  {tool}: {', '.join(status_parts)}")

    # Show registered directories
    dirs = v2_config.get_registered_directories()
    if dirs:
        print(f"\nDirectories ({len(dirs)}):")
        for dir_path, entry in dirs.items():
            profile = entry.get("profile", "")
            suffix = f" (profile: {profile})" if profile else ""
            exists = Path(dir_path).exists()
            marker = "" if exists else " [missing]"
            print(f"  {dir_path}{suffix}{marker}")


def cmd_projects(args):
    """Show interactive projects tree view."""
    from .v2_interactive.dashboard import _run_projects_tree
    _run_projects_tree()


def _guess_component_type(path: Path) -> ComponentType | None:
    """Guess component type from file/directory characteristics."""
    if path.is_dir():
        # Directory with SKILL.md → skill
        if (path / "SKILL.md").exists() or (path / "skill.md").exists():
            return ComponentType.SKILL
        return None

    suffix = path.suffix.lower()
    parent = path.parent.name.lower()

    # Parent directory hints
    if parent == "commands":
        return ComponentType.COMMAND
    if parent == "agents":
        return ComponentType.AGENT
    if parent == "prompts":
        return ComponentType.PROMPT
    if parent == "hooks":
        return ComponentType.HOOK
    if parent == "skills":
        return ComponentType.SKILL
    if parent == "mcp":
        return ComponentType.MCP

    # File extension hints
    if suffix in (".py", ".sh", ".js", ".ts"):
        return ComponentType.HOOK
    if suffix in (".yaml", ".yml"):
        return ComponentType.MCP

    # Markdown with frontmatter → command
    if suffix == ".md":
        try:
            head = path.read_text(errors="replace")[:500]
            if head.startswith("---") and "name:" in head and "description:" in head:
                return ComponentType.COMMAND
        except OSError:
            pass

    return None


def _ask_component_type() -> ComponentType | None:
    """Interactively ask the user what type of component this is."""
    type_options = [
        ("skill", "Skill — reusable instructions / knowledge"),
        ("command", "Command — slash command / action"),
        ("agent", "Agent — autonomous agent definition"),
        ("hook", "Hook — event-triggered script"),
        ("prompt", "Prompt — prompt template"),
        ("mcp", "MCP — MCP server configuration"),
    ]
    print("\nWhat type of component is this?")
    for i, (key, desc) in enumerate(type_options, 1):
        print(f"  {i}) {desc}")

    try:
        choice = input("\nChoice [1-6]: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(type_options):
            return ComponentType(type_options[idx][0])
    except (ValueError, KeyboardInterrupt, EOFError):
        pass
    return None


def _name_from_content(text: str, suffix: str = ".md") -> str:
    """Generate a slug name from the first few words of content."""
    import re
    # Strip frontmatter
    clean = text.strip()
    if clean.startswith("---"):
        end = clean.find("---", 3)
        if end > 0:
            clean = clean[end + 3:].strip()
    # Strip markdown heading markers
    clean = re.sub(r"^#+\s*", "", clean, count=1)
    # Take first 3 words
    words = re.findall(r"[a-zA-Z0-9]+", clean)[:3]
    if not words:
        return f"unnamed{suffix}"
    slug = "-".join(w.lower() for w in words)
    if not slug.endswith(suffix):
        slug += suffix
    return slug


def cmd_add(args):
    """Add a component to the registry."""
    import tempfile

    from .registry import Registry
    from . import v2_config

    # --type flag takes priority over positional type
    valid_types = {ct.value for ct in ComponentType}
    if getattr(args, "type_flag", None):
        args.type = args.type_flag

    # Handle "hawk add /path/to/file.md" (argparse puts path in args.type)
    if args.type and args.type not in valid_types and args.path is None:
        args.path = args.type
        args.type = None

    registry = Registry(v2_config.get_registry_path())
    registry.ensure_dirs()

    # Determine source: file path or stdin
    source = None
    stdin_content = None

    if args.path:
        source = Path(args.path).resolve()
        if not source.exists():
            print(f"Error: {source} does not exist.")
            sys.exit(1)
    elif not sys.stdin.isatty():
        stdin_content = sys.stdin.read()
        if not stdin_content.strip():
            print("Error: no content received from stdin.")
            sys.exit(1)
    else:
        print("Usage: hawk add [type] <path>")
        print("       echo 'content' | hawk add --type skill --name my-skill.md")
        sys.exit(1)

    # Determine component type
    if args.type and args.type in valid_types:
        component_type = ComponentType(args.type)
    elif stdin_content is not None:
        print("Error: --type is required when reading from stdin.")
        print("  echo 'content' | hawk add --type skill --name my-skill.md")
        sys.exit(1)
    else:
        # Try to auto-detect from file
        component_type = _guess_component_type(source) if source else None

        if component_type:
            _print(f"Detected type: [cyan]{component_type.value}[/cyan]")
            try:
                confirm = input(f"Use '{component_type.value}'? [Y/n]: ").strip().lower()
                if confirm and confirm != "y":
                    component_type = _ask_component_type()
            except (KeyboardInterrupt, EOFError):
                return
        else:
            component_type = _ask_component_type()

        if component_type is None:
            print("Cancelled.")
            return

    # Determine name
    if args.name:
        name = args.name
    elif source:
        name = source.name
    else:
        # Auto-generate from content
        name = _name_from_content(stdin_content)
        _print(f"Auto-generated name: [cyan]{name}[/cyan]")

    # If stdin, write to temp file first
    if stdin_content is not None:
        tmp = Path(tempfile.mkdtemp(prefix="hawk-add-")) / name
        tmp.write_text(stdin_content)
        source = tmp

    # Add to registry
    if registry.detect_clash(component_type, name):
        if not args.force:
            _print(f"[red]Error:[/red] {component_type.value}/{name} already exists. Use [cyan]--force[/cyan] to replace.")
            sys.exit(1)
        registry.remove(component_type, name)

    try:
        path = registry.add(component_type, name, source)
        _print(f"\n[green]+[/green] Added [bold]{component_type.value}[/bold]/{name}")
        _print(f"  [dim]->[/dim] {path}")
    except (FileNotFoundError, FileExistsError) as e:
        _print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    # Enable in global config
    if getattr(args, "enable", True):
        cfg = v2_config.load_global_config()
        global_section = cfg.get("global", {})
        field = component_type.registry_dir
        enabled = global_section.get(field, [])
        if name not in enabled:
            enabled.append(name)
            global_section[field] = enabled
            cfg["global"] = global_section
            v2_config.save_global_config(cfg)
            _print(f"[green]+[/green] Enabled in global config [dim]({field})[/dim]")

    _print(f"\n[dim]Run[/dim] [cyan]hawk sync[/cyan] [dim]to apply.[/dim]")


def cmd_remove(args):
    """Remove a component from the registry."""
    from .registry import Registry
    from . import v2_config

    registry = Registry(v2_config.get_registry_path())
    component_type = ComponentType(args.type)

    if registry.remove(component_type, args.name):
        print(f"Removed {component_type}/{args.name}")
        print("Run 'hawk sync' to update tool configs.")
    else:
        print(f"Not found: {component_type}/{args.name}")
        sys.exit(1)


def cmd_list(args):
    """List registry contents."""
    from .registry import Registry
    from . import v2_config

    registry = Registry(v2_config.get_registry_path())

    if args.type:
        component_type = ComponentType(args.type)
        contents = registry.list(component_type)
    else:
        contents = registry.list()

    for ct, names in contents.items():
        if names:
            print(f"{ct.registry_dir}/")
            for name in names:
                print(f"  {name}")


def cmd_profile_list(args):
    """List available profiles."""
    from . import v2_config

    profiles = v2_config.list_profiles()
    if not profiles:
        print("No profiles found.")
        print(f"Create one in: {v2_config.get_profiles_dir()}/")
        return
    for name in profiles:
        print(f"  {name}")


def cmd_profile_show(args):
    """Show profile details."""
    from . import v2_config

    import yaml

    profile = v2_config.load_profile(args.name)
    if profile is None:
        print(f"Profile not found: {args.name}")
        sys.exit(1)

    print(yaml.dump(profile, default_flow_style=False))


def _build_pkg_items(items_to_add, added, registry_path):
    """Build package item list with hashes for items that were successfully added."""
    from . import v2_config

    pkg_items = []
    for item in items_to_add:
        item_key = f"{item.component_type}/{item.name}"
        if item_key in added:
            item_path = registry_path / item.component_type.registry_dir / item.name
            item_hash = v2_config.hash_registry_item(item_path)
            pkg_items.append({
                "type": item.component_type.value,
                "name": item.name,
                "hash": item_hash,
            })
    return pkg_items


def cmd_download(args):
    """Download components from a git URL."""
    import shutil

    from .downloader import (
        add_items_to_registry, check_clashes, classify, get_head_commit, shallow_clone,
    )
    from .registry import Registry
    from . import v2_config

    url = args.url
    registry = Registry(v2_config.get_registry_path())
    registry.ensure_dirs()

    # 1. Shallow clone
    print(f"Cloning {url}...")
    try:
        clone_dir = shallow_clone(url)
    except Exception as e:
        print(f"Error cloning: {e}")
        sys.exit(1)

    try:
        # Get commit hash for package tracking
        commit_hash = get_head_commit(clone_dir)

        # 2. Classify contents
        content = classify(clone_dir)
        if not content.items:
            print("No components found in repository.")
            return

        print(f"\nFound {len(content.items)} component(s):")
        for item in content.items:
            print(f"  [{item.component_type.value}] {item.name}")

        # 3. Let user select (unless --all)
        if args.all:
            selected_items = content.items
        else:
            selected_items = _interactive_select_items(content.items, registry)
            if not selected_items:
                print("\nNo components selected.")
                return

        # 4. Check for clashes
        clashes = check_clashes(selected_items, registry)
        if clashes:
            print(f"\nClashes with existing registry entries:")
            for item in clashes:
                print(f"  {item.component_type.value}/{item.name}")

        # 5. Add to registry
        replace = args.replace
        if clashes and not replace:
            print("\nUse --replace to overwrite existing entries.")
            clash_keys = {(c.component_type, c.name) for c in clashes}
            items_to_add = [
                i for i in selected_items
                if (i.component_type, i.name) not in clash_keys
            ]
        else:
            items_to_add = selected_items

        if not items_to_add:
            print("\nNo new components to add.")
            return

        added, skipped = add_items_to_registry(items_to_add, registry, replace=replace)

        # 6. Record package in packages.yaml
        if added:
            pkg_name = (
                getattr(args, "name", None)
                or (content.package_meta.name if content.package_meta else None)
                or v2_config.package_name_from_url(url)
            )
            registry_path = v2_config.get_registry_path()
            pkg_items = _build_pkg_items(items_to_add, added, registry_path)
            if pkg_items:
                v2_config.record_package(pkg_name, url, commit_hash, pkg_items)
                print(f"\nRecorded package: {pkg_name} ({len(pkg_items)} items)")

        # 7. Summary
        if added:
            print(f"\nAdded {len(added)} component(s):")
            for name in added:
                print(f"  + {name}")
        if skipped:
            print(f"\nSkipped {len(skipped)}:")
            for name in skipped:
                print(f"  - {name}")

        print("\nNext steps:")
        print("  hawk list              # View registry")
        print("  hawk sync              # Sync to tools")
    finally:
        # Clean up temp dir
        shutil.rmtree(clone_dir, ignore_errors=True)


def _interactive_select_items(items, registry=None):
    """Show interactive multi-select for download items. Returns selected items."""
    from simple_term_menu import TerminalMenu

    options = []
    preselected = []
    for i, item in enumerate(items):
        exists = registry and registry.has(item.component_type, item.name)
        label = f"[{item.component_type.value}] {item.name}"
        if exists:
            label += "  (already registered)"
        else:
            preselected.append(i)
        options.append(label)

    menu = TerminalMenu(
        options,
        title=f"\nSelect components to add ({len(options)} found, space to toggle, enter to confirm):",
        multi_select=True,
        preselected_entries=preselected,
        multi_select_select_on_accept=False,
        clear_screen=True,
        menu_cursor="\u276f ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
        quit_keys=("q", "\x1b"),
        show_search_hint=True,
        search_key="/",
        status_bar="Space: toggle  /: search  Enter: confirm  q: quit",
    )
    result = menu.show()
    if result is None:
        return []
    indices = list(result) if isinstance(result, tuple) else [result]
    return [items[i] for i in indices]


def cmd_scan(args):
    """Scan a directory tree for hawk-compatible components and import selected ones."""
    from .downloader import (
        add_items_to_registry, check_clashes, scan_directory,
    )
    from .registry import Registry
    from . import v2_config

    scan_path = Path(args.path).resolve()
    if not scan_path.is_dir():
        print(f"Error: {scan_path} is not a directory.")
        sys.exit(1)

    registry = Registry(v2_config.get_registry_path())
    registry.ensure_dirs()

    # Scan
    depth = getattr(args, "depth", 5)
    print(f"Scanning {scan_path} (max depth {depth})...")
    content = scan_directory(scan_path, max_depth=depth)

    if not content.items:
        print("No components found.")
        return

    # Show compact summary (avoid flooding terminal before interactive menu)
    by_type = content.by_type
    type_counts = ", ".join(
        f"{len(items)} {ct.value}{'s' if len(items) != 1 else ''}"
        for ct, items in sorted(by_type.items(), key=lambda x: x[0].value)
    )
    print(f"\nFound {len(content.items)} component(s): {type_counts}")

    # Let user select (unless --all)
    if args.all:
        selected_items = content.items
    else:
        selected_items = _interactive_select_items(content.items, registry)
        if not selected_items:
            print("\nNo components selected.")
            return

    # Check clashes
    clashes = check_clashes(selected_items, registry)
    if clashes:
        print(f"\nClashes with existing registry entries:")
        for item in clashes:
            print(f"  {item.component_type.value}/{item.name}")

    # Add to registry (copies files)
    replace = args.replace
    if clashes and not replace:
        print("\nUse --replace to overwrite existing entries.")
        clash_keys = {(c.component_type, c.name) for c in clashes}
        items_to_add = [
            i for i in selected_items
            if (i.component_type, i.name) not in clash_keys
        ]
    else:
        items_to_add = selected_items

    if not items_to_add:
        print("\nNo new components to add.")
        return

    added, skipped = add_items_to_registry(items_to_add, registry, replace=replace)

    # Record package if manifest found
    if added and content.package_meta:
        registry_path = v2_config.get_registry_path()
        pkg_items = _build_pkg_items(items_to_add, added, registry_path)
        if pkg_items:
            v2_config.record_package(
                content.package_meta.name, "", "", pkg_items,
                path=str(scan_path),
            )
            _print(f"\n[green]Package:[/green] {content.package_meta.name}")
            if content.package_meta.description:
                _print(f"  {content.package_meta.description}")

    # Enable in global config
    if added and not args.no_enable:
        cfg = v2_config.load_global_config()
        global_section = cfg.get("global", {})
        for item in items_to_add:
            item_key = f"{item.component_type}/{item.name}"
            if item_key in added:
                field = item.component_type.registry_dir
                enabled = global_section.get(field, [])
                if item.name not in enabled:
                    enabled.append(item.name)
                global_section[field] = enabled
        cfg["global"] = global_section
        v2_config.save_global_config(cfg)
        print(f"\nEnabled {len(added)} component(s) in global config.")

    # Summary
    if added:
        print(f"\nAdded {len(added)} component(s):")
        for name in added:
            print(f"  + {name}")
    if skipped:
        print(f"\nSkipped {len(skipped)}:")
        for name in skipped:
            print(f"  - {name}")

    if added:
        print("\nRun 'hawk sync' to apply changes.")


def cmd_packages(args):
    """List installed packages."""
    from . import v2_config

    packages = v2_config.load_packages()
    if not packages:
        print("No packages installed.")
        print("Run 'hawk download <url>' to install a package.")
        return

    print("Packages:")
    for name, data in sorted(packages.items()):
        item_count = len(data.get("items", []))
        installed = data.get("installed", "unknown")
        url = data.get("url", "")
        commit = data.get("commit", "")[:7]
        print(f"  {name:<30} {item_count} items  installed {installed}")
        if url:
            suffix = f" @ {commit}" if commit else ""
            print(f"    {url}{suffix}")


def cmd_update(args):
    """Update packages from their git sources."""
    import shutil

    from .downloader import (
        add_items_to_registry, classify, get_head_commit, shallow_clone,
    )
    from .registry import Registry
    from . import v2_config

    packages = v2_config.load_packages()
    if not packages:
        print("No packages installed.")
        return

    registry = Registry(v2_config.get_registry_path())
    registry.ensure_dirs()

    # Filter to specific package if requested
    target = getattr(args, "package", None)
    if target:
        if target not in packages:
            print(f"Package not found: {target}")
            print(f"Installed: {', '.join(sorted(packages.keys()))}")
            sys.exit(1)
        to_update = {target: packages[target]}
    else:
        to_update = packages

    check_only = getattr(args, "check", False)
    force = getattr(args, "force", False)
    prune = getattr(args, "prune", False)

    any_changes = False
    up_to_date = []

    for pkg_name, pkg_data in sorted(to_update.items()):
        url = pkg_data.get("url", "")
        if not url:
            print(f"{pkg_name}: no URL recorded, skipping")
            continue

        print(f"\n{pkg_name}:")
        print(f"  Cloning {url}...")

        try:
            clone_dir = shallow_clone(url)
        except Exception as e:
            print(f"  Error cloning: {e}")
            continue

        try:
            new_commit = get_head_commit(clone_dir)
            old_commit = pkg_data.get("commit", "")

            if new_commit == old_commit and not force:
                up_to_date.append(pkg_name)
                print(f"  Up to date ({new_commit[:7]})")
                continue

            if check_only:
                print(f"  Update available: {old_commit[:7]} -> {new_commit[:7]}")
                any_changes = True
                continue

            # Re-classify and diff
            content = classify(clone_dir)
            old_items = {(i["type"], i["name"]): i.get("hash", "") for i in pkg_data.get("items", [])}
            registry_path = v2_config.get_registry_path()

            new_pkg_items = []
            added_count = 0
            updated_count = 0
            unchanged_count = 0

            for item in content.items:
                item_key = (item.component_type.value, item.name)

                # Add to registry (replace if exists)
                if registry.detect_clash(item.component_type, item.name):
                    registry.remove(item.component_type, item.name)

                try:
                    registry.add(item.component_type, item.name, item.source_path)
                except (FileNotFoundError, FileExistsError, OSError) as e:
                    print(f"  ! {item.name}: {e}")
                    continue

                item_path = registry_path / item.component_type.registry_dir / item.name
                new_hash = v2_config.hash_registry_item(item_path)

                new_pkg_items.append({
                    "type": item.component_type.value,
                    "name": item.name,
                    "hash": new_hash,
                })

                old_hash = old_items.get(item_key, "")
                if not old_hash:
                    print(f"  + {item.name} (added)")
                    added_count += 1
                elif old_hash != new_hash:
                    print(f"  ~ {item.name} (updated)")
                    updated_count += 1
                else:
                    print(f"  = {item.name} (unchanged)")
                    unchanged_count += 1

            # Check for items removed upstream
            new_keys = {(i["type"], i["name"]) for i in new_pkg_items}
            for (t, n), _ in old_items.items():
                if (t, n) not in new_keys:
                    if prune:
                        ct = ComponentType(t)
                        registry.remove(ct, n)
                        print(f"  - {n} (pruned)")
                    else:
                        print(f"  ? {n} (removed upstream, kept locally)")

            # Update packages.yaml
            v2_config.record_package(pkg_name, url, new_commit, new_pkg_items)

            parts = []
            if updated_count:
                parts.append(f"{updated_count} updated")
            if added_count:
                parts.append(f"{added_count} new")
            if parts:
                print(f"  {', '.join(parts)}")
                any_changes = True

        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

    if up_to_date:
        print(f"\nAll packages up to date: {', '.join(up_to_date)}")

    if any_changes and not check_only:
        from .v2_sync import sync_all
        print("\nSyncing...")
        sync_all(force=True)
        print("Done.")


def cmd_remove_package(args):
    """Remove a package and all its items."""
    from . import v2_config
    from .registry import Registry

    packages = v2_config.load_packages()
    pkg_name = args.name

    if pkg_name not in packages:
        print(f"Package not found: {pkg_name}")
        print(f"Installed: {', '.join(sorted(packages.keys())) or '(none)'}")
        sys.exit(1)

    pkg_data = packages[pkg_name]
    items = pkg_data.get("items", [])

    if not args.yes:
        print(f"Package: {pkg_name}")
        print(f"Items ({len(items)}):")
        for item in items:
            print(f"  [{item['type']}] {item['name']}")
        print(f"\nThis will remove all items from the registry and config.")
        confirm = input("Continue? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Cancelled.")
            return

    registry = Registry(v2_config.get_registry_path())

    # Remove items from registry
    removed = 0
    for item in items:
        try:
            ct = ComponentType(item["type"])
            if registry.remove(ct, item["name"]):
                removed += 1
                print(f"  Removed {item['type']}/{item['name']}")
        except (ValueError, KeyError):
            pass

    # Remove from enabled lists in global config
    cfg = v2_config.load_global_config()
    global_section = cfg.get("global", {})
    item_names_by_field: dict[str, set[str]] = {}
    for item in items:
        field = ComponentType(item["type"]).registry_dir
        item_names_by_field.setdefault(field, set()).add(item["name"])

    for field, names in item_names_by_field.items():
        enabled = global_section.get(field, [])
        if isinstance(enabled, list):
            new_enabled = [n for n in enabled if n not in names]
            if len(new_enabled) != len(enabled):
                global_section[field] = new_enabled

    cfg["global"] = global_section
    v2_config.save_global_config(cfg)

    # Remove from all registered directory configs
    dirs = v2_config.get_registered_directories()
    for dir_path_str in dirs:
        dir_cfg = v2_config.load_dir_config(Path(dir_path_str))
        if not dir_cfg:
            continue
        dir_changed = False
        for field, names in item_names_by_field.items():
            section = dir_cfg.get(field, {})
            if isinstance(section, dict):
                enabled = section.get("enabled", [])
                new_enabled = [n for n in enabled if n not in names]
                if len(new_enabled) != len(enabled):
                    section["enabled"] = new_enabled
                    dir_cfg[field] = section
                    dir_changed = True
        if dir_changed:
            v2_config.save_dir_config(Path(dir_path_str), dir_cfg)

    # Remove package entry
    v2_config.remove_package(pkg_name)

    print(f"\nRemoved package '{pkg_name}' ({removed} items)")

    # Sync
    from .v2_sync import sync_all
    print("Syncing...")
    sync_all(force=True)
    print("Done.")


def cmd_clean(args):
    """Remove all hawk-managed symlinks, MCP entries, and cache."""
    from .v2_sync import clean_all, clean_directory, clean_global, format_sync_results

    tools = [Tool(args.tool)] if args.tool else None

    if args.dir:
        project_dir = Path(args.dir).resolve()
        results = clean_directory(project_dir, tools=tools, dry_run=args.dry_run)
        formatted = format_sync_results({str(project_dir): results})
    elif args.globals_only:
        results = clean_global(tools=tools, dry_run=args.dry_run)
        formatted = format_sync_results({"global": results})
    else:
        all_results = clean_all(tools=tools, dry_run=args.dry_run)
        formatted = format_sync_results(all_results)

    if args.dry_run:
        print("Dry run (no changes applied):")
    print(formatted or "  No changes.")

    if not args.dry_run:
        print("\nAll hawk-managed items removed from tool configs.")


def cmd_config(args):
    """Open interactive config editor."""
    from .v2_interactive.config_editor import run_config_editor

    run_config_editor()


def cmd_migrate(args):
    """Migrate v1 config to v2."""
    from .migration import run_migration

    success, msg = run_migration(backup=not args.no_backup)
    if success:
        print(f"Migration successful: {msg}")
        print("\nNext steps:")
        print("  hawk status   # Review the migrated config")
        print("  hawk sync     # Sync to tools")
    else:
        print(f"Migration skipped: {msg}")


def cmd_new(args):
    """Create a new component from a template."""
    from . import v2_config
    from .events import EVENTS
    from .templates import (
        AGENT_TEMPLATE, COMMAND_PROMPT_TEMPLATE, PROMPT_TEMPLATE,
        get_template,
    )

    from .registry import _validate_name

    registry_path = v2_config.get_registry_path()
    comp_type = args.type
    name = args.name
    event = getattr(args, "event", "pre_tool_use")
    lang = getattr(args, "lang", ".py")

    try:
        _validate_name(name)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if not lang.startswith("."):
        lang = f".{lang}"

    if comp_type == "hook":
        # Script hook with hawk-hook metadata
        template = get_template(lang)
        if not template:
            print(f"Error: No template for extension '{lang}'")
            print("Supported: .py, .sh, .js, .ts")
            sys.exit(1)

        if event not in EVENTS:
            print(f"Error: Unknown event '{event}'")
            print(f"Events: {', '.join(EVENTS.keys())}")
            sys.exit(1)

        # Ensure name has the right extension
        if not name.endswith(lang):
            name = f"{name}{lang}"

        # Inject hawk-hook metadata into template
        if lang in (".py", ".sh"):
            # Insert hawk-hook headers after shebang
            lines = template.split("\n")
            insert_idx = 1  # After shebang
            hawk_lines = [
                f"# hawk-hook: events={event}",
            ]
            for i, hl in enumerate(hawk_lines):
                lines.insert(insert_idx + i, hl)
            content = "\n".join(lines)
        elif lang in (".js", ".ts"):
            lines = template.split("\n")
            insert_idx = 1
            hawk_lines = [
                f"// hawk-hook: events={event}",
            ]
            for i, hl in enumerate(hawk_lines):
                lines.insert(insert_idx + i, hl)
            content = "\n".join(lines)
        else:
            content = template

        dest = registry_path / "hooks" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not args.force:
            print(f"Error: {dest} already exists. Use --force to overwrite.")
            sys.exit(1)
        dest.write_text(content)
        dest.chmod(0o755)

        _print(f"[green]+[/green] Created hook: {dest}")
        _print(f"  Event: {event}")

    elif comp_type == "command":
        if not name.endswith(".md"):
            name = f"{name}.md"

        content = COMMAND_PROMPT_TEMPLATE.format(
            name=name.replace(".md", ""),
            description="Your command description",
        )

        dest = registry_path / "commands" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not args.force:
            print(f"Error: {dest} already exists. Use --force to overwrite.")
            sys.exit(1)
        dest.write_text(content)

        _print(f"[green]+[/green] Created command: {dest}")

    elif comp_type == "agent":
        if not name.endswith(".md"):
            name = f"{name}.md"

        content = AGENT_TEMPLATE.format(
            name=name.replace(".md", ""),
            description="Your agent description",
        )

        dest = registry_path / "agents" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not args.force:
            print(f"Error: {dest} already exists. Use --force to overwrite.")
            sys.exit(1)
        dest.write_text(content)

        _print(f"[green]+[/green] Created agent: {dest}")

    elif comp_type == "prompt-hook":
        if not name.endswith(".prompt.json"):
            name = f"{name}.prompt.json"

        if event not in EVENTS:
            print(f"Error: Unknown event '{event}'")
            sys.exit(1)

        import json
        prompt_data = json.loads(PROMPT_TEMPLATE)
        prompt_data["hawk-hook"] = {"events": [event]}
        content = json.dumps(prompt_data, indent=2) + "\n"

        dest = registry_path / "hooks" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not args.force:
            print(f"Error: {dest} already exists. Use --force to overwrite.")
            sys.exit(1)
        dest.write_text(content)

        _print(f"[green]+[/green] Created prompt hook: {dest}")
        _print(f"  Event: {event}")

    else:
        print(f"Error: Unknown type '{comp_type}'")
        sys.exit(1)

    # prompt-hook creates files in hooks/ dir, so the add type is "hook"
    add_type = "hook" if comp_type == "prompt-hook" else comp_type
    _print(f"\n[dim]Run[/dim] [cyan]hawk add {add_type} {dest}[/cyan] [dim]to register, or edit the file first.[/dim]")


def cmd_deps(args):
    """Install dependencies for all hooks in the registry."""
    import subprocess
    from . import v2_config
    from .hook_meta import parse_hook_meta

    registry_path = v2_config.get_registry_path()
    hooks_dir = registry_path / "hooks"

    if not hooks_dir.exists():
        print("No hooks directory found.")
        return

    # Scan all hooks for deps
    all_deps: set[str] = set()
    for hook_file in sorted(hooks_dir.iterdir()):
        if hook_file.is_file():
            meta = parse_hook_meta(hook_file)
            if meta.deps:
                for dep in meta.deps.split(","):
                    dep = dep.strip()
                    if dep:
                        all_deps.add(dep)

    if not all_deps:
        print("No dependencies found in hook metadata.")
        return

    print(f"Found {len(all_deps)} dependency(ies): {', '.join(sorted(all_deps))}")

    # Create/update venv
    venv_dir = v2_config.get_config_dir() / ".venv"
    venv_python = venv_dir / "bin" / "python"

    if not venv_dir.exists():
        print(f"Creating venv at {venv_dir}...")
        try:
            subprocess.run(
                ["python3", "-m", "venv", str(venv_dir)],
                check=True, capture_output=True, text=True, timeout=60,
            )
        except subprocess.CalledProcessError as e:
            print(f"Error creating venv: {e.stderr}")
            sys.exit(1)

    # Install deps
    print(f"Installing: {', '.join(sorted(all_deps))}...")
    try:
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--quiet"] + sorted(all_deps),
            check=True, capture_output=True, text=True, timeout=300,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error installing: {e.stderr}")
        sys.exit(1)

    print(f"\nInstalled {len(all_deps)} package(s) into {venv_dir}")
    print("Runners will use venv Python automatically on next sync.")


def build_parser() -> argparse.ArgumentParser:
    """Build the v2 CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="hawk",
        description="hawk-hooks: Multi-agent CLI package manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"hawk-hooks {__version__}")
    parser.add_argument("--dir", dest="main_dir", help="Scope TUI to specific directory")

    subparsers = parser.add_subparsers(dest="command")

    # init
    init_p = subparsers.add_parser("init", help="Initialize directory for hawk management")
    init_p.add_argument("--profile", help="Profile to use")
    init_p.add_argument("--dir", help="Directory to initialize (default: cwd)")
    init_p.add_argument("--force", action="store_true", help="Reinitialize if exists")
    init_p.set_defaults(func=cmd_init)

    # sync
    sync_p = subparsers.add_parser("sync", help="Sync components to tools")
    sync_p.add_argument("--dir", help="Sync specific directory")
    sync_p.add_argument("--tool", choices=[t.value for t in Tool], help="Sync specific tool")
    sync_p.add_argument("--dry-run", action="store_true", help="Show what would change")
    sync_p.add_argument("--force", action="store_true", help="Bypass cache, sync unconditionally")
    sync_p.add_argument("--global", dest="globals_only", action="store_true", help="Sync global only")
    sync_p.set_defaults(func=cmd_sync)

    # status
    status_p = subparsers.add_parser("status", help="Show current status")
    status_p.add_argument("--dir", help="Show status for specific directory")
    status_p.set_defaults(func=cmd_status)

    # add
    add_p = subparsers.add_parser("add", help="Add component to registry")
    add_p.add_argument("type", nargs="?", default=None,
                       help="Component type: skill, hook, command, agent, mcp, prompt (auto-detected if omitted)")
    add_p.add_argument("path", nargs="?", help="Path to component (reads stdin if omitted)")
    add_p.add_argument("--type", dest="type_flag",
                       choices=[ct.value for ct in ComponentType],
                       help="Component type (alternative to positional)")
    add_p.add_argument("--name", help="Name in registry (default: filename or auto-generated)")
    add_p.add_argument("--force", action="store_true", help="Replace existing")
    add_p.add_argument("--enable", action="store_true", default=True,
                       help="Enable in global config (default)")
    add_p.add_argument("--no-enable", dest="enable", action="store_false",
                       help="Don't enable in global config")
    add_p.set_defaults(func=cmd_add)

    # remove
    rm_p = subparsers.add_parser("remove", help="Remove component from registry")
    rm_p.add_argument("type", choices=[ct.value for ct in ComponentType], help="Component type")
    rm_p.add_argument("name", help="Component name")
    rm_p.set_defaults(func=cmd_remove)

    # list
    list_p = subparsers.add_parser("list", help="List registry contents")
    list_p.add_argument("type", nargs="?", choices=[ct.value for ct in ComponentType], help="Filter by type")
    list_p.set_defaults(func=cmd_list)

    # profile
    profile_p = subparsers.add_parser("profile", help="Profile management")
    profile_sub = profile_p.add_subparsers(dest="profile_cmd")

    profile_list_p = profile_sub.add_parser("list", help="List profiles")
    profile_list_p.set_defaults(func=cmd_profile_list)

    profile_show_p = profile_sub.add_parser("show", help="Show profile details")
    profile_show_p.add_argument("name", help="Profile name")
    profile_show_p.set_defaults(func=cmd_profile_show)

    # scan
    scan_p = subparsers.add_parser("scan", help="Scan directory for components to import")
    scan_p.add_argument("path", nargs="?", default=".", help="Directory to scan (default: cwd)")
    scan_p.add_argument("--all", action="store_true", help="Import all found components without prompting")
    scan_p.add_argument("--replace", action="store_true", help="Replace existing registry entries")
    scan_p.add_argument("--depth", type=int, default=5, help="Max scan depth (default: 5)")
    scan_p.add_argument("--no-enable", action="store_true", help="Add to registry without enabling in config")
    scan_p.set_defaults(func=cmd_scan)

    # download
    dl_p = subparsers.add_parser("download", help="Download components from git URL")
    dl_p.add_argument("url", help="Git URL to clone")
    dl_p.add_argument("--all", action="store_true", help="Add all components without prompting")
    dl_p.add_argument("--replace", action="store_true", help="Replace existing registry entries")
    dl_p.add_argument("--name", help="Package name (default: derived from URL)")
    dl_p.set_defaults(func=cmd_download)

    # packages
    packages_p = subparsers.add_parser("packages", help="List installed packages")
    packages_p.set_defaults(func=cmd_packages)

    # update
    update_p = subparsers.add_parser("update", help="Update packages from git")
    update_p.add_argument("package", nargs="?", help="Specific package to update")
    update_p.add_argument("--check", action="store_true", help="Check for updates without applying")
    update_p.add_argument("--force", action="store_true", help="Update even if commit unchanged")
    update_p.add_argument("--prune", action="store_true", help="Remove items deleted upstream")
    update_p.set_defaults(func=cmd_update)

    # remove-package
    rmpkg_p = subparsers.add_parser("remove-package", help="Remove a package and all its items")
    rmpkg_p.add_argument("name", help="Package name")
    rmpkg_p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    rmpkg_p.set_defaults(func=cmd_remove_package)

    # projects
    projects_p = subparsers.add_parser("projects", help="Interactive projects tree view")
    projects_p.set_defaults(func=cmd_projects)

    # clean
    clean_p = subparsers.add_parser("clean", help="Remove all hawk-managed items from tools")
    clean_p.add_argument("--dir", help="Clean specific directory only")
    clean_p.add_argument("--tool", choices=[t.value for t in Tool], help="Clean specific tool")
    clean_p.add_argument("--dry-run", action="store_true", help="Show what would be removed")
    clean_p.add_argument("--global", dest="globals_only", action="store_true", help="Clean global only")
    clean_p.set_defaults(func=cmd_clean)

    # config
    config_p = subparsers.add_parser("config", help="Interactive settings editor")
    config_p.set_defaults(func=cmd_config)

    # new
    new_p = subparsers.add_parser("new", help="Create a new component from template")
    new_p.add_argument("type", choices=["hook", "command", "agent", "prompt-hook"],
                       help="Component type")
    new_p.add_argument("name", help="Component name")
    new_p.add_argument("--event", default="pre_tool_use", help="Target event (for hooks, default: pre_tool_use)")
    new_p.add_argument("--lang", default=".py", help="Language extension (for hooks, default: .py)")
    new_p.add_argument("--force", action="store_true", help="Overwrite existing file")
    new_p.set_defaults(func=cmd_new)

    # deps
    deps_p = subparsers.add_parser("deps", help="Install dependencies for hooks")
    deps_p.set_defaults(func=cmd_deps)

    # migrate
    migrate_p = subparsers.add_parser("migrate", help="Migrate v1 config to v2")
    migrate_p.add_argument("--no-backup", action="store_true", help="Skip backup of v1 config")
    migrate_p.set_defaults(func=cmd_migrate)

    return parser


def main_v2():
    """v2 main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Warn if top-level --dir used with a subcommand (ambiguous)
    if args.command is not None and args.main_dir is not None:
        print(f"Warning: --dir before subcommand scopes the TUI, not '{args.command}'.")
        print(f"  Use: hawk {args.command} --dir {args.main_dir}")
        sys.exit(1)

    try:
        if args.command is None:
            try:
                from .v2_interactive import v2_interactive_menu
                v2_interactive_menu(scope_dir=args.main_dir)
            except ImportError:
                parser.print_help()
        elif hasattr(args, "func"):
            args.func(args)
        else:
            parser.print_help()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
