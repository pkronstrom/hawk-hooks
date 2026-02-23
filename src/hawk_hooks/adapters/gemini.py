"""Gemini CLI adapter for hawk-hooks v2."""

from __future__ import annotations

import json
from pathlib import Path
import re

from ..types import Tool
from .base import ToolAdapter

_HAWK_HOOK_MARKER = "__hawk_managed"


def _escape_toml_string(s: str) -> str:
    """Escape a string for TOML basic string (double-quoted)."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def md_to_toml(source: Path) -> str:
    """Convert a markdown command file to Gemini TOML format.

    Reads the markdown file, extracts frontmatter (if any), and generates
    a TOML command file with name, description, and prompt fields.
    """
    content = source.read_text()

    # Try to parse frontmatter
    name = source.stem
    description = ""
    body = content

    # Simple frontmatter extraction
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            import yaml

            try:
                fm = yaml.safe_load(parts[1])
                if isinstance(fm, dict):
                    name = fm.get("name", name)
                    description = fm.get("description", "")
                body = parts[2].strip()
            except Exception:
                body = content

    name_escaped = _escape_toml_string(name)
    desc_escaped = _escape_toml_string(description)
    # Use TOML multiline literal string for body
    body_escaped = body.replace("'''", "'''\"'''\"'''")

    return f"""name = "{name_escaped}"
description = "{desc_escaped}"

prompt = '''
{body_escaped}
'''
"""


class GeminiAdapter(ToolAdapter):
    """Adapter for Gemini CLI."""
    HOOK_SUPPORT = "native"

    @property
    def tool(self) -> Tool:
        return Tool.GEMINI

    def detect_installed(self) -> bool:
        return self.get_global_dir().exists()

    def get_global_dir(self) -> Path:
        return Path.home() / ".gemini"

    def get_project_dir(self, project: Path) -> Path:
        return project / ".gemini"

    def link_command(self, source: Path, target_dir: Path) -> Path:
        """Convert markdown command to TOML and write to commands dir."""
        commands_dir = self.get_commands_dir(target_dir)
        commands_dir.mkdir(parents=True, exist_ok=True)

        # Generate TOML filename
        dest = commands_dir / f"{source.stem}.toml"

        toml_content = md_to_toml(source)
        dest.write_text(toml_content)
        return dest

    def unlink_command(self, name: str, target_dir: Path) -> bool:
        """Remove a TOML command file."""
        commands_dir = self.get_commands_dir(target_dir)
        # Try both .toml and .md extensions
        for ext in [".toml", ".md", ""]:
            stem = name.rsplit(".", 1)[0] if "." in name else name
            path = commands_dir / f"{stem}{ext}" if ext else commands_dir / name
            if path.exists():
                path.unlink()
                return True
        return False

    def get_prompts_dir(self, target_dir: Path) -> Path:
        """Gemini slash prompts are stored in the commands directory."""
        return self.get_commands_dir(target_dir)

    def link_prompt(self, source: Path, target_dir: Path) -> Path:
        """Prompts use the same TOML conversion pipeline as commands."""
        return self.link_command(source, target_dir)

    def unlink_prompt(self, name: str, target_dir: Path) -> bool:
        """Prompts use the same cleanup behavior as commands."""
        return self.unlink_command(name, target_dir)

    @staticmethod
    def _find_current_toml_commands(comp_dir: Path, source_dir: Path) -> set[str]:
        """Find .toml command files whose stems match registry .md names."""
        current: set[str] = set()
        if not comp_dir.exists():
            return current
        registry_stems = set()
        if source_dir.exists():
            registry_stems = {f.stem for f in source_dir.iterdir() if f.is_file()}
        for entry in comp_dir.iterdir():
            if entry.suffix == ".toml" and entry.stem in registry_stems:
                # Return the .md name so it matches the desired set
                current.add(f"{entry.stem}.md")
        return current

    def sync(self, resolved, target_dir: Path, registry_path: Path):
        """Override sync to pass custom command finder for toml cleanup."""
        from ..types import SyncResult
        from ..registry import _validate_name

        result = SyncResult(tool=str(self.tool))

        for dir_getter in [self.get_skills_dir, self.get_agents_dir, self.get_prompts_dir]:
            dir_getter(target_dir).mkdir(parents=True, exist_ok=True)

        self._sync_component(resolved.skills, registry_path / "skills", target_dir,
                             self.link_skill, self.unlink_skill, self.get_skills_dir, result)
        self._sync_component(resolved.agents, registry_path / "agents", target_dir,
                             self.link_agent, self.unlink_agent, self.get_agents_dir, result)
        # Prompts: use toml-aware finder because Gemini expects .toml command files.
        self._sync_component(
            resolved.prompts,
            registry_path / "prompts",
            target_dir,
            self.link_prompt,
            self.unlink_prompt,
            self.get_prompts_dir,
            result,
            find_current_fn=self._find_current_toml_commands,
        )

        try:
            self._set_hook_diagnostics(skipped=[], errors=[])
            registered = self.register_hooks(resolved.hooks, target_dir, registry_path=registry_path)
            result.linked.extend(f"hook:{h}" for h in registered)
            for skipped in self._take_hook_skipped():
                result.skipped.append(f"hooks: {skipped}")
            for hook_error in self._take_hook_errors():
                result.errors.append(f"hooks: {hook_error}")
        except Exception as e:
            result.errors.append(f"hooks: {e}")

        try:
            servers = self._load_mcp_servers(resolved.mcp, registry_path / "mcp") if resolved.mcp else {}
            self.write_mcp_config(servers, target_dir)
            result.linked.extend(f"mcp:{name}" for name in servers)
        except Exception as e:
            result.errors.append(f"mcp: {e}")

        return result

    def register_hooks(self, hook_names: list[str], target_dir: Path, registry_path: Path | None = None) -> list[str]:
        """Register command hooks in Gemini settings.json.

        Gemini uses a Claude-like hooks array in settings.json. It only
        supports command hooks natively. Hawk bridges .prompt.json hooks by
        generating command runners that inject `additionalContext`.
        """
        from ..event_mapping import get_event_support, get_tool_event_or_none
        from ..hook_meta import parse_hook_meta

        skipped: list[str] = []
        runners_dir = target_dir / "runners"

        if not hook_names or registry_path is None:
            self._remove_hawk_hooks(target_dir)
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

        runners = self._generate_runners(script_hooks, registry_path, runners_dir) if script_hooks else {}
        for stale in runners_dir.glob("prompt-*.sh"):
            stale.unlink(missing_ok=True)

        event_timeouts: dict[str, int] = {}
        for name in script_hooks:
            hook_path = hooks_dir / name
            if not hook_path.is_file():
                continue
            meta = parse_hook_meta(hook_path)
            for event in meta.events:
                if event in runners and meta.timeout > 0:
                    event_timeouts[event] = max(event_timeouts.get(event, 0), meta.timeout)

        settings_path = target_dir / "settings.json"
        settings = self._load_json(settings_path)
        existing_hooks = settings.get("hooks", [])
        if not isinstance(existing_hooks, list):
            existing_hooks = [existing_hooks] if existing_hooks else []
        user_hooks = [h for h in existing_hooks if not self._is_hawk_hook(h)]

        hawk_entries: list[dict] = []
        registered_events: set[str] = set()

        for event_name, runner_path in sorted(runners.items()):
            support = get_event_support(event_name, "gemini")
            matcher = get_tool_event_or_none(event_name, "gemini")
            if support == "unsupported" or not matcher:
                skipped.append(f"{event_name} is unsupported by gemini and was skipped")
                runner_path.unlink(missing_ok=True)
                continue

            hook_def: dict = {
                "type": "command",
                "command": str(runner_path),
                _HAWK_HOOK_MARKER: True,
            }
            if event_name in event_timeouts:
                hook_def["timeout"] = event_timeouts[event_name]

            hawk_entries.append(
                {
                    "matcher": matcher,
                    "hooks": [hook_def],
                }
            )
            registered_events.add(event_name)

        registered_prompt_hooks: set[str] = set()
        for name in prompt_hooks:
            hook_path = hooks_dir / name
            if not hook_path.is_file():
                continue
            try:
                data = json.loads(hook_path.read_text())
            except (json.JSONDecodeError, OSError):
                skipped.append(f"{name} is invalid JSON and was skipped")
                continue
            if not isinstance(data, dict):
                skipped.append(f"{name} is not a JSON object and was skipped")
                continue

            prompt_text = str(data.get("prompt", "")).strip()
            if not prompt_text:
                skipped.append(f"{name} has no prompt text and was skipped")
                continue

            meta = parse_hook_meta(hook_path)
            events = meta.events if meta.events else ["pre_tool_use"]
            try:
                timeout = int(data.get("timeout", meta.timeout))
            except (TypeError, ValueError):
                timeout = 0

            for event_name in events:
                support = get_event_support(event_name, "gemini")
                matcher = get_tool_event_or_none(event_name, "gemini")
                if support == "unsupported" or not matcher:
                    skipped.append(f"{event_name} is unsupported by gemini and was skipped")
                    continue

                bridge_path = self._write_prompt_bridge_runner(
                    runners_dir=runners_dir,
                    hook_name=name,
                    event_name=event_name,
                    prompt_text=prompt_text,
                )
                hook_def: dict = {
                    "type": "command",
                    "command": str(bridge_path),
                    _HAWK_HOOK_MARKER: True,
                }
                if timeout > 0:
                    hook_def["timeout"] = timeout

                hawk_entries.append(
                    {
                        "matcher": matcher,
                        "hooks": [hook_def],
                    }
                )
                registered_prompt_hooks.add(name)

        settings["hooks"] = user_hooks + hawk_entries
        self._save_json(settings_path, settings)

        registered: list[str] = []
        for name in script_hooks:
            hook_path = hooks_dir / name
            if not hook_path.is_file():
                continue
            events = parse_hook_meta(hook_path).events
            if any(event in registered_events for event in events):
                registered.append(name)

        registered.extend(sorted(registered_prompt_hooks))
        self._set_hook_diagnostics(skipped=skipped, errors=[])
        return registered

    def write_mcp_config(
        self,
        servers: dict[str, dict],
        target_dir: Path,
    ) -> None:
        """Merge hawk-managed MCP servers into .gemini/settings.json.

        Uses sidecar tracking to avoid injecting __hawk_managed into
        server entries, which Gemini's strict config validation rejects.
        """
        self._merge_mcp_sidecar(target_dir / "settings.json", servers)

    # -- Hook helpers --

    def _remove_hawk_hooks(self, target_dir: Path) -> None:
        settings_path = target_dir / "settings.json"
        settings = self._load_json(settings_path)
        existing_hooks = settings.get("hooks", [])
        if not isinstance(existing_hooks, list):
            existing_hooks = [existing_hooks] if existing_hooks else []
        user_hooks = [h for h in existing_hooks if not self._is_hawk_hook(h)]
        if len(user_hooks) != len(existing_hooks):
            settings["hooks"] = user_hooks
            self._save_json(settings_path, settings)

    @staticmethod
    def _is_hawk_hook(hook_entry: object) -> bool:
        if not isinstance(hook_entry, dict):
            return False
        hooks = hook_entry.get("hooks", [])
        if not isinstance(hooks, list):
            return False
        return any(isinstance(h, dict) and h.get(_HAWK_HOOK_MARKER) for h in hooks)

    @staticmethod
    def _load_json(path: Path) -> dict:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    @staticmethod
    def _save_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")

    @staticmethod
    def _write_prompt_bridge_runner(
        *,
        runners_dir: Path,
        hook_name: str,
        event_name: str,
        prompt_text: str,
    ) -> Path:
        """Generate a command hook runner that injects prompt text as context."""
        import shlex
        from ..runner_utils import _atomic_write_executable

        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(hook_name).stem).strip("-") or "prompt"
        safe_event = re.sub(r"[^A-Za-z0-9._-]+", "-", event_name).strip("-") or "event"
        runner_path = runners_dir / f"prompt-{stem}-{safe_event}.sh"
        payload = json.dumps(
            {
                "hookSpecificOutput": {
                    "additionalContext": prompt_text,
                }
            }
        )
        quoted_payload = shlex.quote(payload)
        content = (
            "#!/usr/bin/env bash\n"
            "# Auto-generated by hawk v2 - Gemini prompt hook bridge\n"
            "set -euo pipefail\n"
            "cat >/dev/null\n"
            f"printf '%s\\n' {quoted_payload}\n"
        )
        _atomic_write_executable(runner_path, content)
        return runner_path
