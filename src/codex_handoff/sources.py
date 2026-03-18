from __future__ import annotations

import shutil
import subprocess
from pathlib import PurePosixPath

from codex_handoff.config import default_config
from codex_handoff.files import parse_markdown_sections, read_optional_text, strip_first_heading, to_posix_path
from codex_handoff.models import CommitSummary, FileChange, ManualContext, ProjectConfig, ReadmeContext, RepoSnapshot
from codex_handoff.paths import ProjectPaths
from codex_handoff.processes import hidden_subprocess_kwargs


SECTION_NAMES = {
    "purpose": "\u76ee\u7684",
    "constraints": "\u5236\u7d04",
    "important_files": "\u91cd\u8981\u30d5\u30a1\u30a4\u30eb",
    "operating_rules": "\u904b\u7528\u30eb\u30fc\u30eb",
    "assumptions": "\u4eee\u5b9a",
}
SECTION_ORDER = ("purpose", "constraints", "important_files", "operating_rules", "assumptions")


class ManualFilesSource:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    def collect(self) -> ManualContext:
        sections = parse_markdown_sections(read_optional_text(self.paths.project_file))
        ordered_values = [value for value in sections.values() if value]
        return ManualContext(
            purpose=_get_section(sections, ordered_values, "purpose"),
            constraints=_get_section(sections, ordered_values, "constraints"),
            important_files=_get_section(sections, ordered_values, "important_files"),
            operating_rules=_get_section(sections, ordered_values, "operating_rules"),
            assumptions=_get_section(sections, ordered_values, "assumptions"),
            decisions_markdown=strip_first_heading(read_optional_text(self.paths.decisions_file)),
            tasks_markdown=strip_first_heading(read_optional_text(self.paths.tasks_file)),
        )


class AgentsSource:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    def collect(self) -> ManualContext:
        return ManualContext(agents_markdown=read_optional_text(self.paths.repo_agents_file).strip())


class ReadmeSource:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    def collect(self) -> ReadmeContext:
        readme_path = self.paths.root / "README.md"
        if not readme_path.exists():
            return ReadmeContext()

        markdown = read_optional_text(readme_path)
        body = strip_first_heading(markdown)
        return ReadmeContext(
            intro=_extract_readme_intro(body),
            sections=parse_markdown_sections(markdown),
            path=readme_path.as_posix(),
        )


class GitSource:
    def __init__(self, paths: ProjectPaths, config: ProjectConfig | None = None) -> None:
        self.paths = paths
        self.config = config or default_config(paths.root)

    def collect(self) -> RepoSnapshot:
        git_binary = shutil.which("git")
        detected_important_paths = self._detect_important_paths()
        if git_binary is None:
            return RepoSnapshot(
                git_available=False,
                is_repo=False,
                detected_important_paths=detected_important_paths,
            )

        probe = self._run_git("rev-parse", "--is-inside-work-tree", check=False)
        if probe.returncode != 0 or probe.stdout.strip().lower() != "true":
            return RepoSnapshot(
                git_available=True,
                is_repo=False,
                detected_important_paths=detected_important_paths,
            )

        branch = self._run_git("branch", "--show-current", check=False).stdout.strip() or None
        git_root = self._run_git("rev-parse", "--show-toplevel", check=False).stdout.strip() or None
        changed_files = self._collect_changed_files()
        recent_commits = self._collect_recent_commits()
        return RepoSnapshot(
            git_available=True,
            is_repo=True,
            branch=branch,
            is_dirty=bool(changed_files),
            changed_files=changed_files,
            recent_commits=recent_commits,
            detected_important_paths=detected_important_paths,
            git_root=to_posix_path(git_root) if git_root else None,
        )

    def _collect_changed_files(self) -> list[FileChange]:
        result = self._run_git("status", "--short", "--untracked-files=all", check=False)
        if result.returncode != 0:
            return []

        changed: list[FileChange] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            status = line[:2].strip() or "?"
            raw_path = line[3:].strip()
            if " -> " in raw_path:
                raw_path = raw_path.split(" -> ", 1)[1].strip()
            normalized = to_posix_path(raw_path)
            if self._is_excluded(normalized):
                continue
            changed.append(FileChange(status=status, path=normalized))
            if len(changed) >= self.config.output.max_changed_files:
                break
        return changed

    def _collect_recent_commits(self) -> list[CommitSummary]:
        result = self._run_git(
            "log",
            f"-n{self.config.output.max_recent_commits}",
            "--pretty=format:%h%x09%s",
            check=False,
        )
        if result.returncode != 0:
            return []

        commits: list[CommitSummary] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            short_hash, _, summary = line.partition("\t")
            commits.append(CommitSummary(short_hash=short_hash.strip(), summary=summary.strip()))
        return commits

    def _detect_important_paths(self) -> list[str]:
        detected: list[str] = []
        for candidate in self.config.important_paths:
            path = self.paths.root / candidate
            if path.exists():
                detected.append(to_posix_path(candidate))
        return detected

    def _is_excluded(self, relative_path: str) -> bool:
        posix_path = PurePosixPath(relative_path)
        for pattern in self.config.exclude_globs:
            if posix_path.match(pattern) or relative_path == pattern.rstrip("/"):
                return True
        return False

    def _run_git(self, *args: str, check: bool) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.paths.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=check,
            **hidden_subprocess_kwargs(),
        )


def _extract_readme_intro(body: str) -> str:
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _get_section(sections: dict[str, str], ordered_values: list[str], key: str) -> str:
    value = sections.get(SECTION_NAMES[key])
    if value:
        return value

    index = SECTION_ORDER.index(key)
    if index < len(ordered_values):
        return ordered_values[index]
    return ""
