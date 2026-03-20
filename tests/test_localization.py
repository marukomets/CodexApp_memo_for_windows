from __future__ import annotations

from pathlib import Path

from codex_handoff.codex_state import CodexWorkspaceState
from codex_handoff.gui import render_finish_summary
from codex_handoff.localization import detect_language, detect_system_language
from codex_handoff.memory import MemorySnapshot
from codex_handoff.models import HandoffDocument, ManualContext, RepoSnapshot
from codex_handoff.paths import GlobalPaths, ProjectPaths
from codex_handoff.sources import ReadmeSource
from codex_handoff.renderer import CodexMarkdownRenderer


def test_detect_language_prefers_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_HANDOFF_LANG", "en")

    assert detect_language() == "en"


def test_detect_language_defaults_to_english_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("CODEX_HANDOFF_LANG", raising=False)

    assert detect_language() == "en"


def test_detect_system_language_stays_japanese_when_locale_is_ja(monkeypatch) -> None:
    monkeypatch.delenv("CODEX_HANDOFF_LANG", raising=False)
    monkeypatch.setattr("codex_handoff.localization.locale.getlocale", lambda: ("ja_JP", "utf-8"))

    assert detect_system_language() == "ja"


def test_renderer_uses_english_headings() -> None:
    document = HandoffDocument(
        project_name="Demo",
        root_path="C:/demo",
        handoff_dir="C:/store",
        generated_at="2026-03-21T00:00:00+09:00",
        manual_context=ManualContext(),
        repo_snapshot=RepoSnapshot(git_available=False, is_repo=False),
        memory_snapshot=MemorySnapshot(),
    )

    markdown = CodexMarkdownRenderer(language="en").render_next_thread(document)

    assert "# Next Thread Brief: Demo" in markdown
    assert "## Project memory" in markdown
    assert "- No project memory has been extracted yet." in markdown
    assert "## Current state" in markdown
    assert "- Git: unavailable. Generating handoff for a non-Git directory." in markdown


def test_finish_summary_uses_english_fallback(tmp_path: Path) -> None:
    global_paths = GlobalPaths(
        app_home=tmp_path / "global",
        projects_dir=tmp_path / "projects",
        codex_home=tmp_path / "codex",
        global_agents_file=tmp_path / "codex" / "AGENTS.md",
        user_memory_file=tmp_path / "global" / "user-memory.json",
    )

    summary = render_finish_summary(
        global_paths=global_paths,
        workspace_state=CodexWorkspaceState(),
        agents_enabled=False,
        background_enabled=False,
        language="en",
    )

    assert "Global store" in summary
    assert "No active Codex workspace detected yet." in summary


def test_readme_source_prefers_readme_md_as_canonical_source(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# English\n\nEnglish intro\n", encoding="utf-8")
    (root / "README.en.md").write_text("# English alt\n\nAlternate intro\n", encoding="utf-8")

    paths = ProjectPaths(
        global_paths=GlobalPaths(
            app_home=tmp_path / "global",
            projects_dir=tmp_path / "projects",
            codex_home=tmp_path / "codex",
            global_agents_file=tmp_path / "codex" / "AGENTS.md",
            user_memory_file=tmp_path / "global" / "user-memory.json",
        ),
        root=root,
        project_id="demo",
        handoff_dir=tmp_path / "store",
        config_file=tmp_path / "store" / "config.toml",
        project_file=tmp_path / "store" / "project.md",
        decisions_file=tmp_path / "store" / "decisions.md",
        tasks_file=tmp_path / "store" / "tasks.md",
        memory_file=tmp_path / "store" / "memory.json",
        state_file=tmp_path / "store" / "state.json",
        next_thread_file=tmp_path / "store" / "next-thread.md",
        repo_agents_file=root / "AGENTS.md",
        local_handoff_dir=root / ".codex-handoff",
    )

    context = ReadmeSource(paths).collect()

    assert context.path is not None
    assert context.path.endswith("README.md")
