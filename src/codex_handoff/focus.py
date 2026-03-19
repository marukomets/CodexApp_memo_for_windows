from __future__ import annotations

from codex_handoff.models import FileChange


GENERATED_CHANGE_PREFIXES = (
    "build-assets/background-build/",
    "build-assets/background-dist/",
    "build/",
    "dist/",
)

GENERATED_CHANGE_PATHS = (
    "build-assets/codex-handoff.ico",
    "build-assets/CodexHandoffBackground.zip",
    "build-assets/version_info.txt",
)


def select_user_facing_changed_files(changed_files: list[FileChange], limit: int) -> list[FileChange]:
    primary = [item for item in changed_files if _is_primary_focus_path(item.path)]
    if primary:
        return primary[:limit]

    secondary = [item for item in changed_files if item.path.startswith(".codex-handoff/")]
    if secondary:
        return secondary[:limit]

    return changed_files[:limit]


def _is_primary_focus_path(path: str) -> bool:
    if path.startswith(".codex-handoff/"):
        return False
    if _is_generated_build_output(path):
        return False
    return True


def _is_generated_build_output(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in GENERATED_CHANGE_PREFIXES):
        return True
    return path in GENERATED_CHANGE_PATHS
