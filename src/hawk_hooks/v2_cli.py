"""v2 CLI interface for hawk-hooks.

New command structure for multi-tool management.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .types import ComponentType, Tool


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


def cmd_add(args):
    """Add a component to the registry."""
    from .registry import Registry
    from . import v2_config

    registry = Registry(v2_config.get_registry_path())
    registry.ensure_dirs()

    component_type = ComponentType(args.type)
    source = Path(args.path).resolve()
    name = args.name or source.name

    if registry.detect_clash(component_type, name):
        if not args.force:
            print(f"Error: {component_type}/{name} already exists. Use --force to replace.")
            sys.exit(1)
        registry.remove(component_type, name)

    try:
        path = registry.add(component_type, name, source)
        print(f"Added {component_type}/{name}")
        print(f"  -> {path}")
        print(f"\nTo activate: add '{name}' to your config's {component_type.registry_dir} list")
        print(f"  or run: hawk sync")
    except (FileNotFoundError, FileExistsError) as e:
        print(f"Error: {e}")
        sys.exit(1)


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


def cmd_download(args):
    """Download components from a git URL."""
    import shutil

    from .downloader import add_items_to_registry, check_clashes, classify, shallow_clone
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
            selected_items = _interactive_select_items(content.items)
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

        # 6. Summary
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


def _interactive_select_items(items):
    """Show interactive multi-select for download items. Returns selected items."""
    from simple_term_menu import TerminalMenu

    options = [f"[{item.component_type.value}] {item.name}" for item in items]
    menu = TerminalMenu(
        options,
        title="\nSelect components to add (space to toggle, enter to confirm):",
        multi_select=True,
        preselected_entries=list(range(len(options))),
        multi_select_select_on_accept=False,
        menu_cursor="\u276f ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_cyan", "bold"),
        quit_keys=("q",),
    )
    result = menu.show()
    if result is None:
        return []
    indices = list(result) if isinstance(result, tuple) else [result]
    return [items[i] for i in indices]


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
    add_p.add_argument("type", choices=[ct.value for ct in ComponentType], help="Component type")
    add_p.add_argument("path", help="Path to component file or directory")
    add_p.add_argument("--name", help="Name in registry (default: filename)")
    add_p.add_argument("--force", action="store_true", help="Replace existing")
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

    # download
    dl_p = subparsers.add_parser("download", help="Download components from git URL")
    dl_p.add_argument("url", help="Git URL to clone")
    dl_p.add_argument("--all", action="store_true", help="Add all components without prompting")
    dl_p.add_argument("--replace", action="store_true", help="Replace existing registry entries")
    dl_p.set_defaults(func=cmd_download)

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

    # migrate
    migrate_p = subparsers.add_parser("migrate", help="Migrate v1 config to v2")
    migrate_p.add_argument("--no-backup", action="store_true", help="Skip backup of v1 config")
    migrate_p.set_defaults(func=cmd_migrate)

    return parser


def main_v2():
    """v2 main entry point."""
    parser = build_parser()
    args = parser.parse_args()

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
