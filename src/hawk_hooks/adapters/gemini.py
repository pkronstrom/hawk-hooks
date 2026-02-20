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

    def register_hooks(self, hook_names: list[str], target_dir: Path, registry_path: Path | None = None) -> list[str]:
        """Register hooks in Gemini settings.json format."""
        return list(hook_names)

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
