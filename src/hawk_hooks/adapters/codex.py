"""Codex CLI adapter for hawk-hooks v2."""

from __future__ import annotations

import re
from pathlib import Path

from ..types import Tool
from .base import HAWK_MCP_MARKER, ToolAdapter

_BEGIN_NOTIFY_BLOCK = "# >>> hawk-hooks notify >>>"
_END_NOTIFY_BLOCK = "# <<< hawk-hooks notify <<<"


class CodexAdapter(ToolAdapter):
    """Adapter for Codex CLI."""
    HOOK_SUPPORT = "bridge"

    @property
    def tool(self) -> Tool:
        return Tool.CODEX

    def detect_installed(self) -> bool:
        return self.get_global_dir().exists()

    def get_global_dir(self) -> Path:
        return Path.home() / ".codex"

    def get_project_dir(self, project: Path) -> Path:
        return project / ".codex"

    def get_skills_dir(self, target_dir: Path) -> Path:
        """Codex uses a flat agents/ dir for skills."""
        return target_dir / "agents"

    def get_agents_dir(self, target_dir: Path) -> Path:
        """Codex doesn't have a separate agents concept, reuse agents/."""
        return target_dir / "agents"

    def get_commands_dir(self, target_dir: Path) -> Path:
        """Codex doesn't have slash commands; commands become skills."""
        return target_dir / "agents"

    def register_hooks(self, hook_names: list[str], target_dir: Path, registry_path: Path | None = None) -> list[str]:
        """Register limited hook bridge using Codex notify callbacks.

        Codex currently exposes a minimal notify callback path (turn-complete),
        so we bridge only stop/notification class events.
        """
        from ..event_mapping import get_event_support
        from ..hook_meta import parse_hook_meta

        skipped: list[str] = []
        errors: list[str] = []
        runners_dir = target_dir / "runners"
        config_path = target_dir / "config.toml"

        if not hook_names or registry_path is None:
            self._update_notify_block(config_path, [])
            if runners_dir.exists():
                for f in runners_dir.iterdir():
                    if f.suffix == ".sh":
                        f.unlink()
            self._set_hook_diagnostics(skipped=[], errors=[])
            return []

        hooks_dir = registry_path / "hooks"

        script_hooks: list[str] = []
        prompt_hooks: list[str] = []
        for name in hook_names:
            if name.endswith(".prompt.json"):
                prompt_hooks.append(name)
            else:
                script_hooks.append(name)

        if prompt_hooks:
            skipped.append(
                f"prompt hooks are unsupported by codex and were skipped: {', '.join(sorted(prompt_hooks))}"
            )

        runners = self._generate_runners(script_hooks, registry_path, runners_dir) if script_hooks else {}

        notify_commands: list[str] = []
        bridged_events: set[str] = set()
        for event_name, runner_path in sorted(runners.items()):
            if get_event_support(event_name, "codex") == "bridge":
                notify_commands.append(str(runner_path))
                bridged_events.add(event_name)
            else:
                skipped.append(f"{event_name} is unsupported by codex and was skipped")
                runner_path.unlink(missing_ok=True)

        if self._has_manual_notify_key_outside_block(config_path):
            errors.append("codex config.toml has a manual notify key; hawk notify bridge was not modified")
            self._set_hook_diagnostics(skipped=skipped, errors=errors)
            return []

        self._update_notify_block(config_path, notify_commands)

        registered: list[str] = []
        for name in script_hooks:
            hook_path = hooks_dir / name
            if not hook_path.is_file():
                continue
            events = parse_hook_meta(hook_path).events
            if any(event in bridged_events for event in events):
                registered.append(name)

        self._set_hook_diagnostics(skipped=skipped, errors=errors)
        return registered

    def write_mcp_config(
        self,
        servers: dict[str, dict],
        target_dir: Path,
    ) -> None:
        """Write MCP config for Codex (mcp.json)."""
        self._merge_mcp_json(target_dir / "mcp.json", servers)

    @staticmethod
    def _update_notify_block(config_path: Path, commands: list[str]) -> None:
        """Insert/replace/remove hawk-managed notify block in config.toml."""
        text = config_path.read_text() if config_path.exists() else ""
        block_re = re.compile(
            rf"{re.escape(_BEGIN_NOTIFY_BLOCK)}\n.*?{re.escape(_END_NOTIFY_BLOCK)}\n?",
            re.DOTALL,
        )
        text = block_re.sub("", text).rstrip()

        if commands:
            lines = [
                _BEGIN_NOTIFY_BLOCK,
                "notify = [",
                *[f'  "{cmd}",' for cmd in commands],
                "]",
                _END_NOTIFY_BLOCK,
            ]
            block = "\n".join(lines)
            text = f"{text}\n\n{block}\n" if text else f"{block}\n"
        elif text:
            text = text + "\n"

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(text)

    @staticmethod
    def _has_manual_notify_key_outside_block(config_path: Path) -> bool:
        """Detect user-managed notify keys to avoid TOML key collisions."""
        if not config_path.exists():
            return False
        text = config_path.read_text()
        block_re = re.compile(
            rf"{re.escape(_BEGIN_NOTIFY_BLOCK)}\n.*?{re.escape(_END_NOTIFY_BLOCK)}\n?",
            re.DOTALL,
        )
        stripped = block_re.sub("", text)
        return bool(re.search(r"(?m)^\s*notify\s*=", stripped))
