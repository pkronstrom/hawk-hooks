"""Project scope handlers for the dashboard."""

from __future__ import annotations

import shutil
from pathlib import Path

from ... import v2_config
from .. import dashboard as _dashboard

console = _dashboard.console


def TerminalMenu(*args, **kwargs):
    return _dashboard.TerminalMenu(*args, **kwargs)


def terminal_menu_style_kwargs(*args, **kwargs):
    return _dashboard.terminal_menu_style_kwargs(*args, **kwargs)


def wait_for_continue(*args, **kwargs):
    return _dashboard.wait_for_continue(*args, **kwargs)


def _prompt_delete_scope(*args, **kwargs):
    return _dashboard._prompt_delete_scope(*args, **kwargs)


def _delete_project_scope(*args, **kwargs):
    return _dashboard._delete_project_scope(*args, **kwargs)


def _run_projects_tree(*args, **kwargs):
    return _dashboard._run_projects_tree(*args, **kwargs)

def handle_projects(state: dict) -> None:
    """Interactive projects tree view."""
    _run_projects_tree()


def delete_project_scope(project_dir: Path, *, delete_local_hawk: bool) -> tuple[bool, str]:
    """Delete a registered project scope, optionally removing local .hawk files."""
    project_dir = project_dir.resolve()
    try:
        v2_config.unregister_directory(project_dir)
    except Exception as e:
        return False, f"Failed to remove scope: {e}"

    if delete_local_hawk:
        hawk_dir = project_dir / ".hawk"
        try:
            if hawk_dir.is_symlink() or hawk_dir.is_file():
                hawk_dir.unlink()
            elif hawk_dir.is_dir():
                shutil.rmtree(hawk_dir)
        except OSError as e:
            return False, f"Scope removed, but failed to delete .hawk: {e}"

    if delete_local_hawk:
        return True, f"Removed scope and local .hawk for: {project_dir}"
    return True, f"Removed scope registration for: {project_dir}"


def prompt_delete_scope(project_dir: Path, *, prefer_delete_local: bool = False) -> bool | None:
    """Prompt user for scope deletion details.

    Returns:
        True  -> delete scope + local .hawk
        False -> delete scope registration only
        None  -> cancelled
    """
    step1 = TerminalMenu(
        ["Cancel", "Delete scope"],
        title=(
            "\nDelete local scope?\n"
            f"{project_dir}\n"
            "This removes the project from Hawk Project Scopes."
        ),
        cursor_index=0,
        menu_cursor="\u203a ",
        **terminal_menu_style_kwargs(),
        quit_keys=("q", "\x1b"),
    )
    choice1 = step1.show()
    if choice1 != 1:
        return None

    default_idx = 1 if prefer_delete_local else 0
    step2 = TerminalMenu(
        ["Keep local .hawk files", "Delete local .hawk files", "Cancel"],
        title=(
            "\nAlso delete local .hawk files?\n"
            "Use this if you want to fully remove local Hawk setup for this project."
        ),
        cursor_index=default_idx,
        menu_cursor="\u203a ",
        **terminal_menu_style_kwargs(),
        quit_keys=("q", "\x1b"),
    )
    choice2 = step2.show()
    if choice2 is None or choice2 == 2:
        return None
    return choice2 == 1


def run_projects_tree() -> None:
    """Show interactive tree of all registered directories."""
    while True:
        dirs = v2_config.get_registered_directories()

        if not dirs:
            console.print("\n[dim]No directories registered.[/dim]")
            console.print("[dim]Run [cyan]hawk init[/cyan] in a project directory to register it.[/dim]\n")
            wait_for_continue()
            return

        # Build tree structure: group by parent-child relationships
        dir_paths = sorted(dirs.keys())
        tree_entries: list[tuple[str, int, str]] = []  # (path, indent, label)

        # Find root dirs (not children of any other registered dir)
        roots: list[str] = []
        for dp in dir_paths:
            dp_path = Path(dp)
            is_child = False
            for other in dir_paths:
                if other != dp:
                    try:
                        if dp_path.is_relative_to(Path(other)):
                            is_child = True
                            break
                    except (ValueError, TypeError):
                        continue
            if not is_child:
                roots.append(dp)

        def _add_tree(parent: str, indent: int) -> None:
            p = Path(parent)
            entry = dirs.get(parent, {})
            profile = entry.get("profile", "")

            # Count enabled items
            dir_config = v2_config.load_dir_config(p)
            parts: list[str] = []
            if profile:
                parts.append(f"profile: {profile}")
            if dir_config:
                for field in ["skills", "hooks", "prompts", "agents", "mcp"]:
                    section = dir_config.get(field, {})
                    if isinstance(section, dict):
                        count = len(section.get("enabled", []))
                    elif isinstance(section, list):
                        count = len(section)
                    else:
                        count = 0
                    if count:
                        parts.append(f"+{count} {field}")

            suffix = f"  {', '.join(parts)}" if parts else ""
            exists = p.exists()
            marker = " [missing]" if not exists else ""

            if indent == 0:
                label = f"{parent}{suffix}{marker}"
            else:
                label = f"{'   ' * indent}{p.name}{suffix}{marker}"

            tree_entries.append((parent, indent, label))

            # Find children
            children = [
                dp for dp in dir_paths
                if dp != parent and dp.startswith(parent + "/")
                and not any(
                    other != parent and other != dp
                    and dp.startswith(other + "/")
                    and other.startswith(parent + "/")
                    for other in dir_paths
                )
            ]
            for child in sorted(children):
                _add_tree(child, indent + 1)

        for root in sorted(roots):
            _add_tree(root, 0)

        # Add global entry at top
        cfg = v2_config.load_global_config()
        global_section = cfg.get("global", {})
        global_parts: list[str] = []
        for field in ["skills", "hooks", "prompts", "agents", "mcp"]:
            count = len(global_section.get(field, []))
            if count:
                global_parts.append(f"{count} {field}")
        global_suffix = f"  {', '.join(global_parts)}" if global_parts else ""

        menu_entries = [f"Global{global_suffix}"] + [e[2] for e in tree_entries]
        menu_paths = ["global"] + [e[0] for e in tree_entries]

        menu = TerminalMenu(
            menu_entries,
            title="\nhawk projects\n" + "\u2500" * 40,
            menu_cursor="\u203a ",
            **terminal_menu_style_kwargs(include_status_bar=True),
            accept_keys=("enter", "d", "x"),
            quit_keys=("q", "\x1b"),
            status_bar="↵ open · d/x delete scope · q/esc back",
        )

        choice = menu.show()
        if choice is None:
            break

        selected_path = menu_paths[choice]
        accept_key = getattr(menu, "chosen_accept_key", "enter")
        if accept_key in ("d", "x"):
            if selected_path == "global":
                console.print("\n[yellow]Global scope cannot be deleted.[/yellow]\n")
                wait_for_continue()
                continue

            project_dir = Path(selected_path)
            remove_local = _prompt_delete_scope(
                project_dir,
                prefer_delete_local=(accept_key == "x"),
            )
            if remove_local is None:
                continue

            ok, msg = _delete_project_scope(project_dir, delete_local_hawk=remove_local)
            style = "green" if ok else "red"
            console.print(f"\n[{style}]{msg}[/{style}]\n")
            wait_for_continue()
            continue

        if selected_path == "global":
            # Open settings editor for global config
            from ..config_editor import run_config_editor
            run_config_editor()
        else:
            # Open dashboard scoped to that directory
            from .. import v2_interactive_menu
            v2_interactive_menu(scope_dir=selected_path)
            break
