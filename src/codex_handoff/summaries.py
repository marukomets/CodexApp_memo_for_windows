from __future__ import annotations

import re

from codex_handoff.relevance import is_transient_review_message


MAX_USER_REQUEST_SUMMARY = 160

LEADING_DISCOURSE_PATTERNS = (
    r"^(?:そうだね。?\s*)+",
    r"^(?:その通りです。?\s*)+",
    r"^(?:うん。?\s*)+",
)

TRAILING_SOFTENER_PATTERNS = (
    r"(?:うまくできるかな|大丈夫かな|どうかな)[。?？!！]*$",
)

FOLLOWUP_ONLY_MESSAGES = {
    "やって",
    "やってください",
    "進めて",
    "進めてください",
    "続き",
    "続きを",
    "続けて",
    "続けてください",
    "お願いします",
    "お願い",
    "やれるならやって",
    "完璧にしよう",
}

STATUS_ONLY_PHRASES = (
    "今何点",
    "さらにつめるところ",
    "subagentで結果の評価",
    "完成度としてはどう",
    "かなりいい感じ",
    "問題ない",
    "自信のほど",
)

VAGUE_FOLLOWUP_PATTERNS = (
    r"^(?:そこ|それ|このへん|ここ)(?:も|は)?",
    r"ちゃんと(?:詰め|進め)",
    r"^最後の力を振り絞って",
)

META_MEMORY_TUNING_PATTERNS = (
    r"このメモの内容を最適化",
    r"このメモ.*最適化",
)

ORCHESTRATION_ONLY_PATTERNS = (
    r"subagent.*駆使",
    r"subagent.*評価",
    r"subagent.*調整",
    r"subagent.*仕上げ",
)


def summarize_user_request(text: str | None, limit: int = MAX_USER_REQUEST_SUMMARY) -> str | None:
    cleaned = normalize_summary_text(text)
    if not cleaned or is_transient_review_message(cleaned):
        return None
    if any(re.search(pattern, cleaned) for pattern in META_MEMORY_TUNING_PATTERNS):
        return None
    if any(re.search(pattern, cleaned, re.IGNORECASE) for pattern in ORCHESTRATION_ONLY_PATTERNS):
        return None
    if _is_followup_only_request(cleaned):
        return None
    cleaned = _compact_request_text(cleaned)
    if not cleaned:
        return None
    return truncate_summary(cleaned, limit)


def summarize_actionable_request(text: str | None, limit: int = MAX_USER_REQUEST_SUMMARY) -> str | None:
    cleaned = summarize_user_request(text, limit=max(limit * 2, MAX_USER_REQUEST_SUMMARY))
    if not cleaned:
        return None

    sentences = [_actionify_request_sentence(part) for part in _split_request_sentences(cleaned)]
    actionable = " ".join(part for part in sentences if part).strip()
    if not actionable:
        return None
    return truncate_summary(actionable, limit)


def normalize_summary_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


def split_summary_sentences(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    parts: list[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts.extend(_split_line_sentences(line))
    return parts or [text.strip()]


def truncate_summary(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _is_followup_only_request(text: str) -> bool:
    lowered = text.lower()
    if lowered in FOLLOWUP_ONLY_MESSAGES:
        return True
    if text.endswith(("どう？", "どう?", "いい？", "いい?")) and len(text) <= 30:
        return True
    if any(phrase in text for phrase in STATUS_ONLY_PHRASES):
        return True
    if any(re.search(pattern, text) for pattern in VAGUE_FOLLOWUP_PATTERNS):
        action_markers = ("やって", "進め", "詰め", "頼む", "お願い", "目指しましょう", "目指そう", "最適化", "改善")
        if any(marker in text for marker in action_markers):
            return True
    return False


def _compact_request_text(text: str) -> str:
    compacted = text.strip()
    for pattern in LEADING_DISCOURSE_PATTERNS:
        compacted = re.sub(pattern, "", compacted).strip()
    for pattern in TRAILING_SOFTENER_PATTERNS:
        compacted = re.sub(pattern, "", compacted).strip()
    compacted = re.sub(r"\s+", " ", compacted).strip()
    return compacted


def _split_request_sentences(text: str) -> list[str]:
    return split_summary_sentences(text)


def _split_line_sentences(line: str) -> list[str]:
    sentences: list[str] = []
    buffer: list[str] = []
    in_code = False
    length = len(line)
    for index, char in enumerate(line):
        if char == "`":
            in_code = not in_code
        buffer.append(char)
        if in_code:
            continue
        if char in "。！？":
            sentence = "".join(buffer).strip()
            if sentence:
                sentences.append(sentence)
            buffer = []
            continue
        if char not in ".!?":
            continue
        next_char = line[index + 1] if index + 1 < length else ""
        if next_char and not next_char.isspace():
            continue
        sentence = "".join(buffer).strip()
        if sentence:
            sentences.append(sentence)
        buffer = []

    trailing = "".join(buffer).strip()
    if trailing:
        sentences.append(trailing)
    return sentences


def _actionify_request_sentence(text: str) -> str:
    sentence = text.strip()
    if not sentence:
        return ""

    sentence = re.sub(r"^(?:でも|ただ|あと|それと)\s*", "", sentence)
    if _is_followup_only_request(sentence.rstrip("。.!?！？").strip()):
        return ""
    sentence = re.sub(r"してほしい(?:です)?(?=[。.!?！？]?$)", "する", sentence)
    sentence = re.sub(r"したい(?:な|です)?(?=[。.!?！？]?$)", "する", sentence)
    sentence = re.sub(r"も必要(?:だね|です|だ)?(?=[。.!?！？]?$)", "も含める", sentence)
    sentence = re.sub(r"が必要(?:だね|です|だ)?(?=[。.!?！？]?$)", "が必要", sentence)
    sentence = re.sub(r"(?:うまくできるかな|できるかな|かな)(?=[。.!?！？]?$)", "", sentence)
    sentence = re.sub(r"\s+", " ", sentence).strip().rstrip("。.!?！？")
    return f"{sentence}。" if sentence else ""
