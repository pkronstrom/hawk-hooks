"""Claude Code adapter for hawk-hooks v2."""

from __future__ import annotations

import json
from pathlib import Path

from ..types import Tool
from .base import HAWK_MCP_MARKER, ToolAdapter

# Marker to identify hawk-managed hook entries in settings.json
_HAWK_HOOK_MARKER = "__hawk_managed"


class ClaudeAdapter(ToolAdapter):
    """Adapter for Claude Code."""

    @property
    def tool(self) -> Tool:
        return Tool.CLAUDE

    def detect_installed(self) -> bool:
        return self.get_global_dir().exists()

    def get_global_dir(self) -> Path:
        return Path.home() / ".claude"

    def get_project_dir(self, project: Path) -> Path:
        return project / ".claude"

    # Claude uses standard symlink behavior for skills, agents, commands
    # (inherited from base class)

    def get_prompts_dir(self, target_dir: Path) -> Path:
        """Prompts go into Claude's commands/ directory."""
        return self.get_commands_dir(target_dir)

    def register_hooks(self, hook_names: list[str], target_dir: Path, registry_path: Path | None = None) -> list[str]:
        """Register hooks via bash runners and prompt entries in Claude's settings.json.

        1. Separate .prompt.json hooks from script hooks.
        2. Generate runners (one per event) for script hooks.
        3. Register runners as type: "command" entries.
        4. Register .prompt.json as type: "prompt" entries.
        5. Compute max timeout per event across all hooks.
        6. Remove stale hawk-managed entries.
        """
        from ..events import EVENTS
        from ..hook_meta import parse_hook_meta

        runners_dir = target_dir / "runners"

        if not hook_names or registry_path is None:
            # No hooks — clean up any existing hawk entries
            self._remove_hawk_hooks(target_dir)
            # Clean up stale runners
            if runners_dir.exists():
                for f in runners_dir.iterdir():
                    if f.suffix == ".sh":
                        f.unlink()
            return []

        hooks_dir = registry_path / "hooks"

        # Separate prompt hooks from script hooks
        script_hooks = []
        prompt_hooks = []
        for name in hook_names:
            if name.endswith(".prompt.json"):
                prompt_hooks.append(name)
            else:
                script_hooks.append(name)

        # Generate runners for script hooks
        runners = self._generate_runners(script_hooks, registry_path, runners_dir) if script_hooks else {}

        # Collect timeout per event from all script hooks
        event_timeouts: dict[str, int] = {}
        for name in script_hooks:
            hook_path = hooks_dir / name
            if not hook_path.is_file():
                continue
            meta = parse_hook_meta(hook_path)
            for event in meta.events:
                if event in runners and meta.timeout > 0:
                    event_timeouts[event] = max(event_timeouts.get(event, 0), meta.timeout)

        # Load settings.json
        settings_path = target_dir / "settings.json"
        settings = self._load_json(settings_path)

        # Remove existing hawk-managed hook entries
        existing_hooks = settings.get("hooks", [])
        user_hooks = [h for h in existing_hooks if not self._is_hawk_hook(h)]

        # Add hawk entries for each runner (command hooks)
        hawk_entries = []
        for event_name, runner_path in sorted(runners.items()):
            # Map canonical event name to Claude's PascalCase matcher
            event_def = EVENTS.get(event_name)
            matcher = event_def.claude_name if event_def else event_name

            hook_def: dict = {
                "type": "command",
                "command": str(runner_path),
                _HAWK_HOOK_MARKER: True,
            }
            if event_name in event_timeouts:
                hook_def["timeout"] = event_timeouts[event_name]

            hawk_entries.append({
                "matcher": matcher,
                "hooks": [hook_def],
            })

        # Add hawk entries for prompt hooks (.prompt.json)
        registered_prompt_hooks: set[str] = set()
        for name in prompt_hooks:
            hook_path = hooks_dir / name
            if not hook_path.is_file():
                continue
            try:
                data = json.loads(hook_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(data, dict):
                continue

            prompt_text = data.get("prompt", "")
            if not prompt_text:
                continue

            # Determine events from hawk-hook metadata, or default to pre_tool_use
            meta = parse_hook_meta(hook_path)
            events = meta.events if meta.events else ["pre_tool_use"]
            try:
                timeout = int(data.get("timeout", meta.timeout))
            except (ValueError, TypeError):
                timeout = 0

            for event in events:
                event_def = EVENTS.get(event)
                if not event_def:
                    continue
                matcher = event_def.claude_name

                hook_def = {
                    "type": "prompt",
                    "prompt": prompt_text,
                    _HAWK_HOOK_MARKER: True,
                }
                if timeout > 0:
                    hook_def["timeout"] = timeout

                hawk_entries.append({
                    "matcher": matcher,
                    "hooks": [hook_def],
                })
                registered_prompt_hooks.add(name)

        settings["hooks"] = user_hooks + hawk_entries
        self._save_json(settings_path, settings)

        # Return hook names that ended up registered
        registered = []
        for name in script_hooks:
            hook_path = hooks_dir / name
            if hook_path.is_file():
                meta = parse_hook_meta(hook_path)
                if any(event in runners for event in meta.events):
                    registered.append(name)
        registered.extend(sorted(registered_prompt_hooks))
        return registered

    def write_mcp_config(
        self,
        servers: dict[str, dict],
        target_dir: Path,
    ) -> None:
        """Merge hawk-managed MCP servers into .mcp.json."""
        self._merge_mcp_json(target_dir / ".mcp.json", servers)

    def read_mcp_config(self, target_dir: Path) -> dict[str, dict]:
        """Read current MCP config, returning only hawk-managed entries."""
        return self._read_mcp_json(target_dir / ".mcp.json")

    # ── Hook helpers ──

    def _remove_hawk_hooks(self, target_dir: Path) -> None:
        """Remove all hawk-managed hook entries from settings.json."""
        settings_path = target_dir / "settings.json"
        settings = self._load_json(settings_path)
        existing_hooks = settings.get("hooks", [])
        user_hooks = [h for h in existing_hooks if not self._is_hawk_hook(h)]
        if len(user_hooks) != len(existing_hooks):
            settings["hooks"] = user_hooks
            self._save_json(settings_path, settings)

    @staticmethod
    def _is_hawk_hook(hook_entry: dict) -> bool:
        """Check if a hook entry is hawk-managed."""
        hooks = hook_entry.get("hooks", [])
        return any(h.get(_HAWK_HOOK_MARKER) for h in hooks)

    @staticmethod
    def _load_json(path: Path) -> dict:
        """Load a JSON file, returning empty dict if missing/invalid."""
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    @staticmethod
    def _save_json(path: Path, data: dict) -> None:
        """Save a dict as JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")
