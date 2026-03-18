from __future__ import annotations

import json
from pathlib import Path

from codex_handoff.config import default_config
from codex_handoff.models import ProjectConfig, SessionRecord
from codex_handoff.paths import ProjectPaths


MAX_EXCERPT_CHARS = 280


class CodexSessionSource:
    def __init__(self, paths: ProjectPaths, config: ProjectConfig | None = None) -> None:
        self.paths = paths
        self.config = config or default_config(paths.root)

    def collect(self) -> list[SessionRecord]:
        records: list[SessionRecord] = []
        for session_file in self._list_session_files():
            meta = self._read_session_meta(session_file)
            if meta is None:
                continue
            if _is_subagent_session(meta):
                continue
            cwd = self._read_session_cwd(meta)
            if cwd is None or not _paths_related(self.paths.root, cwd):
                continue
            record = self._read_session_record(session_file, meta, cwd)
            if record is None:
                continue
            records.append(record)
            if len(records) >= self.config.output.max_recent_sessions:
                break
        return records

    def _list_session_files(self) -> list[Path]:
        session_files: list[Path] = []
        for directory in (
            self.paths.global_paths.codex_home / "sessions",
            self.paths.global_paths.codex_home / "archived_sessions",
        ):
            if not directory.exists():
                continue
            session_files.extend(path for path in directory.rglob("*.jsonl") if path.is_file())
        session_files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return session_files

    def _read_session_meta(self, session_file: Path) -> dict[str, object] | None:
        try:
            with session_file.open("r", encoding="utf-8") as handle:
                first_line = handle.readline()
        except OSError:
            return None
        if not first_line.strip():
            return None
        try:
            payload = json.loads(first_line)
        except json.JSONDecodeError:
            return None
        if payload.get("type") != "session_meta":
            return None
        raw_meta = payload.get("payload")
        return raw_meta if isinstance(raw_meta, dict) else None

    def _read_session_cwd(self, meta: dict[str, object]) -> Path | None:
        cwd = meta.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip():
            return None
        return Path(cwd).expanduser().resolve()

    def _read_session_record(self, session_file: Path, meta: dict[str, object], cwd: Path) -> SessionRecord | None:
        started_at = _string_or_none(meta.get("timestamp"))
        record = SessionRecord(
            session_id=_string_or_none(meta.get("id")) or session_file.stem,
            started_at=started_at,
            updated_at=started_at,
            cwd=cwd.as_posix(),
            source_path=session_file.as_posix(),
        )

        try:
            with session_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    self._apply_session_line(record, line)
        except OSError:
            return None

        if not any(
            (
                record.first_user_message,
                record.latest_user_message,
                record.latest_assistant_message,
            )
        ):
            return None
        return record

    def _apply_session_line(self, record: SessionRecord, line: str) -> None:
        if not line.strip():
            return
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            return

        timestamp = _string_or_none(item.get("timestamp"))
        if timestamp:
            record.updated_at = timestamp

        item_type = item.get("type")
        payload = item.get("payload")
        if not isinstance(payload, dict):
            return

        if item_type == "event_msg" and payload.get("type") == "user_message":
            text = _normalize_excerpt(payload.get("message"))
            if text:
                if not record.first_user_message:
                    record.first_user_message = text
                record.latest_user_message = text
            return

        if item_type != "response_item":
            return
        if payload.get("type") != "message" or payload.get("role") != "assistant":
            return

        text = _extract_assistant_text(payload.get("content"))
        if not text:
            return

        if payload.get("phase") == "final_answer":
            record.latest_assistant_message = text
            return

        record.latest_assistant_message = text


def _paths_related(project_root: Path, session_cwd: Path) -> bool:
    root = project_root.resolve()
    cwd = session_cwd.resolve()
    return cwd == root or root in cwd.parents


def _extract_assistant_text(content: object) -> str | None:
    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return _normalize_excerpt("\n".join(parts))


def _normalize_excerpt(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    collapsed = " ".join(segment for segment in value.split())
    if not collapsed:
        return None
    if len(collapsed) <= MAX_EXCERPT_CHARS:
        return collapsed
    return collapsed[: MAX_EXCERPT_CHARS - 1].rstrip() + "…"


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _is_subagent_session(meta: dict[str, object]) -> bool:
    if meta.get("forked_from_id"):
        return True
    if meta.get("agent_role"):
        return True
    source = meta.get("source")
    return isinstance(source, dict) and "subagent" in source
