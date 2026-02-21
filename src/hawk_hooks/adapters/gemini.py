"""Gemini CLI adapter for hawk-hooks v2."""

from __future__ import annotations

from pathlib import Path

from ..types import Tool
from .base import ToolAdapter


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
            registered = self.register_hooks(resolved.hooks, target_dir, registry_path=registry_path)
            result.linked.extend(f"hook:{h}" for h in registered)
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
        """Gemini does not support hooks natively."""
        return []

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
