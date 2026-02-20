"""Tests for hawk-hook metadata parsing."""
from dataclasses import field
from pathlib import Path

import pytest

from hawk_hooks.hook_meta import HookMeta, parse_hook_meta


class TestParseCommentHeaders:
    """Parse hawk-hook: comment headers from scripts."""

    def test_single_event(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]

    def test_multiple_events(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# hawk-hook: events=stop,notification\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["stop", "notification"]

    def test_all_fields(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text(
            "#!/usr/bin/env python3\n"
            "# hawk-hook: events=pre_tool_use\n"
            "# hawk-hook: description=Block bad files\n"
            "# hawk-hook: deps=requests\n"
            "# hawk-hook: env=DESKTOP=true\n"
            "# hawk-hook: env=NTFY_ENABLED=false\n"
            "import sys\n"
        )
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]
        assert meta.description == "Block bad files"
        assert meta.deps == "requests"
        assert meta.env == ["DESKTOP=true", "NTFY_ENABLED=false"]

    def test_bash_script(self, tmp_path):
        f = tmp_path / "hook.sh"
        f.write_text("#!/usr/bin/env bash\n# hawk-hook: events=pre_tool_use\n# hawk-hook: description=Block dangerous commands\nset -euo pipefail\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]
        assert meta.description == "Block dangerous commands"

    def test_no_header_returns_empty_events(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# Description: old style\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == []

    def test_stops_at_non_comment_line(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# hawk-hook: events=stop\nimport sys\n# hawk-hook: events=notification\n")
        meta = parse_hook_meta(f)
        # Should only find the header before code starts
        assert meta.events == ["stop"]


class TestJsTsCommentHeaders:
    """Parse // hawk-hook: headers from JS/TS files."""

    def test_js_comment_header(self, tmp_path):
        f = tmp_path / "hook.js"
        f.write_text("#!/usr/bin/env node\n// hawk-hook: events=pre_tool_use\nconst x = 1;\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]

    def test_ts_comment_header_with_description(self, tmp_path):
        f = tmp_path / "hook.ts"
        f.write_text(
            "#!/usr/bin/env bun\n"
            "// hawk-hook: events=stop,notification\n"
            "// hawk-hook: description=TS guard\n"
            "const data = 1;\n"
        )
        meta = parse_hook_meta(f)
        assert meta.events == ["stop", "notification"]
        assert meta.description == "TS guard"

    def test_js_stops_at_code_line(self, tmp_path):
        f = tmp_path / "hook.js"
        f.write_text("#!/usr/bin/env node\n// hawk-hook: events=stop\nconst x = 1;\n// hawk-hook: events=notification\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["stop"]


class TestParseFrontmatter:
    """Parse hawk-hook YAML frontmatter from .md/.txt files."""

    def test_markdown_frontmatter(self, tmp_path):
        f = tmp_path / "hook.md"
        f.write_text("---\nhawk-hook:\n  events: [stop]\n  description: Check completion\n---\nContent here\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["stop"]
        assert meta.description == "Check completion"

    def test_txt_frontmatter(self, tmp_path):
        f = tmp_path / "hook.txt"
        f.write_text("---\nhawk-hook:\n  events: [user_prompt_submit]\n---\nContent here\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["user_prompt_submit"]

    def test_no_hawk_hook_key_in_frontmatter(self, tmp_path):
        f = tmp_path / "hook.md"
        f.write_text("---\nname: my-command\ndescription: A command\n---\nContent\n")
        meta = parse_hook_meta(f)
        assert meta.events == []

    def test_no_frontmatter(self, tmp_path):
        f = tmp_path / "hook.md"
        f.write_text("# Just a markdown file\nNo frontmatter here.\n")
        meta = parse_hook_meta(f)
        assert meta.events == []

    def test_frontmatter_with_all_fields(self, tmp_path):
        f = tmp_path / "hook.md"
        f.write_text("---\nhawk-hook:\n  events: [stop, notification]\n  description: Notify\n  deps: requests\n  env:\n    - DESKTOP=true\n---\nContent\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["stop", "notification"]
        assert meta.deps == "requests"
        assert meta.env == ["DESKTOP=true"]


class TestDirectoryFallback:
    """Fall back to parent directory name for event inference."""

    def test_parent_is_known_event(self, tmp_path):
        event_dir = tmp_path / "pre_tool_use"
        event_dir.mkdir()
        f = event_dir / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# Description: old style\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]

    def test_parent_is_unknown(self, tmp_path):
        other_dir = tmp_path / "random"
        other_dir.mkdir()
        f = other_dir / "hook.py"
        f.write_text("#!/usr/bin/env python3\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == []

    def test_header_takes_priority_over_parent(self, tmp_path):
        event_dir = tmp_path / "pre_tool_use"
        event_dir.mkdir()
        f = event_dir / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# hawk-hook: events=stop,notification\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["stop", "notification"]

    def test_stdout_md_no_header_uses_parent(self, tmp_path):
        event_dir = tmp_path / "stop"
        event_dir.mkdir()
        f = event_dir / "check.stdout.md"
        f.write_text("# Check things\nDo stuff\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["stop"]


class TestTimeoutParsing:
    """Test timeout field parsing across all formats."""

    def test_comment_header_timeout(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\n# hawk-hook: timeout=60\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]
        assert meta.timeout == 60

    def test_frontmatter_timeout(self, tmp_path):
        f = tmp_path / "hook.md"
        f.write_text("---\nhawk-hook:\n  events: [stop]\n  timeout: 30\n---\nContent\n")
        meta = parse_hook_meta(f)
        assert meta.events == ["stop"]
        assert meta.timeout == 30

    def test_json_timeout(self, tmp_path):
        f = tmp_path / "hook.json"
        f.write_text('{"hawk-hook": {"events": ["pre_tool_use"], "timeout": 45}}')
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]
        assert meta.timeout == 45

    def test_default_timeout_is_zero(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.timeout == 0

    def test_invalid_timeout_ignored(self, tmp_path):
        f = tmp_path / "hook.py"
        f.write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\n# hawk-hook: timeout=abc\nimport sys\n")
        meta = parse_hook_meta(f)
        assert meta.timeout == 0


class TestJsonMeta:
    """Test JSON hawk-hook metadata parsing."""

    def test_basic_json_meta(self, tmp_path):
        f = tmp_path / "hook.json"
        f.write_text('{"hawk-hook": {"events": ["pre_tool_use"], "description": "A guard"}}')
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]
        assert meta.description == "A guard"

    def test_json_with_all_fields(self, tmp_path):
        f = tmp_path / "hook.json"
        f.write_text('{"hawk-hook": {"events": ["stop"], "description": "Check", "deps": "requests", "env": ["KEY=val"], "timeout": 30}}')
        meta = parse_hook_meta(f)
        assert meta.events == ["stop"]
        assert meta.deps == "requests"
        assert meta.env == ["KEY=val"]
        assert meta.timeout == 30

    def test_json_no_hawk_hook_key(self, tmp_path):
        f = tmp_path / "hook.json"
        f.write_text('{"prompt": "some prompt", "timeout": 30}')
        meta = parse_hook_meta(f)
        assert meta.events == []

    def test_json_invalid_json(self, tmp_path):
        f = tmp_path / "hook.json"
        f.write_text("not json at all")
        meta = parse_hook_meta(f)
        assert meta.events == []

    def test_json_comma_separated_events(self, tmp_path):
        f = tmp_path / "hook.json"
        f.write_text('{"hawk-hook": {"events": "pre_tool_use,stop"}}')
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use", "stop"]

    def test_prompt_json_with_meta(self, tmp_path):
        """A .prompt.json file with hawk-hook metadata."""
        f = tmp_path / "guard.prompt.json"
        f.write_text('{"prompt": "Evaluate this action", "timeout": 30, "hawk-hook": {"events": ["pre_tool_use"]}}')
        meta = parse_hook_meta(f)
        assert meta.events == ["pre_tool_use"]


class TestBuiltins:
    """Verify all bundled hooks have valid hawk-hook metadata."""

    def test_all_builtins_have_events(self):
        for candidate in [
            Path(__file__).parent.parent / "builtins" / "hooks",
            Path(__file__).parent.parent / "src" / "hawk_hooks" / "builtins" / "hooks",
        ]:
            if candidate.exists():
                builtins_dir = candidate
                break
        else:
            pytest.skip("builtins/hooks not found")

        for f in sorted(builtins_dir.iterdir()):
            if f.name.startswith(".") or f.is_dir():
                continue
            meta = parse_hook_meta(f)
            assert meta.events, f"{f.name} has no events in hawk-hook metadata"
            assert meta.description, f"{f.name} has no description in hawk-hook metadata"
