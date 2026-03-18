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
    latest_user_message: str | None = None
    latest_assistant_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


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
