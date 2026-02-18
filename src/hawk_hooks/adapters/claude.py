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
        """Register hooks via bash runners in Claude's settings.json.

        1. Generate runners (one per event) from hook references.
        2. Register each runner in settings.json as a hook entry.
        3. Remove stale hawk-managed entries.
        """
        from ..events import EVENTS
        from .. import v2_config

        runners_dir = v2_config.get_config_dir() / "runners"

        if not hook_names or registry_path is None:
            # No hooks — clean up any existing hawk entries
            self._remove_hawk_hooks(target_dir)
            # Clean up stale runners
            if runners_dir.exists():
                for f in runners_dir.iterdir():
                    if f.suffix == ".sh":
                        f.unlink()
            return []

        # Generate runners
        runners = self._generate_runners(hook_names, registry_path, runners_dir)

        # Load settings.json
        settings_path = target_dir / "settings.json"
        settings = self._load_json(settings_path)

        # Remove existing hawk-managed hook entries
        existing_hooks = settings.get("hooks", [])
        user_hooks = [h for h in existing_hooks if not self._is_hawk_hook(h)]

        # Add new hawk entries for each runner
        hawk_entries = []
        for event_name, runner_path in sorted(runners.items()):
            # Map canonical event name to Claude's PascalCase matcher
            event_def = EVENTS.get(event_name)
            matcher = event_def.claude_name if event_def else event_name

            hawk_entries.append({
                "matcher": matcher,
                "hooks": [{
                    "type": "command",
                    "command": str(runner_path),
                    _HAWK_HOOK_MARKER: True,
                }],
            })

        settings["hooks"] = user_hooks + hawk_entries
        self._save_json(settings_path, settings)

        # Return hook names that ended up in at least one runner
        from ..hook_meta import parse_hook_meta
        hooks_dir = registry_path / "hooks"
        registered = []
        for name in hook_names:
            hook_path = hooks_dir / name
            if hook_path.is_file():
                meta = parse_hook_meta(hook_path)
                if any(event in runners for event in meta.events):
                    registered.append(name)
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
