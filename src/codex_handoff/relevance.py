from __future__ import annotations


TRANSIENT_REVIEW_MESSAGE_MARKERS = (
    "## Code review guidelines",
    "# Review findings:",
    "Review findings:",
    "review the current code changes",
    "provide prioritized findings",
    "rerun the review",
    "未コミットの変更をレビュー",
    "未コミット差分をレビュー",
    "現在のコード変更をレビュー",
    "P1とP2日本語で簡単に教えて",
)

TRANSIENT_REVIEW_NOTE_MARKERS = (
    "staged/unstaged",
    "差分量と中身を確認",
    "関連箇所を追います",
    "Select-String",
    "実害のある退行が入っているかを見ます",
)


def normalize_relevance_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.split()).strip()


def is_transient_review_message(text: str | None) -> bool:
    cleaned = normalize_relevance_text(text)
    if not cleaned:
        return False

    lowered = cleaned.lower()
    if any(marker.lower() in lowered for marker in TRANSIENT_REVIEW_MESSAGE_MARKERS):
        return True

    return "review findings" in lowered and ".codex-handoff" in lowered


def is_transient_review_note(text: str | None) -> bool:
    cleaned = normalize_relevance_text(text)
    if not cleaned:
        return False
    if is_transient_review_message(cleaned):
        return True
    return any(marker in cleaned for marker in TRANSIENT_REVIEW_NOTE_MARKERS)
