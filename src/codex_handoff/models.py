from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, Protocol


@dataclass(slots=True)
class OutputSettings:
    max_recent_commits: int = 3
    max_changed_files: int = 12
    max_recent_sessions: int = 3


@dataclass(slots=True)
class ProjectConfig:
    project_name: str
    important_paths: list[str] = field(default_factory=list)
    exclude_globs: list[str] = field(default_factory=list)
    output: OutputSettings = field(default_factory=OutputSettings)


@dataclass(slots=True)
class FileChange:
    status: str
    path: str


@dataclass(slots=True)
class CommitSummary:
    short_hash: str
    summary: str


@dataclass(slots=True)
class RepoSnapshot:
    git_available: bool
    is_repo: bool
    branch: str | None = None
    is_dirty: bool = False
    changed_files: list[FileChange] = field(default_factory=list)
    recent_commits: list[CommitSummary] = field(default_factory=list)
    detected_important_paths: list[str] = field(default_factory=list)
    git_root: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    started_at: str | None = None
    updated_at: str | None = None
    cwd: str | None = None
    source_path: str | None = None
    first_user_message: str | None = None
    first_user_summary: str | None = None
    latest_user_message: str | None = None
    latest_user_summary: str | None = None
    latest_substantive_user_message: str | None = None
    latest_substantive_user_summary: str | None = None
    latest_assistant_message: str | None = None
    latest_assistant_summary: str | None = None
    assistant_has_final_answer: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "cwd": self.cwd,
            "source_path": self.source_path,
            "first_user_message": self.first_user_message,
            "first_user_summary": self.first_user_summary,
            "latest_user_message": self.latest_user_message,
            "latest_user_summary": self.latest_user_summary,
            "latest_substantive_user_message": self.latest_substantive_user_message,
            "latest_substantive_user_summary": self.latest_substantive_user_summary,
            "latest_assistant_message": self.latest_assistant_message,
            "latest_assistant_summary": self.latest_assistant_summary,
        }


SemanticMemoryKind = Literal["preference", "spec", "constraint", "assessment", "success", "failure", "decision"]
MemoryKind = SemanticMemoryKind
WorklogKind = Literal["progress", "verification", "commit", "change"]


@dataclass(slots=True)
class MemoryEntry:
    kind: MemoryKind
    summary: str
    topic: str | None = None
    source_session_id: str | None = None
    source_role: Literal["user", "assistant"] | None = None
    updated_at: str | None = None
    evidence_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class WorklogEntry:
    kind: WorklogKind
    summary: str
    source: Literal["assistant_final", "git"] | None = None
    source_session_id: str | None = None
    updated_at: str | None = None
    evidence_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class FocusPathEntry:
    path: str
    reason: Literal["changed", "mentioned", "important"]
    note: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class NextActionEntry:
    summary: str
    path: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class MemorySnapshot:
    semantic_entries: list[MemoryEntry] = field(default_factory=list)
    worklog_entries: list[WorklogEntry] = field(default_factory=list)
    current_focus: str | None = None
    focus_paths: list[FocusPathEntry] = field(default_factory=list)
    next_actions: list[NextActionEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "semantic_entries": [item.to_dict() for item in self.semantic_entries],
            "worklog_entries": [item.to_dict() for item in self.worklog_entries],
            "current_focus": self.current_focus,
            "focus_paths": [item.to_dict() for item in self.focus_paths],
            "next_actions": [item.to_dict() for item in self.next_actions],
        }


@dataclass(slots=True)
class ManualContext:
    purpose: str = ""
    constraints: str = ""
    important_files: str = ""
    operating_rules: str = ""
    assumptions: str = ""
    decisions_markdown: str = ""
    tasks_markdown: str = ""
    agents_markdown: str = ""

    def merge(self, other: "ManualContext") -> "ManualContext":
        return ManualContext(
            purpose=_join_blocks(self.purpose, other.purpose),
            constraints=_join_blocks(self.constraints, other.constraints),
            important_files=_join_blocks(self.important_files, other.important_files),
            operating_rules=_join_blocks(self.operating_rules, other.operating_rules),
            assumptions=_join_blocks(self.assumptions, other.assumptions),
            decisions_markdown=_join_blocks(self.decisions_markdown, other.decisions_markdown),
            tasks_markdown=_join_blocks(self.tasks_markdown, other.tasks_markdown),
            agents_markdown=_join_blocks(self.agents_markdown, other.agents_markdown),
        )


@dataclass(slots=True)
class ReadmeContext:
    intro: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    path: str | None = None


@dataclass(slots=True)
class HandoffDocument:
    project_name: str
    root_path: str
    handoff_dir: str
    generated_at: str
    manual_context: ManualContext
    repo_snapshot: RepoSnapshot
    memory_snapshot: MemorySnapshot = field(default_factory=MemorySnapshot)
    user_memory_entries: list[MemoryEntry] = field(default_factory=list)
    recent_sessions: list[SessionRecord] = field(default_factory=list)


@dataclass(slots=True)
class DoctorFinding:
    severity: Literal["ok", "warning", "error"]
    code: str
    message: str

    def render(self) -> str:
        labels = {
            "ok": "OK",
            "warning": "WARN",
            "error": "ERROR",
        }
        return f"[{labels[self.severity]}] {self.code}: {self.message}"


class ContextSource(Protocol):
    def collect(self) -> ManualContext | RepoSnapshot:
        ...


def _join_blocks(left: str, right: str) -> str:
    left = left.strip()
    right = right.strip()
    if not left:
        return right
    if not right or right == left:
        return left
    return f"{left}\n\n{right}"
