from __future__ import annotations

from codex_handoff.memory import (
    _classify_assistant_semantic_text,
    _classify_user_text,
    _is_durable_assistant_semantic,
    _limit_semantic_entries,
    _looks_like_assessment,
    _merge_semantic_entries,
)
from codex_handoff.models import MemoryEntry


def test_assessment_detection_accepts_decimal_point_scores() -> None:
    text = "今は9.95点です。満点にかなり近いです。"

    assert _looks_like_assessment(text) is True
    assert "assessment" in _classify_assistant_semantic_text(text)


def test_assessment_detection_does_not_promote_generic_praise() -> None:
    text = "かなりいいです。問題ありません。"

    assert _looks_like_assessment(text) is False
    assert "assessment" not in _classify_assistant_semantic_text(text)


def test_assistant_assessment_filter_rejects_generic_quality_push() -> None:
    text = "ここまでやると、かなり 10/10 に近づきます。"

    assert _looks_like_assessment(text) is True
    assert _is_durable_assistant_semantic(text, "assessment") is False


def test_assistant_assessment_filter_rejects_readme_followup_status() -> None:
    text = "今の残件は本質的には README の追従くらいで、挙動としてはかなり満点に近いです。"

    assert _looks_like_assessment(text) is False
    assert _is_durable_assistant_semantic(text, "assessment") is False


def test_assistant_decision_filter_rejects_unresolved_current_state() -> None:
    text = "今は bootstrap.py で `~/.codex-handoff/user-memory.json` を読むよう指示していますが、service.py 側で「次スレッド投入用の compact context」に直接混ぜてはいません。"

    assert _is_durable_assistant_semantic(text, "decision") is False


def test_assistant_decision_filter_rejects_recommendation_status() -> None:
    text = "今のテストは単体としては十分ですが、「A プロジェクトで global 更新 → B プロジェクトで project memory は混ざらず global だけ効く」を 1 本の E2E で固定すると安心です。"

    assert _is_durable_assistant_semantic(text, "decision") is False


def test_generic_success_without_concrete_anchor_is_not_durable() -> None:
    text = "常用経路も揃えました。"

    assert "success" in _classify_assistant_semantic_text(text)
    assert _is_durable_assistant_semantic(text, "success") is False


def test_user_global_policy_echo_is_not_durable_project_decision() -> None:
    text = "破壊的操作前の確認方針"

    assert "decision" not in _classify_assistant_semantic_text(text) or _is_durable_assistant_semantic(text, "decision") is False


def test_assistant_decision_filter_rejects_user_global_scope_fragments() -> None:
    fragments = (
        "仕様や設計判断も原則禁止",
        "current focus 禁止",
        "これは project 限定のままが正しいです。",
    )

    for text in fragments:
        assert _is_durable_assistant_semantic(text, "decision") is False


def test_user_project_goal_statement_promotes_to_spec() -> None:
    text = "ユーザーに見せる必要ないよ。スレッド間で情報共有できることが目的です。"

    assert _classify_user_text(text) == ["spec"]


def test_limit_semantic_entries_keeps_project_goal_spec_under_recency_pressure() -> None:
    entries = [
        MemoryEntry(
            kind="spec",
            summary="ユーザーに見せる必要ないよ。スレッド間で情報共有できることが目的です。",
            source_role="user",
            updated_at="2026-03-18T10:00:00+09:00",
        ),
        MemoryEntry(kind="spec", summary="現在の評価を必須項目にしたいわけではないです。", source_role="user", updated_at="2026-03-19T10:00:00+09:00"),
        MemoryEntry(kind="spec", summary="でも作業進捗とかコミットとかも必要だね。", source_role="user", updated_at="2026-03-19T10:01:00+09:00"),
        MemoryEntry(kind="spec", summary="項目を細分化し、必須項目を増やすほどうまく処理できないのではないでしょうか？", source_role="user", updated_at="2026-03-19T10:02:00+09:00"),
        MemoryEntry(kind="spec", summary="ファイルやフォルダ名込みで何をどう操作したかが残るといい。", source_role="user", updated_at="2026-03-19T10:03:00+09:00"),
        MemoryEntry(kind="spec", summary="これからどうすべきかも残るといい。", source_role="user", updated_at="2026-03-19T10:04:00+09:00"),
    ]

    limited = _limit_semantic_entries(entries)
    summaries = [entry.summary for entry in limited if entry.kind == "spec"]

    assert len(summaries) == 5
    assert "ユーザーに見せる必要ないよ。スレッド間で情報共有できることが目的です。" in summaries


def test_merge_semantic_entries_supersedes_same_topic_with_newer_spec() -> None:
    existing = [
        MemoryEntry(
            kind="spec",
            summary="主要なあらすじを引き継げればいいです。",
            topic="handoff_goal",
            source_role="user",
            updated_at="2026-03-18T10:00:00+09:00",
        )
    ]
    current = [
        MemoryEntry(
            kind="spec",
            summary="スレッド間で情報共有できることが目的です。",
            topic="handoff_goal",
            source_role="user",
            updated_at="2026-03-19T10:00:00+09:00",
        )
    ]

    merged = _merge_semantic_entries(current, existing)

    assert [entry.summary for entry in merged if entry.topic == "handoff_goal"] == [
        "スレッド間で情報共有できることが目的です。"
    ]


def test_merge_semantic_entries_supersedes_same_topic_across_kinds_by_recency() -> None:
    existing = [
        MemoryEntry(
            kind="spec",
            summary="`memory.json` を正本として扱いたい。",
            topic="storage_strategy",
            source_role="user",
            updated_at="2026-03-18T10:00:00+09:00",
        )
    ]
    current = [
        MemoryEntry(
            kind="decision",
            summary="`memory.json` を内部状態の正本にして次スレッドへ再注入する方針です。",
            topic="storage_strategy",
            source_role="assistant",
            updated_at="2026-03-19T10:00:00+09:00",
        )
    ]

    merged = _merge_semantic_entries(current, existing)

    assert [entry.summary for entry in merged if entry.topic == "storage_strategy"] == [
        "`memory.json` を内部状態の正本にして次スレッドへ再注入する方針です。"
    ]
