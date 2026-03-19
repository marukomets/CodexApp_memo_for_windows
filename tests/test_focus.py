from __future__ import annotations

from codex_handoff.focus import select_user_facing_changed_files
from codex_handoff.models import FileChange


def test_select_user_facing_changed_files_keeps_real_html_files() -> None:
    changed_files = [
        FileChange(path="docs/help.html", status="M"),
        FileChange(path=".codex-handoff/next-thread.md", status="M"),
    ]

    selected = select_user_facing_changed_files(changed_files, limit=3)

    assert [item.path for item in selected] == ["docs/help.html"]


def test_select_user_facing_changed_files_filters_known_generated_build_assets() -> None:
    changed_files = [
        FileChange(path="build-assets/CodexHandoffBackground.zip", status="M"),
        FileChange(path="build-assets/version_info.txt", status="M"),
        FileChange(path="src/app.py", status="M"),
    ]

    selected = select_user_facing_changed_files(changed_files, limit=3)

    assert [item.path for item in selected] == ["src/app.py"]
