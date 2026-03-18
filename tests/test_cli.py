from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

import codex_handoff.service as service_module
from codex_handoff.cli import app
from codex_handoff.files import has_utf8_bom
from codex_handoff.paths import make_project_id

runner = CliRunner()
FIXED_NOW = "2026-03-18T10:00:00+09:00"


def test_setup_creates_global_store_without_touching_global_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0
    assert global_home.exists()
    assert (global_home / "projects").exists()
    assert (global_home / "global-agents-snippet.md").exists()
    assert not (codex_home / "AGENTS.md").exists()


def test_setup_can_install_global_agents_with_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, codex_home = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)

    global_agents = codex_home / "AGENTS.md"
    global_agents.parent.mkdir(parents=True, exist_ok=True)
    global_agents.write_text("existing rules\n", encoding="utf-8", newline="\n")

    result = runner.invoke(app, ["setup", "--install-global-agents"])
    assert result.exit_code == 0

    content = global_agents.read_text(encoding="utf-8")
    assert "<!-- codex-handoff:start -->" in content
    assert "codex-handoff prepare --stdout" in content

    backups = list(global_agents.parent.glob("AGENTS.md.bak-*"))
    assert backups
    assert backups[0].read_text(encoding="utf-8") == "existing rules\n"


def test_uninstall_global_agents_removes_only_managed_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, codex_home = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)

    assert runner.invoke(app, ["setup", "--install-global-agents"]).exit_code == 0
    global_agents = codex_home / "AGENTS.md"
    global_agents.write_text(
        "custom header\n\n"
        + global_agents.read_text(encoding="utf-8")
        + "\ncustom footer\n",
        encoding="utf-8",
        newline="\n",
    )

    result = runner.invoke(app, ["uninstall-global-agents"])
    assert result.exit_code == 0

    content = global_agents.read_text(encoding="utf-8")
    assert "custom header" in content
    assert "custom footer" in content
    assert "<!-- codex-handoff:start -->" not in content


def test_prepare_auto_creates_global_project_store_and_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_git()
    global_home, _ = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "sample-repo"
    repo.mkdir()
    _init_git_repo(repo)
    _write(repo / "README.md", "# Demo\n")
    _write(repo / "src" / "app.py", "print('v1')\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")
    _git(repo, "branch", "-M", "main")
    commit_hash = _git(repo, "rev-parse", "--short", "HEAD")
    _write(repo / "src" / "app.py", "print('v2')\n")
    _write(repo / "tests" / "sample_test.py", "def test_placeholder():\n    assert True\n")
    _write(repo / "AGENTS.md", "Reply in Japanese.\nAsk before destructive actions.\n")

    monkeypatch.chdir(repo)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["setup", "--install-global-agents"]).exit_code == 0
    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    project_id = make_project_id(repo)
    store = global_home / "projects" / project_id
    assert store.exists()
    local_store = repo / ".codex-handoff"
    assert local_store.exists()

    file_text = (store / "next-thread.md").read_text(encoding="utf-8")
    assert result.stdout == file_text
    assert (local_store / "next-thread.md").read_text(encoding="utf-8-sig") == file_text
    assert has_utf8_bom(local_store / "project.md")
    assert has_utf8_bom(local_store / "next-thread.md")

    assert f"# Next Thread Brief: {repo.name}" in file_text
    assert f"- ルート: `{repo.as_posix()}`" in file_text
    assert f"- メモ保存先: `{store.as_posix()}`" in file_text
    assert "## 現在の主題" in file_text
    assert "## 直近の決定事項" in file_text
    assert "## 未完了タスク" in file_text
    assert "`README.md`" in file_text
    assert "`src`" in file_text
    assert "`tests`" in file_text
    assert f"`{commit_hash}` Initial commit" in file_text

    project_text = (store / "project.md").read_text(encoding="utf-8")
    assert "# Project Context" in project_text
    assert "## 重要ファイル" in project_text
    assert "`README.md`" in project_text
    assert "Reply in Japanese." in project_text

    decisions_text = (store / "decisions.md").read_text(encoding="utf-8")
    assert "# Decisions" in decisions_text
    assert "自動更新" in decisions_text

    tasks_text = (store / "tasks.md").read_text(encoding="utf-8")
    assert "# Tasks" in tasks_text
    assert "重要ファイルを確認して文脈を戻す" in tasks_text or "変更ファイルを確認する" in tasks_text


def test_capture_updates_state_in_global_store_and_appends_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_git()
    global_home, _ = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "dirty-repo"
    repo.mkdir()
    _init_git_repo(repo)
    _write(repo / "README.md", "# Demo\n")
    _write(repo / "src" / "app.py", "print('v1')\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")
    _git(repo, "branch", "-M", "main")
    _write(repo / "src" / "app.py", "print('v2')\n")
    _write(repo / "notes" / "memo.txt", "todo\n")

    monkeypatch.chdir(repo)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["capture", "--note", "resume api error check"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(repo)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    assert state["project_id"] == make_project_id(repo)
    assert state["root_path"] == repo.as_posix()
    assert state["handoff_dir"] == store.as_posix()
    assert state["is_repo"] is True
    assert state["is_dirty"] is True

    changed_paths = [item["path"] for item in state["changed_files"]]
    assert "src/app.py" in changed_paths
    assert "notes/memo.txt" in changed_paths

    tasks_text = (store / "tasks.md").read_text(encoding="utf-8")
    assert "resume api error check (captured 2026-03-18T10:00:00+09:00)" in tasks_text


def test_prepare_works_in_non_git_directory_and_uses_path_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, _ = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "non-git"
    workdir.mkdir()

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    assert state["is_repo"] is False
    assert state["root_path"] == workdir.as_posix()
    assert (workdir / ".codex-handoff" / "next-thread.md").exists()


def test_prepare_includes_recent_codex_session_for_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_git()
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "session-repo"
    repo.mkdir()
    _init_git_repo(repo)
    _write(repo / "README.md", "# Demo\n")
    _write(repo / "src" / "app.py", "print('v1')\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")

    _write_session_log(
        codex_home,
        repo / "src",
        session_id="session-git-001",
        entries=[
            {"role": "user", "text": "Need a Windows-friendly installer flow."},
            {"role": "assistant", "text": "I will move setup into a guided flow.", "phase": "commentary"},
            {"role": "user", "text": "Record this thread automatically across new sessions."},
            {"role": "assistant", "text": "I will persist recent Codex session summaries into handoff.", "phase": "final_answer"},
        ],
    )

    monkeypatch.chdir(repo)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(repo)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    assert state["recent_sessions"]
    assert state["recent_sessions"][0]["session_id"] == "session-git-001"
    assert state["recent_sessions"][0]["cwd"] == (repo / "src").resolve().as_posix()
    assert "## 現在の主題" in result.stdout
    assert "最初の依頼: Need a Windows-friendly installer flow." in result.stdout
    assert "直近の依頼: Record this thread automatically across new sessions." in result.stdout
    assert "直近の回答: I will persist recent Codex session summaries into handoff." in result.stdout
    assert "- [ ] Record this thread automatically across new sessions." in (store / "tasks.md").read_text(encoding="utf-8")


def test_prepare_includes_recent_codex_session_for_non_git_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "session-non-git"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="session-non-git-001",
        entries=[
            {"role": "user", "text": "This folder is not a git repo."},
            {"role": "assistant", "text": "Non-git workspaces are supported.", "phase": "final_answer"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    assert state["is_repo"] is False
    assert state["recent_sessions"][0]["session_id"] == "session-non-git-001"
    assert "最初の依頼: This folder is not a git repo." in result.stdout
    assert "直近の回答: Non-git workspaces are supported." in result.stdout
    assert "This folder is not a git repo." in (store / "tasks.md").read_text(encoding="utf-8")


def test_prepare_extracts_only_explicit_decisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "decision-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="decision-session-001",
        entries=[
            {"role": "user", "text": "引き継げてる？"},
            {"role": "assistant", "text": "そうです。今は引き継げています。", "phase": "final_answer"},
        ],
    )
    _write_session_log(
        codex_home,
        workdir,
        session_id="decision-session-002",
        entries=[
            {"role": "user", "text": "保存先の扱いを決めたい。"},
            {
                "role": "assistant",
                "text": "global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    decisions = (store / "decisions.md").read_text(encoding="utf-8")
    assert "global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。" in decisions
    assert "そうです。今は引き継げています。" not in decisions


def test_prepare_skips_task_when_latest_response_marks_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "completed-task-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="completed-task-001",
        entries=[
            {"role": "user", "text": "project.md と tasks.md を自動更新に揃えてください。"},
            {
                "role": "assistant",
                "text": "project.md / decisions.md / tasks.md / next-thread.md を自動再生成するよう更新しました。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    tasks = (store / "tasks.md").read_text(encoding="utf-8")
    assert "project.md と tasks.md を自動更新に揃えてください。" not in tasks
    assert "重要ファイルを確認して文脈を戻す" in tasks


def test_prepare_preserves_existing_generated_notes_without_recent_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "preserve-generated-notes"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="preserve-session-001",
        entries=[
            {"role": "user", "text": "保存先を決めたい。"},
            {
                "role": "assistant",
                "text": "global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    first_decisions = (store / "decisions.md").read_text(encoding="utf-8")
    assert "global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。" in first_decisions

    sessions_dir = codex_home / "sessions"
    archived_dir = codex_home / "archived_sessions"
    if sessions_dir.exists():
        shutil.rmtree(sessions_dir)
    if archived_dir.exists():
        shutil.rmtree(archived_dir)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    second_decisions = (store / "decisions.md").read_text(encoding="utf-8")
    assert "global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。" in second_decisions


def test_prepare_uses_latest_commentary_when_final_answer_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "commentary-only-session"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="commentary-session-001",
        entries=[
            {"role": "user", "text": "Track the latest commentary."},
            {"role": "assistant", "text": "First commentary.", "phase": "commentary"},
            {"role": "assistant", "text": "Second commentary should win.", "phase": "commentary"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    assert state["recent_sessions"][0]["latest_assistant_message"] == "Second commentary should win."
    assert "直近の回答: Second commentary should win." in result.stdout


def test_prepare_finds_relevant_session_beyond_many_unrelated_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "deep-session-search"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    for index in range(50):
        other_dir = tmp_path / f"other-{index}"
        other_dir.mkdir(exist_ok=True)
        _write_session_log(
            codex_home,
            other_dir,
            session_id=f"other-session-{index:03d}",
            entries=[
                {"role": "user", "text": f"Ignore other workspace {index}."},
                {"role": "assistant", "text": "Unrelated.", "phase": "final_answer"},
            ],
        )

    _write_session_log(
        codex_home,
        workdir,
        session_id="target-session-001",
        entries=[
            {"role": "user", "text": "Keep this target session."},
            {"role": "assistant", "text": "This is the relevant session.", "phase": "final_answer"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    assert state["recent_sessions"][0]["session_id"] == "target-session-001"
    assert "Keep this target session." in result.stdout
    assert (global_home / "projects").exists()


def test_prepare_ignores_sessions_from_parent_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    parent = tmp_path / "workspace"
    workdir = parent / "project"
    workdir.mkdir(parents=True)
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        parent,
        session_id="parent-session-001",
        entries=[
            {"role": "user", "text": "This belongs to the parent workspace only."},
            {"role": "assistant", "text": "Do not import this into the child project.", "phase": "final_answer"},
        ],
    )
    _write_session_log(
        codex_home,
        workdir,
        session_id="project-session-001",
        entries=[
            {"role": "user", "text": "Keep this project session."},
            {"role": "assistant", "text": "This session should remain visible.", "phase": "final_answer"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    assert len(state["recent_sessions"]) == 1
    assert state["recent_sessions"][0]["session_id"] == "project-session-001"
    assert "This belongs to the parent workspace only." not in result.stdout


def test_prepare_ignores_subagent_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "subagent-filter"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="main-session-001",
        entries=[
            {"role": "user", "text": "Keep only the main session in handoff."},
            {"role": "assistant", "text": "I will filter out subagent sessions.", "phase": "final_answer"},
        ],
    )

    session_file = codex_home / "sessions" / "2026" / "03" / "18" / "rollout-subagent-session-001.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-03-18T01:00:00.000Z",
                        "type": "session_meta",
                        "payload": {
                            "id": "subagent-session-001",
                            "forked_from_id": "main-session-001",
                            "timestamp": "2026-03-18T01:00:00.000Z",
                            "cwd": str(workdir),
                            "originator": "Codex Desktop",
                            "source": {"subagent": {"thread_spawn": {"parent_thread_id": "main-session-001"}}},
                            "agent_role": "explorer",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-18T01:00:01.000Z",
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": "This is a subagent prompt."},
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    assert len(state["recent_sessions"]) == 1
    assert state["recent_sessions"][0]["session_id"] == "main-session-001"
    assert "This is a subagent prompt." not in result.stdout


def test_where_reports_global_project_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    global_home, _ = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "where-repo"
    repo.mkdir()
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["where"])
    assert result.exit_code == 0
    store = global_home / "projects" / make_project_id(repo)
    assert f"project store: {store}" in result.stdout
    assert f"local mirror: {repo / '.codex-handoff'}" in result.stdout
    assert f"project id: {make_project_id(repo)}" in result.stdout


def test_legacy_local_store_is_migrated_to_global_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, _ = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "legacy-repo"
    repo.mkdir()
    legacy = repo / ".codex-handoff"
    legacy.mkdir()
    _write(
        legacy / "config.toml",
        'project_name = "legacy-renamed"\nimportant_paths = ["README.md", "docs"]\nexclude_globs = []\n\n[output]\nmax_recent_commits = 3\nmax_changed_files = 12\nmax_recent_sessions = 3\n',
    )
    _write(repo / "README.md", "# Demo\n")
    _write(repo / "docs" / "guide.md", "hello\n")

    monkeypatch.chdir(repo)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(repo)
    config_text = (store / "config.toml").read_text(encoding="utf-8")
    assert 'project_name = "legacy-renamed"' in config_text
    project_text = (store / "project.md").read_text(encoding="utf-8")
    assert "`docs`" in project_text
    assert has_utf8_bom(legacy / "project.md")


def test_prepare_imports_newer_local_config_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, _ = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "mirror-repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(repo)
    local_config = repo / ".codex-handoff" / "config.toml"
    local_config.write_text(
        'project_name = "mirror-custom"\nimportant_paths = ["README.md", "custom"]\nexclude_globs = []\n\n[output]\nmax_recent_commits = 3\nmax_changed_files = 12\nmax_recent_sessions = 3\n',
        encoding="utf-8-sig",
        newline="\n",
    )

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    config_text = (store / "config.toml").read_text(encoding="utf-8")
    assert 'project_name = "mirror-custom"' in config_text
    assert 'important_paths = ["README.md", "custom"]' in config_text


def test_doctor_reports_missing_global_agents_when_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "doctor-repo"
    repo.mkdir()
    monkeypatch.chdir(repo)

    assert runner.invoke(app, ["setup"]).exit_code == 0
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "[WARN] global_agents_missing:" in result.stdout
    assert "[OK] project_store:" in result.stdout


def _set_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    global_home = tmp_path / "global-home"
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HANDOFF_HOME", str(global_home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    return global_home, codex_home


def _require_git() -> None:
    if shutil.which("git") is None:
        pytest.skip("git is required for this test")


def _init_git_repo(root: Path) -> None:
    init = subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if init.returncode != 0:
        _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _write_session_log(codex_home: Path, cwd: Path, session_id: str, entries: list[dict[str, str]]) -> None:
    session_file = codex_home / "sessions" / "2026" / "03" / "18" / f"rollout-{session_id}.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        json.dumps(
            {
                "timestamp": "2026-03-18T01:00:00.000Z",
                "type": "session_meta",
                "payload": {
                    "id": session_id,
                    "timestamp": "2026-03-18T01:00:00.000Z",
                    "cwd": str(cwd),
                    "originator": "Codex Desktop",
                },
            },
            ensure_ascii=False,
        )
    ]

    for index, entry in enumerate(entries, start=1):
        timestamp = f"2026-03-18T01:00:{index:02d}.000Z"
        if entry["role"] == "user":
            lines.append(
                json.dumps(
                    {
                        "timestamp": timestamp,
                        "type": "event_msg",
                        "payload": {
                            "type": "user_message",
                            "message": entry["text"],
                        },
                    },
                    ensure_ascii=False,
                )
            )
            continue

        lines.append(
            json.dumps(
                {
                    "timestamp": timestamp,
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "phase": entry.get("phase", "commentary"),
                        "content": [
                            {
                                "type": "output_text",
                                "text": entry["text"],
                            }
                        ],
                    },
                },
                ensure_ascii=False,
            )
        )

    session_file.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
