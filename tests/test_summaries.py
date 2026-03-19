from __future__ import annotations

from codex_handoff.summaries import split_summary_sentences, summarize_actionable_request


def test_summarize_actionable_request_splits_japanese_sentences_without_spaces() -> None:
    text = "説明を更新したい。テストも追加したい。"

    assert summarize_actionable_request(text) == "説明を更新する。 テストも追加する。"


def test_summarize_actionable_request_drops_sentence_level_followups() -> None:
    text = "READMEを更新したい。お願いします。"

    assert summarize_actionable_request(text) == "READMEを更新する。"


def test_split_summary_sentences_keeps_japanese_periods_inside_backticks() -> None:
    text = "依頼要約は、日本語の句点直後に空白がなくても文分割できるようにし、文単位の `お願いします。` のような追従だけを落とすようにしました。"

    assert split_summary_sentences(text) == [text]
