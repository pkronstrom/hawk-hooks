"""Google Antigravity adapter for hawk-hooks v2.

Antigravity replaced Gemini CLI, which Google sunset. The `agy` CLI, the
Antigravity IDE and Antigravity 2.0 all share one customization system:

- Global customization root: ``~/.gemini/config/``
- Workspace customization root: ``<project>/.agents/``
- Skills:  ``<root>/skills/<name>/SKILL.md``
- Agents:  ``<root>/agents/<name>.md`` (YAML frontmatter with name+description)
- Hooks:   ``<root>/hooks.json``
- MCP:     ``<root>/mcp_config.json`` (``mcpServers`` map)

Capability verification (2026-08-04, agy 1.1.10, probed against the live CLI):

- Verified working:
  - Skills in ``~/.gemini/config/skills/`` are discovered and listed.
  - Agents in ``~/.gemini/config/agents/*.md`` appear in ``agy agents``.
  - ``~/.gemini/config/hooks.json`` fires natively; a ``PreInvocation`` hook
    injecting an ``ephemeralMessage`` reached the model.
  - MCP servers load from ``~/.gemini/config/mcp_config.json``.
- Verified NOT working:
  - Custom slash commands. Neither ``.toml`` nor ``.md`` files in
    ``~/.gemini/commands/`` are recognized; agy ships a fixed set of built-ins
    (/plan, /goal, /schedule, /learn, /grill-me). Antigravity's own docs direct
    custom workflows to skills instead, so hawk reports prompts as unsupported.
  - Workspace ``.agents/`` discovery in the CLI. A skill placed in a trusted
    repo's ``.agents/skills/`` was not picked up by agy 1.1.10, with or without
    a declaring ``.agents/skills.json``. ``.agents/`` remains the documented
    workspace root (and is what the IDE reads), so project sync still writes
    there — but the CLI will not see it until Google ships that discovery path.

Hook bridge contract
--------------------
Antigravity hooks exchange JSON: the payload arrives on stdin (camelCase) and
the handler must answer with a JSON object on stdout. Hawk hooks use Claude
semantics instead (exit 0 = proceed, non-zero = block), so each event gets a
generated bridge wrapper that runs hawk's normal runner and translates the
result.

``PreToolUse`` answers ``{"decision": "ask"}`` when the hook passes. This was
chosen deliberately: an empty ``{}`` response *denies* the tool call (verified),
and ``"allow"`` would auto-approve every tool call the moment any pre_tool_use
hook is registered, silently disabling Antigravity's permission prompts.
``"ask"`` honors the normal permission flow — it respects the "Always Allow"
cache in interactive sessions and is auto-approved under
``--dangerously-skip-permissions`` (both verified), so it fails safe without
breaking headless runs.
"""

from __future__ import annotations

import json
import shlex
import shutil
from pathlib import Path

from ..types import Tool
from .base import ToolAdapter

# Single top-level key in hooks.json owned by hawk. Everything else in the
# file belongs to the user (or other tools) and is preserved verbatim.
_HAWK_HOOK_KEY = "hawk"

# Antigravity events that wrap handlers in a {matcher, hooks} group. The rest
# (Stop, PreInvocation, PostInvocation) take a flat list of handler objects.
_GROUPED_EVENTS = frozenset({"PreToolUse", "PostToolUse"})

# Cap on hook output echoed back to the agent as a deny/continue reason.
_MAX_REASON_CHARS = 4000


class AntigravityAdapter(ToolAdapter):
    """Adapter for Google Antigravity (agy CLI, IDE and Antigravity 2.0)."""

    HOOK_SUPPORT = "native"

    @property
    def tool(self) -> Tool:
        return Tool.ANTIGRAVITY

    def detect_installed(self) -> bool:
        return shutil.which("agy") is not None or self.get_global_dir().exists()

    def get_global_dir(self) -> Path:
        return Path.home() / ".gemini" / "config"

    def get_project_dir(self, project: Path) -> Path:
        return project / ".agents"

    # ── Components ──

    def get_skills_dir(self, target_dir: Path) -> Path:
        return target_dir / "skills"

    def get_agents_dir(self, target_dir: Path) -> Path:
        return target_dir / "agents"

    # ── Sync ──

    def sync(self, resolved, target_dir: Path, registry_path: Path):
        """Sync skills, agents, hooks and MCP. Prompts are unsupported.

        Antigravity has no custom slash commands, so registered prompts are
        reported as skipped rather than written somewhere agy will never read.
        """
        from ..types import SyncResult

        result = SyncResult(tool=str(self.tool))

        for dir_getter in (self.get_skills_dir, self.get_agents_dir):
            dir_getter(target_dir).mkdir(parents=True, exist_ok=True)

        self._sync_component(
            resolved.skills, registry_path / "skills", target_dir,
            self.link_skill, self.unlink_skill, self.get_skills_dir, result,
        )
        self._sync_component(
            resolved.agents, registry_path / "agents", target_dir,
            self.link_agent, self.unlink_agent, self.get_agents_dir, result,
        )

        prompt_count = len(resolved.prompts) + len(resolved.commands)
        if prompt_count:
            result.skipped.append(
                f"prompts: antigravity has no custom slash commands; "
                f"skipped {prompt_count} prompt(s)"
            )
        self._remove_legacy_prompt_links(target_dir, registry_path)

        try:
            self._set_hook_diagnostics(skipped=[], errors=[])
            registered = self.register_hooks(
                resolved.hooks, target_dir, registry_path=registry_path
            )
            result.linked.extend(f"hook:{h}" for h in registered)
            for skipped in self._take_hook_skipped():
                result.skipped.append(f"hooks: {skipped}")
            for hook_error in self._take_hook_errors():
                result.errors.append(f"hooks: {hook_error}")
        except Exception as e:
            result.errors.append(f"hooks: {e}")

        try:
            servers = (
                self._load_mcp_servers(resolved.mcp, registry_path / "mcp")
                if resolved.mcp
                else {}
            )
            self.write_mcp_config(servers, target_dir)
            result.linked.extend(f"mcp:{name}" for name in servers)
        except Exception as e:
            result.errors.append(f"mcp: {e}")

        return result

    def _remove_legacy_prompt_links(self, target_dir: Path, registry_path: Path) -> None:
        """Drop prompt symlinks left behind by older hawk versions."""
        prompts_dir = target_dir / "prompts"
        if not prompts_dir.is_dir():
            return
        for name in self._find_current_symlinks(prompts_dir, registry_path / "prompts"):
            self._remove_link(prompts_dir / name)

    # ── Hooks ──

    def register_hooks(
        self,
        hook_names: list[str],
        target_dir: Path,
        registry_path: Path | None = None,
    ) -> list[str]:
        """Register hooks under the ``hawk`` key of ``<root>/hooks.json``."""
        from ..event_mapping import get_event_support, get_tool_event_or_none
        from ..hook_meta import parse_hook_meta

        skipped: list[str] = []
        hooks_json = target_dir / "hooks.json"
        runners_dir = target_dir / "runners"

        if not hook_names or registry_path is None:
            self._write_hawk_hooks(hooks_json, {})
            if runners_dir.is_dir():
                for stale in runners_dir.glob("*.sh"):
                    stale.unlink(missing_ok=True)
            self._set_hook_diagnostics(skipped=[], errors=[])
            return []

        hooks_dir = registry_path / "hooks"

        script_hooks: list[str] = []
        for name in hook_names:
            if name.endswith(".prompt.json"):
                skipped.append(
                    f"{name} is a prompt hook; antigravity only supports command hooks"
                )
            else:
                script_hooks.append(name)

        # _generate_runners writes <event>.sh and prunes every other .sh in the
        # directory, so bridge wrappers must be (re)written after it runs.
        runners = (
            self._generate_runners(script_hooks, registry_path, runners_dir)
            if script_hooks
            else {}
        )

        event_timeouts: dict[str, int] = {}
        for name in script_hooks:
            hook_path = hooks_dir / name
            if not hook_path.is_file():
                continue
            meta = parse_hook_meta(hook_path)
            for event in meta.events:
                if event in runners and meta.timeout > 0:
                    event_timeouts[event] = max(event_timeouts.get(event, 0), meta.timeout)

        hawk_hooks: dict[str, list] = {}
        registered_events: set[str] = set()

        for event_name, runner_path in sorted(runners.items()):
            support = get_event_support(event_name, "antigravity")
            tool_event = get_tool_event_or_none(event_name, "antigravity")
            if support == "unsupported" or not tool_event:
                skipped.append(f"{event_name} is unsupported by antigravity and was skipped")
                runner_path.unlink(missing_ok=True)
                continue

            bridge = self._write_bridge_runner(
                runners_dir=runners_dir,
                hawk_event=event_name,
                tool_event=tool_event,
                runner_path=runner_path,
            )

            handler: dict = {"type": "command", "command": str(bridge)}
            if event_name in event_timeouts:
                handler["timeout"] = event_timeouts[event_name]

            if tool_event in _GROUPED_EVENTS:
                hawk_hooks.setdefault(tool_event, []).append(
                    {"matcher": "*", "hooks": [handler]}
                )
            else:
                hawk_hooks.setdefault(tool_event, []).append(handler)
            registered_events.add(event_name)

        self._write_hawk_hooks(hooks_json, hawk_hooks)

        registered: list[str] = []
        for name in script_hooks:
            hook_path = hooks_dir / name
            if not hook_path.is_file():
                continue
            if any(event in registered_events for event in parse_hook_meta(hook_path).events):
                registered.append(name)

        self._set_hook_diagnostics(skipped=skipped, errors=[])
        return registered

    @staticmethod
    def _write_hawk_hooks(hooks_json: Path, hawk_hooks: dict[str, list]) -> None:
        """Replace the ``hawk`` key in hooks.json, preserving everything else."""
        data: dict = {}
        if hooks_json.exists():
            try:
                loaded = json.loads(hooks_json.read_text())
                if isinstance(loaded, dict):
                    data = loaded
            except (json.JSONDecodeError, OSError):
                data = {}

        if hawk_hooks:
            data[_HAWK_HOOK_KEY] = hawk_hooks
        else:
            data.pop(_HAWK_HOOK_KEY, None)

        if data:
            hooks_json.parent.mkdir(parents=True, exist_ok=True)
            hooks_json.write_text(json.dumps(data, indent=2) + "\n")
        elif hooks_json.exists():
            hooks_json.unlink()

    @staticmethod
    def _write_bridge_runner(
        *,
        runners_dir: Path,
        hawk_event: str,
        tool_event: str,
        runner_path: Path,
    ) -> Path:
        """Generate the wrapper translating a hawk runner to Antigravity's contract."""
        from .. import config as _config
        from ..runner_utils import _atomic_write_executable

        venv_python = _config.get_config_dir() / ".venv" / "bin" / "python"
        python_cmd = shlex.quote(str(venv_python)) if venv_python.is_file() else "python3"
        runner = shlex.quote(str(runner_path))

        header = (
            "#!/usr/bin/env bash\n"
            f"# Auto-generated by hawk v2 - Antigravity {tool_event} bridge\n"
            f"# Hawk event: {hawk_event}\n"
            "# Regenerate with: hawk sync --force\n"
            "\n"
            # No `set -e`: a non-zero hook exit is meaningful, not fatal.
            "set -uo pipefail\n"
            "\n"
            "INPUT=$(cat)\n"
        )

        def reason_json(decision: str, fallback: str) -> str:
            script = (
                "import json,os,sys;"
                f"r=os.environ.get('HAWK_OUTPUT','').strip()[:{_MAX_REASON_CHARS}]"
                f" or {fallback!r};"
                f"sys.stdout.write(json.dumps({{'decision':{decision!r},'reason':r}})+'\\n')"
            )
            return f"export HAWK_OUTPUT\n{python_cmd} -c {shlex.quote(script)}\n"

        if tool_event == "PostToolUse":
            # PostToolUse expects an empty object; hook output is advisory only.
            body = (
                f"printf '%s' \"$INPUT\" | {runner} >/dev/null 2>&1 || true\n"
                "printf '%s\\n' '{}'\n"
            )
        elif tool_event == "PreToolUse":
            body = (
                f"HAWK_OUTPUT=$(printf '%s' \"$INPUT\" | {runner} 2>&1)\n"
                "HAWK_STATUS=$?\n"
                "\n"
                "if [[ $HAWK_STATUS -eq 0 ]]; then\n"
                "  printf '%s\\n' '{\"decision\":\"ask\"}'\n"
                "else\n"
                + _indent(reason_json("deny", "Blocked by a hawk hook."), "  ")
                + "fi\n"
            )
        else:
            # Stop: a non-zero exit means "don't stop yet".
            body = (
                f"HAWK_OUTPUT=$(printf '%s' \"$INPUT\" | {runner} 2>&1)\n"
                "HAWK_STATUS=$?\n"
                "\n"
                "if [[ $HAWK_STATUS -eq 0 ]]; then\n"
                "  printf '%s\\n' '{}'\n"
                "else\n"
                + _indent(reason_json("continue", "A hawk hook requested continuation."), "  ")
                + "fi\n"
            )

        bridge_path = runners_dir / f"antigravity-{hawk_event}.sh"
        _atomic_write_executable(bridge_path, header + "\n" + body + "\nexit 0\n")
        return bridge_path

    # ── MCP ──

    def write_mcp_config(self, servers: dict[str, dict], target_dir: Path) -> None:
        """Merge hawk-managed MCP servers into ``<root>/mcp_config.json``.

        Uses sidecar tracking so server entries stay free of hawk's marker key.
        """
        self._merge_mcp_sidecar(target_dir / "mcp_config.json", servers)


def _indent(text: str, prefix: str) -> str:
    """Indent every non-empty line of *text*."""
    return "".join(prefix + line if line.strip() else line for line in text.splitlines(True))
