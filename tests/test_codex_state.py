from __future__ import annotations

import json
from pathlib import Path

from codex_handoff.codex_state import load_codex_workspace_state


def test_load_codex_workspace_state_prefers_active_and_dedupes(tmp_path: Path) -> None:
    active = tmp_path / "active-project"
    saved = tmp_path / "saved-project"
    active.mkdir()
    saved.mkdir()

    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / ".codex-global-state.json").write_text(
        json.dumps(
            {
                "active-workspace-roots": [str(active)],
                "electron-saved-workspace-roots": [str(saved), str(active)],
            }
        ),
        encoding="utf-8",
    )

    state = load_codex_workspace_state(codex_home)

    assert state.preferred_root() == active.resolve()
    assert state.candidate_roots() == [active.resolve(), saved.resolve()]


def test_load_codex_workspace_state_ignores_missing_paths(tmp_path: Path) -> None:
    existing = tmp_path / "existing-project"
    existing.mkdir()

    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / ".codex-global-state.json").write_text(
        json.dumps(
            {
                "active-workspace-roots": [str(tmp_path / "missing-project")],
                "electron-saved-workspace-roots": [str(existing)],
            }
        ),
        encoding="utf-8",
    )

    state = load_codex_workspace_state(codex_home)

    assert state.preferred_root() == existing.resolve()
    assert state.candidate_roots() == [existing.resolve()]
