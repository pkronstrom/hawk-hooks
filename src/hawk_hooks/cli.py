"""CLI interface for hawk-hooks."""

import argparse

from . import __version__, config, generator, installer, scanner
from .events import EVENTS
from .hook_manager import HookManager
from .interactive import install_deps, interactive_menu, show_status


def find_hook(name: str) -> tuple[str, str] | None:
    """Find hook by name, return (event, hook_name) or None.

    Supports formats:
      - "file-guard" - auto-detect event by scanning all events
      - "pre_tool_use/file-guard" - explicit event/hook
    """
    hooks = scanner.scan_hooks()

    if "/" in name:
        event, hook_name = name.split("/", 1)
        if event in hooks and any(h.name == hook_name for h in hooks[event]):
            return (event, hook_name)
        return None

    for event, event_hooks in hooks.items():
        if any(h.name == name for h in event_hooks):
            return (event, name)
    return None


def cmd_enable(args):
    """CLI: Enable hooks by name."""
    manager = HookManager(scope="global")
    changed = False

    for name in args.hooks:
        result = find_hook(name)
        if not result:
            print(f"  ✗ Hook not found: {name}")
            continue
        event, hook_name = result
        if manager.enable_hook(event, hook_name, auto_sync=False):
            print(f"  ✓ Enabled {event}/{hook_name}")
            changed = True
        else:
            print(f"  - Already enabled: {event}/{hook_name}")

    if changed:
        manager.sync()
        print("Runners regenerated.")


def cmd_disable(args):
    """CLI: Disable hooks by name."""
    manager = HookManager(scope="global")
    changed = False

    for name in args.hooks:
        result = find_hook(name)
        if not result:
            print(f"  ✗ Hook not found: {name}")
            continue
        event, hook_name = result
        if manager.disable_hook(event, hook_name, auto_sync=False):
            print(f"  ✓ Disabled {event}/{hook_name}")
            changed = True
        else:
            print(f"  - Already disabled: {event}/{hook_name}")

    if changed:
        manager.sync()
        print("Runners regenerated.")


def cmd_list(args):
    """CLI: List hooks (scriptable output)."""
    hooks = scanner.scan_hooks()
    cfg = config.load_config()

    for event in EVENTS:
        event_hooks = hooks.get(event, [])
        if not event_hooks:
            continue

        enabled_list = cfg.get("enabled", {}).get(event, [])

        for hook in event_hooks:
            is_enabled = hook.name in enabled_list

            if args.enabled and not is_enabled:
                continue
            if args.disabled and is_enabled:
                continue

            status = "enabled" if is_enabled else "disabled"
            print(f"{event}/{hook.name}\t{status}\t{hook.description}")


def cmd_status(args):
    """CLI: Show status."""
    show_status()


def cmd_install(args):
    """CLI: Install hooks."""
    results = installer.install_hooks(scope=args.scope)
    for event, success in results.items():
        icon = "✓" if success else "✗"
        print(f"  {icon} {event}")


def cmd_uninstall(args):
    """CLI: Uninstall hooks."""
    installer.uninstall_hooks(scope=args.scope)
    print("Hooks uninstalled.")
    print("\nTo fully remove hawk-hooks:")
    print(f"  rm -rf {config.get_config_dir()}  # config + hooks")
    print("  pipx uninstall hawk-hooks        # program")


def cmd_toggle(args):
    """CLI: Toggle (non-interactive just regenerates)."""
    generator.generate_all_runners()
    print("Runners regenerated.")


def cmd_deps(args):
    """CLI: Install dependencies."""
    install_deps()


def cmd_sync_examples(args):
    """CLI: Sync examples from package to config directory."""
    import shutil
    from pathlib import Path

    # Try installed location first (package/examples), then editable location (project root)
    examples_base = Path(__file__).parent / "examples"
    if not examples_base.exists():
        # Editable install: go from src/hawk_hooks/ to project root
        examples_base = Path(__file__).parent.parent.parent / "examples"

    copied = 0
    skipped = 0

    if not examples_base.exists():
        print("Error: Examples directory not found")
        print(f"Searched: {Path(__file__).parent / 'examples'}")
        print(f"      and: {Path(__file__).parent.parent.parent / 'examples'}")
        return

    # Sync hooks
    hooks_examples = examples_base / "hooks"
    if hooks_examples.exists():
        hooks_dir = config.get_hooks_dir()
        for event in EVENTS:
            src_event = hooks_examples / event
            dst_event = hooks_dir / event
            if src_event.exists():
                dst_event.mkdir(parents=True, exist_ok=True)
                for hook_file in src_event.iterdir():
                    if hook_file.is_file():
                        dst_file = dst_event / hook_file.name
                        if dst_file.exists() and not args.force:
                            if args.verbose:
                                print(f"  - Skip (exists): hooks/{event}/{hook_file.name}")
                            skipped += 1
                        else:
                            shutil.copy(hook_file, dst_file)
                            print(f"  ✓ hooks/{event}/{hook_file.name}")
                            copied += 1

    # Sync agents
    agents_examples = examples_base / "agents"
    if agents_examples.exists():
        agents_dir = config.get_agents_dir()
        agents_dir.mkdir(parents=True, exist_ok=True)
        for agent_file in agents_examples.iterdir():
            if agent_file.is_file() and agent_file.suffix == ".md":
                dst_file = agents_dir / agent_file.name
                if dst_file.exists() and not args.force:
                    if args.verbose:
                        print(f"  - Skip (exists): agents/{agent_file.name}")
                    skipped += 1
                else:
                    shutil.copy(agent_file, dst_file)
                    print(f"  ✓ agents/{agent_file.name}")
                    copied += 1

    # Sync prompts
    prompts_examples = examples_base / "prompts"
    if prompts_examples.exists():
        prompts_dir = config.get_prompts_dir()
        prompts_dir.mkdir(parents=True, exist_ok=True)
        for prompt_file in prompts_examples.iterdir():
            if prompt_file.is_file() and prompt_file.suffix == ".md":
                dst_file = prompts_dir / prompt_file.name
                if dst_file.exists() and not args.force:
                    if args.verbose:
                        print(f"  - Skip (exists): prompts/{prompt_file.name}")
                    skipped += 1
                else:
                    shutil.copy(prompt_file, dst_file)
                    print(f"  ✓ prompts/{prompt_file.name}")
                    copied += 1

    print()
    if copied > 0:
        print(f"Copied {copied} file(s).")
    if skipped > 0:
        print(f"Skipped {skipped} existing file(s). Use --force to overwrite.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="hawk-hooks: A modular Claude Code hooks manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"hawk-hooks {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show hooks status")
    status_parser.set_defaults(func=cmd_status)

    # Install command
    install_parser = subparsers.add_parser("install", help="Install hooks to Claude settings")
    install_parser.add_argument(
        "--scope",
        choices=["user", "project"],
        default="user",
        help="Installation scope (default: user)",
    )
    install_parser.set_defaults(func=cmd_install)

    # Uninstall command
    uninstall_parser = subparsers.add_parser(
        "uninstall", help="Uninstall hooks from Claude settings"
    )
    uninstall_parser.add_argument(
        "--scope",
        choices=["user", "project"],
        default="user",
        help="Uninstallation scope (default: user)",
    )
    uninstall_parser.set_defaults(func=cmd_uninstall)

    # Toggle command
    toggle_parser = subparsers.add_parser("toggle", help="Regenerate runners")
    toggle_parser.set_defaults(func=cmd_toggle)

    # Install-deps command
    deps_parser = subparsers.add_parser("install-deps", help="Install Python dependencies")
    deps_parser.set_defaults(func=cmd_deps)

    # Enable command
    enable_parser = subparsers.add_parser("enable", help="Enable hooks by name")
    enable_parser.add_argument(
        "hooks",
        nargs="+",
        help="Hook names (e.g., file-guard or pre_tool_use/file-guard)",
    )
    enable_parser.set_defaults(func=cmd_enable)

    # Disable command
    disable_parser = subparsers.add_parser("disable", help="Disable hooks by name")
    disable_parser.add_argument(
        "hooks",
        nargs="+",
        help="Hook names (e.g., file-guard or pre_tool_use/file-guard)",
    )
    disable_parser.set_defaults(func=cmd_disable)

    # List command
    list_parser = subparsers.add_parser("list", help="List hooks (scriptable output)")
    list_parser.add_argument(
        "--enabled",
        action="store_true",
        help="Show only enabled hooks",
    )
    list_parser.add_argument(
        "--disabled",
        action="store_true",
        help="Show only disabled hooks",
    )
    list_parser.set_defaults(func=cmd_list)

    # Sync-examples command
    sync_parser = subparsers.add_parser(
        "sync-examples", help="Copy new examples to config directory"
    )
    sync_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite existing files",
    )
    sync_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show skipped files",
    )
    sync_parser.set_defaults(func=cmd_sync_examples)

    args = parser.parse_args()

    if args.command is None:
        interactive_menu()
    else:
        args.func(args)


if __name__ == "__main__":
    main()
