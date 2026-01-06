# Add Hook Feature - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a top-level "Add hook" menu item to quickly create or link new hooks.

**Architecture:** New `templates.py` module for script templates + docs generation. New `interactive_add_hook()` function in `cli.py`. Add `get_docs_dir()` helper to `config.py`.

**Tech Stack:** Python, questionary, rich, pathlib, shutil

---

## Task 1: Add docs directory helper to config.py

**Files:**
- Modify: `src/captain_hook/config.py`

**Step 1: Add get_docs_dir function**

Add after `get_log_path()` (around line 64):

```python
def get_docs_dir() -> Path:
    """Get the path to the docs directory."""
    return get_config_dir() / "docs"
```

**Step 2: Update ensure_dirs to create docs dir**

Modify `ensure_dirs()` to also create docs directory. Add after line 93:

```python
    get_docs_dir().mkdir(parents=True, exist_ok=True)
```

**Step 3: Commit**

```bash
git add src/captain_hook/config.py
git commit -m "feat(config): add docs directory helper"
```

---

## Task 2: Create templates.py module

**Files:**
- Create: `src/captain_hook/templates.py`

**Step 1: Create templates module with all templates**

```python
"""Script templates for captain-hook."""

import shutil
from pathlib import Path

# Python template
PYTHON_TEMPLATE = '''#!/usr/bin/env python3
# Description: Your hook description
# Deps:
# Env:

import json
import sys


def main():
    data = json.load(sys.stdin)
    # See: ~/.config/captain-hook/docs/hooks.md
    # Exit 0 = ok, Exit 2 = block, other = error
    sys.exit(0)


if __name__ == "__main__":
    main()
'''

# Shell template
SHELL_TEMPLATE = '''#!/usr/bin/env bash
# Description: Your hook description
# Deps: jq
# Env:

set -euo pipefail
INPUT=$(cat)
# See: ~/.config/captain-hook/docs/hooks.md
# Exit 0 = ok, Exit 2 = block, other = error
exit 0
'''

# Node template
NODE_TEMPLATE = '''#!/usr/bin/env node
// Description: Your hook description
// Deps:
// Env:

const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));
// See: ~/.config/captain-hook/docs/hooks.md
// Exit 0 = ok, Exit 2 = block, other = error
process.exit(0);
'''

# TypeScript template (bun)
TS_BUN_TEMPLATE = '''#!/usr/bin/env bun
// Description: Your hook description
// Deps:
// Env:

const data = await Bun.stdin.json();
// See: ~/.config/captain-hook/docs/hooks.md
// Exit 0 = ok, Exit 2 = block, other = error
process.exit(0);
'''

# TypeScript template (tsx via npx)
TS_TSX_TEMPLATE = '''#!/usr/bin/env -S npx tsx
// Description: Your hook description
// Deps:
// Env:

import * as fs from 'fs';
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
// See: ~/.config/captain-hook/docs/hooks.md
// Exit 0 = ok, Exit 2 = block, other = error
process.exit(0);
'''

# Stdout template
STDOUT_TEMPLATE = '''# Context for Claude

Add your context here. This content is injected when the hook runs.
'''

# Prompt hook template
PROMPT_TEMPLATE = '''{
  "prompt": "Evaluate if this action should proceed. Respond with {\\"decision\\": \\"approve\\"} or {\\"decision\\": \\"block\\", \\"reason\\": \\"why\\"}",
  "timeout": 30
}
'''

# Documentation file content
HOOKS_DOC = '''# Captain-Hook Reference

Official Claude Code hooks documentation:
https://docs.anthropic.com/en/docs/claude-code/hooks

## Script Comments

- `# Description: ...` - Shown in status/toggle menus
- `# Deps: pkg1, pkg2` - Python packages (auto-installed)
- `# Env: VAR=default` - Config menu option, baked into runner

## Exit Codes

- `0` = success (stdout shown in verbose mode)
- `2` = block operation (stderr shown to Claude)
- `other` = error (shown to user, non-blocking)

## Events

### pre_tool_use
Runs before tool execution. Can block.
Fields: session_id, cwd, tool_name, tool_input, tool_use_id

### post_tool_use
Runs after tool completes. Can provide feedback.
Fields: session_id, cwd, tool_name, tool_input, tool_response

### stop
Runs when agent finishes. Can request continuation.
Fields: session_id, cwd, stop_reason

### user_prompt_submit
Runs when user submits prompt. Can block or add context.
Fields: session_id, cwd, prompt

### notification
Runs when Claude sends notifications.
Fields: session_id, cwd, message

### subagent_stop
Runs when subagent/Task tool finishes.
Fields: session_id, cwd, stop_reason

### session_start
Runs at session start/resume/clear.
Fields: session_id, cwd, source (startup|resume|clear|compact)

### session_end
Runs when session ends.
Fields: session_id, cwd, reason

### pre_compact
Runs before context compaction.
Fields: session_id, cwd, source (manual|auto)
'''


def get_template(extension: str) -> str:
    """Get the template for a given extension."""
    templates = {
        ".py": PYTHON_TEMPLATE,
        ".sh": SHELL_TEMPLATE,
        ".js": NODE_TEMPLATE,
        ".ts": _get_ts_template(),
    }
    return templates.get(extension, "")


def _get_ts_template() -> str:
    """Get TypeScript template based on available runtime."""
    if shutil.which("bun"):
        return TS_BUN_TEMPLATE
    return TS_TSX_TEMPLATE


def get_ts_runtime() -> str | None:
    """Detect available TypeScript runtime."""
    if shutil.which("bun"):
        return "bun"
    if shutil.which("npx"):
        return "tsx"
    return None


def ensure_docs(docs_dir: Path) -> Path:
    """Ensure hooks.md documentation exists. Returns path to docs file."""
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_path = docs_dir / "hooks.md"
    if not docs_path.exists():
        docs_path.write_text(HOOKS_DOC)
    return docs_path
```

**Step 2: Commit**

```bash
git add src/captain_hook/templates.py
git commit -m "feat(templates): add script templates and docs"
```

---

## Task 3: Add interactive_add_hook function to cli.py

**Files:**
- Modify: `src/captain_hook/cli.py`

**Step 1: Add import for templates module**

Add to imports (around line 15):

```python
from . import __version__, config, generator, installer, scanner, templates
```

**Step 2: Add interactive_add_hook function**

Add after `interactive_config()` function (around line 688):

```python
def interactive_add_hook():
    """Interactive hook creation wizard."""
    console.print()
    console.print("[bold]Add Hook[/bold]")
    console.print("─" * 50)

    # Step 1: Select event
    event = questionary.select(
        "Select event:",
        choices=[questionary.Choice(e, value=e) for e in config.EVENTS],
        style=custom_style,
        instruction="(Esc cancel)",
    ).ask()

    if event is None:
        return

    # Step 2: Select hook type
    hook_type = questionary.select(
        "Hook type:",
        choices=[
            questionary.Choice("Link existing script (updates with original)", value="link"),
            questionary.Choice("Copy existing script (independent snapshot)", value="copy"),
            questionary.Choice("Create command script (.py/.sh/.js/.ts)", value="script"),
            questionary.Choice("Create stdout hook (.stdout.md)", value="stdout"),
            questionary.Choice("Create prompt hook (.prompt.json)", value="prompt"),
        ],
        style=custom_style,
        instruction="(Esc cancel)",
    ).ask()

    if hook_type is None:
        return

    hooks_dir = config.get_hooks_dir() / event
    hooks_dir.mkdir(parents=True, exist_ok=True)

    if hook_type in ("link", "copy"):
        _add_existing_hook(event, hooks_dir, copy=(hook_type == "copy"))
    elif hook_type == "script":
        _add_new_script(event, hooks_dir)
    elif hook_type == "stdout":
        _add_new_stdout(event, hooks_dir)
    elif hook_type == "prompt":
        _add_new_prompt(event, hooks_dir)


def _add_existing_hook(event: str, hooks_dir: Path, copy: bool = False):
    """Link or copy an existing script."""
    # Get path from user
    path_str = questionary.path(
        "Script path:",
        style=custom_style,
    ).ask()

    if path_str is None:
        return

    source_path = Path(path_str).expanduser().resolve()

    # Validate file exists
    if not source_path.exists():
        console.print(f"[red]File not found:[/red] {source_path}")
        return

    # Validate extension
    valid_exts = {".py", ".sh", ".js", ".ts"}
    if source_path.suffix.lower() not in valid_exts:
        console.print(f"[red]Unsupported extension.[/red] Use: {', '.join(valid_exts)}")
        return

    # Check if executable (for scripts)
    if not os.access(source_path, os.X_OK):
        make_exec = questionary.confirm(
            "File is not executable. Make executable?",
            default=True,
            style=custom_style,
        ).ask()
        if make_exec:
            import stat
            current = source_path.stat().st_mode
            source_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            console.print(f"  [green]✓[/green] Made executable")

    dest_path = hooks_dir / source_path.name

    # Check if already exists
    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {dest_path.name}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return
        dest_path.unlink()

    if copy:
        shutil.copy2(source_path, dest_path)
        console.print(f"  [green]✓[/green] Copied to {dest_path}")
    else:
        dest_path.symlink_to(source_path)
        console.print(f"  [green]✓[/green] Linked to {dest_path}")

    # Show docs path
    docs_path = templates.ensure_docs(config.get_docs_dir())
    console.print(f"  [dim]Docs: {docs_path}[/dim]")

    _prompt_enable_hook(event, source_path.stem)


def _add_new_script(event: str, hooks_dir: Path):
    """Create a new script from template."""
    # Select script type
    script_type = questionary.select(
        "Script type:",
        choices=[
            questionary.Choice("Python (.py)", value=".py"),
            questionary.Choice("Shell (.sh)", value=".sh"),
            questionary.Choice("Node (.js)", value=".js"),
            questionary.Choice("TypeScript (.ts)", value=".ts"),
        ],
        style=custom_style,
        instruction="(Esc cancel)",
    ).ask()

    if script_type is None:
        return

    # Warn about TypeScript runtime if needed
    if script_type == ".ts":
        ts_runtime = templates.get_ts_runtime()
        if ts_runtime is None:
            console.print("[yellow]Warning:[/yellow] No TypeScript runtime found.")
            console.print("[dim]Install bun or npm to run .ts hooks.[/dim]")
            console.print()

    # Get filename
    filename = questionary.text(
        f"Filename (must end with {script_type}):",
        style=custom_style,
    ).ask()

    if filename is None:
        return

    # Validate suffix
    if not filename.endswith(script_type):
        console.print(f"[red]Filename must end with {script_type}[/red]")
        return

    dest_path = hooks_dir / filename

    # Check if already exists
    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {filename}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return

    # Write template
    template_content = templates.get_template(script_type)
    dest_path.write_text(template_content)

    # Make executable
    import stat
    current = dest_path.stat().st_mode
    dest_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    console.print(f"  [green]✓[/green] Created {dest_path}")

    # Show docs path
    docs_path = templates.ensure_docs(config.get_docs_dir())
    console.print(f"  [dim]Docs: {docs_path}[/dim]")

    # Offer to open in editor
    _open_in_editor(dest_path)

    # Get hook name (stem without extension)
    hook_name = dest_path.stem
    _prompt_enable_hook(event, hook_name)


def _add_new_stdout(event: str, hooks_dir: Path):
    """Create a new stdout hook."""
    # Get filename
    filename = questionary.text(
        "Filename (must end with .stdout.md or .stdout.txt):",
        style=custom_style,
    ).ask()

    if filename is None:
        return

    # Validate suffix
    if not (filename.endswith(".stdout.md") or filename.endswith(".stdout.txt")):
        console.print("[red]Filename must end with .stdout.md or .stdout.txt[/red]")
        return

    dest_path = hooks_dir / filename

    # Check if already exists
    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {filename}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return

    # Write template
    dest_path.write_text(templates.STDOUT_TEMPLATE)
    console.print(f"  [green]✓[/green] Created {dest_path}")

    # Offer to open in editor
    _open_in_editor(dest_path)

    # Get hook name (part before .stdout.)
    hook_name = filename.split(".stdout.")[0]
    _prompt_enable_hook(event, hook_name)


def _add_new_prompt(event: str, hooks_dir: Path):
    """Create a new prompt hook."""
    # Get filename
    filename = questionary.text(
        "Filename (must end with .prompt.json):",
        style=custom_style,
    ).ask()

    if filename is None:
        return

    # Validate suffix
    if not filename.endswith(".prompt.json"):
        console.print("[red]Filename must end with .prompt.json[/red]")
        return

    dest_path = hooks_dir / filename

    # Check if already exists
    if dest_path.exists():
        overwrite = questionary.confirm(
            f"Hook already exists: {filename}. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        if not overwrite:
            return

    # Write template
    dest_path.write_text(templates.PROMPT_TEMPLATE)
    console.print(f"  [green]✓[/green] Created {dest_path}")

    # Offer to open in editor
    _open_in_editor(dest_path)

    # Get hook name (part before .prompt.json)
    hook_name = filename[:-len(".prompt.json")]
    _prompt_enable_hook(event, hook_name)


def _open_in_editor(path: Path):
    """Offer to open file in editor."""
    open_editor = questionary.confirm(
        "Open in editor?",
        default=True,
        style=custom_style,
    ).ask()

    if not open_editor:
        return

    import os
    editor = os.environ.get("EDITOR")
    if not editor:
        if shutil.which("nano"):
            editor = "nano"
        elif shutil.which("vi"):
            editor = "vi"
        else:
            console.print(f"[yellow]No editor found.[/yellow] Edit manually: {path}")
            return

    try:
        subprocess.run([editor, str(path)], check=False)
    except Exception as e:
        console.print(f"[red]Failed to open editor:[/red] {e}")


def _prompt_enable_hook(event: str, hook_name: str):
    """Ask to enable the hook."""
    console.print()
    enable = questionary.confirm(
        "Enable this hook now?",
        default=True,
        style=custom_style,
    ).ask()

    if not enable:
        console.print("[dim]Hook created but not enabled. Use Toggle to enable later.[/dim]")
        return

    # Add to enabled hooks
    cfg = config.load_config()
    enabled = cfg.get("enabled", {}).get(event, [])
    if hook_name not in enabled:
        enabled.append(hook_name)
        config.set_enabled_hooks(event, enabled)

    # Regenerate runners
    console.print()
    console.print("[bold]Updating hooks...[/bold]")
    runners = generator.generate_all_runners()
    for runner in runners:
        console.print(f"  [green]✓[/green] {runner.name}")

    # Sync prompt hooks if needed
    prompt_results = installer.sync_prompt_hooks(level="user")
    for name, success in prompt_results.items():
        if success:
            console.print(f"  [green]✓[/green] {name} [dim](prompt)[/dim]")

    console.print()
    console.print(f"[green]Hook enabled![/green]")
    console.print()
```

**Step 3: Add import for os at top of file**

Add `import os` to the imports if not already present.

**Step 4: Commit**

```bash
git add src/captain_hook/cli.py
git commit -m "feat(cli): add interactive_add_hook function"
```

---

## Task 4: Add "Add hook" to main menu

**Files:**
- Modify: `src/captain_hook/cli.py`

**Step 1: Update interactive_menu choices**

Find the `interactive_menu()` function (around line 690) and update the choices list. Add after "Toggle":

```python
                questionary.Choice("Add hook    Create or link a new hook", value="add"),
```

**Step 2: Add handler for "add" choice**

In the same function, add after the `elif choice == "toggle":` block:

```python
        elif choice == "add":
            interactive_add_hook()
```

**Step 3: Commit**

```bash
git add src/captain_hook/cli.py
git commit -m "feat(cli): add 'Add hook' to main menu"
```

---

## Task 5: Test the feature manually

**Step 1: Run captain-hook**

```bash
captain-hook
```

**Step 2: Test each path**

1. Add hook → pre_tool_use → Link existing script → test with a .py file
2. Add hook → stop → Create command script → Python → test.py
3. Add hook → user_prompt_submit → Create stdout hook → context.stdout.md
4. Add hook → stop → Create prompt hook → check.prompt.json

**Step 3: Verify docs file created**

```bash
cat ~/.config/captain-hook/docs/hooks.md
```

**Step 4: Verify hooks appear in Toggle menu**

---

## Task 6: Final commit and version bump

**Step 1: Bump version**

Edit `src/captain_hook/__init__.py`:

```python
__version__ = "0.4.0"
```

**Step 2: Commit and tag**

```bash
git add -A
git commit -m "feat: add 'Add hook' menu for quick hook creation

- Add hook menu item to create/link hooks interactively
- Support link (symlink) and copy modes for existing scripts
- Templates for Python, Shell, Node, TypeScript scripts
- Templates for stdout (.stdout.md) and prompt (.prompt.json) hooks
- Auto-detect TypeScript runtime (bun/tsx)
- Generate hooks.md documentation on first use
- Validate extensions and offer chmod +x for non-executable scripts"

git tag v0.4.0
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add docs directory helper | config.py |
| 2 | Create templates module | templates.py (new) |
| 3 | Add interactive_add_hook | cli.py |
| 4 | Add to main menu | cli.py |
| 5 | Manual testing | - |
| 6 | Version bump + tag | __init__.py |
