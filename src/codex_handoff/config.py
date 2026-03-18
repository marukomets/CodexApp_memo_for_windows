from __future__ import annotations

import tomllib
from pathlib import Path

from codex_handoff.errors import CodexHandoffError
from codex_handoff.models import OutputSettings, ProjectConfig


def default_config(project_root: Path) -> ProjectConfig:
    project_name = project_root.name or "Unnamed Project"
    return ProjectConfig(
        project_name=project_name,
        important_paths=["README.md", "src", "tests"],
        exclude_globs=[".git/**", ".codex-handoff/**", ".venv/**", "__pycache__/**", "AGENTS.md"],
        output=OutputSettings(max_recent_commits=3, max_changed_files=12, max_recent_sessions=3),
    )


def load_config(path: Path) -> ProjectConfig:
    if not path.exists():
        raise CodexHandoffError(f"設定ファイルがありません: {path}")
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        raise CodexHandoffError(f"config.toml の解析に失敗しました: {exc}") from exc

    project_name = _expect_string(payload, "project_name")
    important_paths = _expect_string_list(payload.get("important_paths", []), "important_paths")
    exclude_globs = _expect_string_list(payload.get("exclude_globs", []), "exclude_globs")
    output_raw = payload.get("output", {})
    if not isinstance(output_raw, dict):
        raise CodexHandoffError("config.toml の [output] はテーブルである必要があります。")

    max_recent_commits = _expect_positive_int(output_raw.get("max_recent_commits", 3), "output.max_recent_commits")
    max_changed_files = _expect_positive_int(output_raw.get("max_changed_files", 12), "output.max_changed_files")
    max_recent_sessions = _expect_positive_int(output_raw.get("max_recent_sessions", 3), "output.max_recent_sessions")
    return ProjectConfig(
        project_name=project_name,
        important_paths=important_paths,
        exclude_globs=exclude_globs,
        output=OutputSettings(
            max_recent_commits=max_recent_commits,
            max_changed_files=max_changed_files,
            max_recent_sessions=max_recent_sessions,
        ),
    )


def render_config(config: ProjectConfig) -> str:
    important_paths = _render_string_list(config.important_paths)
    exclude_globs = _render_string_list(config.exclude_globs)
    return (
        f'project_name = "{config.project_name}"\n'
        f"important_paths = [{important_paths}]\n"
        f"exclude_globs = [{exclude_globs}]\n"
        "\n"
        "[output]\n"
        f"max_recent_commits = {config.output.max_recent_commits}\n"
        f"max_changed_files = {config.output.max_changed_files}\n"
        f"max_recent_sessions = {config.output.max_recent_sessions}\n"
    )


def validate_config(config: ProjectConfig) -> list[str]:
    issues: list[str] = []
    if not config.project_name.strip():
        issues.append("project_name が空です。")
    if config.output.max_recent_commits <= 0:
        issues.append("output.max_recent_commits は 1 以上である必要があります。")
    if config.output.max_changed_files <= 0:
        issues.append("output.max_changed_files は 1 以上である必要があります。")
    return issues


def _expect_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CodexHandoffError(f"config.toml の `{key}` は空でない文字列である必要があります。")
    return value


def _expect_string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CodexHandoffError(f"config.toml の `{field_name}` は文字列配列である必要があります。")
    return list(value)


def _expect_positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise CodexHandoffError(f"config.toml の `{field_name}` は 1 以上の整数である必要があります。")
    return value


def _render_string_list(items: list[str]) -> str:
    return ", ".join(f'"{item}"' for item in items)
