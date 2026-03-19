from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import PurePosixPath
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from codex_handoff.config import default_config
from codex_handoff.files import parse_markdown_sections, read_optional_text, strip_first_heading, to_posix_path
from codex_handoff.models import (
    CommitSummary,
    FileChange,
    LiveRelease,
    LiveWorkflow,
    ManualContext,
    ProjectConfig,
    ReadmeContext,
    RepoSnapshot,
    VolatileStatus,
)
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
        self._tracked_handoff_paths: set[str] | None = None

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
        ranked = sorted(enumerate(changed), key=lambda item: (_changed_file_sort_key(item[1].path), item[0]))
        return [change for _, change in ranked[: self.config.output.max_changed_files]]

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
        if relative_path.startswith(".codex-handoff/") and self._is_tracked_handoff_path(relative_path):
            return False
        posix_path = PurePosixPath(relative_path)
        for pattern in self.config.exclude_globs:
            if posix_path.match(pattern) or relative_path == pattern.rstrip("/"):
                return True
        return False

    def _is_tracked_handoff_path(self, relative_path: str) -> bool:
        if self._tracked_handoff_paths is None:
            result = self._run_git("ls-files", "--", ".codex-handoff", check=False)
            if result.returncode != 0:
                self._tracked_handoff_paths = set()
            else:
                self._tracked_handoff_paths = {
                    to_posix_path(line.strip())
                    for line in result.stdout.splitlines()
                    if line.strip()
                }
        return relative_path in self._tracked_handoff_paths

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


class LiveStatusSource:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths
        self._cached_remote_repository: str | None = None
        self._cached_release: LiveRelease | None = None
        self._cached_workflow: LiveWorkflow | None = None
        self._has_loaded_remote_metadata = False

    def collect(self, snapshot: RepoSnapshot, *, refreshed_at: str) -> VolatileStatus:
        status = VolatileStatus(refreshed_at=refreshed_at)
        if not snapshot.git_available or not snapshot.is_repo:
            return status

        if snapshot.recent_commits:
            status.latest_local_commit = snapshot.recent_commits[0]
        status.latest_tag = self._latest_tag()
        status.tracking_branch = self._tracking_branch()

        remote_name = self._default_remote_name()
        if status.tracking_branch:
            status.behind_count, status.ahead_count = self._ahead_behind_counts()
            status.latest_upstream_commit = self._short_rev("@{upstream}")
            remote_name = status.tracking_branch.split("/", 1)[0]

        if remote_name:
            status.remote_url = self._remote_url(remote_name)
            status.remote_repository = _parse_github_repository(status.remote_url)

        if status.remote_repository:
            status.latest_release, status.latest_workflow = self._load_remote_metadata(status.remote_repository)
        return status

    def _latest_tag(self) -> str | None:
        result = self._run_git("describe", "--tags", "--abbrev=0", check=False)
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def _tracking_branch(self) -> str | None:
        result = self._run_git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False)
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def _ahead_behind_counts(self) -> tuple[int, int]:
        result = self._run_git("rev-list", "--left-right", "--count", "@{upstream}...HEAD", check=False)
        if result.returncode != 0:
            return (0, 0)
        parts = result.stdout.strip().replace("\t", " ").split()
        if len(parts) < 2:
            return (0, 0)
        try:
            behind_count = int(parts[0])
            ahead_count = int(parts[1])
        except ValueError:
            return (0, 0)
        return (behind_count, ahead_count)

    def _short_rev(self, revision: str) -> str | None:
        result = self._run_git("rev-parse", "--short", revision, check=False)
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def _default_remote_name(self) -> str | None:
        result = self._run_git("remote", check=False)
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            value = line.strip()
            if value:
                return value
        return None

    def _remote_url(self, remote_name: str) -> str | None:
        result = self._run_git("remote", "get-url", remote_name, check=False)
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def _load_remote_metadata(self, repository: str) -> tuple[LiveRelease | None, LiveWorkflow | None]:
        if self._has_loaded_remote_metadata and self._cached_remote_repository == repository:
            return self._cached_release, self._cached_workflow

        self._cached_remote_repository = repository
        self._cached_release = None
        self._cached_workflow = None
        self._has_loaded_remote_metadata = True

        release_payload = _github_api_json(f"https://api.github.com/repos/{repository}/releases?per_page=1")
        if isinstance(release_payload, list) and release_payload:
            self._cached_release = _parse_release(release_payload[0])

        workflow_payload = _github_api_json(f"https://api.github.com/repos/{repository}/actions/runs?per_page=1")
        if isinstance(workflow_payload, dict):
            runs = workflow_payload.get("workflow_runs")
            if isinstance(runs, list) and runs:
                self._cached_workflow = _parse_workflow(runs[0])

        return self._cached_release, self._cached_workflow

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


def _changed_file_sort_key(path: str) -> tuple[int, str]:
    return (-_changed_file_priority(path), path)


def _changed_file_priority(path: str) -> int:
    score = 0
    if path.startswith("src/"):
        score += 120
    elif path.startswith("tests/"):
        score += 110
    elif path in {"README.md", "AGENTS.md", "pyproject.toml", "uv.lock"}:
        score += 100
    elif path.startswith(".codex-handoff/"):
        score += 90
    elif path.startswith("build-assets/"):
        score += 20

    if path.endswith((".py", ".md", ".toml", ".json", ".lock")):
        score += 10
    if path.endswith((".toc", ".pkg", ".pyz", ".zip", ".exe", ".html")):
        score -= 25
    return score


def _parse_github_repository(remote_url: str | None) -> str | None:
    if not remote_url:
        return None

    if remote_url.startswith("git@github.com:"):
        path = remote_url.split(":", 1)[1]
        return _normalize_github_repository_path(path)

    parsed = urlparse(remote_url)
    if parsed.netloc.lower() != "github.com":
        return None
    return _normalize_github_repository_path(parsed.path)


def _normalize_github_repository_path(path: str) -> str | None:
    normalized = path.strip().lstrip("/").rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    if normalized.count("/") != 1:
        return None
    owner, repo = normalized.split("/", 1)
    if not owner or not repo:
        return None
    return f"{owner}/{repo}"


def _github_api_json(url: str) -> object | None:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "codex-handoff",
        },
    )
    try:
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError):
        return None


def _parse_release(payload: object) -> LiveRelease | None:
    if not isinstance(payload, dict):
        return None
    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not tag.strip():
        return None
    url = payload.get("html_url")
    published_at = payload.get("published_at")
    return LiveRelease(
        tag=tag.strip(),
        url=url if isinstance(url, str) and url else None,
        published_at=published_at if isinstance(published_at, str) and published_at else None,
    )


def _parse_workflow(payload: object) -> LiveWorkflow | None:
    if not isinstance(payload, dict):
        return None
    name = payload.get("name")
    status = payload.get("status")
    if not isinstance(name, str) or not isinstance(status, str):
        return None
    conclusion = payload.get("conclusion")
    url = payload.get("html_url")
    updated_at = payload.get("updated_at")
    return LiveWorkflow(
        name=name,
        status=status,
        conclusion=conclusion if isinstance(conclusion, str) and conclusion else None,
        url=url if isinstance(url, str) and url else None,
        updated_at=updated_at if isinstance(updated_at, str) and updated_at else None,
    )
