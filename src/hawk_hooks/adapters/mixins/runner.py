"""Hook runner generation mixin for adapters."""

from __future__ import annotations

import logging
import re
from pathlib import Path

_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
logger = logging.getLogger(__name__)


class HookRunnerMixin:
    """Provide hook runner generation shared by multiple adapters."""

    def _generate_runners(
        self,
        hook_names: list[str],
        registry_path: Path,
        runners_dir: Path,
    ) -> dict[str, Path]:
        """Generate bash runners from hook files using hawk-hook metadata.

        Hook names are plain filenames (e.g. "file-guard.py").
        Each hook's metadata declares which events it targets.
        One runner is generated per event, chaining all hooks for that event.

        Returns dict of {event_name: runner_path}.
        """
        from collections import defaultdict
        import shlex

        from ...events import EVENTS
        from ...hook_meta import HookMeta
        from ...hook_meta import parse_hook_meta
        from ...runner_utils import _atomic_write_executable, _get_interpreter_path

        # Resolve hooks and group by event, keeping metadata
        hooks_by_event: dict[str, list[tuple[Path, HookMeta]]] = defaultdict(list)
        hooks_dir = registry_path / "hooks"
        for name in hook_names:
            hook_path = hooks_dir / name
            if not hook_path.is_file():
                continue
            meta = parse_hook_meta(hook_path)
            for event in meta.events:
                # Validate event name against canonical events to prevent
                # path traversal (e.g. events=../../foo) and unknown events
                if event not in EVENTS:
                    continue
                hooks_by_event[event].append((hook_path, meta))

        runners: dict[str, Path] = {}
        runners_dir.mkdir(parents=True, exist_ok=True)

        # Check for venv python
        from ... import v2_config

        venv_python = v2_config.get_config_dir() / ".venv" / "bin" / "python"
        python_cmd = shlex.quote(str(venv_python)) if venv_python.is_file() else "python3"

        for event, hook_entries in hooks_by_event.items():
            calls: list[str] = []
            for script, meta in hook_entries:
                safe_path = shlex.quote(str(script))
                suffix = script.suffix

                # Inject env var exports for entries with = (value assigned)
                env_exports: list[str] = []
                for env_entry in meta.env:
                    if "=" in env_entry:
                        var_name, _, var_value = env_entry.partition("=")
                        if not _ENV_VAR_NAME_RE.fullmatch(var_name):
                            logger.warning(
                                "Skipping invalid env var name in hook metadata: %r (hook=%s)",
                                var_name,
                                script.name,
                            )
                            continue
                        env_exports.append(f"export {var_name}={shlex.quote(var_value)}")
                if env_exports:
                    calls.extend(env_exports)

                # Content hooks: cat the file
                if script.name.endswith((".stdout.md", ".stdout.txt")) or suffix in (".md", ".txt"):
                    try:
                        cat_path = _get_interpreter_path("cat")
                    except FileNotFoundError:
                        cat_path = "cat"
                    calls.append(f'[[ -f {safe_path} ]] && {cat_path} {safe_path}')
                elif suffix == ".py":
                    calls.append(
                        f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {python_cmd} {safe_path} || exit $?; }}'
                    )
                elif suffix == ".sh":
                    try:
                        bash_path = _get_interpreter_path("bash")
                    except FileNotFoundError:
                        bash_path = "bash"
                    calls.append(
                        f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {bash_path} {safe_path} || exit $?; }}'
                    )
                elif suffix == ".js":
                    try:
                        node_path = _get_interpreter_path("node")
                    except FileNotFoundError:
                        node_path = "node"
                    calls.append(
                        f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {node_path} {safe_path} || exit $?; }}'
                    )
                elif suffix == ".ts":
                    try:
                        bun_path = _get_interpreter_path("bun")
                    except FileNotFoundError:
                        bun_path = "bun"
                    calls.append(
                        f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {bun_path} run {safe_path} || exit $?; }}'
                    )
                else:
                    calls.append(
                        f'[[ -f {safe_path} ]] && {{ echo "$INPUT" | {safe_path} || exit $?; }}'
                    )

            hook_calls_str = "\n".join(calls)
            content = f"""#!/usr/bin/env bash
# Auto-generated by hawk v2 - do not edit manually
# Event: {event}
# Regenerate with: hawk sync --force

set -euo pipefail

INPUT=$(cat)

{hook_calls_str}

exit 0
"""
            runner_path = runners_dir / f"{event}.sh"
            _atomic_write_executable(runner_path, content)
            runners[event] = runner_path

        # Clean up stale runners for events that no longer have hooks
        for existing in runners_dir.iterdir():
            if existing.suffix == ".sh" and existing.stem not in hooks_by_event:
                existing.unlink()

        return runners
