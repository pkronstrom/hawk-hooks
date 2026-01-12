"""Dependency installation for hooks.

Handles venv creation, Python deps, shell tools, and Node packages.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import questionary

from .. import config, scanner
from .core import _run_command, console, custom_style


def _detect_package_manager() -> str | None:
    """Detect available package manager."""
    managers = [
        ("brew", "brew"),
        ("apt", "apt-get"),
        ("dnf", "dnf"),
        ("yum", "yum"),
        ("pacman", "pacman"),
        ("apk", "apk"),
    ]
    for name, cmd in managers:
        if shutil.which(cmd):
            return name
    return None


def _get_install_command(pkg_manager: str, packages: set[str]) -> str:
    """Get install command for package manager (display only)."""
    pkg_list = " ".join(sorted(packages))
    commands = {
        "brew": f"brew install {pkg_list}",
        "apt": f"sudo apt-get install -y {pkg_list}",
        "dnf": f"sudo dnf install -y {pkg_list}",
        "yum": f"sudo yum install -y {pkg_list}",
        "pacman": f"sudo pacman -S --noconfirm {pkg_list}",
        "apk": f"sudo apk add {pkg_list}",
    }
    return commands.get(pkg_manager, f"# Install: {pkg_list}")


def _get_install_command_list(pkg_manager: str, packages: set[str]) -> list[str]:
    """Get install command as a list for subprocess."""
    pkg_list = sorted(packages)
    commands: dict[str, list[str]] = {
        "brew": ["brew", "install", *pkg_list],
        "apt": ["sudo", "apt-get", "install", "-y", *pkg_list],
        "dnf": ["sudo", "dnf", "install", "-y", *pkg_list],
        "yum": ["sudo", "yum", "install", "-y", *pkg_list],
        "pacman": ["sudo", "pacman", "-S", "--noconfirm", *pkg_list],
        "apk": ["sudo", "apk", "add", *pkg_list],
    }
    return commands.get(pkg_manager, [])


def _ensure_venv(venv_dir: Path) -> bool:
    """Create venv if it doesn't exist.

    Returns:
        True if venv is ready, False if creation failed.
    """
    if venv_dir.exists():
        return True

    console.print(f"  Creating venv at {venv_dir}...")
    success, error = _run_command(
        [sys.executable, "-m", "venv", str(venv_dir)],
        timeout=120,
        description="Create venv",
    )
    if not success:
        console.print(f"  [red]✗[/red] Failed to create venv: {error}")
        return False

    console.print("  [green]✓[/green] Venv created")
    return True


def _install_python_deps(venv_python: Path) -> bool:
    """Install Python dependencies into venv.

    Returns:
        True if installation succeeded, False otherwise.
    """
    python_deps = scanner.get_python_deps()

    if not python_deps:
        console.print("  [dim]No Python dependencies required[/dim]")
        return True

    all_deps = set()
    for deps in python_deps.values():
        all_deps.update(deps)

    if not all_deps:
        return True

    console.print(f"  Installing: {', '.join(sorted(all_deps))}")
    success, error = _run_command(
        [str(venv_python), "-m", "pip", "install", "--quiet", *list(all_deps)],
        timeout=300,
        description="Install Python dependencies",
    )
    if not success:
        console.print(f"  [red]✗[/red] Failed to install Python deps: {error}")
        return False

    console.print("  [green]✓[/green] Python deps installed")
    return True


def _install_shell_tools(shell_tools: set[str]) -> None:
    """Install shell tools via package manager."""
    import subprocess

    pkg_manager = _detect_package_manager()
    if not pkg_manager:
        console.print("[bold]Shell tools needed (install manually):[/bold]")
        console.print(f"  {', '.join(sorted(shell_tools))}")
        return

    install_cmd_display = _get_install_command(pkg_manager, shell_tools)
    install_cmd_list = _get_install_command_list(pkg_manager, shell_tools)
    console.print(f"[bold]Shell tools needed:[/bold] {', '.join(sorted(shell_tools))}")
    console.print(f"[dim]Command: {install_cmd_display}[/dim]")
    console.print()

    install_shell = questionary.confirm(
        f"Install via {pkg_manager}?",
        default=True,
        style=custom_style,
    ).ask()
    console.print()

    if install_shell and install_cmd_list:
        try:
            subprocess.run(install_cmd_list, check=True, timeout=300)
            console.print("  [green]✓[/green] Shell tools installed")
        except subprocess.CalledProcessError as e:
            console.print(f"  [red]✗[/red] Installation failed (exit {e.returncode})")
            console.print(f"  [dim]Run manually: {install_cmd_display}[/dim]")
        except subprocess.TimeoutExpired:
            console.print("  [red]✗[/red] Installation timed out")


def _install_node_deps(node_deps: set[str]) -> None:
    """Install Node packages via npm."""
    import subprocess

    npm_cmd_display = f"npm install -g {' '.join(sorted(node_deps))}"
    npm_cmd_list = ["npm", "install", "-g", *sorted(node_deps)]
    console.print(f"[bold]Node packages needed:[/bold] {', '.join(sorted(node_deps))}")
    console.print(f"[dim]Command: {npm_cmd_display}[/dim]")
    console.print()

    if not shutil.which("npm"):
        console.print("[dim]npm not found - install Node.js first[/dim]")
        return

    install_node = questionary.confirm(
        "Install via npm?",
        default=True,
        style=custom_style,
    ).ask()
    console.print()

    if install_node:
        try:
            subprocess.run(npm_cmd_list, check=True, timeout=300)
            console.print("  [green]✓[/green] Node packages installed")
        except subprocess.CalledProcessError as e:
            console.print(f"  [red]✗[/red] Installation failed (exit {e.returncode})")
        except subprocess.TimeoutExpired:
            console.print("  [red]✗[/red] Installation timed out")


def install_deps():
    """Install Python dependencies for hooks."""
    venv_dir = config.get_venv_dir()
    venv_python = config.get_venv_python()

    console.print("[bold]Installing dependencies...[/bold]")
    console.print(f"[dim]Venv location: {venv_dir}[/dim]")
    console.print()

    if not _ensure_venv(venv_dir):
        console.print("[red]Cannot continue without venv.[/red]")
        console.print()
        return

    _install_python_deps(venv_python)

    other_deps = scanner.get_non_python_deps()
    if other_deps:
        console.print()

        shell_tools = set()
        node_deps = set()
        for lang, hooks_deps in other_deps.items():
            for deps in hooks_deps.values():
                if lang == "bash":
                    shell_tools.update(deps)
                elif lang == "node":
                    node_deps.update(deps)

        if shell_tools:
            _install_shell_tools(shell_tools)

        if node_deps:
            console.print()
            _install_node_deps(node_deps)

    console.print()
