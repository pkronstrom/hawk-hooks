"""OpenCode adapter for hawk-hooks v2."""

from __future__ import annotations

import json
from pathlib import Path

from ..types import Tool
from .base import HAWK_MCP_MARKER, ToolAdapter


class OpenCodeAdapter(ToolAdapter):
    """Adapter for OpenCode."""
    HOOK_SUPPORT = "bridge"

    @property
    def tool(self) -> Tool:
        return Tool.OPENCODE

    def detect_installed(self) -> bool:
        return self.get_global_dir().exists()

    def get_global_dir(self) -> Path:
        return Path.home() / ".config" / "opencode"

    def get_project_dir(self, project: Path) -> Path:
        return project / ".opencode"

    def get_prompts_dir(self, target_dir: Path) -> Path:
        """OpenCode prompts map to command markdown files."""
        return self.get_commands_dir(target_dir)

    def register_hooks(self, hook_names: list[str], target_dir: Path, registry_path: Path | None = None) -> list[str]:
        """Bridge hook runners into OpenCode via a generated plugin."""
        from ..event_mapping import get_event_support, get_tool_event_or_none
        from ..hook_meta import parse_hook_meta

        skipped: list[str] = []
        runners_dir = target_dir / "runners"
        plugin_path = target_dir / "plugins" / "hawk-hooks.ts"

        if not hook_names or registry_path is None:
            if runners_dir.exists():
                for f in runners_dir.iterdir():
                    if f.suffix == ".sh":
                        f.unlink()
            plugin_path.unlink(missing_ok=True)
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
                f"prompt hooks are unsupported by opencode and were skipped: {', '.join(sorted(prompt_hooks))}"
            )

        runners = self._generate_runners(script_hooks, registry_path, runners_dir) if script_hooks else {}
        mapped_events: dict[str, list[str]] = {}
        bridged_events: set[str] = set()

        for event_name, runner_path in sorted(runners.items()):
            support = get_event_support(event_name, "opencode")
            tool_event = get_tool_event_or_none(event_name, "opencode")
            if support == "unsupported" or not tool_event:
                skipped.append(f"{event_name} is unsupported by opencode and was skipped")
                runner_path.unlink(missing_ok=True)
                continue
            mapped_events.setdefault(tool_event, []).append(str(runner_path))
            bridged_events.add(event_name)

        if mapped_events:
            self._write_hook_plugin(plugin_path, mapped_events)
        else:
            plugin_path.unlink(missing_ok=True)

        registered: list[str] = []
        for name in script_hooks:
            hook_path = hooks_dir / name
            if not hook_path.is_file():
                continue
            events = parse_hook_meta(hook_path).events
            if any(event in bridged_events for event in events):
                registered.append(name)

        self._set_hook_diagnostics(skipped=skipped, errors=[])
        return registered

    def write_mcp_config(
        self,
        servers: dict[str, dict],
        target_dir: Path,
    ) -> None:
        """Write MCP config into opencode.json under the native `mcp` key.

        - Preserves manual entries in either legacy `mcpServers` or native `mcp`
        - Migrates legacy manual entries into `mcp`
        - Tracks hawk-managed names via sidecar (no inline marker injection)
        """
        config_path = target_dir / "opencode.json"
        sidecar_path = target_dir / ".hawk-mcp.json"

        data: dict = {}
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}

        native = data.get("mcp", {})
        legacy = data.get("mcpServers", {})
        if not isinstance(native, dict):
            native = {}
        if not isinstance(legacy, dict):
            legacy = {}

        old_managed: set[str] = set()
        if sidecar_path.exists():
            try:
                old_managed = set(json.loads(sidecar_path.read_text()))
            except (json.JSONDecodeError, OSError):
                old_managed = set()

        for bucket in (native, legacy):
            for name, cfg in bucket.items():
                if isinstance(cfg, dict) and cfg.get(HAWK_MCP_MARKER):
                    old_managed.add(name)

        merged: dict[str, dict] = {}
        for name, cfg in native.items():
            if name in old_managed:
                continue
            if isinstance(cfg, dict):
                cfg = {k: v for k, v in cfg.items() if k != HAWK_MCP_MARKER}
            merged[name] = cfg

        # Backward-compatible migration: carry manual legacy mcpServers entries.
        for name, cfg in legacy.items():
            if name in old_managed or name in merged:
                continue
            if isinstance(cfg, dict):
                cfg = {k: v for k, v in cfg.items() if k != HAWK_MCP_MARKER}
            merged[name] = cfg

        for name, cfg in servers.items():
            merged[name] = cfg

        data["mcp"] = merged
        data.pop("mcpServers", None)

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2) + "\n")

        managed_names = sorted(servers.keys())
        if managed_names:
            sidecar_path.write_text(json.dumps(managed_names, indent=2) + "\n")
        elif sidecar_path.exists():
            sidecar_path.unlink()

    @staticmethod
    def _write_hook_plugin(plugin_path: Path, mapped_events: dict[str, list[str]]) -> None:
        """Write an OpenCode plugin that executes hawk event runners."""
        plugin_path.parent.mkdir(parents=True, exist_ok=True)

        event_lines: list[str] = []
        for event_name in sorted(mapped_events.keys()):
            commands = mapped_events[event_name]
            calls = "\n".join(f"      await runHook({json.dumps(cmd)}, input);" for cmd in commands)
            event_lines.append(
                f'    {json.dumps(event_name)}: async (input) => {{\n{calls}\n    }},'
            )
        event_block = "\n".join(event_lines)

        content = (
            "// hawk-hooks managed: opencode-hook-plugin\n"
            'import { definePlugin } from "@opencode-ai/plugin"\n\n'
            "async function runHook(command: string, payload: unknown): Promise<void> {\n"
            "  const input = JSON.stringify(payload ?? {});\n"
            "  const proc = Bun.spawn([command], {\n"
            "    stdin: \"pipe\",\n"
            "    stdout: \"ignore\",\n"
            "    stderr: \"pipe\",\n"
            "  });\n"
            "  const writer = proc.stdin.getWriter();\n"
            "  await writer.write(new TextEncoder().encode(input));\n"
            "  await writer.close();\n"
            "  const exitCode = await proc.exited;\n"
            "  if (exitCode !== 0) {\n"
            "    const stderr = await new Response(proc.stderr).text();\n"
            "    throw new Error(`hawk hook failed (${exitCode}): ${stderr}`.trim());\n"
            "  }\n"
            "}\n\n"
            "export default definePlugin({\n"
            "  event: {\n"
            f"{event_block}\n"
            "  },\n"
            "});\n"
        )
        plugin_path.write_text(content)
