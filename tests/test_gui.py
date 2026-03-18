from __future__ import annotations

import subprocess
from pathlib import Path

from codex_handoff.gui import build_setup_view_state


def test_gui_self_check() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "scripts/launch_gui.py", "--self-check"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    assert result.stdout.strip() == "gui-ok"


def test_build_setup_view_state_requires_install_first() -> None:
    state = build_setup_view_state(
        can_install=True,
        installed=False,
        setup_started=False,
        agents_enabled=False,
        background_enabled=False,
        desired_auto_loading=True,
        desired_background_sync=True,
    )

    assert state.screen == "install"
    assert state.can_run_setup is False
    assert "not installed" in state.install_status


def test_build_setup_view_state_marks_completed_setup() -> None:
    state = build_setup_view_state(
        can_install=True,
        installed=True,
        setup_started=True,
        agents_enabled=True,
        background_enabled=True,
        desired_auto_loading=True,
        desired_background_sync=True,
    )

    assert state.screen == "install"
    assert "installed" in state.install_status


def test_build_setup_view_state_prefers_configure_when_automation_missing() -> None:
    state = build_setup_view_state(
        can_install=False,
        installed=True,
        setup_started=True,
        agents_enabled=False,
        background_enabled=False,
        desired_auto_loading=True,
        desired_background_sync=True,
    )

    assert state.screen == "configure"
    assert state.can_run_setup is True


def test_build_setup_view_state_stays_on_configure_when_background_missing() -> None:
    state = build_setup_view_state(
        can_install=False,
        installed=True,
        setup_started=True,
        agents_enabled=True,
        background_enabled=False,
        desired_auto_loading=True,
        desired_background_sync=True,
    )

    assert state.screen == "configure"


def test_build_setup_view_state_can_finish_when_user_does_not_want_background() -> None:
    state = build_setup_view_state(
        can_install=False,
        installed=True,
        setup_started=True,
        agents_enabled=True,
        background_enabled=False,
        desired_auto_loading=True,
        desired_background_sync=False,
    )

    assert state.screen == "finish"


def test_build_setup_view_state_always_starts_with_install_for_packaged_exe() -> None:
    state = build_setup_view_state(
        can_install=True,
        installed=True,
        setup_started=True,
        agents_enabled=True,
        background_enabled=True,
        desired_auto_loading=True,
        desired_background_sync=True,
    )

    assert state.screen == "install"
    assert state.install_button_text == "Install or update app"
