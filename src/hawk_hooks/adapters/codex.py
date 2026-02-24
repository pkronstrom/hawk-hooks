"""Codex CLI adapter for hawk-hooks v2."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import tomllib
from typing import Any

from ..managed_config import ManagedConfigOp, TomlBlockDriver
from ..registry import _validate_name
from ..types import ResolvedSet, SyncResult, Tool
from .base import ToolAdapter

_BEGIN_NOTIFY_BLOCK = "# >>> hawk-hooks notify >>>"
_END_NOTIFY_BLOCK = "# <<< hawk-hooks notify <<<"

_AGENT_SIDECAR = ".hawk-codex-agents.json"
_MULTI_AGENT_UNIT = "codex-multi-agent"
_AGENT_UNIT_PREFIX = "codex-agent-"
_MCP_UNIT_PREFIX = "codex-mcp-"
_ROLE_FILE_MARKER = "hawk-hooks managed: codex-agent-role"
_LAUNCHER_MARKER = "hawk-hooks managed: codex-agent-launcher"


@dataclass
class _CodexAgentSpec:
    source_name: str
    role_key: str
    launcher_skill: str
    description: str
    instructions: str


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
        """Codex native skills live in ~/.agents/skills or .agents/skills."""
        return target_dir.parent / ".agents" / "skills"

    def get_agents_dir(self, target_dir: Path) -> Path:
        """Codex role config files for multi-agent mode."""
        return target_dir / "agents"

    def get_commands_dir(self, target_dir: Path) -> Path:
        """Legacy command alias: map to Codex custom prompts directory."""
        return target_dir / "prompts"

    def sync(
        self,
        resolved: ResolvedSet,
        target_dir: Path,
        registry_path: Path,
    ) -> SyncResult:
        """Custom sync for Codex native layout and generated agent launchers."""
        result = SyncResult(tool=str(self.tool))

        for dir_getter in [self.get_skills_dir, self.get_agents_dir, self.get_prompts_dir]:
            dir_getter(target_dir).mkdir(parents=True, exist_ok=True)

        self._sync_component(
            resolved.skills,
            registry_path / "skills",
            target_dir,
            self.link_skill,
            self.unlink_skill,
            self.get_skills_dir,
            result,
        )

        self._sync_component(
            resolved.prompts,
            registry_path / "prompts",
            target_dir,
            self.link_prompt,
            self.unlink_prompt,
            self.get_prompts_dir,
            result,
        )

        try:
            self._sync_codex_agents(resolved.agents, target_dir, registry_path, result)
        except Exception as exc:
            result.errors.append(f"agents: {exc}")

        try:
            self._set_hook_diagnostics(skipped=[], errors=[])
            registered = self.register_hooks(resolved.hooks, target_dir, registry_path=registry_path)
            result.linked.extend(f"hook:{h}" for h in registered)
            for skipped in self._take_hook_skipped():
                result.skipped.append(f"hooks: {skipped}")
            for hook_error in self._take_hook_errors():
                result.errors.append(f"hooks: {hook_error}")
        except Exception as exc:
            result.errors.append(f"hooks: {exc}")

        try:
            servers = self._load_mcp_servers(resolved.mcp, registry_path / "mcp") if resolved.mcp else {}
            self.write_mcp_config(servers, target_dir)
            result.linked.extend(f"mcp:{name}" for name in servers)
        except Exception as exc:
            result.errors.append(f"mcp: {exc}")

        return result

    def register_hooks(
        self, hook_names: list[str], target_dir: Path, registry_path: Path | None = None
    ) -> list[str]:
        """Register limited hook bridge using Codex notify callbacks."""
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
        """Write Codex MCP config into managed blocks in config.toml.

        Writes one hawk-managed TOML block per server:
        [mcp_servers."<name>"]
        ...

        Existing manual MCP tables are preserved. If a manual table already
        exists for a server name hawk wants to manage, this raises an error.
        """
        config_path = target_dir / "config.toml"
        text = config_path.read_text() if config_path.exists() else ""
        manual_text = TomlBlockDriver.strip_all(text)

        existing_units = self._extract_managed_mcp_units(text)
        desired_units: set[str] = set()
        ops: list[ManagedConfigOp] = []

        for raw_name, cfg in sorted(servers.items()):
            name = str(raw_name)
            _validate_name(name)
            if not isinstance(cfg, dict):
                raise ValueError(f"invalid MCP server config for {name!r}: expected object")
            if self._has_manual_mcp_table(manual_text, name):
                raise ValueError(
                    f"codex config.toml already has a manual [mcp_servers.{name}] table; "
                    "remove it or let hawk manage a different server name"
                )
            unit_id = self._mcp_unit_id(name)
            desired_units.add(unit_id)
            ops.append(
                ManagedConfigOp(
                    file=config_path,
                    unit_id=unit_id,
                    action="upsert",
                    payload=self._render_mcp_payload(name, cfg),
                )
            )

        for stale_unit in sorted(existing_units - desired_units):
            ops.append(
                ManagedConfigOp(
                    file=config_path,
                    unit_id=stale_unit,
                    action="remove",
                )
            )

        result = TomlBlockDriver.apply(ops)
        if result.errors:
            raise ValueError("; ".join(result.errors))

    def _sync_codex_agents(
        self,
        agent_names: list[str],
        target_dir: Path,
        registry_path: Path,
        result: SyncResult,
    ) -> None:
        """Generate Codex multi-agent role config + launcher skills."""
        from .. import v2_config

        codex_cfg = v2_config.load_global_config().get("tools", {}).get("codex", {})
        consent = codex_cfg.get("multi_agent_consent")
        if consent not in {"ask", "granted", "denied"}:
            # Backward compatibility with boolean gate.
            consent = "granted" if codex_cfg.get("allow_multi_agent", False) else "ask"
        allow_multi_agent = consent == "granted"
        trigger_mode = str(codex_cfg.get("agent_trigger_mode", "skills")).lower()
        if trigger_mode not in {"skills", "none"}:
            trigger_mode = "skills"

        config_path = target_dir / "config.toml"
        roles_dir = self.get_agents_dir(target_dir)
        skills_dir = self.get_skills_dir(target_dir)

        old_roles, old_launchers = self._load_agent_sidecar(target_dir)

        specs: dict[str, _CodexAgentSpec] = {}
        for name in agent_names:
            try:
                _validate_name(name)
            except ValueError as exc:
                result.errors.append(f"agents: invalid name {name!r}: {exc}")
                continue
            source = registry_path / "agents" / name
            if not source.is_file():
                continue
            spec = self._build_agent_spec(source, name)
            if spec.role_key in specs:
                result.errors.append(
                    f"agents: role key collision for {name!r} -> {spec.role_key!r}"
                )
                continue
            specs[spec.role_key] = spec

        desired_roles = set(specs.keys())
        desired_launchers = (
            {spec.launcher_skill for spec in specs.values()} if trigger_mode == "skills" else set()
        )

        if not desired_roles:
            self._cleanup_stale_agents(
                target_dir=target_dir,
                stale_roles=old_roles,
                stale_launchers=old_launchers,
                result=result,
            )
            self._save_agent_sidecar(target_dir, set(), set())
            TomlBlockDriver.apply(
                [ManagedConfigOp(file=config_path, unit_id=_MULTI_AGENT_UNIT, action="remove")]
            )
            return

        manual_text = self._manual_codex_toml(config_path)
        current_multi = self._read_multi_agent_flag(config_path)
        manual_features_table = bool(re.search(r"(?m)^\s*\[features\]\s*$", manual_text))

        if current_multi is not True:
            if manual_features_table:
                result.errors.append(
                    "agents: codex config.toml already has a manual [features] table; "
                    "set multi_agent = true manually to enable codex agents"
                )
                return
            if not allow_multi_agent:
                result.skipped.append(
                    "agents: codex multi-agent is required; grant consent in TUI or set "
                    "tools.codex.multi_agent_consent: granted"
                )
                return
            op_result = TomlBlockDriver.apply(
                [
                    ManagedConfigOp(
                        file=config_path,
                        unit_id=_MULTI_AGENT_UNIT,
                        action="upsert",
                        payload="[features]\nmulti_agent = true",
                    )
                ]
            )
            result.errors.extend(f"agents: {e}" for e in op_result.errors)
            if op_result.errors:
                return

        managed_roles: set[str] = set()
        managed_launchers: set[str] = set()

        for spec in specs.values():
            if self._has_manual_agent_table(manual_text, spec.role_key):
                result.skipped.append(
                    f"agents: manual [agents.{spec.role_key}] exists; skipped {spec.source_name}"
                )
                continue

            role_file = roles_dir / f"{spec.role_key}.toml"
            if role_file.exists() and spec.role_key not in old_roles and not self._is_hawk_role_file(role_file):
                result.skipped.append(
                    f"agents: role file already exists and is not hawk-managed: {role_file}"
                )
                continue

            role_file.write_text(self._role_file_content(spec.instructions))
            managed_roles.add(spec.role_key)
            if spec.role_key not in old_roles:
                result.linked.append(f"agent:{spec.source_name}")

            agent_payload = (
                f"[agents.{spec.role_key}]\n"
                f'description = "{self._escape_toml_string(spec.description)}"\n'
                f'config_file = "agents/{spec.role_key}.toml"'
            )
            op_result = TomlBlockDriver.apply(
                [
                    ManagedConfigOp(
                        file=config_path,
                        unit_id=f"{_AGENT_UNIT_PREFIX}{spec.role_key}",
                        action="upsert",
                        payload=agent_payload,
                    )
                ]
            )
            result.errors.extend(f"agents: {e}" for e in op_result.errors)
            if op_result.errors:
                continue

            if trigger_mode == "skills":
                launcher_dir = skills_dir / spec.launcher_skill
                if (
                    launcher_dir.exists()
                    and spec.launcher_skill not in old_launchers
                    and not self._is_hawk_launcher_skill(launcher_dir)
                ):
                    result.skipped.append(
                        f"agents: launcher skill already exists and is not hawk-managed: {launcher_dir}"
                    )
                    continue
                self._write_launcher_skill(launcher_dir, spec)
                managed_launchers.add(spec.launcher_skill)
                if spec.launcher_skill not in old_launchers:
                    result.linked.append(f"skill:{spec.launcher_skill}")

        stale_roles = old_roles - managed_roles
        stale_launchers = old_launchers - managed_launchers
        self._cleanup_stale_agents(
            target_dir=target_dir,
            stale_roles=stale_roles,
            stale_launchers=stale_launchers,
            result=result,
        )

        self._save_agent_sidecar(target_dir, managed_roles, managed_launchers)

        if not managed_roles:
            TomlBlockDriver.apply(
                [ManagedConfigOp(file=config_path, unit_id=_MULTI_AGENT_UNIT, action="remove")]
            )

    def _cleanup_stale_agents(
        self,
        *,
        target_dir: Path,
        stale_roles: set[str],
        stale_launchers: set[str],
        result: SyncResult,
    ) -> None:
        """Cleanup stale hawk-managed codex role files + launcher skills."""
        config_path = target_dir / "config.toml"
        roles_dir = self.get_agents_dir(target_dir)
        skills_dir = self.get_skills_dir(target_dir)

        remove_ops: list[ManagedConfigOp] = []
        for role in sorted(stale_roles):
            remove_ops.append(
                ManagedConfigOp(
                    file=config_path,
                    unit_id=f"{_AGENT_UNIT_PREFIX}{role}",
                    action="remove",
                )
            )
            role_file = roles_dir / f"{role}.toml"
            if self._is_hawk_role_file(role_file):
                role_file.unlink(missing_ok=True)
            result.unlinked.append(f"agent:{role}")

        op_result = TomlBlockDriver.apply(remove_ops)
        result.errors.extend(f"agents: {e}" for e in op_result.errors)

        for launcher in sorted(stale_launchers):
            launcher_dir = skills_dir / launcher
            if self._is_hawk_launcher_skill(launcher_dir):
                shutil.rmtree(launcher_dir, ignore_errors=True)
            result.unlinked.append(f"skill:{launcher}")

    def _build_agent_spec(self, source: Path, source_name: str) -> _CodexAgentSpec:
        """Convert registry agent markdown into codex role + launcher names."""
        from ..frontmatter import parse_frontmatter

        raw = source.read_text()
        description = f"Hawk-managed Codex agent for {source.stem}"
        instructions = raw.strip()

        try:
            frontmatter, body = parse_frontmatter(raw, warn_unknown_tools=False)
        except ValueError:
            frontmatter, body = None, raw

        if frontmatter is not None and frontmatter.description.strip():
            description = frontmatter.description.strip()

        body_text = body.strip()
        if body_text:
            instructions = body_text

        stem_slug = self._slug(source.stem)
        role_key = stem_slug.replace("-", "_")
        if role_key and role_key[0].isdigit():
            role_key = f"agent_{role_key}"
        launcher_skill = f"agent-{stem_slug}"

        return _CodexAgentSpec(
            source_name=source_name,
            role_key=role_key or "agent_default",
            launcher_skill=launcher_skill,
            description=description,
            instructions=instructions or f"Use instructions from {source_name}.",
        )

    @staticmethod
    def _slug(text: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return slug or "agent"

    @staticmethod
    def _mcp_unit_id(name: str) -> str:
        return f"{_MCP_UNIT_PREFIX}{name}"

    @staticmethod
    def _extract_managed_mcp_units(text: str) -> set[str]:
        return set(
            re.findall(
                rf"(?m)^# >>> hawk-hooks managed: ({re.escape(_MCP_UNIT_PREFIX)}[A-Za-z0-9_.-]+) >>>$",
                text,
            )
        )

    @staticmethod
    def _has_manual_mcp_table(manual_text: str, name: str) -> bool:
        pattern = (
            rf'(?m)^\s*\[\s*mcp_servers\.(?:{re.escape(name)}|"{re.escape(name)}")(?:\s*\]|[.])'
        )
        return bool(re.search(pattern, manual_text))

    @classmethod
    def _render_mcp_payload(cls, name: str, cfg: dict[str, Any]) -> str:
        return cls._render_toml_table(["mcp_servers", name], cfg)

    @classmethod
    def _render_toml_table(cls, path_parts: list[str], data: dict[str, Any]) -> str:
        if not isinstance(data, dict):
            raise ValueError(f"invalid TOML table for {'.'.join(path_parts)}: expected object")
        table_name = ".".join(cls._render_toml_key(part) for part in path_parts)
        lines = [f"[{table_name}]"]
        nested: list[tuple[list[str], dict[str, Any]]] = []

        for key in sorted(data.keys()):
            value = data[key]
            if value is None:
                continue
            if isinstance(value, dict):
                nested.append((path_parts + [str(key)], value))
                continue
            lines.append(f"{cls._render_toml_key(str(key))} = {cls._render_toml_value(value)}")

        blocks = ["\n".join(lines)]
        for sub_path, sub_data in nested:
            blocks.append(cls._render_toml_table(sub_path, sub_data))
        return "\n\n".join(blocks)

    @staticmethod
    def _render_toml_key(key: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9_-]+", key):
            return key
        escaped = key.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    @classmethod
    def _render_toml_value(cls, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return repr(value)
        if isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{escaped}"'
        if isinstance(value, list):
            rendered = ", ".join(cls._render_toml_value(v) for v in value)
            return f"[{rendered}]"
        raise ValueError(f"unsupported TOML value type: {type(value).__name__}")

    @staticmethod
    def _escape_toml_string(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _role_file_content(instructions: str) -> str:
        body = instructions.replace('"""', '\\"""')
        return (
            f"# {_ROLE_FILE_MARKER}\n\n"
            "developer_instructions = \"\"\"\n"
            f"{body}\n"
            "\"\"\"\n"
        )

    def _write_launcher_skill(self, launcher_dir: Path, spec: _CodexAgentSpec) -> None:
        launcher_dir.mkdir(parents=True, exist_ok=True)
        skill_path = launcher_dir / "SKILL.md"
        content = (
            "---\n"
            f"name: {spec.launcher_skill}\n"
            f"description: Invoke Codex agent role {spec.role_key}\n"
            "---\n\n"
            f"<!-- {_LAUNCHER_MARKER} -->\n\n"
            f"Use the Codex multi-agent role `{spec.role_key}` for this task.\n"
        )
        skill_path.write_text(content)

    @staticmethod
    def _load_agent_sidecar(target_dir: Path) -> tuple[set[str], set[str]]:
        sidecar = target_dir / _AGENT_SIDECAR
        if not sidecar.exists():
            return set(), set()
        try:
            data = json.loads(sidecar.read_text())
        except (json.JSONDecodeError, OSError):
            return set(), set()
        roles = set(data.get("roles", [])) if isinstance(data, dict) else set()
        launchers = set(data.get("launchers", [])) if isinstance(data, dict) else set()
        return roles, launchers

    @staticmethod
    def _save_agent_sidecar(target_dir: Path, roles: set[str], launchers: set[str]) -> None:
        sidecar = target_dir / _AGENT_SIDECAR
        if not roles and not launchers:
            sidecar.unlink(missing_ok=True)
            return
        payload = {"roles": sorted(roles), "launchers": sorted(launchers)}
        sidecar.write_text(json.dumps(payload, indent=2) + "\n")

    @staticmethod
    def _manual_codex_toml(config_path: Path) -> str:
        text = config_path.read_text() if config_path.exists() else ""
        return TomlBlockDriver.strip_all(text)

    @staticmethod
    def _read_multi_agent_flag(config_path: Path) -> bool | None:
        if not config_path.exists():
            return None
        try:
            data = tomllib.loads(config_path.read_text())
        except (tomllib.TOMLDecodeError, OSError):
            return None
        features = data.get("features", {})
        if isinstance(features, dict):
            val = features.get("multi_agent")
            if isinstance(val, bool):
                return val
        return None

    @staticmethod
    def _has_manual_agent_table(manual_text: str, role_key: str) -> bool:
        pattern = rf"(?m)^\s*\[agents\.{re.escape(role_key)}\]\s*$"
        return bool(re.search(pattern, manual_text))

    @staticmethod
    def _is_hawk_role_file(path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            return _ROLE_FILE_MARKER in path.read_text(errors="replace")
        except OSError:
            return False

    @staticmethod
    def _is_hawk_launcher_skill(path: Path) -> bool:
        skill_file = path / "SKILL.md"
        if not skill_file.is_file():
            return False
        try:
            return _LAUNCHER_MARKER in skill_file.read_text(errors="replace")
        except OSError:
            return False

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
            escaped_commands = [CodexAdapter._escape_toml_string(cmd) for cmd in commands]
            lines = [
                _BEGIN_NOTIFY_BLOCK,
                "notify = [",
                *[f'  "{cmd}",' for cmd in escaped_commands],
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
