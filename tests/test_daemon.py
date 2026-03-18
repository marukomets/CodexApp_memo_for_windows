from __future__ import annotations

import json
from pathlib import Path

import pytest

import codex_handoff.daemon as daemon
from codex_handoff.paths import make_project_id


def test_background_sync_once_prepares_active_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    global_home = tmp_path / ".codex-handoff"

    (codex_home / ".codex-global-state.json").write_text(
        json.dumps({"active-workspace-roots": [str(workspace)]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_HANDOFF_HOME", str(global_home))

    prepared: list[Path] = []
    monkeypatch.setattr(daemon, "prepare_handoff", lambda path: prepared.append(path) or (None, ""))
    monkeypatch.setattr(daemon, "now_local_iso", lambda: "2026-03-18T13:00:00+09:00")

    daemon.run_background_sync(once=True)

    assert prepared == [workspace]
    state = json.loads((global_home / "background-sync.json").read_text(encoding="utf-8"))
    assert state["active_workspace"] == workspace.as_posix()
    assert state["last_error"] is None


def test_background_sync_creates_store_for_new_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    global_home = tmp_path / ".codex-handoff"
    new_workspace = tmp_path / "brand-new-project"
    new_workspace.mkdir()

    (codex_home / ".codex-global-state.json").write_text(
        json.dumps({"active-workspace-roots": [str(new_workspace)]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_HANDOFF_HOME", str(global_home))
    monkeypatch.setattr(daemon, "now_local_iso", lambda: "2026-03-18T13:05:00+09:00")

    daemon.run_background_sync(once=True)

    store = global_home / "projects" / make_project_id(new_workspace)
    assert store.exists()
    assert (store / "project.md").exists()
    assert (store / "state.json").exists()
    assert (store / "next-thread.md").exists()
    assert (new_workspace / ".codex-handoff" / "project.md").exists()
    assert (new_workspace / ".codex-handoff" / "next-thread.md").exists()

    state = json.loads((global_home / "background-sync.json").read_text(encoding="utf-8"))
    assert state["active_workspace"] == new_workspace.as_posix()
    assert state["last_error"] is None


def test_background_sync_exits_when_another_instance_is_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    global_home = tmp_path / ".codex-handoff"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (codex_home / ".codex-global-state.json").write_text(
        json.dumps({"active-workspace-roots": [str(workspace)]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_HANDOFF_HOME", str(global_home))

    prepared: list[Path] = []
    monkeypatch.setattr(daemon, "prepare_handoff", lambda path: prepared.append(path) or (None, ""))
    monkeypatch.setattr(daemon, "try_acquire_background_lock", lambda app_home: None)

    daemon.run_background_sync(once=True)

    assert prepared == []
    assert not (global_home / "background-sync.json").exists()
