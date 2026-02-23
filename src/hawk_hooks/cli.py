"""CLI interface for hawk-hooks."""

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
    from .v2_sync import format_sync_results, sync_directory

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
    total_unlinked = sum(len(r.unlinked) for r in results)
    total_skipped = sum(len(r.skipped) for r in results)
    total_errors = sum(len(r.errors) for r in results)

    if total_linked or total_unlinked or total_skipped or total_errors:
        parts: list[str] = []
        if total_linked:
            parts.append(f"+{total_linked} linked")
        if total_unlinked:
            parts.append(f"-{total_unlinked} unlinked")
        if total_skipped:
            parts.append(f"~{total_skipped} skipped")
        if total_errors:
            parts.append(f"!{total_errors} errors")
        print(f"\nSync summary: {', '.join(parts)}")
        print(format_sync_results({str(project_dir): results}, verbose=getattr(args, "verbose", False)))
    else:
        print("\nSync summary: no changes")

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
        formatted = format_sync_results({str(project_dir): results}, verbose=args.verbose)
    elif args.globals_only:
        results = sync_global(tools=tools, dry_run=args.dry_run, force=force)
        formatted = format_sync_results({"global": results}, verbose=args.verbose)
    else:
        all_results = sync_all(tools=tools, dry_run=args.dry_run, force=force)
        formatted = format_sync_results(all_results, verbose=args.verbose)

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
            for field in ["skills", "hooks", "prompts", "agents", "mcp"]:
                g_items = global_section.get(field, [])
                if g_items:
                    print(f"  global:  {', '.join(g_items)}")
                    break
            # Show each layer's contributions
            for chain_dir, chain_config in config_chain:
                parts: list[str] = []
                for field in ["skills", "hooks", "prompts", "agents", "mcp"]:
                    section = chain_config.get(field, {})
                    if field == "prompts" and "commands" in chain_config:
                        section = chain_config.get("commands", section)
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
            from .scope_resolution import build_resolver_dir_chain

            dir_chain = build_resolver_dir_chain(project_dir, cfg=cfg)
            resolved = resolve(cfg, dir_chain=dir_chain)
        else:
            from .scope_resolution import build_resolver_dir_chain

            dir_chain = build_resolver_dir_chain(project_dir, cfg=cfg)
            resolved = resolve(cfg, dir_chain=dir_chain) if dir_chain else resolve(cfg)

        print(f"\nResolved for {project_dir}:")
    else:
        resolved = resolve(cfg)
        print(f"\nGlobal active:")
    for field in ["skills", "hooks", "prompts", "agents", "mcp"]:
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
        return ComponentType.PROMPT
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
                return ComponentType.PROMPT
        except OSError:
            pass

    return None


def _ask_component_type() -> ComponentType | None:
    """Interactively ask the user what type of component this is."""
    type_options = [
        ("skill", "Skill — reusable instructions / knowledge"),
        ("prompt", "Prompt — slash prompt / command"),
        ("agent", "Agent — autonomous agent definition"),
        ("hook", "Hook — event-triggered script"),
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
        if args.type == "command":
            component_type = ComponentType.PROMPT
        else:
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
    if args.type == "command":
        component_type = ComponentType.PROMPT
    else:
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
        if args.type == "command":
            component_type = ComponentType.PROMPT
        else:
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


def _build_pkg_items(items, registry, package_name: str = "", added_keys: set[str] | None = None):
    """Build package item list with hashes for selected items present in registry."""
    from . import v2_config

    pkg_items = []
    added_keys = added_keys or set()
    owner_map: dict[tuple[str, str], str] = {}
    if package_name:
        for owner_pkg, pkg_data in v2_config.load_packages().items():
            for pkg_item in pkg_data.get("items", []):
                item_type = pkg_item.get("type")
                item_name = pkg_item.get("name")
                if item_type and item_name:
                    owner_map.setdefault((item_type, item_name), owner_pkg)

    seen: set[tuple] = set()
    for item in items:
        item_key = (item.component_type, item.name)
        if item_key in seen:
            continue
        seen.add(item_key)

        item_key_str = f"{item.component_type}/{item.name}"
        item_path = registry.get_path(item.component_type, item.name)
        if item_path is None:
            continue

        if package_name:
            owner = owner_map.get((item.component_type.value, item.name))
            if owner and owner != package_name:
                continue

            # For unowned clashes not added this run, only claim when scanned
            # source content matches current registry content.
            if not owner and item_key_str not in added_keys:
                source_path = item.source_path
                if source_path is None or not source_path.exists():
                    continue
                source_hash = v2_config.hash_registry_item(source_path)
                registry_hash = v2_config.hash_registry_item(item_path)
                if source_hash != registry_hash:
                    continue

        item_hash = v2_config.hash_registry_item(item_path)
        pkg_items.append({
            "type": item.component_type.value,
            "name": item.name,
            "hash": item_hash,
        })
    return pkg_items


def _package_source_type(pkg_data: dict) -> str:
    """Infer package source type from package metadata."""
    if pkg_data.get("url"):
        return "git"
    if pkg_data.get("path"):
        return "local"
    return "manual"


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
        # Extract repo name from URL for synthetic hook naming
        repo_name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        content = classify(clone_dir, repo_name=repo_name)
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
            pkg = content.package_meta.name if content.package_meta else ""
            selected_items, action = _interactive_select_items(
                content.items, registry, package_name=pkg,
                packages=content.packages,
            )
            if not selected_items or action == "cancel":
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
            pkg_items = _build_pkg_items(selected_items, registry, pkg_name, set(added))
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

        if added:
            print("\nRun 'hawk sync' to apply changes.")
    finally:
        # Clean up temp dir
        shutil.rmtree(clone_dir, ignore_errors=True)


def _view_source_in_terminal(path: Path) -> None:
    """View a source file with syntax highlighting, piped through less."""
    import subprocess
    from io import StringIO
    from rich.console import Console as RichConsole
    from rich.syntax import Syntax

    LEXERS = {
        ".py": "python", ".sh": "bash", ".js": "javascript", ".ts": "typescript",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".md": "markdown",
        ".toml": "toml", ".mdc": "markdown",
    }

    try:
        content = path.read_text()
    except OSError:
        print(f"Cannot read: {path}")
        input("Press Enter to go back...")
        return

    buf = StringIO()
    rc = RichConsole(file=buf, force_terminal=True)
    rc.print(f"[bold]{path.name}[/bold]")
    rc.print("[dim]\u2500" * 50 + "[/dim]\n")
    lexer = LEXERS.get(path.suffix.lower(), "text")
    rc.print(Syntax(content, lexer, theme="monokai", line_numbers=True))
    rendered = buf.getvalue()

    try:
        subprocess.run(["less", "-R"], input=rendered, text=True, check=False)
    except FileNotFoundError:
        print(rendered)
        input("Press Enter to go back...")


def _interactive_select_items(items, registry=None, package_name: str = "",
                              packages: list | None = None):
    """Show interactive multi-select for download/scan items.

    Uses Rich Live + readchar for a scrollable list that works in small panes.
    Items are grouped by package (if multiple) then by component type,
    with collapsible section headers.
    Returns selected items.
    """
    import os
    import readchar
    from rich.console import Console
    from rich.live import Live
    from rich.text import Text
    from .types import ComponentType

    console = Console(highlight=False)

    # ── Row types ──
    ROW_PKG = "pkg"        # top-level package header (collapsible)
    ROW_TYPE = "type"      # component type header (collapsible)
    ROW_ITEM = "item"      # selectable item

    TYPE_ORDER = [
        ComponentType.SKILL, ComponentType.HOOK, ComponentType.PROMPT,
        ComponentType.AGENT, ComponentType.MCP,
    ]

    # ── Group items by package, then by component type ──
    # Determine package names present in items
    pkg_names: list[str] = []
    seen_pkgs: set[str] = set()
    for item in items:
        pkg = getattr(item, "package", "") or ""
        if pkg not in seen_pkgs:
            seen_pkgs.add(pkg)
            pkg_names.append(pkg)

    multi_pkg = len(pkg_names) > 1 or (len(pkg_names) == 1 and pkg_names[0] != "")

    # Build nested structure: packages → type groups → items
    # Each package: {"name": str, "collapsed": bool, "type_groups": [...]}
    # Each type_group: {"type": ComponentType, "collapsed": bool, "items": [(orig_idx, item)]}
    pkg_sections: list[dict] = []
    for pkg in pkg_names:
        pkg_items = [(i, item) for i, item in enumerate(items)
                     if (getattr(item, "package", "") or "") == pkg]
        if not pkg_items:
            continue

        type_groups = []
        for ct in TYPE_ORDER:
            ct_items = [(i, item) for i, item in pkg_items if item.component_type == ct]
            if ct_items:
                type_groups.append({"type": ct, "collapsed": False, "items": ct_items})
        # Catch types not in TYPE_ORDER
        seen_ct = set(TYPE_ORDER)
        for ct in sorted(set(item.component_type for _, item in pkg_items) - seen_ct,
                         key=lambda x: x.value):
            ct_items = [(i, item) for i, item in pkg_items if item.component_type == ct]
            if ct_items:
                type_groups.append({"type": ct, "collapsed": False, "items": ct_items})

        display_name = pkg if pkg else (package_name or "Components")
        pkg_sections.append({
            "name": display_name,
            "collapsed": False,
            "type_groups": type_groups,
        })

    # Pre-select items not already registered
    selected: set[int] = set()
    for i, item in enumerate(items):
        exists = registry and registry.has(item.component_type, item.name)
        if not exists:
            selected.add(i)

    def _build_rows():
        """Build flat row list: (row_type, section_idx, group_idx, orig_idx)."""
        rows = []
        for si, section in enumerate(pkg_sections):
            if multi_pkg:
                rows.append((ROW_PKG, si, -1, -1))
            if multi_pkg and section["collapsed"]:
                continue
            for gi, tg in enumerate(section["type_groups"]):
                rows.append((ROW_TYPE, si, gi, -1))
                if not tg["collapsed"]:
                    for orig_idx, _ in tg["items"]:
                        rows.append((ROW_ITEM, si, gi, orig_idx))
        return rows

    rows = _build_rows()
    cursor = 0
    scroll_offset = 0

    def _get_max_visible():
        try:
            lines = os.get_terminal_size().lines
        except OSError:
            lines = 24
        return max(3, lines - 6)

    def _type_sel_count(tg):
        tot = len(tg["items"])
        sel = sum(1 for idx, _ in tg["items"] if idx in selected)
        return sel, tot

    def _pkg_sel_count(section):
        sel = tot = 0
        for tg in section["type_groups"]:
            s, t = _type_sel_count(tg)
            sel += s
            tot += t
        return sel, tot

    def _build_display():
        nonlocal scroll_offset
        lines = []
        max_vis = _get_max_visible()
        total_rows = len(rows)

        sel_count = len(selected)
        total_items = len(items)
        title = package_name if (package_name and not multi_pkg) else "Select components"
        lines.append(f"[bold cyan]{title}[/bold cyan]  ({sel_count}/{total_items} selected)")
        lines.append("[dim]\u2500" * 50 + "[/dim]")

        if total_rows == 0:
            vis_start, vis_end = 0, 0
        else:
            c = max(0, min(cursor, total_rows - 1))
            if c < scroll_offset:
                scroll_offset = c
            elif c >= scroll_offset + max_vis:
                scroll_offset = c - max_vis + 1
            scroll_offset = max(0, min(scroll_offset, total_rows - 1))
            vis_start = scroll_offset
            vis_end = min(scroll_offset + max_vis, total_rows)

        if vis_start > 0:
            lines.append(f"[dim]  \u2191 {vis_start} more[/dim]")

        for ri in range(vis_start, vis_end):
            row_type, si, gi, orig_idx = rows[ri]
            is_cur = ri == cursor
            prefix = "[cyan]\u276f[/cyan] " if is_cur else "  "

            if row_type == ROW_PKG:
                section = pkg_sections[si]
                sel, tot = _pkg_sel_count(section)
                arrow = "\u25b6" if section["collapsed"] else "\u25bc"
                style = "[bold]" if is_cur else ""
                end = "[/bold]" if is_cur else ""
                count_style = "green" if sel > 0 else "dim"
                lines.append(
                    f"{prefix}{style}\U0001f4e6 {section['name']}  "
                    f"[{count_style}]({sel}/{tot})[/{count_style}]  {arrow}{end}"
                )

            elif row_type == ROW_TYPE:
                tg = pkg_sections[si]["type_groups"][gi]
                ct = tg["type"]
                sel, tot = _type_sel_count(tg)
                arrow = "\u25b6" if tg["collapsed"] else "\u25bc"
                style = "[bold]" if is_cur else ""
                end = "[/bold]" if is_cur else ""
                count_style = "green" if sel > 0 else "dim"
                indent = "  " if multi_pkg else ""
                lines.append(
                    f"{prefix}{indent}{style}{ct.value}s  "
                    f"[{count_style}]({sel}/{tot})[/{count_style}]  {arrow}{end}"
                )

            elif row_type == ROW_ITEM:
                item = items[orig_idx]
                is_sel = orig_idx in selected
                exists = registry and registry.has(item.component_type, item.name)
                mark = "[green]\u25cf[/green]" if is_sel else "[dim]\u25cb[/dim]"
                style = "[bold]" if is_cur else ("[dim]" if not is_sel else "")
                end = "[/bold]" if is_cur else ("[/dim]" if not is_sel else "")
                hint = "  [dim](already registered)[/dim]" if exists else ""
                indent = "    " if multi_pkg else "  "
                lines.append(f"{prefix}{indent}{mark} {style}{item.name}{end}{hint}")

        if vis_end < total_rows:
            remaining = total_rows - vis_end
            lines.append(f"[dim]  \u2193 {remaining} more[/dim]")

        # Action row
        lines.append("")
        actions = ["Save"]
        action_parts = []
        for ai, label in enumerate(actions):
            if ai == action_idx:
                action_parts.append(f"[bold cyan][ {label} ][/bold cyan]")
            else:
                action_parts.append(f"[dim]  {label}  [/dim]")
        lines.append("  ".join(action_parts))

        lines.append("")
        lines.append("[dim]Space: toggle  a: all  n: none  v: view  o: open  Enter: confirm  q: quit[/dim]")
        return "\n".join(lines)

    action_idx = 0
    _ACTION_KEYS = ["add"]

    with Live("", console=console, refresh_per_second=15, transient=True) as live:
        live.update(Text.from_markup(_build_display()))
        while True:
            try:
                key = readchar.readkey()
            except (KeyboardInterrupt, EOFError):
                return [], "cancel"

            total_rows = len(rows)
            if not total_rows:
                if key in ("q", readchar.key.ESC, "\x1b", readchar.key.CTRL_C):
                    return [], "cancel"
                continue

            if key in (readchar.key.UP, "k"):
                cursor = (cursor - 1) % total_rows
            elif key in (readchar.key.DOWN, "j"):
                cursor = (cursor + 1) % total_rows

            elif key in ("\r", "\n", readchar.key.ENTER):
                break

            elif key == " ":
                row_type, si, gi, orig_idx = rows[cursor]
                if row_type == ROW_PKG:
                    pkg_sections[si]["collapsed"] = not pkg_sections[si]["collapsed"]
                    rows = _build_rows()
                    cursor = min(cursor, len(rows) - 1)
                elif row_type == ROW_TYPE:
                    tg = pkg_sections[si]["type_groups"][gi]
                    tg["collapsed"] = not tg["collapsed"]
                    rows = _build_rows()
                    cursor = min(cursor, len(rows) - 1)
                elif row_type == ROW_ITEM:
                    if orig_idx in selected:
                        selected.discard(orig_idx)
                    else:
                        selected.add(orig_idx)

            elif key == "a":
                selected = set(range(len(items)))
            elif key == "n":
                selected.clear()

            elif key == "v":
                row_type, _si, _gi, orig_idx = rows[cursor]
                if row_type == ROW_ITEM:
                    item = items[orig_idx]
                    if item.source_path and item.source_path.is_file():
                        live.stop()
                        _view_source_in_terminal(item.source_path)
                        live.start()

            elif key == "o":
                row_type, _si, _gi, orig_idx = rows[cursor]
                if row_type == ROW_ITEM:
                    item = items[orig_idx]
                    if item.source_path and item.source_path.exists():
                        import subprocess
                        target = item.source_path
                        if sys.platform == "darwin":
                            subprocess.run(
                                ["open", "-R", str(target)] if target.is_file()
                                else ["open", str(target)],
                                check=False,
                            )
                        elif sys.platform == "linux":
                            subprocess.run(
                                ["xdg-open", str(target.parent if target.is_file() else target)],
                                check=False,
                            )

            elif key in ("q", readchar.key.ESC, "\x1b", readchar.key.CTRL_C):
                return [], "cancel"

            live.update(Text.from_markup(_build_display()))

    return [items[i] for i in sorted(selected)], _ACTION_KEYS[action_idx]


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
        pkg = content.package_meta.name if content.package_meta else ""
        selected_items, action = _interactive_select_items(
            content.items, registry, package_name=pkg,
            packages=content.packages,
        )
        if not selected_items or action == "cancel":
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

    if not items_to_add and not content.packages:
        print("\nNo new components to add.")
        return

    # Reject package source-type conflicts up front (before mutating registry)
    if content.packages:
        existing_packages = v2_config.load_packages()
        selected_pkg_names = {
            item.package or (content.package_meta.name if content.package_meta else "")
            for item in selected_items
        }
        for pkg_name in sorted(n for n in selected_pkg_names if n):
            existing = existing_packages.get(pkg_name)
            if not existing:
                continue
            existing_source = _package_source_type(existing)
            if existing_source != "local":
                print(
                    f"Package '{pkg_name}' already exists with source [{existing_source}], "
                    "refusing to replace source metadata."
                )
                print(f"Fix: hawk remove-package {pkg_name} && hawk scan {scan_path} --all")
                print(
                    f"Fix: hawk remove-package {pkg_name} && "
                    f"hawk download <url> --name {pkg_name}"
                )
                sys.exit(1)

    if items_to_add:
        added, skipped = add_items_to_registry(items_to_add, registry, replace=replace)
    else:
        print("\nNo new components to add.")
        added, skipped = [], []

    # Record packages — group items by their per-item .package tag
    if content.packages:
        items_by_pkg: dict[str, list] = {}
        for item in selected_items:
            pkg_name = item.package or (
                content.package_meta.name if content.package_meta else ""
            )
            if pkg_name:
                items_by_pkg.setdefault(pkg_name, []).append(item)
        pkg_meta_by_name = {p.name: p for p in content.packages}
        for pkg_name, pkg_item_list in items_by_pkg.items():
            pkg_items = _build_pkg_items(pkg_item_list, registry, pkg_name, set(added))
            if pkg_items:
                v2_config.record_package(
                    pkg_name, "", "", pkg_items,
                    path=str(scan_path),
                )
                meta = pkg_meta_by_name.get(pkg_name)
                _print(f"\n[green]Package:[/green] {pkg_name}")
                if meta and meta.description:
                    _print(f"  {meta.description}")

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
        source_type = _package_source_type(data)
        url = data.get("url", "")
        path = data.get("path", "")
        commit = data.get("commit", "")[:7]
        print(f"  [{source_type}] {name:<30} {item_count} items  installed {installed}")
        if source_type == "git" and url:
            suffix = f" @ {commit}" if commit else ""
            print(f"    {url}{suffix}")
        elif source_type == "local" and path:
            print(f"    {path}")


def cmd_update(args):
    """Update packages from their git sources."""
    from .package_service import (
        PackageNotFoundError,
        PackageUpdateFailedError,
        update_packages,
    )

    try:
        update_packages(
            package=getattr(args, "package", None),
            check=bool(getattr(args, "check", False)),
            force=bool(getattr(args, "force", False)),
            prune=bool(getattr(args, "prune", False)),
            sync_on_change=True,
            log=print,
        )
    except PackageNotFoundError as e:
        print(f"Package not found: {e.package_name}")
        print(f"Installed: {', '.join(e.installed)}")
        sys.exit(1)
    except PackageUpdateFailedError:
        sys.exit(1)


def cmd_remove_package(args):
    """Remove a package and all its items."""
    from . import v2_config
    from .package_service import PackageNotFoundError, remove_package

    packages = v2_config.load_packages()
    pkg_name = args.name
    pkg_data = packages.get(pkg_name)

    if pkg_data is None:
        print(f"Package not found: {pkg_name}")
        print(f"Installed: {', '.join(sorted(packages.keys())) or '(none)'}")
        sys.exit(1)

    items = pkg_data.get("items", [])

    if not args.yes:
        print(f"Package: {pkg_name}")
        print(f"Items ({len(items)}):")
        for item in items:
            print(f"  [{item['type']}] {item['name']}")
        print("\nThis will remove all items from the registry and config.")
        confirm = input("Continue? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Cancelled.")
            return

    try:
        remove_package(pkg_name, sync_after=True, log=print)
    except PackageNotFoundError as e:
        print(f"Package not found: {e.package_name}")
        print(f"Installed: {', '.join(e.installed) or '(none)'}")
        sys.exit(1)


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


def cmd_prune(args):
    """Aggressively remove hawk-managed and stale hawk-linked artifacts."""
    from .v2_sync import format_sync_results, purge_all, purge_directory, purge_global

    tools = [Tool(args.tool)] if args.tool else None

    if args.dir:
        project_dir = Path(args.dir).resolve()
        results = purge_directory(project_dir, tools=tools, dry_run=args.dry_run)
        formatted = format_sync_results({str(project_dir): results})
    elif args.globals_only:
        results = purge_global(tools=tools, dry_run=args.dry_run)
        formatted = format_sync_results({"global": results})
    else:
        all_results = purge_all(tools=tools, dry_run=args.dry_run)
        formatted = format_sync_results(all_results)

    if args.dry_run:
        print("Dry run (no changes applied):")
    print(formatted or "  No changes.")

    if not args.dry_run:
        print("\nPruned hawk-managed and stale hawk-linked artifacts from tool configs.")


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


def cmd_migrate_prompts(args):
    """One-shot migration from commands schema to prompts schema."""
    from .migrate_prompts import run_migrate_prompts

    check_only = bool(args.check or not args.apply)
    changed_or_needed, summary = run_migrate_prompts(
        check_only=check_only,
        backup=not args.no_backup,
    )

    if check_only:
        print("Migration check:")
        print(summary)
        if not changed_or_needed:
            print("\nNo migration required.")
        else:
            print("\nRun 'hawk migrate-prompts --apply' to apply.")
        return

    if changed_or_needed:
        print("Migration complete:")
        print(summary)
    else:
        print("Migration skipped:")
        print(summary)


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

    elif comp_type in ("command", "prompt"):
        if not name.endswith(".md"):
            name = f"{name}.md"

        content = COMMAND_PROMPT_TEMPLATE.format(
            name=name.replace(".md", ""),
            description="Your command description",
        )

        dest = registry_path / "prompts" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not args.force:
            print(f"Error: {dest} already exists. Use --force to overwrite.")
            sys.exit(1)
        dest.write_text(content)

        _print(f"[green]+[/green] Created prompt: {dest}")

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
    if comp_type == "prompt-hook":
        add_type = "hook"
    elif comp_type == "command":
        add_type = "prompt"
    else:
        add_type = comp_type
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
    init_p.add_argument("-v", "--verbose", action="store_true", help="Show per-item sync details")
    init_p.set_defaults(func=cmd_init)

    # sync
    sync_p = subparsers.add_parser("sync", help="Sync components to tools")
    sync_p.add_argument("--dir", help="Sync specific directory")
    sync_p.add_argument("--tool", choices=[t.value for t in Tool], help="Sync specific tool")
    sync_p.add_argument("--dry-run", action="store_true", help="Show what would change")
    sync_p.add_argument("--force", action="store_true", help="Bypass cache, sync unconditionally")
    sync_p.add_argument("-v", "--verbose", action="store_true", help="Show per-item sync details")
    sync_p.add_argument("--global", dest="globals_only", action="store_true", help="Sync global only")
    sync_p.set_defaults(func=cmd_sync)

    # status
    status_p = subparsers.add_parser("status", help="Show current status")
    status_p.add_argument("--dir", help="Show status for specific directory")
    status_p.set_defaults(func=cmd_status)

    # add
    add_p = subparsers.add_parser("add", help="Add component to registry")
    add_p.add_argument("type", nargs="?", default=None,
                       help="Component type: skill, hook, prompt, agent, mcp (command accepted as alias)")
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

    # prune
    prune_p = subparsers.add_parser(
        "prune",
        help="Aggressively remove hawk-managed + stale hawk-linked artifacts",
    )
    prune_p.add_argument("--dir", help="Prune specific directory only")
    prune_p.add_argument("--tool", choices=[t.value for t in Tool], help="Prune specific tool")
    prune_p.add_argument("--dry-run", action="store_true", help="Show what would be removed")
    prune_p.add_argument(
        "--global", dest="globals_only", action="store_true", help="Prune global only"
    )
    prune_p.set_defaults(func=cmd_prune)

    # config
    config_p = subparsers.add_parser("config", help="Interactive settings editor")
    config_p.set_defaults(func=cmd_config)

    # new
    new_p = subparsers.add_parser("new", help="Create a new component from template")
    new_p.add_argument("type", choices=["hook", "prompt", "command", "agent", "prompt-hook"],
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

    # migrate-prompts
    migrate_prompts_p = subparsers.add_parser(
        "migrate-prompts",
        help="One-shot migration: commands schema -> prompts schema",
    )
    mode = migrate_prompts_p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Show what would change (default)")
    mode.add_argument("--apply", action="store_true", help="Apply migration changes")
    migrate_prompts_p.add_argument("--no-backup", action="store_true", help="Skip config backups")
    migrate_prompts_p.set_defaults(func=cmd_migrate_prompts)

    return parser


def main():
    """Main entry point."""
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


# Backward-compatible alias for older entrypoints.
main_v2 = main
