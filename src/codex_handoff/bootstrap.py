from __future__ import annotations

from datetime import datetime
from pathlib import Path

from codex_handoff.files import read_optional_text, write_text
from codex_handoff.localization import t

BLOCK_START = "<!-- codex-handoff:start -->"
BLOCK_END = "<!-- codex-handoff:end -->"


def ensure_agents_block(path: Path, backup_existing: bool = True) -> tuple[bool, Path | None]:
    existing = read_optional_text(path)
    managed = build_agents_block()
    updated = _replace_managed_block(existing, managed)
    changed = updated != existing
    backup_path: Path | None = None
    if changed:
        if backup_existing and path.exists():
            backup_path = path.with_suffix(path.suffix + f".bak-{_timestamp_suffix()}")
            write_text(backup_path, existing)
        write_text(path, updated)
    return changed, backup_path


def has_agents_block(path: Path) -> bool:
    content = read_optional_text(path)
    return BLOCK_START in content and BLOCK_END in content


def remove_agents_block(path: Path, backup_existing: bool = True) -> tuple[bool, Path | None]:
    existing = read_optional_text(path)
    updated = _remove_managed_block(existing)
    changed = updated != existing
    backup_path: Path | None = None
    if changed:
        if backup_existing and path.exists():
            backup_path = path.with_suffix(path.suffix + f".bak-{_timestamp_suffix()}")
            write_text(backup_path, existing)
        if updated.strip():
            write_text(path, updated)
        elif path.exists():
            path.unlink()
    return changed, backup_path


def build_agents_block() -> str:
    lines = [
        BLOCK_START,
        "## codex-handoff",
        t("bootstrap.prepare_first"),
        t("bootstrap.user_memory"),
        t("bootstrap.project_scope"),
        t("bootstrap.read_docs"),
        t("bootstrap.memory_contract"),
        t("bootstrap.fallback"),
        BLOCK_END,
    ]
    return "\n".join(lines) + "\n"


def _replace_managed_block(existing: str, managed: str) -> str:
    text = existing.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return managed

    if BLOCK_START in text and BLOCK_END in text:
        start = text.index(BLOCK_START)
        end = text.index(BLOCK_END) + len(BLOCK_END)
        before = text[:start].rstrip()
        after = text[end:].lstrip()
        parts = [part for part in (before, managed.strip(), after) if part]
        return "\n\n".join(parts) + "\n"

    return text + "\n\n" + managed


def _remove_managed_block(existing: str) -> str:
    text = existing.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text or BLOCK_START not in text or BLOCK_END not in text:
        return existing
    start = text.index(BLOCK_START)
    end = text.index(BLOCK_END) + len(BLOCK_END)
    before = text[:start].rstrip()
    after = text[end:].lstrip()
    parts = [part for part in (before, after) if part]
    if not parts:
        return ""
    return "\n\n".join(parts) + "\n"


def _timestamp_suffix() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")
