from __future__ import annotations

from codex_handoff.files import markdown_body_or_fallback
from codex_handoff.focus import select_user_facing_changed_files
from codex_handoff.localization import detect_language, normalize_language, t
from codex_handoff.memory import _looks_like_meta_memory_evaluation, grouped_semantic_entries, grouped_worklog_entries
from codex_handoff.models import HandoffDocument, SessionRecord
from codex_handoff.summaries import summarize_actionable_request


class CodexMarkdownRenderer:
    def __init__(self, language: str | None = None) -> None:
        self.language = normalize_language(language) if language is not None else detect_language()

    def render(self, handoff: HandoffDocument) -> str:
        return self.render_next_thread(handoff)

    def _text(self, key: str, **kwargs: object) -> str:
        return t(key, language=self.language, **kwargs)

    def render_project(self, handoff: HandoffDocument) -> str:
        context = handoff.manual_context
        lines = [
            f"# {self._text('renderer.project_context.title')}",
            "",
            self._text("renderer.auto_updated"),
            self._text("renderer.generated_at", value=handoff.generated_at),
            self._text("renderer.root", value=handoff.root_path),
            "",
            f"## {self._text('renderer.project_purpose.title').removeprefix('## ').strip()}",
            "",
            markdown_body_or_fallback(
                context.purpose,
                self._text("renderer.no_purpose"),
            ),
            "",
            f"## {self._text('renderer.semantic.constraints')}",
            "",
            markdown_body_or_fallback(
                context.constraints,
                self._text("renderer.no_constraints"),
            ),
            "",
            f"## {self._text('renderer.important_files.title').removeprefix('## ').strip()}",
            "",
            markdown_body_or_fallback(
                context.important_files,
                self._text("renderer.important_files.no_items"),
            ),
            "",
            f"## {self._text('renderer.assumptions.rules.title').removeprefix('### ').strip()}",
            "",
            markdown_body_or_fallback(
                context.operating_rules,
                self._text("renderer.no_rules"),
            ),
            "",
            f"## {self._text('renderer.assumptions.assumptions.title').removeprefix('### ').strip()}",
            "",
            markdown_body_or_fallback(
                context.assumptions,
                self._text("renderer.no_assumptions"),
            ),
        ]
        return "\n".join(lines).strip() + "\n"

    def render_decisions(self, handoff: HandoffDocument) -> str:
        lines = [
            f"# {self._text('renderer.decisions.title')}",
            "",
            self._text("renderer.auto_updated"),
            self._text("renderer.generated_at", value=handoff.generated_at),
            "",
            markdown_body_or_fallback(
                handoff.manual_context.decisions_markdown,
                self._text("renderer.no_decisions"),
            ),
        ]
        return "\n".join(lines).strip() + "\n"

    def render_tasks(self, handoff: HandoffDocument) -> str:
        lines = [
            f"# {self._text('renderer.tasks.title')}",
            "",
            self._text("renderer.auto_updated"),
            self._text("renderer.generated_at", value=handoff.generated_at),
            "",
            markdown_body_or_fallback(
                handoff.manual_context.tasks_markdown,
                self._text("renderer.no_tasks"),
            ),
        ]
        return "\n".join(lines).strip() + "\n"

    def render_next_thread(self, handoff: HandoffDocument) -> str:
        lines: list[str] = [
            f"# {self._text('renderer.next_thread.title', project=handoff.project_name)}",
            "",
            self._text("renderer.generated_at", value=handoff.generated_at),
            self._text("renderer.root", value=handoff.root_path),
            self._text("renderer.memory_location", value=handoff.handoff_dir),
            "",
            self._text("renderer.project_purpose.title"),
            "",
        ]
        lines.extend(self._purpose_section(handoff))
        lines.extend(
            [
                "",
                self._text("renderer.project_memory.title"),
                "",
            ]
        )
        lines.extend(self._semantic_memory_section(handoff))
        lines.extend(
            [
                "",
                self._text("renderer.recent_worklog.title"),
                "",
            ]
        )
        lines.extend(self._worklog_section(handoff))
        lines.extend(
            [
                "",
                self._text("renderer.current_focus.title"),
                "",
            ]
        )
        lines.extend(self._current_focus_section(handoff))
        lines.extend(
            [
                "",
                self._text("renderer.recent_sessions.title"),
                "",
            ]
        )
        lines.extend(self._recent_sessions_section(handoff))
        lines.extend(
            [
                "",
                self._text("renderer.recent_decisions.title"),
                "",
                markdown_body_or_fallback(
                    handoff.manual_context.decisions_markdown,
                    self._text("renderer.no_decisions"),
                ),
                "",
                self._text("renderer.open_tasks.title"),
                "",
                markdown_body_or_fallback(
                    handoff.manual_context.tasks_markdown,
                    self._text("renderer.no_tasks"),
                ),
                "",
                self._text("renderer.current_state.title"),
                "",
            ]
        )
        lines.extend(self._current_state_section(handoff))
        lines.extend(
            [
                "",
                self._text("renderer.next_steps.title"),
                "",
            ]
        )
        lines.extend(self._initial_steps_section(handoff))
        lines.extend(
            [
                "",
                self._text("renderer.assumptions.title"),
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
                self._text("renderer.no_purpose"),
            )
        ]
        if context.important_files.strip():
            lines.extend(["", self._text("renderer.important_files.title").replace("##", "###", 1), "", context.important_files.strip()])
        elif handoff.repo_snapshot.detected_important_paths:
            lines.extend(["", self._text("renderer.important_files.title").replace("##", "###", 1), ""])
            lines.extend(f"- `{path}`" for path in handoff.repo_snapshot.detected_important_paths)
        return lines

    def _semantic_memory_section(self, handoff: HandoffDocument) -> list[str]:
        grouped = grouped_semantic_entries(handoff.memory_snapshot)
        lines: list[str] = []
        seen_summaries: set[str] = set()

        sections = (
            (self._text("renderer.semantic.user_preferences"), "preference"),
            (self._text("renderer.semantic.specs"), "spec"),
            (self._text("renderer.semantic.constraints"), "constraint"),
            (self._text("renderer.semantic.successes"), "success"),
            (self._text("renderer.semantic.failures"), "failure"),
            (self._text("renderer.semantic.decisions"), "decision"),
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
            return [self._text("renderer.no_project_memory")]

        if lines[-1] == "":
            lines.pop()
        return lines

    def _worklog_section(self, handoff: HandoffDocument) -> list[str]:
        grouped = grouped_worklog_entries(handoff.memory_snapshot)
        sections = (
            (self._text("renderer.worklog.progress"), "progress"),
            (self._text("renderer.worklog.verification"), "verification"),
            (self._text("renderer.worklog.commit"), "commit"),
            (self._text("renderer.worklog.change"), "change"),
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
            return [self._text("renderer.no_worklog")]

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
        return [self._text("renderer.no_current_focus")]

    def _recent_sessions_section(self, handoff: HandoffDocument) -> list[str]:
        if not handoff.recent_sessions:
            return [self._text("renderer.no_sessions")]

        lines: list[str] = []
        for record in handoff.recent_sessions:
            lines.extend(self._render_session_record(record, handoff.root_path))
            lines.append("")
        if lines[-1] == "":
            lines.pop()
        return lines

    def _render_session_record(self, record: SessionRecord, root_path: str) -> list[str]:
        label = record.session_id[:8]
        lines = [self._text("renderer.session.title", label=label)]

        meta_parts: list[str] = []
        if record.started_at:
            meta_parts.append(f"{self._text('renderer.session.started')} `{record.started_at}`")
        if record.updated_at and record.updated_at != record.started_at:
            meta_parts.append(f"{self._text('renderer.session.updated')} `{record.updated_at}`")
        if record.cwd and record.cwd != root_path:
            meta_parts.append(f"{self._text('renderer.session.cwd')} `{record.cwd}`")
        if meta_parts:
            lines.append(f"- {' / '.join(meta_parts)}")

        first_request = record.first_user_summary
        latest_request = record.latest_substantive_user_summary or record.latest_user_summary
        latest_reply = record.latest_assistant_summary
        if not latest_reply and record.latest_assistant_message and not _looks_like_meta_memory_evaluation(record.latest_assistant_message):
            latest_reply = record.latest_assistant_message

        if first_request:
            lines.append(self._text("renderer.session.first_request", value=first_request))
        if latest_request and latest_request != first_request:
            lines.append(self._text("renderer.session.latest_request", value=latest_request))
        if latest_reply:
            lines.append(self._text("renderer.session.latest_reply", value=latest_reply))
        return lines

    def _current_state_section(self, handoff: HandoffDocument) -> list[str]:
        snapshot = handoff.repo_snapshot
        volatile_status = handoff.volatile_status
        lines = [self._text("renderer.state.project_name", value=handoff.project_name)]
        if volatile_status and volatile_status.refreshed_at:
            lines.append(self._text("renderer.state.status_updated", value=volatile_status.refreshed_at))
        if handoff.recent_sessions:
            lines.append(self._text("renderer.state.detected_sessions", count=len(handoff.recent_sessions)))

        if not snapshot.git_available:
            lines.append(self._text("renderer.state.git_unavailable"))
            if snapshot.detected_important_paths:
                lines.append(self._text("renderer.state.detected_paths.title"))
                lines.extend(f"  - `{path}`" for path in snapshot.detected_important_paths)
            return lines

        if not snapshot.is_repo:
            lines.append(self._text("renderer.state.git_not_repo"))
            if snapshot.detected_important_paths:
                lines.append(self._text("renderer.state.detected_paths.title"))
                lines.extend(f"  - `{path}`" for path in snapshot.detected_important_paths)
            return lines

        lines.append(self._text("renderer.state.git_root", value=snapshot.git_root or handoff.root_path))
        lines.append(self._text("renderer.state.branch", value=snapshot.branch or "(detached)"))
        lines.append(self._text("renderer.state.worktree", value="dirty" if snapshot.is_dirty else "clean"))
        if volatile_status and volatile_status.tracking_branch:
            lines.append(self._text("renderer.state.tracking_branch", value=volatile_status.tracking_branch))
            if volatile_status.ahead_count or volatile_status.behind_count:
                lines.append(self._text(
                    "renderer.state.sync_status",
                    value=f"ahead {volatile_status.ahead_count} / behind {volatile_status.behind_count}",
                ))
            else:
                lines.append(self._text("renderer.state.sync_status", value="up-to-date"))
        if volatile_status and volatile_status.latest_upstream_commit:
            lines.append(self._text("renderer.state.latest_push", value=volatile_status.latest_upstream_commit))
        if volatile_status and volatile_status.latest_tag:
            lines.append(self._text("renderer.state.latest_local_tag", value=volatile_status.latest_tag))
        if volatile_status and volatile_status.remote_repository:
            lines.append(self._text("renderer.state.remote", value=volatile_status.remote_repository))
        if volatile_status and volatile_status.latest_release:
            lines.append(
                self._text(
                    "renderer.state.latest_release",
                    value=_render_markdown_link(volatile_status.latest_release.tag, volatile_status.latest_release.url),
                )
            )
        if volatile_status and volatile_status.latest_workflow:
            workflow_state = f"`{volatile_status.latest_workflow.status}`"
            if volatile_status.latest_workflow.conclusion:
                workflow_state = f"{workflow_state} / `{volatile_status.latest_workflow.conclusion}`"
            lines.append(
                self._text(
                    "renderer.state.latest_workflow",
                    value=_render_markdown_link(volatile_status.latest_workflow.name, volatile_status.latest_workflow.url),
                    status=workflow_state,
                )
            )

        if snapshot.changed_files:
            lines.extend(["", self._text("renderer.state.changed_files.title"), ""])
            lines.extend(f"- `{item.path}` ({item.status})" for item in snapshot.changed_files)
        else:
            lines.extend(["", self._text("renderer.state.no_changes")])

        if snapshot.recent_commits:
            lines.extend(["", self._text("renderer.state.recent_commits.title"), ""])
            lines.extend(f"- `{item.short_hash}` {item.summary}" for item in snapshot.recent_commits)

        if snapshot.detected_important_paths:
            lines.extend(["", self._text("renderer.state.detected_paths.title"), ""])
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
            steps.append(self._text("renderer.initial.first_tasks", value=tasks[0]))
        elif recent_session and _substantive_focus_for_record(recent_session):
            summary = _substantive_focus_for_record(recent_session)
            steps.append(self._text("renderer.initial.resume", value=summary))
        else:
            steps.append(self._text("renderer.initial.pick_task"))

        focus_changed_files = select_user_facing_changed_files(snapshot.changed_files, limit=3)
        if snapshot.is_repo and focus_changed_files:
            focus_files = ", ".join(f"`{item.path}`" for item in focus_changed_files)
            suffix = " など" if len(focus_changed_files) < len(snapshot.changed_files) else ""
            steps.append(self._text("renderer.initial.inspect_changes", value=focus_files, suffix=suffix))
        elif snapshot.is_repo and snapshot.recent_commits:
            latest = snapshot.recent_commits[0]
            steps.append(self._text("renderer.initial.inspect_commit", value=latest.short_hash))
        elif handoff.manual_context.important_files.strip():
            focus_paths = ", ".join(
                f"`{item}`"
                for item in _extract_bulleted_items(handoff.manual_context.important_files)[:3]
            )
            steps.append(self._text("renderer.initial.open_important_files", value=focus_paths))
        elif snapshot.detected_important_paths:
            focus_paths = ", ".join(f"`{path}`" for path in snapshot.detected_important_paths[:3])
            steps.append(self._text("renderer.initial.open_important_paths", value=focus_paths))
        else:
            steps.append(self._text("renderer.initial.check_context"))

        if recent_session and (recent_session.latest_assistant_summary or recent_session.latest_assistant_message):
            summary = _truncate_step_text(
                recent_session.latest_assistant_summary or recent_session.latest_assistant_message,
                120,
            )
            steps.append(self._text("renderer.initial.think_next", value=summary))
        else:
            steps.append(self._text("renderer.initial.check_rules"))
        return steps

    def _assumptions_section(self, handoff: HandoffDocument) -> list[str]:
        context = handoff.manual_context
        lines: list[str] = []
        if context.constraints.strip():
            lines.extend([self._text("renderer.assumptions.constraints.title"), "", context.constraints.strip(), ""])
        else:
            lines.extend([self._text("renderer.assumptions.constraints.title"), "", self._text("renderer.no_constraints"), ""])

        if context.operating_rules.strip():
            lines.extend([self._text("renderer.assumptions.rules.title"), "", context.operating_rules.strip(), ""])
        else:
            lines.extend([self._text("renderer.assumptions.rules.title"), "", self._text("renderer.no_rules"), ""])

        if context.assumptions.strip():
            lines.extend([self._text("renderer.assumptions.assumptions.title"), "", context.assumptions.strip(), ""])
        else:
            lines.extend([self._text("renderer.assumptions.assumptions.title"), "", self._text("renderer.no_assumptions"), ""])

        if context.agents_markdown.strip():
            lines.extend([self._text("renderer.assumptions.agents.title"), "", context.agents_markdown.strip(), ""])

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


def _render_markdown_link(label: str, url: str | None) -> str:
    if url:
        return f"[{label}]({url})"
    return f"`{label}`"
