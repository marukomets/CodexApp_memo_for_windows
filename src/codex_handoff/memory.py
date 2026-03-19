from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from codex_handoff.focus import select_user_facing_changed_files
from codex_handoff.models import (
    FocusPathEntry,
    MemoryEntry,
    MemoryKind,
    MemorySnapshot,
    NextActionEntry,
    RepoSnapshot,
    SessionRecord,
    WorklogEntry,
    WorklogKind,
)
from codex_handoff.paths import ProjectPaths
from codex_handoff.relevance import is_transient_review_message, is_transient_review_note
from codex_handoff.summaries import split_summary_sentences, summarize_actionable_request


MAX_MEMORY_SUMMARY = 220
MAX_ASSISTANT_REPLY_SUMMARY = 160
MAX_USER_GLOBAL_ENTRIES = 8
MAX_SEMANTIC_PER_KIND: dict[MemoryKind, int] = {
    "preference": 4,
    "spec": 5,
    "constraint": 4,
    "assessment": 2,
    "success": 3,
    "failure": 3,
    "decision": 5,
}
MAX_WORKLOG_PER_KIND = {
    "progress": 3,
    "verification": 2,
    "commit": 3,
    "change": 4,
}

ASSESSMENT_SCORE_PATTERN = re.compile(
    r"(?<!\d)(?:\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?点|\d+(?:\.\d+)?/(?:10|100))(?!\d)"
)

USER_PREFERENCE_MARKERS = (
    "目指してる",
    "目指している",
    "使いたい",
    "使用感",
    "思想",
    "大事",
    "結論だけだと弱い",
    "こういう",
)
USER_SPEC_MARKERS = (
    "必要",
    "必須",
    "仕様",
    "試行錯誤",
    "記録されていれば",
    "戻ったりしなくなる",
    "だけじゃなくて",
    "入れられたら",
    "ほしい",
)
USER_CONSTRAINT_MARKERS = (
    "前提",
    "制約",
    "依存せず",
    "利用できない",
    "確認する",
    "しない",
)
USER_STRONG_PREFERENCE_MARKERS = (
    "目指してる",
    "目指している",
    "使いたい",
    "使用感",
    "思想",
    "結論だけだと弱い",
    "いいね",
)
USER_STRONG_SPEC_MARKERS = (
    "必要",
    "必須",
    "仕様",
    "試行錯誤",
    "記録されていれば",
    "戻ったりしなくなる",
    "ほしい",
)
USER_META_MEMORY_MARKERS = (
    "今何点",
    "9.9999",
    "このメモの内容",
    "最適化する必要がありそう",
    "さらにつめるところ",
)
USER_PROJECT_GOAL_MARKERS = (
    "スレッド間で情報共有",
    "スレッド間で共有",
    "引き継げればいい",
    "引き継げることが目的",
    "再開できることが目的",
    "内部状態",
    "ユーザーに見せる必要ない",
    "ユーザーに見せる必要はない",
    "見せる必要ない",
    "見せる必要はない",
)
SEMANTIC_TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("storage_strategy", ("正本", "global store", "memory.json", "next-thread.md", "内部状態を正本")),
    ("handoff_goal", ("スレッド間", "情報共有", "引き継", "再開", "主要なあらすじ")),
    ("visibility_policy", ("ユーザーに見せる必要", "見せる必要はない", "見せる必要ない")),
    ("schema_policy", ("項目を細分化", "必須項目", "細分化")),
    ("assessment_policy", ("現在の評価", "点数", "評価を必須項目")),
    ("worklog_policy", ("作業進捗", "コミット", "検証", "変更ファイル")),
    ("path_context_policy", ("ファイルやフォルダ名", "ファイル名", "フォルダ名", "どう操作したか", "これからどうすべきか")),
)
USER_GLOBAL_CANONICAL_RULES: tuple[tuple[str, MemoryKind, tuple[str, ...], str], ...] = (
    ("response_language", "preference", ("日本語", "日本語で"), "回答は日本語。"),
    (
        "execution_environment",
        "constraint",
        ("Windows 11", "PowerShell", "CodexWindowsApp"),
        "開発環境は Windows 11 / PowerShell / CodexWindowsApp。",
    ),
    (
        "assumption_policy",
        "decision",
        ("合理的な仮定", "仮定は明示", "仮定を明示"),
        "不明点は合理的な仮定を置いて前進し、仮定は明示する。",
    ),
    (
        "risky_action_confirmation",
        "constraint",
        ("破壊的操作", "破壊的操作前の確認方針", "外部公開", "課金", "機密情報送信", "必ず確認"),
        "破壊的操作・外部公開・課金・機密情報送信の前は確認する。",
    ),
)
ASSISTANT_ASSESSMENT_MARKERS = (
    "完成度",
    "仕上がり",
    "評価",
    "採点",
    "点数",
    "/10",
    "満点",
)
ASSISTANT_SUCCESS_MARKERS = (
    "できるように",
    "しにくくしました",
    "改善しました",
    "最適化しました",
    "効きました",
    "揃え",
    "実装しました",
    "修正しました",
    "更新しました",
    "更新済み",
    "問題ありません",
    "問題ない",
)
ASSISTANT_FAILURE_MARKERS = (
    "できていません",
    "弱い",
    "問題",
    "副作用",
    "崩れ",
    "だめ",
    "足りません",
    "足りない",
    "ノイズ",
    "拾えず",
    "残せていません",
)
ASSISTANT_DECISION_MARKERS = (
    "正本",
    "同期ミラー",
    "採用",
    "設計",
    "opt-in",
    "path 単位",
    "自動更新",
    "方針",
)
ASSISTANT_PROGRESS_MARKERS = (
    "実装しました",
    "追加しました",
    "更新しました",
    "更新済み",
    "修正しました",
    "対応しました",
    "揃えました",
    "揃え直して",
    "作成しました",
    "再生成しました",
    "切り替えました",
    "改善しました",
    "最適化しました",
    "済ませました",
    "上書きしました",
    "差し替え済み",
    "再インストール",
    "インストールしました",
    "再ビルド",
    "ビルドしました",
)
ASSISTANT_VERIFICATION_MARKERS = (
    "pytest",
    "テスト",
    "通過",
    "通しています",
    "通しました",
    "確認しました",
    "検証",
    "lint",
    "doctor",
    "compileall",
)

ASSISTANT_META_PREFIXES = (
    "できると思います",
    "高いです",
    "かなりいいです",
    "その通りです",
    "実装上の方針はこうです",
    "まず",
    "次に",
    "次は",
    "最後に",
    "そこで",
    "なので",
    "ただし",
    "一点だけ",
    "結論としては",
    "おすすめは",
    "むしろ",
)

ASSISTANT_META_PHRASES = (
    "必要なら",
    "ボトルネック",
    "検索・重複排除・上書き",
    "見ます",
    "確認します",
    "切り分けます",
)

GENERIC_SUCCESS_PREFIXES = (
    "常用経路も更新済みです",
    "配布版まで更新済みです",
    "常用版も更新済みです",
    "配布経路も更新済みです",
)

WORKLOG_PROGRESS_TOPIC_MARKERS = (
    (
        "implementation",
        ("test_cli.py", "tests/", "src/", "codex_handoff", "memory.py", "service.py", "renderer.py", "summaries.py", "回帰"),
    ),
    (
        "distribution",
        (
            "配布",
            "再インストール",
            "インストール",
            "再ビルド",
            "setup",
            ".exe",
            "background",
            "cli",
            "%localappdata%",
            "codexhandoff",
            "path",
            "常用経路",
            "新ビルド",
            "差し替え",
            "上書き",
        ),
    ),
)

WORKLOG_VERIFICATION_TOPIC_MARKERS = (
    ("handoff-prepare", ("codex-handoff", "prepare")),
    ("handoff-prepare", ("codex_handoff", "prepare")),
    ("pytest+compileall", ("pytest", "compileall")),
    ("pytest", ("pytest",)),
    ("compileall", ("compileall",)),
    ("lint", ("lint",)),
    ("doctor", ("doctor",)),
    ("test", ("テスト", "tests")),
)

MEMORY_NORMALIZATION_PREFIXES = (
    "方針は固まりました。",
    "実装方針は見えました。",
    "今回で効いた点は 2 つです。",
    "その通りです。",
    "結論としては",
    "結果としては",
)


def load_memory_snapshot(path: Path) -> MemorySnapshot:
    if not path.exists():
        return MemorySnapshot()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return MemorySnapshot()

    semantic_entries = _load_semantic_entries(payload.get("semantic_entries"))
    if not semantic_entries:
        semantic_entries = _load_semantic_entries(payload.get("entries"))
    worklog_entries = _load_worklog_entries(payload.get("worklog_entries"))
    current_focus = payload.get("current_focus")
    if not isinstance(current_focus, str) or not current_focus.strip():
        current_focus = None
    focus_paths = _load_focus_paths(payload.get("focus_paths"))
    next_actions = _load_next_actions(payload.get("next_actions"))
    return MemorySnapshot(
        semantic_entries=semantic_entries,
        worklog_entries=worklog_entries,
        current_focus=current_focus,
        focus_paths=focus_paths,
        next_actions=next_actions,
    )


def render_memory_json(project_paths: ProjectPaths, snapshot: MemorySnapshot, updated_at: str) -> str:
    payload = {
        "version": 2,
        "project_id": project_paths.project_id,
        "project_name": project_paths.root.name,
        "updated_at": updated_at,
        **snapshot.to_dict(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def load_user_memory(path: Path) -> list[MemoryEntry]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = _load_semantic_entries(payload.get("entries"))
    return [entry for entry in entries if _is_user_global_topic(entry.topic)]


def render_user_memory_json(entries: list[MemoryEntry], updated_at: str) -> str:
    payload = {
        "version": 1,
        "updated_at": updated_at,
        "entries": [entry.to_dict() for entry in entries if _is_user_global_topic(entry.topic)],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_user_memory_entries(
    recent_sessions: list[SessionRecord],
    existing_entries: list[MemoryEntry],
    agents_markdown: str,
    updated_at: str,
) -> list[MemoryEntry]:
    extracted: list[MemoryEntry] = []
    extracted.extend(_extract_user_global_entries_from_agents(agents_markdown, updated_at))
    for record in recent_sessions:
        extracted.extend(_extract_user_global_entries_from_record(record))
    merged = _merge_semantic_entries(extracted, existing_entries)
    filtered = [entry for entry in merged if _is_user_global_topic(entry.topic)]
    return filtered[:MAX_USER_GLOBAL_ENTRIES]


def build_memory_snapshot(
    project_root: Path,
    recent_sessions: list[SessionRecord],
    existing_snapshot: MemorySnapshot,
    repo_snapshot: RepoSnapshot,
    updated_at: str,
) -> MemorySnapshot:
    recent_session_ids = {record.session_id for record in recent_sessions}
    semantic_extracted: list[MemoryEntry] = []
    worklog_extracted: list[WorklogEntry] = []
    for record in recent_sessions:
        semantic_items, worklog_items = _extract_session_entries(record)
        semantic_extracted.extend(semantic_items)
        worklog_extracted.extend(worklog_items)

    git_worklog = _build_git_worklog_entries(repo_snapshot, updated_at)
    preserved_semantic = [
        entry
        for entry in existing_snapshot.semantic_entries
        if entry.source_session_id not in recent_session_ids and _should_preserve_semantic_entry(entry)
    ]
    preserved_worklog = [
        entry
        for entry in existing_snapshot.worklog_entries
        if entry.source != "git" and entry.source_session_id not in recent_session_ids
    ]
    current_focus = _build_current_focus(recent_sessions) or existing_snapshot.current_focus
    merged_semantic = _merge_semantic_entries(semantic_extracted, preserved_semantic)
    merged_worklog = _merge_worklog_entries(worklog_extracted + git_worklog, preserved_worklog)
    focus_paths = _build_focus_paths(
        project_root,
        recent_sessions,
        repo_snapshot,
        existing_snapshot.focus_paths,
        current_focus,
        updated_at,
    )
    next_actions = _build_next_actions(
        project_root,
        recent_sessions,
        repo_snapshot,
        existing_snapshot.next_actions,
        current_focus,
        updated_at,
    )
    return MemorySnapshot(
        semantic_entries=_limit_semantic_entries(merged_semantic),
        worklog_entries=_limit_worklog_entries(merged_worklog),
        current_focus=current_focus,
        focus_paths=focus_paths,
        next_actions=next_actions,
    )


def grouped_semantic_entries(snapshot: MemorySnapshot) -> dict[MemoryKind, list[MemoryEntry]]:
    grouped: dict[MemoryKind, list[MemoryEntry]] = {
        "preference": [],
        "spec": [],
        "constraint": [],
        "assessment": [],
        "success": [],
        "failure": [],
        "decision": [],
    }
    for entry in snapshot.semantic_entries:
        grouped[entry.kind].append(entry)
    return grouped


def grouped_worklog_entries(snapshot: MemorySnapshot) -> dict[WorklogKind, list[WorklogEntry]]:
    grouped: dict[WorklogKind, list[WorklogEntry]] = {
        "progress": [],
        "verification": [],
        "commit": [],
        "change": [],
    }
    for entry in snapshot.worklog_entries:
        grouped[entry.kind].append(entry)
    return grouped


def summarize_assistant_reply(text: str | None, limit: int = MAX_ASSISTANT_REPLY_SUMMARY) -> str | None:
    normalized = _normalize_assistant_text(text)
    if not normalized or is_transient_review_message(normalized) or is_transient_review_note(normalized):
        return None

    durable_sentences: list[str] = []
    fallback_sentences: list[str] = []
    skipped_meta_sentence = False
    for sentence in _extract_sentences(normalized):
        if is_transient_review_message(sentence) or is_transient_review_note(sentence):
            continue
        if _looks_like_heading(sentence) or _is_meta_assistant_sentence(sentence) or _looks_like_meta_memory_evaluation(sentence):
            skipped_meta_sentence = True
            continue
        worklog_kinds = _classify_assistant_worklog_text(sentence)
        if worklog_kinds:
            durable_sentences.append(sentence)
            continue
        semantic_kinds = _classify_assistant_semantic_text(sentence)
        if semantic_kinds and set(semantic_kinds) == {"assessment"}:
            skipped_meta_sentence = True
            continue
        if any(_is_durable_assistant_semantic(sentence, kind) for kind in semantic_kinds):
            durable_sentences.append(sentence)
            continue
        if semantic_kinds:
            skipped_meta_sentence = True
            continue
        fallback_sentences.append(sentence)

    candidates = durable_sentences or fallback_sentences
    if not candidates:
        if skipped_meta_sentence:
            return None
        return _truncate(normalized, limit)
    if len(candidates) > 1:
        first = candidates[0]
        second = candidates[1]
        if len(first) < 18 or (
            len(first) < 80
            and (
                _classify_assistant_worklog_text(second)
                or _classify_assistant_semantic_text(second)
            )
            and not _normalized_memory_text(second).startswith(_normalized_memory_text(first))
        ):
            return _truncate(f"{first} {second}", limit)
    return _truncate(candidates[0], limit)


def _load_semantic_entries(raw_entries: object) -> list[MemoryEntry]:
    if not isinstance(raw_entries, list):
        return []

    entries: list[MemoryEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("kind")
        summary = raw.get("summary")
        if kind not in {"preference", "spec", "constraint", "assessment", "success", "failure", "decision"}:
            continue
        if not isinstance(summary, str) or not summary.strip():
            continue
        topic = raw.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            topic = None
        entries.append(
            MemoryEntry(
                kind=kind,
                summary=summary.strip(),
                topic=topic,
                source_session_id=_string_or_none(raw.get("source_session_id")),
                source_role=_string_or_none(raw.get("source_role")),
                updated_at=_string_or_none(raw.get("updated_at")),
                evidence_path=_string_or_none(raw.get("evidence_path")),
            )
        )
    return entries


def _load_worklog_entries(raw_entries: object) -> list[WorklogEntry]:
    if not isinstance(raw_entries, list):
        return []

    entries: list[WorklogEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("kind")
        summary = raw.get("summary")
        if kind not in {"progress", "verification", "commit", "change"}:
            continue
        if not isinstance(summary, str) or not summary.strip():
            continue
        entries.append(
            WorklogEntry(
                kind=kind,
                summary=summary.strip(),
                source=_string_or_none(raw.get("source")),
                source_session_id=_string_or_none(raw.get("source_session_id")),
                updated_at=_string_or_none(raw.get("updated_at")),
                evidence_path=_string_or_none(raw.get("evidence_path")),
            )
        )
    return entries


def _load_focus_paths(raw_entries: object) -> list[FocusPathEntry]:
    if not isinstance(raw_entries, list):
        return []

    entries: list[FocusPathEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        path = raw.get("path")
        reason = raw.get("reason")
        if not isinstance(path, str) or not path.strip():
            continue
        if reason not in {"changed", "mentioned", "important"}:
            continue
        note = raw.get("note")
        if not isinstance(note, str) or not note.strip():
            note = None
        entries.append(
            FocusPathEntry(
                path=path.strip(),
                reason=reason,
                note=note,
                updated_at=_string_or_none(raw.get("updated_at")),
            )
        )
    return entries


def _load_next_actions(raw_entries: object) -> list[NextActionEntry]:
    if not isinstance(raw_entries, list):
        return []

    entries: list[NextActionEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        summary = raw.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            continue
        path = raw.get("path")
        if not isinstance(path, str) or not path.strip():
            path = None
        entries.append(
            NextActionEntry(
                summary=summary.strip(),
                path=path,
                updated_at=_string_or_none(raw.get("updated_at")),
            )
        )
    return entries


def _extract_session_entries(record: SessionRecord) -> tuple[list[MemoryEntry], list[WorklogEntry]]:
    source_path = Path(record.source_path) if record.source_path else None
    if source_path is None or not source_path.exists():
        return [], []

    semantic_entries: list[MemoryEntry] = []
    worklog_entries: list[WorklogEntry] = []
    try:
        with source_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                semantic_batch, worklog_batch = _extract_entries_from_line(line, record)
                semantic_entries.extend(semantic_batch)
                worklog_entries.extend(worklog_batch)
    except OSError:
        return [], []
    return semantic_entries, worklog_entries


def _extract_entries_from_line(line: str, record: SessionRecord) -> tuple[list[MemoryEntry], list[WorklogEntry]]:
    if not line.strip():
        return [], []
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        return [], []

    timestamp = _string_or_none(item.get("timestamp"))
    item_type = item.get("type")
    payload = item.get("payload")
    if not isinstance(payload, dict):
        return [], []

    if item_type == "event_msg" and payload.get("type") == "user_message":
        text = _normalize_text(payload.get("message"))
        if not text:
            return [], []
        return (
            _semantic_entries_from_text(
                text,
                record=record,
                timestamp=timestamp,
                source_role="user",
                kinds=_classify_user_text,
            ),
            [],
        )

    if item_type != "response_item":
        return [], []
    if payload.get("type") != "message" or payload.get("role") != "assistant":
        return [], []
    if payload.get("phase") != "final_answer":
        return [], []

    text = _extract_assistant_text(payload.get("content"))
    if not text:
        return [], []
    return (
        _semantic_entries_from_text(
            text,
            record=record,
            timestamp=timestamp,
            source_role="assistant",
            kinds=_classify_assistant_semantic_text,
        ),
        _worklog_entries_from_text(
            text,
            record=record,
            timestamp=timestamp,
        ),
    )


def _semantic_entries_from_text(
    text: str,
    *,
    record: SessionRecord,
    timestamp: str | None,
    source_role: str,
    kinds,
) -> list[MemoryEntry]:
    if is_transient_review_message(text) or is_transient_review_note(text):
        return []

    entries: list[MemoryEntry] = []
    for sentence in _extract_sentences(text):
        if is_transient_review_message(sentence) or is_transient_review_note(sentence):
            continue
        assistant_worklog_kinds = _classify_assistant_worklog_text(sentence) if source_role == "assistant" else []
        canonical_user_global = _canonical_user_global_entry(
            sentence,
            source_session_id=None,
            evidence_path=None,
            updated_at=None,
        )
        canonical_assistant_entries = (
            _canonical_assistant_semantic_entries(
                sentence,
                record=record,
                timestamp=timestamp,
            )
            if source_role == "assistant"
            else []
        )
        handled_kinds = {entry.kind for entry in canonical_assistant_entries}
        entries.extend(canonical_assistant_entries)
        for kind in kinds(sentence):
            if source_role == "user" and _looks_like_meta_user_memory_tuning(sentence):
                continue
            if source_role == "user" and canonical_user_global:
                continue
            if source_role == "assistant" and canonical_user_global:
                continue
            if source_role == "assistant" and kind in handled_kinds:
                continue
            if source_role == "assistant" and assistant_worklog_kinds and kind != "assessment":
                continue
            if source_role == "assistant" and not _is_durable_assistant_semantic(sentence, kind):
                continue
            entries.append(
                MemoryEntry(
                    kind=kind,
                    summary=_truncate(sentence, MAX_MEMORY_SUMMARY),
                    topic=_semantic_topic(kind, sentence, source_role),
                    source_session_id=record.session_id,
                    source_role=source_role,  # type: ignore[arg-type]
                    updated_at=timestamp or record.updated_at,
                    evidence_path=record.source_path,
                )
            )
    return entries


def _worklog_entries_from_text(
    text: str,
    *,
    record: SessionRecord,
    timestamp: str | None,
) -> list[WorklogEntry]:
    if is_transient_review_message(text) or is_transient_review_note(text):
        return []

    entries: list[WorklogEntry] = []
    for sentence in _extract_sentences(text):
        if is_transient_review_message(sentence) or is_transient_review_note(sentence):
            continue
        matched = False
        for clause in _extract_worklog_clauses(sentence):
            kinds = _classify_assistant_worklog_text(clause)
            if not kinds:
                continue
            matched = True
            for kind in kinds:
                summary = _normalize_worklog_summary(clause, kind)
                if not summary:
                    continue
                entries.append(
                    WorklogEntry(
                        kind=kind,
                        summary=summary,
                        source="assistant_final",
                        source_session_id=record.session_id,
                        updated_at=timestamp or record.updated_at,
                        evidence_path=record.source_path,
                    )
                )
        if matched:
            continue
        for kind in _classify_assistant_worklog_text(sentence):
            entries.append(
                WorklogEntry(
                    kind=kind,
                    summary=_truncate(sentence, MAX_MEMORY_SUMMARY),
                    source="assistant_final",
                    source_session_id=record.session_id,
                    updated_at=timestamp or record.updated_at,
                    evidence_path=record.source_path,
                )
            )
    return entries


def _build_git_worklog_entries(repo_snapshot: RepoSnapshot, updated_at: str) -> list[WorklogEntry]:
    entries: list[WorklogEntry] = []
    for commit in repo_snapshot.recent_commits:
        entries.append(
            WorklogEntry(
                kind="commit",
                summary=f"`{commit.short_hash}` {commit.summary}",
                source="git",
                updated_at=updated_at,
            )
        )

    for change in select_user_facing_changed_files(repo_snapshot.changed_files, limit=MAX_WORKLOG_PER_KIND["change"]):
        entries.append(
            WorklogEntry(
                kind="change",
                summary=f"`{change.path}` ({change.status})",
                source="git",
                updated_at=updated_at,
            )
        )
    return entries


def _build_current_focus(recent_sessions: list[SessionRecord]) -> str | None:
    for record in recent_sessions:
        focus = summarize_actionable_request(
            record.latest_substantive_user_summary
            or record.latest_user_summary
            or record.first_user_summary
            or record.latest_user_message
            or record.first_user_message
        )
        if focus:
            return focus
    return None


def _extract_user_global_entries_from_agents(markdown: str, updated_at: str) -> list[MemoryEntry]:
    entries: list[MemoryEntry] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("<!--") or line.startswith("#"):
            continue
        if line.startswith(("- ", "* ")):
            line = line[2:].strip()
        entry = _canonical_user_global_entry(
            line,
            source_session_id=None,
            evidence_path=None,
            updated_at=updated_at,
        )
        if entry is not None:
            entries.append(entry)
    return entries


def _extract_user_global_entries_from_record(record: SessionRecord) -> list[MemoryEntry]:
    entries: list[MemoryEntry] = []
    for text in (
        record.first_user_message,
        record.latest_user_message,
        record.latest_substantive_user_message,
    ):
        if not text:
            continue
        for sentence in _extract_sentences(text):
            entry = _canonical_user_global_entry(
                sentence,
                source_session_id=record.session_id,
                evidence_path=record.source_path,
                updated_at=record.updated_at,
            )
            if entry is not None:
                entries.append(entry)
    return entries


def _canonical_user_global_entry(
    text: str,
    *,
    source_session_id: str | None,
    evidence_path: str | None,
    updated_at: str | None,
) -> MemoryEntry | None:
    prepared = _prepare_summary(text) or ""
    if not prepared:
        return None
    for topic, kind, markers, canonical in USER_GLOBAL_CANONICAL_RULES:
        if not _matches_user_global_rule(prepared, markers):
            continue
        return MemoryEntry(
            kind=kind,
            summary=canonical,
            topic=topic,
            source_session_id=source_session_id,
            source_role="user",
            updated_at=updated_at,
            evidence_path=evidence_path,
        )
    return None


def _canonical_assistant_semantic_entries(
    text: str,
    *,
    record: SessionRecord,
    timestamp: str | None,
) -> list[MemoryEntry]:
    prepared = _prepare_summary(text) or ""
    if not prepared:
        return []
    if _looks_like_user_global_scope_fragment(prepared):
        return [
            MemoryEntry(
                kind="decision",
                summary="`user-global memory` には恒常的な共通ルールだけを入れ、仕様・設計判断・現在の主題・ファイル文脈・次アクションは project memory に残す。",
                topic="user_global_scope_policy",
                source_session_id=record.session_id,
                source_role="assistant",
                updated_at=timestamp or record.updated_at,
                evidence_path=record.source_path,
            )
        ]
    return []


def _build_focus_paths(
    project_root: Path,
    recent_sessions: list[SessionRecord],
    repo_snapshot: RepoSnapshot,
    existing_entries: list[FocusPathEntry],
    current_focus: str | None,
    updated_at: str,
) -> list[FocusPathEntry]:
    entries: list[FocusPathEntry] = []
    for change in select_user_facing_changed_files(repo_snapshot.changed_files, limit=5):
        entries.append(
            FocusPathEntry(
                path=change.path,
                reason="changed",
                note=current_focus or "最近の変更ファイル",
                updated_at=updated_at,
            )
        )

    for record in recent_sessions[:2]:
        note = _truncate(
            current_focus
            or record.latest_assistant_summary
            or record.latest_substantive_user_summary
            or record.latest_user_summary
            or "最近の会話で参照されたパス",
            120,
        )
        for text in (
            record.latest_substantive_user_message,
            record.latest_user_message,
            record.latest_assistant_message,
            record.first_user_message,
        ):
            for path in _extract_path_candidates(project_root, text):
                entries.append(
                    FocusPathEntry(
                        path=path,
                        reason="mentioned",
                        note=note,
                        updated_at=record.updated_at or updated_at,
                    )
                )

    for path in repo_snapshot.detected_important_paths[:4]:
        entries.append(
            FocusPathEntry(
                path=path,
                reason="important",
                note="重要パス",
                updated_at=updated_at,
            )
        )

    for entry in existing_entries:
        entries.append(entry)

    return _limit_focus_paths(entries, limit=7)


def _build_next_actions(
    project_root: Path,
    recent_sessions: list[SessionRecord],
    repo_snapshot: RepoSnapshot,
    existing_entries: list[NextActionEntry],
    current_focus: str | None,
    updated_at: str,
) -> list[NextActionEntry]:
    entries: list[NextActionEntry] = []
    if current_focus:
        path = _first_path_candidate(project_root, recent_sessions[0].latest_substantive_user_message if recent_sessions else None)
        entries.append(NextActionEntry(summary=current_focus, path=path, updated_at=updated_at))

    for change in select_user_facing_changed_files(repo_snapshot.changed_files, limit=3):
        entries.append(
            NextActionEntry(
                summary=f"`{change.path}` を確認して現在地を把握する。",
                path=change.path,
                updated_at=updated_at,
            )
        )

    if not repo_snapshot.changed_files:
        for path in repo_snapshot.detected_important_paths[:2]:
            entries.append(
                NextActionEntry(
                    summary=f"`{path}` を開いて文脈を戻す。",
                    path=path,
                    updated_at=updated_at,
                )
            )

    for entry in existing_entries:
        entries.append(entry)

    return _limit_next_actions(entries, limit=4)


def _limit_focus_paths(entries: list[FocusPathEntry], limit: int) -> list[FocusPathEntry]:
    deduped: dict[str, FocusPathEntry] = {}
    for entry in sorted(entries, key=_focus_path_sort_key, reverse=True):
        saved = deduped.get(entry.path)
        if saved is None or _focus_path_priority(entry) > _focus_path_priority(saved):
            deduped[entry.path] = entry
    return sorted(deduped.values(), key=_focus_path_sort_key, reverse=True)[:limit]


def _limit_next_actions(entries: list[NextActionEntry], limit: int) -> list[NextActionEntry]:
    deduped: dict[tuple[str, str | None], NextActionEntry] = {}
    for entry in sorted(entries, key=_next_action_sort_key, reverse=True):
        key = (_normalized_memory_text(entry.summary), entry.path)
        deduped.setdefault(key, entry)
    return sorted(deduped.values(), key=_next_action_sort_key, reverse=True)[:limit]


def _focus_path_priority(entry: FocusPathEntry) -> int:
    if entry.reason == "changed":
        return 30
    if entry.reason == "mentioned":
        return 20
    return 10


def _focus_path_sort_key(entry: FocusPathEntry) -> tuple[int, str, str]:
    return (_focus_path_priority(entry), _timestamp_sort_key(entry.updated_at), entry.path)


def _next_action_sort_key(entry: NextActionEntry) -> tuple[str, str, str]:
    return (_timestamp_sort_key(entry.updated_at), entry.path or "", entry.summary)


def _extract_path_candidates(project_root: Path, text: str | None) -> list[str]:
    if not text:
        return []
    candidates: list[str] = []
    for match in re.findall(r"`([^`]+)`", text):
        normalized = _normalize_path_candidate(project_root, match)
        if normalized:
            candidates.append(normalized)
    return _unique(candidates)


def _first_path_candidate(project_root: Path, text: str | None) -> str | None:
    candidates = _extract_path_candidates(project_root, text)
    return candidates[0] if candidates else None


def _normalize_path_candidate(project_root: Path, value: str) -> str | None:
    candidate = value.strip()
    if not candidate:
        return None
    absolute = Path(candidate)
    if absolute.is_absolute():
        try:
            return absolute.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            return None
    relative = (project_root / candidate).resolve()
    if relative.exists():
        return relative.relative_to(project_root.resolve()).as_posix()
    return None


def _classify_user_text(text: str) -> list[MemoryKind]:
    if _looks_like_project_goal_statement(text):
        return ["spec"]
    has_preference = any(marker in text for marker in USER_PREFERENCE_MARKERS)
    has_spec = any(marker in text for marker in USER_SPEC_MARKERS)
    has_constraint = any(marker in text for marker in USER_CONSTRAINT_MARKERS)

    if has_constraint:
        return ["constraint"]
    if has_preference and has_spec:
        preferred = _preferred_user_semantic_kind(text)
        return [preferred] if preferred else []
    if has_preference:
        return ["preference"]
    if has_spec:
        return ["spec"]
    return []


def _classify_assistant_semantic_text(text: str) -> list[MemoryKind]:
    kinds: list[MemoryKind] = []
    if _looks_like_assessment(text):
        kinds.append("assessment")
    if any(marker in text for marker in ASSISTANT_SUCCESS_MARKERS):
        kinds.append("success")
    if _has_failure_marker(text):
        kinds.append("failure")
    if _looks_like_assistant_decision(text):
        kinds.append("decision")
    return kinds


def _classify_assistant_worklog_text(text: str) -> list[WorklogKind]:
    kinds: list[WorklogKind] = []
    if any(marker in text for marker in ASSISTANT_PROGRESS_MARKERS):
        kinds.append("progress")
    lowered = text.lower()
    if (
        any(marker in lowered for marker in ASSISTANT_VERIFICATION_MARKERS)
        and _looks_like_executed_verification(text)
        and not _looks_like_operational_verification(text)
    ):
        kinds.append("verification")
    return kinds


def _is_durable_assistant_semantic(text: str, kind: MemoryKind) -> bool:
    if kind == "assessment":
        if _looks_like_heading(text):
            return False
        if _looks_like_meta_memory_evaluation(text):
            return False
        if _looks_like_relative_quality_assessment(text):
            return False
        return _looks_like_assessment(text)

    if _looks_like_heading(text) or _is_meta_assistant_sentence(text):
        return False

    lowered = text.lower()
    if kind == "success":
        if any(marker in lowered for marker in ASSISTANT_VERIFICATION_MARKERS):
            return False
        if _looks_like_meta_memory_evaluation(text):
            return False
        if _looks_like_confirmation_success(text):
            return False
        if _looks_like_generic_success_status(text):
            return False
        if _looks_like_operational_success(text):
            return False
        if not _has_concrete_semantic_anchor(text):
            return False
        return True

    if kind == "failure":
        if text.startswith(("残っているのは", "そうしないと", "次の")):
            return False
        if _looks_like_meta_memory_evaluation(text):
            return False
        if _looks_like_positive_mitigation(text):
            return False
        if not _has_concrete_semantic_anchor(text):
            return False
        return _looks_like_concrete_failure(text)

    if kind == "decision":
        if len(text) < 12 and "方針" not in text and "設計" not in text:
            return False
        if _looks_like_meta_memory_evaluation(text):
            return False
        if _looks_like_operational_success(text):
            return False
        if _looks_like_user_global_scope_fragment(text):
            return False
        if _looks_like_tentative_assistant_decision(text):
            return False
        if not _looks_like_assistant_decision(text):
            return False
        return _has_decision_action_marker(text)

    return True


def _looks_like_heading(text: str) -> bool:
    cleaned = text.strip("。 ")
    if not cleaned:
        return True
    if cleaned in {
        "ユーザーの思想",
        "守る仕様",
        "避けるべき失敗",
        "現在の評価",
        "直近の進捗",
        "直近の検証結果",
        "直近コミット",
        "会話メモリ",
        "作業メモリ",
    }:
        return True
    return len(cleaned) <= 6 and " " not in cleaned


def _is_meta_assistant_sentence(text: str) -> bool:
    stripped = text.strip()
    if any(stripped.startswith(prefix) for prefix in ASSISTANT_META_PREFIXES):
        return True
    return any(phrase in stripped for phrase in ASSISTANT_META_PHRASES)


def _has_failure_marker(text: str) -> bool:
    positive_problem_phrases = (
        "問題ありません",
        "問題ない",
        "問題はない",
        "支障ありません",
    )
    if any(phrase in text for phrase in positive_problem_phrases):
        return False
    if _looks_like_positive_mitigation(text):
        return False
    return any(marker in text for marker in ASSISTANT_FAILURE_MARKERS)


def _looks_like_executed_verification(text: str) -> bool:
    lowered = text.lower()
    command_markers = ("pytest", "compileall", "lint", "doctor")
    action_markers = ("通しました", "通過", "確認した", "確認しました", "検証しました", "実行しました")
    if any(marker in lowered for marker in command_markers):
        return True
    return any(marker in text for marker in action_markers)


def _looks_like_operational_verification(text: str) -> bool:
    prepared = _prepare_summary(text) or ""
    if not prepared:
        return False
    if any(marker in prepared.lower() for marker in ("pytest", "compileall", "lint", "doctor", "prepare")):
        return False
    return any(
        marker in prepared
        for marker in ("FileVersion", "ProductVersion", ".exe", "%LOCALAPPDATA%", "background")
    )


def _looks_like_meta_memory_evaluation(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "生成された `next-thread.md`",
            "memory.json` を見て",
            "ノイズ・重複・誤優先順位を指摘",
            "再採点",
            "再評価",
            "評価ループ",
            "critic",
            "改善を優先順",
            "現物ベースでは",
            "今すぐ効く改善",
            "満点まで",
            "この順が効きます",
            "少しノイズが残る",
            "昇格条件をもう一段厳しく",
            "README の追従",
            "残件",
            "挙動としては",
            "満点に近い",
            "10/10 に近づ",
        )
    )


def _looks_like_assistant_decision(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith(("方針は固まりました", "実装方針としては", "方針としての結論", "続きをその方針で進められます")):
        return False
    strong_markers = (
        "正本",
        "同期ミラー",
        "global store",
        "local mirror",
        "source of truth",
        "opt-in",
        "path 単位",
        "自動更新",
    )
    if any(marker in text for marker in strong_markers):
        return True
    if not _has_decision_action_marker(text):
        return False
    scope_markers = (
        "候補",
        "方針",
        "正本",
        "同期ミラー",
        "内部状態",
        "memory",
        "next-thread",
        "global store",
        "意味記憶",
        "構造化メモリ",
        "記憶候補",
        "抽出",
        "昇格",
        "作業進捗",
        "コミット",
        "current focus",
        "task",
        "仕様",
        "設計判断",
        "設計方針",
        "現在の主題",
        "ファイル文脈",
        "次アクション",
        "focus_paths",
        "next_actions",
        "user-global",
        "project",
    )
    return any(marker in text for marker in scope_markers)


def _looks_like_user_global_scope_fragment(text: str) -> bool:
    prepared = _prepare_summary(text) or ""
    if not prepared:
        return False
    exact_fragments = {
        "ファイル名禁止",
        "current focus 禁止",
        "next action 禁止",
        "仕様や設計判断も原則禁止",
        "明示的な恒常ルールだけ許可",
    }
    if prepared in exact_fragments:
        return True
    if "これは project 限定のままが正しいです。" in prepared:
        return True
    if "global に入れるとほぼ確実にノイズ" in prepared:
        return True
    return (
        any(marker in prepared for marker in ("user-global", "global"))
        and any(marker in prepared for marker in ("ノイズ", "原則禁止", "禁止", "限定"))
    )


def _has_decision_action_marker(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "にする",
            "とする",
            "禁止",
            "しない",
            "入れる",
            "入れない",
            "分離",
            "追加",
            "維持",
            "優先",
            "正本",
            "同期ミラー",
            "扱う",
            "持たせる",
            "置く",
            "残す",
            "絞る",
            "限定",
            "上書き",
            "再利用",
            "採用",
            "更新",
            "読む",
            "保存",
            "共有",
            "主役にする",
            "脇役",
            "必要があります",
            "必要がある",
            "昇格",
        )
    )


def _looks_like_concrete_failure(text: str) -> bool:
    prepared = _prepare_summary(text) or ""
    if not prepared:
        return False
    if re.search(r"\b[A-Za-z]+Error\b", prepared):
        return True
    concrete_markers = (
        "`",
        ".py",
        ".md",
        ".json",
        ".exe",
        "pytest",
        "compileall",
        "TypeError",
        "FileNotFound",
        "%LOCALAPPDATA%",
        "background",
        "global store",
        "memory.json",
        "next-thread",
        "AGENTS.md",
        "CLI",
        "uv ",
        "scripts/",
        "src/",
    )
    if any(marker in prepared for marker in concrete_markers):
        return True
    problem_markers = ("失敗", "通らない", "崩れる", "上書き", "取りこぼし", "漏れ", "不整合", "ずれる", "古いまま")
    scope_markers = ("memory", "next-thread", "global", "project", "path", "file", "同期", "抽出", "分類", "handoff")
    return any(marker in prepared for marker in problem_markers) and any(marker in prepared for marker in scope_markers)


def _looks_like_tentative_assistant_decision(text: str) -> bool:
    prepared = _prepare_summary(text) or ""
    if not prepared:
        return False
    if prepared.startswith("今は ") and any(marker in prepared for marker in ("まだ", "いません", "ですが", "未", "不足")):
        return True
    if prepared.startswith("今のテストは"):
        return True
    if "使う側まで通しました" in prepared:
        return True
    if "README に明示したい" in prepared:
        return True
    return any(
        marker in prepared
        for marker in (
            "固定すると安心です",
            "明示したいです",
            "改善余地があります",
            "本質的なのは",
        )
    )


def _looks_like_confirmation_success(text: str) -> bool:
    prepared = _prepare_summary(text) or ""
    if not prepared:
        return False
    if not any(phrase in prepared for phrase in ("問題ありません", "大丈夫です", "実用レベルです", "release-ready")):
        return False
    detail_markers = (
        "`",
        ".py",
        ".md",
        ".json",
        ".exe",
        "PATH",
        "CLI",
        "background",
        "pytest",
        "compileall",
        "%LOCALAPPDATA%",
    )
    return not any(marker in prepared for marker in detail_markers)


def _looks_like_generic_success_status(text: str) -> bool:
    prepared = _prepare_summary(text) or ""
    if not prepared:
        return False
    if any(prepared.startswith(prefix) for prefix in GENERIC_SUCCESS_PREFIXES):
        return True
    if not prepared.endswith(("更新済みです。", "更新済みです", "済みです。", "済みです")):
        return False
    detail_markers = ("`", ".py", ".md", ".json", ".exe", "PATH", "CLI", "background", "pytest", "compileall", "%LOCALAPPDATA%")
    return not any(marker in prepared for marker in detail_markers)


def _looks_like_positive_mitigation(text: str) -> bool:
    return any(marker in text for marker in ("減ります", "減らします", "防げます", "避けられます", "抑えます"))


def _looks_like_operational_success(text: str) -> bool:
    operational_markers = (
        "PATH",
        "CLI",
        ".exe",
        ".py",
        ".md",
        "%LOCALAPPDATA%",
        "background",
        "インストール",
        "再インストール",
        "再ビルド",
        "差し替え",
        "ローカル",
        "更新済み",
        "揃えて",
        "揃え直して",
        "バージョン",
    )
    if any(marker in text for marker in ("問題ありません", "問題ない")):
        return True
    if re.search(r"v?\d+\.\d+(?:\.\d+)?", text):
        return True
    if not any(marker in text for marker in operational_markers):
        return False
    return any(
        marker in text
        for marker in (
            "PATH",
            ".exe",
            ".py",
            ".md",
            "%LOCALAPPDATA%",
            "差し替え",
            "再インストール",
            "再ビルド",
            "更新済み",
            "揃え直して",
        )
    )


def _looks_like_relative_quality_assessment(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "満点に近い",
            "満点にかなり近い",
            "10/10 に近い",
            "10/10 に近づ",
            "本質的には README の追従くらい",
        )
    )


def _has_concrete_semantic_anchor(text: str) -> bool:
    anchor_markers = (
        "`",
        ".py",
        ".md",
        ".json",
        ".exe",
        "README",
        "AGENTS.md",
        "memory",
        "memory.json",
        "user-memory",
        "next-thread",
        "次スレッド",
        "global store",
        "project store",
        "handoff",
        "構造化メモリ",
        "意味記憶",
        "記憶候補",
        "抽出",
        "昇格",
        "focus_paths",
        "next_actions",
        "current focus",
        "依頼要約",
        "文分割",
        "要約",
        "コミット",
        "変更ファイル",
        "回帰",
        "テスト",
        "pytest",
        "compileall",
        "prepare",
        "project",
        "プロジェクト",
    )
    return any(marker in text for marker in anchor_markers)


def _should_preserve_semantic_entry(entry: MemoryEntry) -> bool:
    if entry.source_role != "assistant":
        return True
    return _is_durable_assistant_semantic(entry.summary, entry.kind)


def _merge_semantic_entries(current: list[MemoryEntry], existing: list[MemoryEntry]) -> list[MemoryEntry]:
    merged: list[MemoryEntry] = []
    for entry in sorted(current + existing, key=_semantic_sort_key, reverse=True):
        if any(_semantic_entries_match(entry, saved) for saved in merged):
            continue
        merged.append(entry)
    return _dedupe_semantic_entries_across_kinds(merged)


def _merge_worklog_entries(current: list[WorklogEntry], existing: list[WorklogEntry]) -> list[WorklogEntry]:
    merged: dict[tuple[str, str], WorklogEntry] = {}
    for entry in sorted(current + existing, key=_worklog_sort_key, reverse=True):
        key = (entry.kind, _canonical_worklog_key(entry))
        merged.setdefault(key, entry)
    return list(merged.values())


def _limit_semantic_entries(entries: list[MemoryEntry]) -> list[MemoryEntry]:
    limited: list[MemoryEntry] = []
    counts: dict[MemoryKind, int] = {
        "preference": 0,
        "spec": 0,
        "constraint": 0,
        "assessment": 0,
        "success": 0,
        "failure": 0,
        "decision": 0,
    }
    for entry in sorted(entries, key=_semantic_sort_key, reverse=True):
        if counts[entry.kind] >= MAX_SEMANTIC_PER_KIND[entry.kind]:
            continue
        limited.append(entry)
        counts[entry.kind] += 1
    return limited


def _limit_worklog_entries(entries: list[WorklogEntry]) -> list[WorklogEntry]:
    limited: list[WorklogEntry] = []
    counts: dict[WorklogKind, int] = {
        "progress": 0,
        "verification": 0,
        "commit": 0,
        "change": 0,
    }
    verification_topics = {
        _verification_topic_name(entry.summary)
        for entry in entries
        if entry.kind == "verification"
    }
    for entry in sorted(entries, key=_worklog_entry_sort_key, reverse=True):
        if _is_superseded_worklog_entry(entry, verification_topics):
            continue
        if counts[entry.kind] >= MAX_WORKLOG_PER_KIND[entry.kind]:
            continue
        limited.append(entry)
        counts[entry.kind] += 1
    return limited


def _worklog_entry_sort_key(entry: WorklogEntry) -> tuple[int, str, str, str]:
    return (
        _worklog_entry_priority(entry),
        _timestamp_sort_key(entry.updated_at),
        entry.source_session_id or "",
        entry.summary,
    )


def _semantic_entries_match(left: MemoryEntry, right: MemoryEntry) -> bool:
    if left.topic and right.topic and left.topic == right.topic:
        return True
    if left.kind != right.kind:
        return False
    left_key = _normalized_memory_text(left.summary)
    right_key = _normalized_memory_text(right.summary)
    if not left_key or not right_key:
        return False
    if left_key == right_key or left_key.startswith(right_key) or right_key.startswith(left_key):
        return True
    left_tokens = set(left_key.split())
    right_tokens = set(right_key.split())
    if min(len(left_tokens), len(right_tokens)) < 3:
        return False
    return len(left_tokens & right_tokens) >= min(3, len(left_tokens), len(right_tokens))


def _dedupe_semantic_entries_across_kinds(entries: list[MemoryEntry]) -> list[MemoryEntry]:
    deduped: dict[str, MemoryEntry] = {}
    passthrough: list[MemoryEntry] = []
    for entry in sorted(entries, key=_semantic_sort_key, reverse=True):
        key = _semantic_dedupe_key(entry)
        if not key:
            passthrough.append(entry)
            continue
        saved = deduped.get(key)
        if saved is None or _prefer_semantic_entry(entry, saved):
            deduped[key] = entry
    return sorted([*passthrough, *deduped.values()], key=_semantic_sort_key, reverse=True)


def _prefer_semantic_entry(candidate: MemoryEntry, saved: MemoryEntry) -> bool:
    if candidate.topic and saved.topic and candidate.topic == saved.topic:
        candidate_time = _timestamp_sort_key(candidate.updated_at)
        saved_time = _timestamp_sort_key(saved.updated_at)
        if candidate_time != saved_time:
            return candidate_time > saved_time
        candidate_source = _semantic_source_priority(candidate)
        saved_source = _semantic_source_priority(saved)
        if candidate_source != saved_source:
            return candidate_source > saved_source
    candidate_score = _semantic_entry_priority(candidate)
    saved_score = _semantic_entry_priority(saved)
    if candidate_score != saved_score:
        return candidate_score > saved_score
    return _semantic_sort_key(candidate) > _semantic_sort_key(saved)


def _semantic_dedupe_key(entry: MemoryEntry) -> str:
    if entry.topic:
        return f"topic:{entry.topic}"
    return _normalized_memory_text(entry.summary)


def _semantic_source_priority(entry: MemoryEntry) -> int:
    if entry.source_role == "user":
        return 2
    if entry.source_role == "assistant":
        return 1
    return 0


def _semantic_entry_priority(entry: MemoryEntry) -> int:
    if entry.kind == "constraint":
        return 60
    if entry.kind == "decision":
        return 50
    if entry.kind == "assessment":
        return 40
    if entry.kind in {"preference", "spec"}:
        if entry.kind == "spec" and _looks_like_project_goal_statement(entry.summary):
            return 48
        preferred = _preferred_user_semantic_kind(entry.summary)
        if preferred == entry.kind:
            return 45
        return 35
    if entry.kind == "success":
        return 30
    if entry.kind == "failure":
        return 20
    return 10


def _preferred_user_semantic_kind(text: str) -> MemoryKind | None:
    if _looks_like_project_goal_statement(text):
        return "spec"
    if any(marker in text for marker in USER_STRONG_PREFERENCE_MARKERS):
        return "preference"
    if any(marker in text for marker in USER_STRONG_SPEC_MARKERS):
        return "spec"
    if any(marker in text for marker in USER_PREFERENCE_MARKERS):
        return "preference"
    if any(marker in text for marker in USER_SPEC_MARKERS):
        return "spec"
    return None


def _looks_like_meta_user_memory_tuning(text: str) -> bool:
    return any(marker in text for marker in USER_META_MEMORY_MARKERS)


def _is_user_global_topic(topic: str | None) -> bool:
    if not topic:
        return False
    return any(topic == name for name, *_ in USER_GLOBAL_CANONICAL_RULES)


def _matches_user_global_rule(text: str, markers: tuple[str, ...]) -> bool:
    if "必ず確認" in markers:
        base_markers = tuple(marker for marker in markers if marker != "必ず確認")
        return "確認" in text and any(marker in text for marker in base_markers)
    return any(marker in text for marker in markers)


def _semantic_topic(kind: MemoryKind, text: str, source_role: str) -> str | None:
    prepared = _prepare_summary(text) or ""
    if not prepared:
        return None
    for topic, markers in SEMANTIC_TOPIC_RULES:
        if any(marker in prepared for marker in markers):
            if topic == "assessment_policy" and kind != "assessment" and source_role != "user":
                continue
            return topic
    return None


def _looks_like_project_goal_statement(text: str) -> bool:
    prepared = _prepare_summary(text) or ""
    if not prepared:
        return False
    if any(marker in prepared for marker in USER_PROJECT_GOAL_MARKERS):
        return True
    if "目的" not in prepared and "主目的" not in prepared:
        return False
    return any(
        marker in prepared
        for marker in (
            "スレッド",
            "情報共有",
            "引き継",
            "再開",
            "内部状態",
            "ユーザーに見せる",
        )
    )


def _looks_like_assessment(text: str) -> bool:
    prepared = _prepare_summary(text) or ""
    if not prepared:
        return False
    if ASSESSMENT_SCORE_PATTERN.search(prepared):
        return True
    explicit_context = any(marker in prepared for marker in ("評価", "点数", "採点", "スコア", "現在の評価"))
    if "満点" in prepared and explicit_context and any(marker in prepared for marker in ("近い", "届く", "狙う", "目指す")):
        return True
    if not any(marker in prepared for marker in ASSISTANT_ASSESSMENT_MARKERS):
        return False
    if not explicit_context:
        return False
    return any(
        marker in prepared
        for marker in ("高い", "低い", "近い", "届く", "十分", "実用レベル", "かなりいい", "ほぼ", "未満")
    )


def _canonical_worklog_key(entry: WorklogEntry) -> str:
    summary = _prepare_summary(entry.summary) or entry.summary
    if entry.kind == "verification":
        topic = _verification_topic_name(summary)
        if topic:
            return topic
        return _normalized_memory_text(summary)
    if entry.kind == "progress":
        topic = _progress_topic_name(summary)
        if topic:
            return topic
    return _normalized_memory_text(summary)


def _progress_topic_name(summary: str) -> str | None:
    lowered = summary.lower()
    for name, markers in WORKLOG_PROGRESS_TOPIC_MARKERS:
        if any(marker in lowered for marker in markers):
            return name
    return None


def _worklog_entry_priority(entry: WorklogEntry) -> int:
    if entry.kind == "progress":
        topic = _progress_topic_name(entry.summary)
        if topic == "implementation":
            return 30
        if topic == "distribution":
            return 10
    if entry.kind == "verification":
        topic = _verification_topic_name(entry.summary)
        if topic == "pytest+compileall":
            return 25
        if topic == "handoff-prepare":
            return 15
    return 20


def _normalized_memory_text(text: str) -> str:
    cleaned = _prepare_summary(text) or ""
    for prefix in MEMORY_NORMALIZATION_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    cleaned = re.sub(r"v?\d+\.\d+(?:\.\d+)?", "", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", cleaned)
    cleaned = re.sub(r"[「」『』()\[\]{}:：、。,.!?！？/\\]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def _extract_worklog_clauses(sentence: str) -> list[str]:
    normalized = sentence.replace("したうえで", "した,").replace("した上で", "した,")
    parts = [part.strip(" ,") for part in re.split(r"[、,]", normalized) if part.strip(" ,")]
    return parts or [sentence]


def _normalize_worklog_summary(text: str, kind: WorklogKind) -> str | None:
    prepared = _prepare_summary(text)
    if not prepared:
        return None
    prepared = re.sub(r"^(?:あわせて|さらに|また)\s*", "", prepared)
    if kind == "verification" and not any(marker in prepared.lower() for marker in ASSISTANT_VERIFICATION_MARKERS):
        return None
    return _truncate(prepared.rstrip("。 ") + "。", MAX_MEMORY_SUMMARY)


def _semantic_sort_key(entry: MemoryEntry) -> tuple[str, str, str, str]:
    return (
        f"{_semantic_entry_priority(entry):02d}",
        _timestamp_sort_key(entry.updated_at),
        entry.source_session_id or "",
        entry.summary,
    )


def _worklog_sort_key(entry: WorklogEntry) -> tuple[str, str, str, str]:
    return (f"{_worklog_entry_priority(entry):02d}", _timestamp_sort_key(entry.updated_at), entry.source_session_id or "", entry.summary)


def _timestamp_sort_key(value: str | None) -> str:
    if not value:
        return ""
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return value


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_items.append(key)
    return unique_items


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
    return _normalize_assistant_text("\n".join(parts))


def _normalize_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    collapsed = " ".join(segment for segment in value.split())
    return collapsed or None


def _normalize_assistant_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in normalized.splitlines()]
    filtered = [line for line in lines if line]
    return "\n".join(filtered) or None


def _extract_sentences(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace(" - ", "。")
    sentences: list[str] = []
    for raw_line in normalized.splitlines():
        line = re.sub(r"^(?:[-*]\s+|\d+\.\s+)", "", raw_line.strip())
        if not line:
            continue
        for part in split_summary_sentences(line):
            sentence = _prepare_summary(part)
            if sentence:
                sentences.append(sentence)
    return sentences


def _prepare_summary(text: str) -> str | None:
    cleaned = text.strip(" -")
    if not cleaned:
        return None
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "")
    cleaned = " ".join(cleaned.split())
    return cleaned or None


def _verification_topic_name(summary: str) -> str | None:
    lowered = summary.lower()
    for name, markers in WORKLOG_VERIFICATION_TOPIC_MARKERS:
        if all(marker in lowered for marker in markers):
            return name
    return None


def _is_superseded_worklog_entry(entry: WorklogEntry, verification_topics: set[str | None]) -> bool:
    if entry.kind != "verification":
        return False
    topic = _verification_topic_name(entry.summary)
    if topic in {"pytest", "compileall"} and "pytest+compileall" in verification_topics:
        return True
    return False


def _truncate(text: str, limit: int) -> str:
    text = _sanitize_unbalanced_backticks(text)
    if len(text) <= limit:
        return text
    return _sanitize_unbalanced_backticks(text[: limit - 1].rstrip()) + "…"


def _sanitize_unbalanced_backticks(text: str) -> str:
    if text.count("`") % 2 == 0:
        return text
    return text.replace("`", "")


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None
