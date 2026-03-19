from __future__ import annotations

from codex_handoff.files import markdown_body_or_fallback
from codex_handoff.focus import select_user_facing_changed_files
from codex_handoff.memory import _looks_like_meta_memory_evaluation, grouped_semantic_entries, grouped_worklog_entries
from codex_handoff.models import HandoffDocument, SessionRecord
from codex_handoff.summaries import summarize_actionable_request


class CodexMarkdownRenderer:
    def render(self, handoff: HandoffDocument) -> str:
        return self.render_next_thread(handoff)

    def render_project(self, handoff: HandoffDocument) -> str:
        context = handoff.manual_context
        lines = [
            "# Project Context",
            "",
            "- 自動更新: `codex-handoff prepare` / `capture` / background sync",
            f"- 生成日時: `{handoff.generated_at}`",
            f"- ルート: `{handoff.root_path}`",
            "",
            "## 目的",
            "",
            markdown_body_or_fallback(
                context.purpose,
                "- このプロジェクトの目的はまだ抽出できていません。",
            ),
            "",
            "## 制約",
            "",
            markdown_body_or_fallback(
                context.constraints,
                "- 制約はまだ抽出できていません。",
            ),
            "",
            "## 重要ファイル",
            "",
            markdown_body_or_fallback(
                context.important_files,
                "- 重要ファイルはまだ抽出できていません。",
            ),
            "",
            "## 運用ルール",
            "",
            markdown_body_or_fallback(
                context.operating_rules,
                "- 運用ルールはまだ抽出できていません。",
            ),
            "",
            "## 仮定",
            "",
            markdown_body_or_fallback(
                context.assumptions,
                "- 仮定はまだ抽出できていません。",
            ),
        ]
        return "\n".join(lines).strip() + "\n"

    def render_decisions(self, handoff: HandoffDocument) -> str:
        lines = [
            "# Decisions",
            "",
            "- 自動更新: `codex-handoff prepare` / `capture` / background sync",
            f"- 生成日時: `{handoff.generated_at}`",
            "",
            markdown_body_or_fallback(
                handoff.manual_context.decisions_markdown,
                "- 決定事項はまだ抽出できていません。",
            ),
        ]
        return "\n".join(lines).strip() + "\n"

    def render_tasks(self, handoff: HandoffDocument) -> str:
        lines = [
            "# Tasks",
            "",
            "- 自動更新: `codex-handoff prepare` / `capture` / background sync",
            f"- 生成日時: `{handoff.generated_at}`",
            "",
            markdown_body_or_fallback(
                handoff.manual_context.tasks_markdown,
                "- [ ] 次に進める作業はまだ抽出できていません。",
            ),
        ]
        return "\n".join(lines).strip() + "\n"

    def render_next_thread(self, handoff: HandoffDocument) -> str:
        lines: list[str] = [
            f"# Next Thread Brief: {handoff.project_name}",
            "",
            f"- 生成日時: `{handoff.generated_at}`",
            f"- ルート: `{handoff.root_path}`",
            f"- メモ保存先: `{handoff.handoff_dir}`",
            "",
            "## このプロジェクトの目的",
            "",
        ]
        lines.extend(self._purpose_section(handoff))
        lines.extend(
            [
                "",
                "## プロジェクト記憶",
                "",
            ]
        )
        lines.extend(self._semantic_memory_section(handoff))
        lines.extend(
            [
                "",
                "## 最近の作業記録",
                "",
            ]
        )
        lines.extend(self._worklog_section(handoff))
        lines.extend(
            [
                "",
                "## 現在の主題",
                "",
            ]
        )
        lines.extend(self._current_focus_section(handoff))
        lines.extend(
            [
                "",
                "## 直近の会話要点",
                "",
            ]
        )
        lines.extend(self._recent_sessions_section(handoff))
        lines.extend(
            [
                "",
                "## 直近の決定事項",
                "",
                markdown_body_or_fallback(
                    handoff.manual_context.decisions_markdown,
                    "- 決定事項はまだ抽出できていません。",
                ),
                "",
                "## 未完了タスク",
                "",
                markdown_body_or_fallback(
                    handoff.manual_context.tasks_markdown,
                    "- [ ] 次に進める作業はまだ抽出できていません。",
                ),
                "",
                "## 現在の作業状態",
                "",
            ]
        )
        lines.extend(self._current_state_section(handoff))
        lines.extend(
            [
                "",
                "## 新スレッドで最初にやるべき 3 手",
                "",
            ]
        )
        lines.extend(self._initial_steps_section(handoff))
        lines.extend(
            [
                "",
                "## 明示すべき仮定",
                "",
            ]
        )
        lines.extend(self._assumptions_section(handoff))
        return "\n".join(lines).strip() + "\n"

    def _purpose_section(self, handoff: HandoffDocument) -> list[str]:
        context = handoff.manual_context
        lines = [
            markdown_body_or_fallback(
                context.purpose,
                "- このプロジェクトの目的はまだ抽出できていません。",
            )
        ]
        if context.important_files.strip():
            lines.extend(["", "### 重要ファイル", "", context.important_files.strip()])
        elif handoff.repo_snapshot.detected_important_paths:
            lines.extend(["", "### 重要ファイル", ""])
            lines.extend(f"- `{path}`" for path in handoff.repo_snapshot.detected_important_paths)
        return lines

    def _semantic_memory_section(self, handoff: HandoffDocument) -> list[str]:
        grouped = grouped_semantic_entries(handoff.memory_snapshot)
        lines: list[str] = []
        seen_summaries: set[str] = set()

        sections = (
            ("ユーザーの思想", "preference"),
            ("期待仕様", "spec"),
            ("制約", "constraint"),
            ("うまくいったこと", "success"),
            ("避けたいこと", "failure"),
            ("採用した判断", "decision"),
        )
        for title, kind in sections:
            entries = [
                entry
                for entry in grouped[kind]
                if _semantic_render_key(entry.summary) not in seen_summaries
            ]
            if not entries:
                continue
            lines.extend([f"### {title}", ""])
            for entry in entries:
                lines.append(f"- {entry.summary}")
                seen_summaries.add(_semantic_render_key(entry.summary))
            lines.append("")

        if not lines:
            return ["- まだ抽出できたプロジェクト記憶はありません。"]

        if lines[-1] == "":
            lines.pop()
        return lines

    def _worklog_section(self, handoff: HandoffDocument) -> list[str]:
        grouped = grouped_worklog_entries(handoff.memory_snapshot)
        sections = (
            ("進捗", "progress"),
            ("検証", "verification"),
            ("直近コミット", "commit"),
            ("変更ファイル", "change"),
        )

        lines: list[str] = []
        for title, kind in sections:
            entries = grouped[kind]
            if not entries:
                continue
            lines.extend([f"### {title}", ""])
            lines.extend(f"- {entry.summary}" for entry in entries)
            lines.append("")

        if not lines:
            return ["- まだ抽出できた作業記録はありません。"]

        if lines[-1] == "":
            lines.pop()
        return lines

    def _current_focus_section(self, handoff: HandoffDocument) -> list[str]:
        if handoff.memory_snapshot.current_focus:
            return [f"- {handoff.memory_snapshot.current_focus}"]
        tasks = _extract_actionable_items(handoff.manual_context.tasks_markdown)
        if tasks:
            return [f"- {tasks[0]}"]
        recent_session = handoff.recent_sessions[0] if handoff.recent_sessions else None
        if recent_session:
            summary = _substantive_focus_for_record(recent_session)
            if summary:
                return [f"- {summary}"]
        return ["- 現在の主題はまだ抽出できていません。"]

    def _recent_sessions_section(self, handoff: HandoffDocument) -> list[str]:
        if not handoff.recent_sessions:
            return ["- このプロジェクトに紐づく Codex セッション履歴はまだ見つかっていません。"]

        lines: list[str] = []
        for record in handoff.recent_sessions:
            lines.extend(self._render_session_record(record, handoff.root_path))
            lines.append("")
        if lines[-1] == "":
            lines.pop()
        return lines

    def _render_session_record(self, record: SessionRecord, root_path: str) -> list[str]:
        label = record.session_id[:8]
        lines = [f"### セッション `{label}`"]

        meta_parts: list[str] = []
        if record.started_at:
            meta_parts.append(f"開始 `{record.started_at}`")
        if record.updated_at and record.updated_at != record.started_at:
            meta_parts.append(f"更新 `{record.updated_at}`")
        if record.cwd and record.cwd != root_path:
            meta_parts.append(f"cwd `{record.cwd}`")
        if meta_parts:
            lines.append(f"- {' / '.join(meta_parts)}")

        first_request = record.first_user_summary
        latest_request = record.latest_substantive_user_summary or record.latest_user_summary
        latest_reply = record.latest_assistant_summary
        if not latest_reply and record.latest_assistant_message and not _looks_like_meta_memory_evaluation(record.latest_assistant_message):
            latest_reply = record.latest_assistant_message

        if first_request:
            lines.append(f"- 最初の依頼: {first_request}")
        if latest_request and latest_request != first_request:
            lines.append(f"- 直近の依頼: {latest_request}")
        if latest_reply:
            lines.append(f"- 直近の回答: {latest_reply}")
        return lines

    def _current_state_section(self, handoff: HandoffDocument) -> list[str]:
        snapshot = handoff.repo_snapshot
        lines = [f"- プロジェクト名: `{handoff.project_name}`"]
        if handoff.recent_sessions:
            lines.append(f"- 直近に検出した Codex セッション: {len(handoff.recent_sessions)} 件")

        if not snapshot.git_available:
            lines.append("- Git: 利用できません。非 Git ディレクトリとして handoff を生成しています。")
            if snapshot.detected_important_paths:
                lines.append("- 検出した重要パス:")
                lines.extend(f"  - `{path}`" for path in snapshot.detected_important_paths)
            return lines

        if not snapshot.is_repo:
            lines.append("- Git: 利用可能ですが、このディレクトリは Git リポジトリではありません。")
            if snapshot.detected_important_paths:
                lines.append("- 検出した重要パス:")
                lines.extend(f"  - `{path}`" for path in snapshot.detected_important_paths)
            return lines

        lines.append(f"- Git ルート: `{snapshot.git_root or handoff.root_path}`")
        lines.append(f"- ブランチ: `{snapshot.branch or '(detached)'}`")
        lines.append(f"- 作業ツリー: `{'dirty' if snapshot.is_dirty else 'clean'}`")

        if snapshot.changed_files:
            lines.extend(["", "### 変更ファイル", ""])
            lines.extend(f"- `{item.path}` ({item.status})" for item in snapshot.changed_files)
        else:
            lines.extend(["", "- 変更ファイルはありません。"])

        if snapshot.recent_commits:
            lines.extend(["", "### 直近コミット", ""])
            lines.extend(f"- `{item.short_hash}` {item.summary}" for item in snapshot.recent_commits)

        if snapshot.detected_important_paths:
            lines.extend(["", "### 検出した重要パス", ""])
            lines.extend(f"- `{path}`" for path in snapshot.detected_important_paths)
        return lines

    def _initial_steps_section(self, handoff: HandoffDocument) -> list[str]:
        snapshot = handoff.repo_snapshot
        tasks = _extract_actionable_items(handoff.manual_context.tasks_markdown)
        recent_session = handoff.recent_sessions[0] if handoff.recent_sessions else None
        steps: list[str] = []

        if handoff.memory_snapshot.current_focus and handoff.memory_snapshot.next_actions:
            for index, action in enumerate(handoff.memory_snapshot.next_actions[:3], start=1):
                steps.append(f"{index}. {action.summary}")
            return steps

        if tasks:
            steps.append(f"1. `tasks.md` の先頭タスクを確認する: {tasks[0]}")
        elif recent_session and _substantive_focus_for_record(recent_session):
            summary = _substantive_focus_for_record(recent_session)
            steps.append(f"1. 直近の依頼を起点に再開する: {summary}")
        else:
            steps.append("1. `tasks.md` を確認して次の作業を 1 つ決める。")

        focus_changed_files = select_user_facing_changed_files(snapshot.changed_files, limit=3)
        if snapshot.is_repo and focus_changed_files:
            focus_files = ", ".join(f"`{item.path}`" for item in focus_changed_files)
            suffix = " など" if len(focus_changed_files) < len(snapshot.changed_files) else ""
            steps.append(f"2. 変更ファイルを確認して現在地を把握する: {focus_files}{suffix}")
        elif snapshot.is_repo and snapshot.recent_commits:
            latest = snapshot.recent_commits[0]
            steps.append(f"2. 直近コミット `{latest.short_hash}` の意図を確認する。")
        elif handoff.manual_context.important_files.strip():
            focus_paths = ", ".join(
                f"`{item}`"
                for item in _extract_bulleted_items(handoff.manual_context.important_files)[:3]
            )
            steps.append(f"2. 重要ファイルを開いて文脈を取り戻す: {focus_paths}")
        elif snapshot.detected_important_paths:
            focus_paths = ", ".join(f"`{path}`" for path in snapshot.detected_important_paths[:3])
            steps.append(f"2. 重要パスを開いて文脈を取り戻す: {focus_paths}")
        else:
            steps.append("2. `project.md` と `decisions.md` を見て、前提と判断を確認する。")

        if recent_session and (recent_session.latest_assistant_summary or recent_session.latest_assistant_message):
            summary = _truncate_step_text(
                recent_session.latest_assistant_summary or recent_session.latest_assistant_message,
                120,
            )
            steps.append(f"3. 直近の回答内容を踏まえて次の判断を置く: {summary}")
        else:
            steps.append("3. 制約・運用ルール・AGENTS.md を確認してから作業を進める。")
        return steps

    def _assumptions_section(self, handoff: HandoffDocument) -> list[str]:
        context = handoff.manual_context
        lines: list[str] = []
        if context.constraints.strip():
            lines.extend(["### 制約", "", context.constraints.strip(), ""])
        else:
            lines.extend(["### 制約", "", "- 制約はまだ抽出できていません。", ""])

        if context.operating_rules.strip():
            lines.extend(["### 運用ルール", "", context.operating_rules.strip(), ""])
        else:
            lines.extend(["### 運用ルール", "", "- 運用ルールはまだ抽出できていません。", ""])

        if context.assumptions.strip():
            lines.extend(["### 仮定", "", context.assumptions.strip(), ""])
        else:
            lines.extend(["### 仮定", "", "- 仮定はまだ抽出できていません。", ""])

        if context.agents_markdown.strip():
            lines.extend(["### AGENTS.md", "", context.agents_markdown.strip(), ""])

        if lines[-1] == "":
            lines.pop()
        return lines


def _extract_actionable_items(markdown: str) -> list[str]:
    items: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ] "):
            items.append(stripped[6:].strip())
        elif stripped.startswith("* [ ] "):
            items.append(stripped[6:].strip())
    return items


def _substantive_focus_for_record(record: SessionRecord) -> str | None:
    return summarize_actionable_request(
        record.latest_substantive_user_summary
        or record.first_user_summary
        or record.first_user_message
    )


def _semantic_render_key(text: str) -> str:
    cleaned = text.replace("`", "").strip().rstrip("。 ")
    return " ".join(cleaned.split()).lower()


def _extract_bulleted_items(markdown: str) -> list[str]:
    items: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip().strip("`"))
        elif stripped.startswith("* "):
            items.append(stripped[2:].strip().strip("`"))
    return items


def _truncate_step_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
