"""Small runner utilities shared by v2 adapters."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from pathlib import Path


def _get_interpreter_path(interpreter: str) -> str:
    """Get an absolute interpreter path.

    Falls back to known standard locations if not found on PATH.
    """
    standard_paths: dict[str, list[str]] = {
        "cat": ["/bin/cat", "/usr/bin/cat"],
        "bash": ["/bin/bash", "/usr/bin/bash"],
        "node": ["/usr/local/bin/node", "/usr/bin/node", "/opt/homebrew/bin/node"],
        "bun": ["/usr/local/bin/bun", "/opt/homebrew/bin/bun"],
    }

    path = shutil.which(interpreter)
    if path:
        return path

    for standard_path in standard_paths.get(interpreter, []):
        if Path(standard_path).exists():
            return standard_path

    raise FileNotFoundError(
        f"Interpreter '{interpreter}' not found in PATH or standard locations. "
        f"Checked: {standard_paths.get(interpreter, [])}"
    )


def _atomic_write_executable(path: Path, content: str) -> None:
    """Write content atomically and set executable owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)

    original_umask = os.umask(0o077)
    fd = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        os.write(fd, content.encode("utf-8"))
        os.fchmod(fd, stat.S_IRWXU)
        os.close(fd)
        fd = None
        os.rename(tmp_path, path)
        tmp_path = None
    except (OSError, IOError):
        if fd is not None:
            os.close(fd)
        if tmp_path is not None and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    finally:
        os.umask(original_umask)

