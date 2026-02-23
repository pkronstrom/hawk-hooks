"""Best-effort detection of how hawk was installed for uninstall guidance."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def detect_uninstall_command() -> str:
    """Return the best uninstall command hint for the current runtime."""
    exe = str(Path(sys.executable).resolve()).lower()
    prefix = str(Path(sys.prefix).resolve()).lower()
    argv0 = str(Path(sys.argv[0]).resolve()).lower() if sys.argv else ""
    hawk_bin = (shutil.which("hawk") or "").lower()
    combined = " | ".join([exe, prefix, argv0, hawk_bin])

    # pipx-managed installs usually run from a pipx venv path.
    if "pipx/venvs/hawk-hooks" in combined:
        return "pipx uninstall hawk-hooks"

    # uv tool installs usually run from uv tools directory.
    if "/uv/tools/" in combined and "hawk-hooks" in combined:
        return "uv tool uninstall hawk-hooks"

    # Virtualenv / uv run / custom env — uninstall from this interpreter.
    base_prefix = getattr(sys, "base_prefix", sys.prefix)
    if sys.prefix != base_prefix:
        return f'"{sys.executable}" -m pip uninstall hawk-hooks'

    # Fallback preference: pipx when available, else pip.
    if shutil.which("pipx"):
        return "pipx uninstall hawk-hooks"
    if shutil.which("uv"):
        return "uv tool uninstall hawk-hooks"
    return "python -m pip uninstall hawk-hooks"

