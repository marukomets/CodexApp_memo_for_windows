from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

import codex_handoff.service as service_module
from codex_handoff import __version__
from codex_handoff.cli import app
from codex_handoff.files import has_utf8_bom
from codex_handoff.models import LiveRelease, LiveWorkflow, VolatileStatus
from codex_handoff.paths import make_project_id

runner = CliRunner()
FIXED_NOW = "2026-03-18T10:00:00+09:00"


def test_version_option_outputs_package_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


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
    user_memory = global_home / "user-memory.json"
    assert user_memory.exists()
    assert json.loads(user_memory.read_text(encoding="utf-8")) == {
        "version": 1,
        "updated_at": None,
        "entries": [],
    }
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
    assert "user-memory.json" in content
    assert ".codex-handoff/memory.json" in content

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
    assert (store / "memory.json").exists()
    assert (local_store / "memory.json").exists()

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


def test_prepare_records_volatile_status_for_tracking_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_git()
    global_home, _ = _set_env(tmp_path, monkeypatch)
    remote = tmp_path / "remote.git"
    _init_bare_git_repo(remote)

    repo = tmp_path / "upstream-repo"
    repo.mkdir()
    _init_git_repo(repo)
    _write(repo / "README.md", "# Demo\n")
    _write(repo / "src" / "app.py", "print('v1')\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")

    _write(repo / "src" / "app.py", "print('v2')\n")
    _git(repo, "add", "src/app.py")
    _git(repo, "commit", "-m", "Second commit")

    monkeypatch.chdir(repo)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(repo)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    volatile_status = state["volatile_status"]
    assert volatile_status["refreshed_at"] == FIXED_NOW
    assert volatile_status["tracking_branch"] == "origin/main"
    assert volatile_status["ahead_count"] == 1
    assert volatile_status["behind_count"] == 0
    assert volatile_status["latest_upstream_commit"]

    next_thread = (store / "next-thread.md").read_text(encoding="utf-8")
    assert f"- 状態更新: `{FIXED_NOW}`" in next_thread
    assert "- 追跡ブランチ: `origin/main`" in next_thread
    assert "- 同期状況: `ahead 1 / behind 0`" in next_thread


def test_prepare_keeps_volatile_status_out_of_memory_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_git()
    global_home, _ = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "live-status-repo"
    repo.mkdir()
    _init_git_repo(repo)
    _write(repo / "README.md", "# Demo\n")
    _write(repo / "src" / "app.py", "print('v1')\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")

    monkeypatch.chdir(repo)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    def fake_collect(self, snapshot, *, refreshed_at: str) -> VolatileStatus:
        return VolatileStatus(
            refreshed_at=refreshed_at,
            tracking_branch="origin/main",
            ahead_count=1,
            behind_count=0,
            latest_upstream_commit="abc1234",
            remote_repository="marukomets/CodexApp_memo_for_windows",
            latest_tag="v0.6.9",
            latest_release=LiveRelease(
                tag="v0.6.9",
                url="https://example.test/releases/v0.6.9",
            ),
            latest_workflow=LiveWorkflow(
                name="release-windows",
                status="completed",
                conclusion="success",
                url="https://example.test/actions/1",
            ),
        )

    monkeypatch.setattr(service_module.LiveStatusSource, "collect", fake_collect)

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(repo)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    assert state["volatile_status"]["latest_release"]["tag"] == "v0.6.9"
    assert state["volatile_status"]["latest_workflow"]["name"] == "release-windows"

    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    assert "volatile_status" not in memory

    next_thread = (store / "next-thread.md").read_text(encoding="utf-8")
    assert "- 最新 Release: [v0.6.9](https://example.test/releases/v0.6.9)" in next_thread
    assert "- 最新 workflow: [release-windows](https://example.test/actions/1) (`completed` / `success`)" in next_thread


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
    assert "Record this thread automatically across new sessions" in (store / "tasks.md").read_text(encoding="utf-8")


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
    assert "This folder is not a git repo" in (store / "tasks.md").read_text(encoding="utf-8")


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


def test_prepare_keeps_final_answer_when_later_commentary_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "final-answer-over-commentary"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="final-answer-over-commentary-001",
        entries=[
            {"role": "user", "text": "Track the latest final answer."},
            {"role": "assistant", "text": "Final answer should win.", "phase": "final_answer"},
            {"role": "assistant", "text": "Later commentary should not replace it.", "phase": "commentary"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    assert state["recent_sessions"][0]["latest_assistant_message"] == "Final answer should win."
    assert "直近の回答: Final answer should win." in result.stdout
    assert "Later commentary should not replace it." not in result.stdout


def test_prepare_extracts_structured_memory_from_session_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "memory-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="memory-session-001",
        entries=[
            {"role": "user", "text": "結論だけだと弱いんだよね。"},
            {"role": "user", "text": "目指してるのは ChatGPT のメモリみたいな使用感で Codexapp を使いたい。"},
            {"role": "user", "text": "直前の操作だけじゃなくて、上手くいかなかった試行錯誤と成功した実装の両方を記録してほしい。"},
            {
                "role": "assistant",
                "text": "現状は handoff の自動生成が『今の会話』と『本来引き継ぐべきプロジェクト文脈』を分離できていません。",
                "phase": "commentary",
            },
            {
                "role": "assistant",
                "text": "今の handoff は会話の結論しか拾えず、失敗した試行錯誤を十分に残せていません。",
                "phase": "final_answer",
            },
            {
                "role": "assistant",
                "text": "レビュー依頼みたいな一時的なメタ会話を次スレッドの主題にしにくくしました。",
                "phase": "final_answer",
            },
            {
                "role": "assistant",
                "text": "global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。",
                "phase": "final_answer",
            },
            {
                "role": "assistant",
                "text": "構造化メモリを実装しました。",
                "phase": "final_answer",
            },
            {
                "role": "assistant",
                "text": "pytest -q を通しました。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    semantic_kinds = {item["kind"] for item in memory["semantic_entries"]}
    worklog_kinds = {item["kind"] for item in memory["worklog_entries"]}
    semantic_summaries = [item["summary"] for item in memory["semantic_entries"]]
    worklog_summaries = [item["summary"] for item in memory["worklog_entries"]]

    assert {"preference", "spec", "failure", "success", "decision"} <= semantic_kinds
    assert {"progress", "verification"} <= worklog_kinds
    assert any("ChatGPT のメモリみたいな使用感" in item for item in semantic_summaries)
    assert any("試行錯誤と成功した実装の両方を記録してほしい" in item for item in semantic_summaries)
    assert all("引き継ぐべきプロジェクト文脈" not in item for item in semantic_summaries)
    assert any("主題にしにくくしました" in item for item in semantic_summaries)
    assert any("構造化メモリを実装しました" in item for item in worklog_summaries)
    assert any("pytest -q を通しました" in item for item in worklog_summaries)
    assert "## プロジェクト記憶" in result.stdout
    assert "## 最近の作業記録" in result.stdout
    assert "### ユーザーの思想" in result.stdout
    assert "### 期待仕様" in result.stdout
    assert "### 進捗" in result.stdout
    assert "### 検証" in result.stdout


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


def test_prepare_skips_transient_review_session_and_keeps_project_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "review-filter-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="project-session-001",
        entries=[
            {"role": "user", "text": "Keep the installer plan visible."},
            {"role": "assistant", "text": "I will keep the installer plan visible.", "phase": "final_answer"},
        ],
    )
    _write_session_log(
        codex_home,
        workdir,
        session_id="project-session-002",
        entries=[
            {"role": "user", "text": "Track the background sync progress."},
            {"role": "assistant", "text": "I will track the background sync progress.", "phase": "final_answer"},
        ],
    )
    _write_session_log(
        codex_home,
        workdir,
        session_id="project-session-003",
        entries=[
            {"role": "user", "text": "Keep the Windows packaging task in focus."},
            {"role": "assistant", "text": "I will keep the Windows packaging task in focus.", "phase": "final_answer"},
        ],
    )
    _write_session_log(
        codex_home,
        workdir,
        session_id="review-session-001",
        entries=[
            {
                "role": "user",
                "text": "## Code review guidelines: Review the current code changes and provide prioritized findings.",
            },
            {"role": "assistant", "text": "Checking unstaged diffs.", "phase": "commentary"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    session_ids = [item["session_id"] for item in state["recent_sessions"]]
    assert len(session_ids) == 3
    assert set(session_ids) == {"project-session-001", "project-session-002", "project-session-003"}
    assert "Code review guidelines" not in result.stdout
    assert "Keep the installer plan visible." in result.stdout


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
    assert f"memory.json: {store / 'memory.json'}" in result.stdout


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


def test_prepare_preserves_existing_memory_without_recent_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "memory-persist-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="memory-persist-001",
        entries=[
            {"role": "user", "text": "目指してるのは ChatGPT のメモリみたいな使用感で Codexapp を使いたい。"},
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

    sessions_dir = codex_home / "sessions"
    archived_dir = codex_home / "archived_sessions"
    if sessions_dir.exists():
        shutil.rmtree(sessions_dir)
    if archived_dir.exists():
        shutil.rmtree(archived_dir)

    assert runner.invoke(app, ["prepare", "--stdout"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    summaries = [item["summary"] for item in memory["semantic_entries"]]
    assert any("ChatGPT のメモリみたいな使用感" in item for item in summaries)
    assert any("同期ミラーとして扱います" in item for item in summaries)


def test_prepare_records_git_worklog_entries_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_git()
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "git-worklog-repo"
    repo.mkdir()
    _init_git_repo(repo)
    _write(repo / "README.md", "# Demo\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")
    _write(repo / "README.md", "# Demo\n\nupdated\n")

    _write_session_log(
        codex_home,
        repo,
        session_id="git-worklog-001",
        entries=[
            {"role": "user", "text": "作業メモに進捗と検証も入れたい。"},
            {"role": "assistant", "text": "作業メモを分離して実装しました。", "phase": "final_answer"},
            {"role": "assistant", "text": "pytest -q を通しました。", "phase": "final_answer"},
        ],
    )

    monkeypatch.chdir(repo)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(repo)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    worklog = memory["worklog_entries"]
    kinds = {item["kind"] for item in worklog}
    summaries = [item["summary"] for item in worklog]

    assert {"progress", "verification", "commit", "change"} <= kinds
    assert any("Initial commit" in item for item in summaries)
    assert any("README.md" in item for item in summaries)
    assert "## 最近の作業記録" in result.stdout
    assert "### 直近コミット" in result.stdout
    assert "### 変更ファイル" in result.stdout


def test_prepare_splits_final_answer_and_avoids_false_failure_on_positive_problem_phrase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "memory-splitting-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="memory-splitting-001",
        entries=[
            {"role": "user", "text": "読み取り品質を上げたい。"},
            {
                "role": "assistant",
                "text": "Codex 側の読み取り経路は問題ありません。配布版とローカル更新も済ませました。pytest -q を通しました。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    semantic = memory["semantic_entries"]
    worklog = memory["worklog_entries"]

    assert not any(item["summary"] == "Codex 側の読み取り経路は問題ありません。" and item["kind"] == "failure" for item in semantic)
    assert not any(item["summary"] == "Codex 側の読み取り経路は問題ありません。" for item in semantic)
    assert any(item["summary"] == "配布版とローカル更新も済ませました。" and item["kind"] == "progress" for item in worklog)
    assert any(item["summary"] == "pytest -q を通しました。" and item["kind"] == "verification" for item in worklog)
    assert "Codex 側の読み取り経路は問題ありません。" not in result.stdout


def test_prepare_skips_meta_assistant_explanations_in_semantic_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "meta-memory-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="meta-memory-001",
        entries=[
            {"role": "user", "text": "意味記憶の抽出方針を固めたい。"},
            {
                "role": "assistant",
                "text": (
                    "できると思います。\n\n"
                    "実装上の方針はこうです。\n\n"
                    "- assistant の commentary は原則 memory 候補から除外\n"
                    "- assistant の final_answer だけを意味記憶の候補にする\n"
                    "次のボトルネックは抽出ノイズの削減です。\n"
                    "必要なら次はそこまで実装します。"
                ),
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    semantic_summaries = [item["summary"] for item in memory["semantic_entries"]]

    assert "assistant の final_answer だけを意味記憶の候補にする" in semantic_summaries
    assert "次のボトルネックは抽出ノイズの削減です。" not in semantic_summaries
    assert "必要なら次はそこまで実装します。" not in semantic_summaries


def test_prepare_preserves_manual_tasks_but_drops_conversational_stale_tasks_and_duplicate_decisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "preserve-manual-task-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="manual-task-001",
        entries=[
            {"role": "user", "text": "global store と local mirror の扱いを決めたい。"},
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
    _write(
        store / "tasks.md",
        "# Tasks\n\n"
        "- 自動更新: `codex-handoff prepare` / `capture` / background sync\n"
        "- 生成日時: `2026-03-18T09:59:00+09:00`\n\n"
        "- [ ] とりあえずやってみて結果を見よう\n"
        "- [ ] 手動で残したタスク\n",
    )
    _write(
        store / "decisions.md",
        "# Decisions\n\n"
        "- 自動更新: `codex-handoff prepare` / `capture` / background sync\n"
        "- 生成日時: `2026-03-18T09:59:00+09:00`\n\n"
        "- 2026-03-18: global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。追加説明付き\n"
        "- 2026-03-18: 手動で残した決定\n",
    )

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    tasks = (store / "tasks.md").read_text(encoding="utf-8")
    decisions = (store / "decisions.md").read_text(encoding="utf-8")

    assert "とりあえずやってみて結果を見よう" not in tasks
    assert "手動で残したタスク" in tasks
    assert decisions.count("global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います") == 1
    assert "手動で残した決定" in decisions


def test_prepare_recent_session_section_prefers_session_summaries_over_raw_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "recent-session-summary-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="recent-summary-001",
        entries=[
            {"role": "user", "text": "意味記憶の抽出方針を固めたい。"},
            {
                "role": "assistant",
                "text": (
                    "できると思います。\n\n"
                    "実装上の方針はこうです。\n\n"
                    "- assistant の final_answer だけを意味記憶の候補にする\n"
                    "必要なら次はそこまで実装します。"
                ),
                "phase": "final_answer",
            },
            {"role": "user", "text": "やれるならやって"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    session = state["recent_sessions"][0]

    assert session["latest_user_message"] == "やれるならやって"
    assert session["latest_substantive_user_summary"] == "意味記憶の抽出方針を固めたい。"
    assert session["latest_assistant_summary"] == "assistant の final_answer だけを意味記憶の候補にする"
    assert "## 現在の主題" in result.stdout
    assert "- 意味記憶の抽出方針を固めたい。" in result.stdout
    assert "- 直近の回答: assistant の final_answer だけを意味記憶の候補にする" in result.stdout
    assert "必要なら次はそこまで実装します。" not in result.stdout


def test_prepare_does_not_promote_meta_quality_question_to_current_focus_or_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "meta-quality-focus-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="meta-quality-focus-001",
        entries=[
            {"role": "user", "text": "task/current focus の優先順位を整理したい。"},
            {"role": "assistant", "text": "優先順位の見直し方針を整理します。", "phase": "final_answer"},
            {"role": "user", "text": "今何点？さらにつめるところは？subagentで結果の評価と調整繰り返した方がいいんじゃない？"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    tasks = (store / "tasks.md").read_text(encoding="utf-8")

    assert "今何点？" not in tasks
    assert "- [ ] task/current focus の優先順位を整理する。" in tasks
    assert "## 現在の主題" in result.stdout
    assert "- task/current focus の優先順位を整理する。" in result.stdout


def test_prepare_preserves_high_signal_score_like_success_in_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "score-success-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="score-success-001",
        entries=[
            {"role": "user", "text": "task/current focus の優先順位を整理したい。"},
            {"role": "assistant", "text": "更新しました、95/100点です。", "phase": "final_answer"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    session = state["recent_sessions"][0]
    semantic_summaries = [item["summary"] for item in memory["semantic_entries"]]

    assert session["latest_substantive_user_summary"] == "task/current focus の優先順位を整理したい。"
    assert any("95/100点" in item for item in semantic_summaries)
    assert "95/100点" in result.stdout
    assert "### 現在の評価" not in result.stdout


def test_prepare_preserves_internal_state_goal_in_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "handoff-goal-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="handoff-goal-001",
        entries=[
            {
                "role": "user",
                "text": "ユーザーに見せる必要ないよ。スレッド間で情報共有できることが目的です。",
            },
            {
                "role": "assistant",
                "text": "内部状態を正本にして次スレッドへ再注入する方針で進めます。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    semantic_summaries = [item["summary"] for item in memory["semantic_entries"]]

    assert any("スレッド間で情報共有できることが目的" in item for item in semantic_summaries)
    assert "スレッド間で情報共有できることが目的" in result.stdout


def test_prepare_records_working_context_with_focus_paths_and_next_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "working-context-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")
    _write(workdir / "src" / "codex_handoff" / "memory.py", "print('demo')\n")
    _write(workdir / "src" / "codex_handoff" / "renderer.py", "print('demo')\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="working-context-001",
        entries=[
            {
                "role": "user",
                "text": "`src/codex_handoff/memory.py` の topic-based memory 更新を進めたい。",
            },
            {
                "role": "assistant",
                "text": "`src/codex_handoff/renderer.py` も合わせて確認します。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))

    assert "memory.py" in (memory["current_focus"] or "")
    focus_paths = [item["path"] for item in memory["focus_paths"]]
    next_actions = [item["summary"] for item in memory["next_actions"]]

    assert "src/codex_handoff/memory.py" in focus_paths
    assert "src/codex_handoff/renderer.py" in focus_paths
    assert any("memory.py" in item for item in next_actions)
    assert "memory.py" in result.stdout


def test_prepare_dogfoods_topic_supersede_and_keeps_working_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "dogfood-topic-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")
    _write(workdir / "src" / "codex_handoff" / "memory.py", "print('demo')\n")
    _write(workdir / "src" / "codex_handoff" / "renderer.py", "print('demo')\n")

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    (store / "memory.json").write_text(
        json.dumps(
            {
                "version": 2,
                "project_id": make_project_id(workdir),
                "project_name": workdir.name,
                "updated_at": "2026-03-18T09:59:00+09:00",
                "semantic_entries": [
                    {
                        "kind": "spec",
                        "summary": "`memory.json` を正本として扱いたい。",
                        "topic": "storage_strategy",
                        "source_role": "user",
                        "updated_at": "2026-03-18T09:59:00+09:00",
                    }
                ],
                "worklog_entries": [],
                "current_focus": None,
                "focus_paths": [],
                "next_actions": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    _write_session_log(
        codex_home,
        workdir,
        session_id="dogfood-topic-001",
        entries=[
            {
                "role": "user",
                "text": "`src/codex_handoff/memory.py` の topic-based supersede を詰めたい。",
            },
            {
                "role": "assistant",
                "text": "`memory.json` を内部状態の正本にして次スレッドへ再注入する方針です。`src/codex_handoff/renderer.py` も確認します。",
                "phase": "final_answer",
            },
        ],
    )

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    storage_entries = [item for item in memory["semantic_entries"] if item.get("topic") == "storage_strategy"]

    assert len(storage_entries) == 1
    assert storage_entries[0]["kind"] == "decision"
    assert storage_entries[0]["summary"] == "`memory.json` を内部状態の正本にして次スレッドへ再注入する方針です。"
    assert "memory.py" in (memory["current_focus"] or "")
    assert "src/codex_handoff/memory.py" in [item["path"] for item in memory["focus_paths"]]
    assert any("memory.py" in item["summary"] for item in memory["next_actions"])
    assert "memory.py" in result.stdout


def test_prepare_compacts_conversational_wrapper_from_substantive_focus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "compact-focus-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="compact-focus-001",
        entries=[
            {
                "role": "user",
                "text": "そうだね。途中の推論部分は省いて双方の発話ベースにしたいな。 でも作業進捗とかコミットとかも必要だね。うまくできるかな",
            },
            {"role": "assistant", "text": "発話ベースと作業記録を分離します。", "phase": "final_answer"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    tasks = (store / "tasks.md").read_text(encoding="utf-8")

    assert "そうだね。" not in tasks
    assert "うまくできるかな" not in tasks
    assert "途中の推論部分は省いて双方の発話ベースにする。 作業進捗とかコミットとかも含める。" in tasks
    assert "## 現在の主題" in result.stdout
    assert "- 途中の推論部分は省いて双方の発話ベースにする。 作業進捗とかコミットとかも含める。" in result.stdout


def test_prepare_drops_quality_push_followups_and_keeps_previous_substantive_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "quality-push-focus-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="quality-push-focus-001",
        entries=[
            {
                "role": "user",
                "text": "途中の推論部分は省いて双方の発話ベースにしたいな。 でも作業進捗とかコミットとかも必要だね。",
            },
            {"role": "assistant", "text": "次はそのノイズを落とします。", "phase": "final_answer"},
            {"role": "user", "text": "完璧にしよう"},
            {"role": "user", "text": "最後の力を振り絞って9.9999ぐらいまで目指しましょう"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    tasks = (store / "tasks.md").read_text(encoding="utf-8")
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    session = state["recent_sessions"][0]

    assert "完璧にしよう" not in tasks
    assert "最後の力を振り絞って" not in tasks
    assert session["latest_substantive_user_summary"] == "途中の推論部分は省いて双方の発話ベースにしたいな。 でも作業進捗とかコミットとかも必要だね。"
    assert "- 途中の推論部分は省いて双方の発話ベースにする。 作業進捗とかコミットとかも含める。" in result.stdout


def test_prepare_drops_continuation_only_followup_and_keeps_previous_substantive_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "continuation-focus-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="continuation-focus-001",
        entries=[
            {"role": "user", "text": "semantic memory と worklog の役割分担を固めたい。"},
            {"role": "assistant", "text": "memory の役割分担を整理します。", "phase": "final_answer"},
            {"role": "user", "text": "続きを"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    tasks = (store / "tasks.md").read_text(encoding="utf-8")
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    session = state["recent_sessions"][0]

    assert "続きを" not in tasks
    assert session["latest_substantive_user_summary"] == "semantic memory と worklog の役割分担を固めたい。"
    assert "- semantic memory と worklog の役割分担を固めたい。" in result.stdout


def test_prepare_drops_orchestration_only_followup_and_keeps_previous_substantive_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "orchestration-focus-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="orchestration-focus-001",
        entries=[
            {"role": "user", "text": "途中の推論部分は省いて双方の発話ベースにしたいな。 でも作業進捗とかコミットとかも必要だね。"},
            {"role": "assistant", "text": "その方向で整理します。", "phase": "final_answer"},
            {"role": "user", "text": "subagent駆使して更に実用的なものに仕上げて"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    tasks = (store / "tasks.md").read_text(encoding="utf-8")
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    session = state["recent_sessions"][0]

    assert "subagent駆使して更に実用的なものに仕上げて" not in tasks
    assert session["latest_substantive_user_summary"] == "途中の推論部分は省いて双方の発話ベースにしたいな。 でも作業進捗とかコミットとかも必要だね。"
    assert "- 途中の推論部分は省いて双方の発話ベースにする。 作業進捗とかコミットとかも含める。" in result.stdout


def test_prepare_prioritizes_substantive_tasks_over_housekeeping_and_vague_followups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "task-priority-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="task-priority-001",
        entries=[
            {"role": "user", "text": "task/current focus の優先順位を整理したい。"},
            {"role": "assistant", "text": "タスク生成の優先順位を見直しました。", "phase": "final_answer"},
            {"role": "user", "text": "そこも良くなる確信があるならちゃんと詰めよう。"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    _write(
        store / "tasks.md",
        "# Tasks\n\n"
        "- 自動更新: `codex-handoff prepare` / `capture` / background sync\n"
        "- 生成日時: `2026-03-18T09:59:00+09:00`\n\n"
        "- [ ] やれるならやって\n"
        "- [ ] 変更ファイルを確認する: `README.md`\n"
        "- [ ] task/current focus の優先順位を整理したい。\n",
    )

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    tasks = (store / "tasks.md").read_text(encoding="utf-8")
    task_lines = [line for line in tasks.splitlines() if line.startswith("- [ ] ")]

    assert task_lines[0] == "- [ ] task/current focus の優先順位を整理する。"
    assert "やれるならやって" not in tasks
    assert "## 現在の主題" in result.stdout
    assert "- task/current focus の優先順位を整理する。" in result.stdout


def test_prepare_deduplicates_normalized_current_and_preserved_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "task-dedupe-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="task-dedupe-001",
        entries=[
            {"role": "user", "text": "途中の推論部分は省いて双方の発話ベースにしたいな。 でも作業進捗とかコミットとかも必要だね。"},
            {"role": "assistant", "text": "意味記憶と作業記録を分離します。", "phase": "final_answer"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    _write(
        store / "tasks.md",
        "# Tasks\n\n"
        "- [ ] 途中の推論部分は省いて双方の発話ベースにしたいな。 でも作業進捗とかコミットとかも必要だね。\n",
    )

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    tasks = (store / "tasks.md").read_text(encoding="utf-8")
    matching = [line for line in tasks.splitlines() if "双方の発話ベース" in line]

    assert len(matching) == 1


def test_prepare_uses_concise_memory_decisions_and_drops_verbose_preambles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "concise-decision-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="concise-decision-001",
        entries=[
            {"role": "user", "text": "global store と local mirror の扱いを決めたい。"},
            {
                "role": "assistant",
                "text": (
                    "方針は固まりました。\n\n"
                    "global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。\n"
                    "今回で効いた点は 2 つです。"
                ),
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    _write(
        store / "decisions.md",
        "# Decisions\n\n"
        "- 自動更新: `codex-handoff prepare` / `capture` / background sync\n"
        "- 生成日時: `2026-03-18T09:59:00+09:00`\n\n"
        "- 2026-03-18: 方針は固まりました。global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。\n",
    )

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    decisions = (store / "decisions.md").read_text(encoding="utf-8")
    assert "方針は固まりました" not in decisions
    assert decisions.count("global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。") == 1


def test_prepare_drops_stale_probe_decisions_from_existing_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "stale-probe-decision-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="stale-probe-decision-001",
        entries=[
            {"role": "user", "text": "global store と local mirror の扱いを決めたい。"},
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
    _write(
        store / "decisions.md",
        "# Decisions\n\n"
        "- 自動更新: `codex-handoff prepare` / `capture` / background sync\n"
        "- 生成日時: `2026-03-18T09:59:00+09:00`\n\n"
        "- 2026-03-18: このリポジトリの設定どおり確認します。まず `codex-handoff prepare --stdout` を実行して、その後 `.codex-handoff` の状態を見ます。\n"
        "- 2026-03-18: global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。\n",
    )

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    decisions = (store / "decisions.md").read_text(encoding="utf-8")
    assert "このリポジトリの設定どおり確認します" not in decisions
    assert decisions.count("global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。") == 1


def test_prepare_drops_stale_quality_decisions_from_existing_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "stale-quality-decision-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="stale-quality-decision-001",
        entries=[
            {"role": "user", "text": "global store を正本にする方針で進めたい。"},
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
    _write(
        store / "decisions.md",
        "# Decisions\n\n"
        "- 自動更新: `codex-handoff prepare` / `capture` / background sync\n"
        "- 生成日時: `2026-03-18T09:59:00+09:00`\n\n"
        "- 2026-03-18: 機能はかなり良いですが、満点にするにはこの順が効きます。\n"
        "- 2026-03-18: global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。\n",
    )

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    decisions = (store / "decisions.md").read_text(encoding="utf-8")
    assert "機能はかなり良いですが、満点にするにはこの順が効きます。" not in decisions
    assert decisions.count("global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱います。") == 1


def test_prepare_filters_meta_memory_evaluation_from_semantic_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "meta-memory-filter-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="meta-memory-filter-001",
        entries=[
            {"role": "user", "text": "失敗知識を durable memory に寄せたい。"},
            {
                "role": "assistant",
                "text": (
                    "生成された `next-thread.md` / `memory.json` を見て、ノイズ・重複・誤優先順位を指摘する。\n"
                    "生ログを積むだけだとノイズになるので、会話から「記憶候補」を抽出して、安定したものだけを昇格させる必要があります。"
                ),
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    semantic_summaries = [item["summary"] for item in memory["semantic_entries"]]

    assert "生成された `next-thread.md` / `memory.json` を見て、ノイズ・重複・誤優先順位を指摘する" not in semantic_summaries
    assert any("安定したものだけを昇格させる必要があります" in item for item in semantic_summaries)


def test_prepare_collapses_existing_cross_kind_duplicate_semantic_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, _ = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "dedupe-semantic-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    duplicated_summary = "失敗だけじゃなくて成功したものとかユーザーの求めてる思想・仕様とかもメモリに入れられたらいいね"
    (store / "memory.json").write_text(
        json.dumps(
            {
                "version": 2,
                "project_id": make_project_id(workdir),
                "project_name": workdir.name,
                "updated_at": FIXED_NOW,
                "semantic_entries": [
                    {
                        "kind": "preference",
                        "summary": duplicated_summary,
                        "source_role": "user",
                        "source_session_id": "older-session",
                        "updated_at": FIXED_NOW,
                    },
                    {
                        "kind": "spec",
                        "summary": duplicated_summary,
                        "source_role": "user",
                        "source_session_id": "older-session",
                        "updated_at": FIXED_NOW,
                    },
                ],
                "worklog_entries": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    matching_entries = [item for item in memory["semantic_entries"] if item["summary"] == duplicated_summary]

    assert len(matching_entries) == 1
    assert matching_entries[0]["kind"] == "preference"
    assert result.stdout.count(duplicated_summary) == 1


def test_prepare_filters_meta_user_memory_tuning_from_semantic_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "meta-user-memory-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="meta-user-memory-001",
        entries=[
            {"role": "user", "text": "このメモの内容を最適化する必要がありそうだな。"},
            {"role": "assistant", "text": "quality tuning の会話は durable memory に上げないようにします。", "phase": "final_answer"},
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    semantic_summaries = [item["summary"] for item in memory["semantic_entries"]]

    assert "このメモの内容を最適化する必要がありそうだな。" not in semantic_summaries
    assert "このメモの内容を最適化する必要がありそうだな。" not in result.stdout


def test_prepare_deduplicates_stale_distribution_and_verification_worklog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "dedupe-worklog-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="dedupe-worklog-001",
        entries=[
            {"role": "user", "text": "配布更新と検証結果の見え方を整理したい。"},
            {
                "role": "assistant",
                "text": (
                    "版は `0.6.2` に上げ、`pytest` 全件通過と `compileall` を確認したうえで "
                    "PATH 側 CLI を再インストールし、Windows 配布物も再ビルドしてローカル更新も済ませました。"
                ),
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    (store / "memory.json").write_text(
        json.dumps(
            {
                "version": 2,
                "project_id": make_project_id(workdir),
                "project_name": workdir.name,
                "updated_at": "2026-03-18T09:59:00+09:00",
                "semantic_entries": [],
                "worklog_entries": [
                    {
                        "kind": "progress",
                        "summary": "版は `0.6.1` に上げ、PATH 側 CLI を再インストールし、Windows 配布物も再ビルドしてローカル更新も済ませました。",
                        "source": "assistant_final",
                        "source_session_id": "older-session",
                        "updated_at": "2026-03-18T09:59:00+09:00",
                    },
                    {
                        "kind": "verification",
                        "summary": "`pytest` 全件通過と `compileall` を確認しました。",
                        "source": "assistant_final",
                        "source_session_id": "older-session",
                        "updated_at": "2026-03-18T09:59:00+09:00",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    summaries = [item["summary"] for item in memory["worklog_entries"]]

    assert not any("0.6.1" in item for item in summaries)
    assert any("pytest" in item and "compileall" in item for item in summaries)
    assert any("ローカル更新も済ませました" in item for item in summaries)
    assert "0.6.1" not in result.stdout


def test_prepare_keeps_code_progress_when_distribution_updates_are_newer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "progress-priority-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="progress-priority-001",
        entries=[
            {"role": "user", "text": "進捗の出し方をもっと実用寄りにしたい。"},
            {
                "role": "assistant",
                "text": "回帰は test_cli.py に追加しました。",
                "phase": "final_answer",
            },
            {
                "role": "assistant",
                "text": (
                    "ローカルの CodexHandoff.exe と CodexHandoffBackground.exe も新ビルドへ差し替え済みです。"
                    " 常用経路も更新済みです。"
                    " ローカルの `%LOCALAPPDATA%\\\\CodexHandoff` も新ビルドで上書きしました。"
                ),
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    progress_entries = [item["summary"] for item in memory["worklog_entries"] if item["kind"] == "progress"]

    assert any("test_cli.py" in item for item in progress_entries)
    distribution_entries = [
        item
        for item in progress_entries
        if "CodexHandoff.exe" in item or "%LOCALAPPDATA%" in item or "常用経路" in item
    ]
    assert len(distribution_entries) == 1


def test_prepare_deduplicates_prepare_verification_topics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "prepare-verification-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="prepare-verification-001",
        entries=[
            {"role": "user", "text": "prepare 系の検証重複を減らしたい。"},
            {
                "role": "assistant",
                "text": (
                    "検証は `pytest -q` と `python -m compileall src` が通過です。 "
                    "`.venv\\Scripts\\python.exe -m codex_handoff prepare` で global store と local mirror の更新表示まで確認しました。"
                ),
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    (store / "memory.json").write_text(
        json.dumps(
            {
                "version": 2,
                "project_id": make_project_id(workdir),
                "project_name": workdir.name,
                "updated_at": "2026-03-18T09:59:00+09:00",
                "semantic_entries": [],
                "worklog_entries": [
                    {
                        "kind": "verification",
                        "summary": "`codex-handoff prepare --stdout` も新ロジックで一致することを確認しました。",
                        "source": "assistant_final",
                        "source_session_id": "older-session",
                        "updated_at": "2026-03-18T09:59:00+09:00",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    verification_entries = [item["summary"] for item in memory["worklog_entries"] if item["kind"] == "verification"]
    prepare_entries = [item for item in verification_entries if "prepare" in item]

    assert len(prepare_entries) == 1
    assert ".venv\\Scripts\\python.exe -m codex_handoff prepare" in prepare_entries[0]
    assert any("pytest" in item and "compileall" in item for item in verification_entries)
    assert len(verification_entries) <= 2


def test_prepare_filters_generic_success_and_positive_failure_memory_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "semantic-filter-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="semantic-filter-001",
        entries=[
            {"role": "user", "text": "handoff の品質を上げたい。"},
            {
                "role": "assistant",
                "text": (
                    "常用版も `0.6.4` に揃えて、PATH の `codex-handoff` と CodexHandoff.exe を更新済みです。\n"
                    "常用経路も更新済みです。\n"
                    "これで「違う話を引き継ぐ」という主要な崩れ方はかなり減ります。"
                ),
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    summaries = [item["summary"] for item in memory["semantic_entries"]]

    assert not any("常用版も `0.6.4` に揃えて" in item for item in summaries)
    assert "常用経路も更新済みです。" not in summaries
    assert not any("かなり減ります" in item for item in summaries)


def test_prepare_filters_confirmation_status_and_operational_success_from_semantic_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "confirmation-filter-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="confirmation-filter-001",
        entries=[
            {"role": "user", "text": "handoff の品質を確認したい。"},
            {
                "role": "assistant",
                "text": (
                    "かなりいいです。Codex 側の読み取り経路は問題ありません。"
                    "global の AGENTS.md を新構成に揃えて、`.codex-handoff/memory.json` を読む文面まで更新しました。"
                ),
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    semantic_summaries = [item["summary"] for item in memory["semantic_entries"]]
    progress_summaries = [item["summary"] for item in memory["worklog_entries"] if item["kind"] == "progress"]

    assert not any("問題ありません" in item for item in semantic_summaries)
    assert not any("AGENTS.md" in item for item in semantic_summaries)
    assert any("memory.json" in item for item in progress_summaries)


def test_prepare_prioritizes_high_signal_progress_over_operational_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "progress-priority-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="progress-priority-001",
        entries=[
            {"role": "user", "text": "handoff の改善を進めて。"},
            {"role": "assistant", "text": "回帰は test_cli.py に追加しました。", "phase": "final_answer"},
            {"role": "assistant", "text": "PATH 側 CLI も `codex-handoff v0.6.6` に更新済みです。", "phase": "final_answer"},
            {"role": "assistant", "text": "ローカルの `%LOCALAPPDATA%\\CodexHandoff` も新ビルドで上書きしました。", "phase": "final_answer"},
            {
                "role": "assistant",
                "text": "ローカルの CodexHandoff.exe と CodexHandoffBackground.exe も新ビルドへ差し替え済みです。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    progress_summaries = [item["summary"] for item in memory["worklog_entries"] if item["kind"] == "progress"]

    assert any("test_cli.py" in item for item in progress_summaries)
    assert len(progress_summaries) <= 3


def test_prepare_filters_operational_version_checks_from_verification_worklog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "verification-filter-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="verification-filter-001",
        entries=[
            {"role": "user", "text": "handoff の検証ログを整理したい。"},
            {
                "role": "assistant",
                "text": "両方の exe の FileVersion / ProductVersion が 0.5.1.0 であることを確認しました。",
                "phase": "final_answer",
            },
            {
                "role": "assistant",
                "text": "検証は `pytest -q` と `python -m compileall src` を通しました。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    verification_summaries = [item["summary"] for item in memory["worklog_entries"] if item["kind"] == "verification"]

    assert any("pytest -q" in item and "compileall" in item for item in verification_summaries)
    assert not any("FileVersion" in item or "ProductVersion" in item for item in verification_summaries)


def test_prepare_combined_verification_supersedes_partial_verification_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "verification-supersede-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="verification-supersede-001",
        entries=[
            {"role": "user", "text": "検証ログの見え方を整理したい。"},
            {
                "role": "assistant",
                "text": "検証は `pytest -q` と `python -m compileall src` を通しました。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    (store / "memory.json").write_text(
        json.dumps(
            {
                "version": 2,
                "project_id": make_project_id(workdir),
                "project_name": workdir.name,
                "updated_at": "2026-03-18T09:59:00+09:00",
                "semantic_entries": [],
                "worklog_entries": [
                    {
                        "kind": "verification",
                        "summary": "`pytest -q` を通しました。",
                        "source": "assistant_final",
                        "source_session_id": "older-session",
                        "updated_at": "2026-03-18T09:59:00+09:00",
                    },
                    {
                        "kind": "verification",
                        "summary": "`python -m compileall src` を確認しました。",
                        "source": "assistant_final",
                        "source_session_id": "older-session",
                        "updated_at": "2026-03-18T09:59:00+09:00",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    verification = [item["summary"] for item in memory["worklog_entries"] if item["kind"] == "verification"]

    assert any("pytest -q" in item and "compileall" in item for item in verification)
    assert "`pytest -q` を通しました。" not in verification
    assert "`python -m compileall src` を確認しました。" not in verification


def test_prepare_prioritizes_source_changes_over_generated_build_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_git()
    global_home, _ = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "changed-file-priority-repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    (repo / "build-assets" / "background-build" / "CodexHandoffBackground").mkdir(parents=True)
    _write(repo / "README.md", "# Demo\n")
    _write(repo / "src" / "app.py", "print('v1')\n")
    _write(repo / "tests" / "test_app.py", "def test_demo():\n    assert True\n")
    _write(repo / "build-assets" / "background-build" / "CodexHandoffBackground" / "EXE-00.toc", "v1\n")
    _init_git_repo(repo)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")

    _write(repo / "src" / "app.py", "print('v2')\n")
    _write(repo / "tests" / "test_app.py", "def test_demo():\n    assert 1 == 1\n")
    _write(repo / "build-assets" / "background-build" / "CodexHandoffBackground" / "EXE-00.toc", "v2\n")

    monkeypatch.chdir(repo)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(repo)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    changed_paths = [item["path"] for item in state["changed_files"]]

    assert changed_paths.index("src/app.py") < changed_paths.index(
        "build-assets/background-build/CodexHandoffBackground/EXE-00.toc"
    )
    assert changed_paths.index("tests/test_app.py") < changed_paths.index(
        "build-assets/background-build/CodexHandoffBackground/EXE-00.toc"
    )


def test_prepare_uses_user_facing_changed_files_in_tasks_initial_steps_and_worklog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_git()
    global_home, _ = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "user-facing-change-repo"
    (repo / "src").mkdir(parents=True)
    (repo / ".codex-handoff").mkdir(parents=True)
    (repo / "build-assets" / "background-build" / "CodexHandoffBackground").mkdir(parents=True)
    _write(repo / "README.md", "# Demo\n")
    _write(repo / "src" / "app.py", "print('v1')\n")
    _write(repo / ".codex-handoff" / "next-thread.md", "# old\n")
    _write(repo / "build-assets" / "background-build" / "CodexHandoffBackground" / "EXE-00.toc", "v1\n")
    _init_git_repo(repo)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")

    _write(repo / "src" / "app.py", "print('v2')\n")
    _write(repo / ".codex-handoff" / "next-thread.md", "# new\n")
    _write(repo / "build-assets" / "background-build" / "CodexHandoffBackground" / "EXE-00.toc", "v2\n")

    monkeypatch.chdir(repo)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(repo)
    tasks = (store / "tasks.md").read_text(encoding="utf-8")
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    change_entries = [item["summary"] for item in memory["worklog_entries"] if item["kind"] == "change"]

    assert "変更ファイルを確認する: `src/app.py`" in tasks
    assert ".codex-handoff/next-thread.md" not in tasks
    assert "build-assets/background-build/CodexHandoffBackground/EXE-00.toc" not in tasks
    assert "2. 変更ファイルを確認して現在地を把握する: `src/app.py`" in result.stdout
    assert any("`src/app.py` (M)" == item for item in change_entries)
    assert not any(".codex-handoff/next-thread.md" in item for item in change_entries)
    assert not any("build-assets/background-build/CodexHandoffBackground/EXE-00.toc" in item for item in change_entries)


def test_prepare_marks_tracked_local_handoff_files_as_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_git()
    global_home, _ = _set_env(tmp_path, monkeypatch)
    repo = tmp_path / "tracked-handoff-repo"
    repo.mkdir()
    _init_git_repo(repo)
    _write(repo / "README.md", "# Demo\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")

    monkeypatch.chdir(repo)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0
    _git(repo, "add", ".codex-handoff")
    _git(repo, "commit", "-m", "Track handoff mirror")

    monkeypatch.setattr(service_module, "now_local_iso", lambda: "2026-03-18T10:05:00+09:00")

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(repo)
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    changed_paths = [item["path"] for item in state["changed_files"]]
    assert state["is_dirty"] is True
    assert ".codex-handoff/next-thread.md" in changed_paths
    assert ".codex-handoff/state.json" in changed_paths


def test_prepare_drops_stale_review_items_from_existing_generated_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, _ = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "drop-review-notes"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    _write(
        store / "tasks.md",
        "# Tasks\n\n- 自動更新: `codex-handoff prepare` / `capture` / background sync\n- 生成日時: `2026-03-18T09:59:00+09:00`\n\n- [ ] ## Code review guidelines: Review the current code changes and provide prioritized findings.\n- [ ] 重要ファイルを確認して文脈を戻す: `README.md`\n",
    )
    _write(
        store / "decisions.md",
        "# Decisions\n\n- 自動更新: `codex-handoff prepare` / `capture` / background sync\n- 生成日時: `2026-03-18T09:59:00+09:00`\n\n- 2026-03-18: 変更は現状 `.codex-handoff` 配下だけで、まずは staged/unstaged の差分量と中身を確認しています。\n- 2026-03-18: global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱う。\n",
    )

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    tasks = (store / "tasks.md").read_text(encoding="utf-8")
    decisions = (store / "decisions.md").read_text(encoding="utf-8")
    assert "Code review guidelines" not in tasks
    assert "重要ファイルを確認して文脈を戻す" in tasks
    assert "staged/unstaged" not in decisions
    assert "global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱う。" in decisions


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
    assert "[OK] user_memory:" in result.stdout
    assert "[OK] project_store:" in result.stdout


def test_prepare_updates_user_global_memory_without_polluting_project_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "user-global-memory-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")
    _write(
        workdir / "AGENTS.md",
        "\n".join(
            (
                "回答は日本語。",
                "開発環境は Windows 11。CodexWindowsApp。",
                "不明点は合理的な仮定を置いて前進し、仮定は明示する。",
                "破壊的操作・外部公開・課金・機密情報送信の前は必ず確認する。",
            )
        )
        + "\n",
    )
    _write_session_log(
        codex_home,
        workdir,
        session_id="user-global-memory-001",
        entries=[
            {
                "role": "user",
                "text": "以後も回答は日本語で。破壊的操作の前は確認して。",
            },
            {
                "role": "assistant",
                "text": "了解しました。以後も日本語で進め、破壊的操作の前は確認します。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    user_memory = json.loads((global_home / "user-memory.json").read_text(encoding="utf-8"))
    topics = {item["topic"] for item in user_memory["entries"]}
    summaries = {item["summary"] for item in user_memory["entries"]}
    assert topics >= {
        "response_language",
        "execution_environment",
        "assumption_policy",
        "risky_action_confirmation",
    }
    assert "回答は日本語。" in summaries
    assert "開発環境は Windows 11 / PowerShell / CodexWindowsApp。" in summaries
    assert "不明点は合理的な仮定を置いて前進し、仮定は明示する。" in summaries
    assert "破壊的操作・外部公開・課金・機密情報送信の前は確認する。" in summaries

    store = global_home / "projects" / make_project_id(workdir)
    project_memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    project_summaries = {item["summary"] for item in project_memory["semantic_entries"]}
    assert "回答は日本語。" not in project_summaries
    assert "開発環境は Windows 11 / PowerShell / CodexWindowsApp。" not in project_summaries


def test_prepare_applies_user_global_memory_to_other_projects_without_project_memory_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, _ = _set_env(tmp_path, monkeypatch)
    project_a = tmp_path / "user-global-source"
    project_b = tmp_path / "user-global-target"
    project_a.mkdir()
    project_b.mkdir()
    _write(project_a / "README.md", "# Source\n")
    _write(project_b / "README.md", "# Target\n")
    _write(
        project_a / "AGENTS.md",
        "\n".join(
            (
                "回答は日本語。",
                "開発環境は Windows 11。CodexWindowsApp。",
                "不明点は合理的な仮定を置いて前進し、仮定は明示する。",
                "破壊的操作・外部公開・課金・機密情報送信の前は必ず確認する。",
            )
        )
        + "\n",
    )

    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)
    monkeypatch.chdir(project_a)
    assert runner.invoke(app, ["prepare"]).exit_code == 0

    monkeypatch.chdir(project_b)
    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0
    assert "回答は日本語。" in result.stdout
    assert "開発環境は Windows 11 / PowerShell / CodexWindowsApp。" in result.stdout
    assert "不明点は合理的な仮定を置いて前進し、仮定は明示する。" in result.stdout
    assert "破壊的操作・外部公開・課金・機密情報送信の前は確認する。" in result.stdout

    store_b = global_home / "projects" / make_project_id(project_b)
    project_b_memory = json.loads((store_b / "memory.json").read_text(encoding="utf-8"))
    project_b_summaries = {item["summary"] for item in project_b_memory["semantic_entries"]}
    assert "回答は日本語。" not in project_b_summaries
    assert "開発環境は Windows 11 / PowerShell / CodexWindowsApp。" not in project_b_summaries


def test_prepare_builds_user_global_memory_from_global_agents_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "global-agents-user-memory"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")
    _write(
        codex_home / "AGENTS.md",
        "\n".join(
            (
                "回答は日本語。",
                "開発環境は Windows 11。CodexWindowsApp。",
                "不明点は合理的な仮定を置いて前進し、仮定は明示する。",
                "破壊的操作・外部公開・課金・機密情報送信の前は必ず確認する。",
            )
        )
        + "\n",
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    user_memory = json.loads((global_home / "user-memory.json").read_text(encoding="utf-8"))
    summaries = {item["summary"] for item in user_memory["entries"]}
    assert "回答は日本語。" in summaries
    assert "開発環境は Windows 11 / PowerShell / CodexWindowsApp。" in summaries
    assert "不明点は合理的な仮定を置いて前進し、仮定は明示する。" in summaries
    assert "破壊的操作・外部公開・課金・機密情報送信の前は確認する。" in summaries
    assert "回答は日本語。" in result.stdout


def test_prepare_canonicalizes_user_global_scope_decision_and_drops_fragments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "user-global-scope-canonicalization"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="user-global-scope-001",
        entries=[
            {"role": "user", "text": "global memory は薄くしたい。"},
            {
                "role": "assistant",
                "text": "\n".join(
                    (
                        "実装するなら、`user-global` には厳しい制限をかけるべきです。",
                        "- ファイル名禁止",
                        "- current focus 禁止",
                        "- next action 禁止",
                        "- 仕様や設計判断も原則禁止",
                        "- 明示的な恒常ルールだけ許可",
                        "一方で、仕様、設計方針、今の主題、ファイル文脈、次アクションは global に入れるとほぼ確実にノイズです。これは project 限定のままが正しいです。",
                    )
                ),
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    decision_summaries = [
        item["summary"]
        for item in memory["semantic_entries"]
        if item["kind"] == "decision"
    ]

    canonical = "`user-global memory` には恒常的な共通ルールだけを入れ、仕様・設計判断・現在の主題・ファイル文脈・次アクションは project memory に残す。"
    assert canonical in decision_summaries

    fragments = (
        "ファイル名禁止",
        "current focus 禁止",
        "next action 禁止",
        "仕様や設計判断も原則禁止",
        "明示的な恒常ルールだけ許可",
        "一方で、仕様、設計方針、今の主題、ファイル文脈、次アクションは global に入れるとほぼ確実にノイズです。",
        "これは project 限定のままが正しいです。",
    )
    for fragment in fragments:
        assert fragment not in decision_summaries
        assert fragment not in result.stdout


def test_prepare_drops_stale_user_global_scope_fragments_from_existing_decisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, _ = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "stale-user-global-scope-decisions"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    canonical = "`user-global memory` には恒常的な共通ルールだけを入れ、仕様・設計判断・現在の主題・ファイル文脈・次アクションは project memory に残す。"
    (store / "memory.json").write_text(
        json.dumps(
            {
                "version": 2,
                "project_id": make_project_id(workdir),
                "project_name": workdir.name,
                "updated_at": "2026-03-18T09:59:00+09:00",
                "semantic_entries": [
                    {
                        "kind": "decision",
                        "summary": canonical,
                        "topic": "user_global_scope_policy",
                        "source_session_id": "older-session",
                        "source_role": "assistant",
                        "updated_at": "2026-03-18T09:59:00+09:00",
                    }
                ],
                "worklog_entries": [],
                "current_focus": None,
                "focus_paths": [],
                "next_actions": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write(
        store / "decisions.md",
        "# Decisions\n\n"
        "- 自動生成: `codex-handoff prepare` / `capture` / background sync\n"
        "- 生成日時: `2026-03-18T09:59:00+09:00`\n\n"
        "- 2026-03-19: 仕様や設計判断も原則禁止\n"
        "- 2026-03-19: 一方で、仕様、設計方針、今の主題、ファイル文脈、次アクションは global に入れるとほぼ確実にノイズです。\n"
        "- 2026-03-19: これは project 限定のままが正しいです。\n"
        "- 2026-03-19: current focus 禁止\n"
        f"- 2026-03-19: {canonical}\n",
    )

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    decisions = (store / "decisions.md").read_text(encoding="utf-8")
    assert canonical in decisions
    assert "仕様や設計判断も原則禁止" not in decisions
    assert "current focus 禁止" not in decisions
    assert "global に入れるとほぼ確実にノイズです。" not in decisions
    assert "project 限定のままが正しいです。" not in decisions
    assert "仕様や設計判断も原則禁止" not in result.stdout
    assert "current focus 禁止" not in result.stdout


def test_prepare_filters_meta_quality_assessment_from_assistant_semantic_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "quality-meta-filter-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="quality-meta-filter-001",
        entries=[
            {"role": "user", "text": "あと満点まで足りないものは？"},
            {
                "role": "assistant",
                "text": "機能はかなり良いですが、満点にするにはこの順が効きます。",
                "phase": "final_answer",
            },
            {
                "role": "assistant",
                "text": "今の `next-thread` にも少しノイズが残るので、semantic の昇格条件をもう一段厳しくしたいです。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    semantic_summaries = {item["summary"] for item in memory["semantic_entries"]}
    assert "機能はかなり良いですが、満点にするにはこの順が効きます。" not in semantic_summaries
    assert "今の `next-thread` にも少しノイズが残るので、semantic の昇格条件をもう一段厳しくしたいです。" not in semantic_summaries
    assert "機能はかなり良いですが、満点にするにはこの順が効きます。" not in result.stdout
    assert "今の `next-thread` にも少しノイズが残るので、semantic の昇格条件をもう一段厳しくしたいです。" not in result.stdout


def test_prepare_drops_stale_meta_quality_entries_from_existing_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, _ = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "quality-meta-preserve-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    assert runner.invoke(app, ["prepare"]).exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    (store / "memory.json").write_text(
        json.dumps(
            {
                "version": 2,
                "project_id": make_project_id(workdir),
                "project_name": workdir.name,
                "updated_at": "2026-03-18T09:59:00+09:00",
                "semantic_entries": [
                    {
                        "kind": "decision",
                        "summary": "機能はかなり良いですが、満点にするにはこの順が効きます。",
                        "source_session_id": "older-session",
                        "source_role": "assistant",
                        "updated_at": "2026-03-18T09:59:00+09:00",
                    },
                    {
                        "kind": "failure",
                        "summary": "今の `next-thread` にも少しノイズが残るので、semantic の昇格条件をもう一段厳しくしたいです。",
                        "source_session_id": "older-session",
                        "source_role": "assistant",
                        "updated_at": "2026-03-18T09:59:00+09:00",
                    },
                ],
                "worklog_entries": [],
                "current_focus": None,
                "focus_paths": [],
                "next_actions": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 0

    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    semantic_summaries = {item["summary"] for item in memory["semantic_entries"]}
    assert "機能はかなり良いですが、満点にするにはこの順が効きます。" not in semantic_summaries
    assert "今の `next-thread` にも少しノイズが残るので、semantic の昇格条件をもう一段厳しくしたいです。" not in semantic_summaries


def test_prepare_filters_generic_quality_push_assessments_from_semantic_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_home, codex_home = _set_env(tmp_path, monkeypatch)
    workdir = tmp_path / "quality-push-assessment-workspace"
    workdir.mkdir()
    _write(workdir / "README.md", "# Demo\n")

    _write_session_log(
        codex_home,
        workdir,
        session_id="quality-push-assessment-001",
        entries=[
            {"role": "user", "text": "あと満点まで足りないものは？"},
            {
                "role": "assistant",
                "text": "ここまでやると、かなり 10/10 に近づきます。",
                "phase": "final_answer",
            },
            {
                "role": "assistant",
                "text": "今の残件は本質的には README の追従くらいで、挙動としてはかなり満点に近いです。",
                "phase": "final_answer",
            },
        ],
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(service_module, "now_local_iso", lambda: FIXED_NOW)

    result = runner.invoke(app, ["prepare", "--stdout"])
    assert result.exit_code == 0

    store = global_home / "projects" / make_project_id(workdir)
    memory = json.loads((store / "memory.json").read_text(encoding="utf-8"))
    semantic_summaries = {item["summary"] for item in memory["semantic_entries"]}

    assert "ここまでやると、かなり 10/10 に近づきます。" not in semantic_summaries
    assert "今の残件は本質的には README の追従くらいで、挙動としてはかなり満点に近いです。" not in semantic_summaries
    assert "ここまでやると、かなり 10/10 に近づきます。" not in result.stdout
    assert "今の残件は本質的には README の追従くらいで、挙動としてはかなり満点に近いです。" not in result.stdout


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


def _init_bare_git_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--bare"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


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
