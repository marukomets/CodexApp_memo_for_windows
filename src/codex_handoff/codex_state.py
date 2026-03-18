from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


GLOBAL_STATE_FILE_NAME = ".codex-global-state.json"


@dataclass(slots=True)
class CodexWorkspaceState:
    active_workspace_roots: list[Path] = field(default_factory=list)
    saved_workspace_roots: list[Path] = field(default_factory=list)

    def preferred_root(self) -> Path | None:
        ordered = self.candidate_roots()
        return ordered[0] if ordered else None

    def candidate_roots(self) -> list[Path]:
        ordered: list[Path] = []
        seen: set[str] = set()
        for path in [*self.active_workspace_roots, *self.saved_workspace_roots]:
            key = path.as_posix().lower()
            if key in seen:
                continue
            ordered.append(path)
            seen.add(key)
        return ordered


def load_codex_workspace_state(codex_home: Path) -> CodexWorkspaceState:
    state_file = codex_home / GLOBAL_STATE_FILE_NAME
    if not state_file.exists():
        return CodexWorkspaceState()

    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return CodexWorkspaceState()

    return CodexWorkspaceState(
        active_workspace_roots=_read_workspace_roots(payload.get("active-workspace-roots")),
        saved_workspace_roots=_read_workspace_roots(payload.get("electron-saved-workspace-roots")),
    )


def _read_workspace_roots(value: object) -> list[Path]:
    if not isinstance(value, list):
        return []

    roots: list[Path] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            continue
        path = Path(item).expanduser()
        if path.exists():
            roots.append(path.resolve())
    return roots
