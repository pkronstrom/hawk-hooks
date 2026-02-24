"""Shared helpers for hawk-managed config ownership blocks.

This module provides a minimal, format-aware interface for managed config
writes. Start small with TOML block ownership and expand only when needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Literal


@dataclass
class ManagedConfigOp:
    """A single managed-config mutation."""

    file: Path
    unit_id: str
    action: Literal["upsert", "remove"]
    payload: str = ""
    format: Literal["toml"] = "toml"
    ownership: Literal["block"] = "block"
    conflict_policy: Literal["skip", "error"] = "error"


@dataclass
class ManagedConfigResult:
    """Result from applying managed-config operations."""

    applied: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class TomlBlockDriver:
    """Manage TOML snippets via explicit hawk-owned comment fences."""

    @staticmethod
    def _begin(unit_id: str) -> str:
        return f"# >>> hawk-hooks managed: {unit_id} >>>"

    @staticmethod
    def _end(unit_id: str) -> str:
        return f"# <<< hawk-hooks managed: {unit_id} <<<"

    @classmethod
    def _unit_re(cls, unit_id: str) -> re.Pattern[str]:
        begin = re.escape(cls._begin(unit_id))
        end = re.escape(cls._end(unit_id))
        return re.compile(rf"(?ms)^{begin}\n.*?^{end}\n?")

    @staticmethod
    def _normalize_newlines(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @classmethod
    def strip_unit(cls, text: str, unit_id: str) -> str:
        """Remove one managed unit block from TOML text."""
        text = cls._normalize_newlines(text)
        return cls._unit_re(unit_id).sub("", text).rstrip()

    @classmethod
    def strip_all(cls, text: str) -> str:
        """Remove all hawk-managed TOML blocks from text."""
        text = cls._normalize_newlines(text)
        return re.sub(
            r"(?ms)^# >>> hawk-hooks managed: [A-Za-z0-9_.-]+ >>>\n.*?^# <<< hawk-hooks managed: [A-Za-z0-9_.-]+ <<<\n?",
            "",
            text,
        ).rstrip()

    @classmethod
    def upsert(cls, path: Path, unit_id: str, payload: str) -> None:
        """Insert or replace a managed TOML block."""
        text = path.read_text() if path.exists() else ""
        text = cls.strip_unit(text, unit_id)
        begin = cls._begin(unit_id)
        end = cls._end(unit_id)
        body = payload.strip("\n")
        block = f"{begin}\n{body}\n{end}"

        if text:
            new_text = f"{text}\n\n{block}\n"
        else:
            new_text = f"{block}\n"

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_text)

    @classmethod
    def remove(cls, path: Path, unit_id: str) -> bool:
        """Remove a managed block. Returns True when content changed."""
        if not path.exists():
            return False
        old = cls._normalize_newlines(path.read_text())
        new = cls.strip_unit(old, unit_id)
        if new == old.rstrip():
            return False
        path.write_text(new + "\n" if new else "")
        return True

    @classmethod
    def apply(cls, ops: list[ManagedConfigOp]) -> ManagedConfigResult:
        """Apply managed config operations sequentially."""
        result = ManagedConfigResult()
        for op in ops:
            if op.format != "toml" or op.ownership != "block":
                result.errors.append(
                    f"{op.unit_id}: unsupported driver ({op.format}/{op.ownership})"
                )
                continue
            try:
                if op.action == "upsert":
                    cls.upsert(op.file, op.unit_id, op.payload)
                    result.applied.append(op.unit_id)
                elif op.action == "remove":
                    if cls.remove(op.file, op.unit_id):
                        result.applied.append(op.unit_id)
                else:
                    result.errors.append(f"{op.unit_id}: unknown action {op.action}")
            except OSError as exc:
                result.errors.append(f"{op.unit_id}: {exc}")
        return result
