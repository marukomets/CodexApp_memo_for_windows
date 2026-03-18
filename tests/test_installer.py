from __future__ import annotations

import zipfile
from pathlib import Path

import codex_handoff.installer as installer


def test_install_current_app_copies_executable_without_shortcuts(
    tmp_path: Path, monkeypatch
) -> None:
    source_exe = tmp_path / "Downloads" / "CodexHandoffSetup.exe"
    source_exe.parent.mkdir(parents=True, exist_ok=True)
    source_exe.write_bytes(b"fake-exe")

    monkeypatch.setattr(installer, "current_app_path", lambda: source_exe)
    monkeypatch.setattr(installer, "recommended_install_dir", lambda: tmp_path / "LocalAppData" / "CodexHandoff")

    result = installer.install_current_app(
        create_desktop_shortcut=False,
        create_start_menu_shortcut=False,
    )

    assert result.installed_exe == tmp_path / "LocalAppData" / "CodexHandoff" / "CodexHandoff.exe"
    assert result.installed_exe.read_bytes() == b"fake-exe"
    assert result.desktop_shortcut is None
    assert result.start_menu_shortcut is None


def test_install_current_app_extracts_background_bundle(tmp_path: Path, monkeypatch) -> None:
    source_exe = tmp_path / "Downloads" / "CodexHandoffSetup.exe"
    source_exe.parent.mkdir(parents=True, exist_ok=True)
    source_exe.write_bytes(b"fake-exe")

    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()
    background_exe = bundle_root / "CodexHandoffBackground.exe"
    background_exe.write_bytes(b"fake-background-exe")
    (bundle_root / "support.dll").write_bytes(b"fake-support")

    zip_path = tmp_path / "CodexHandoffBackground.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(background_exe, background_exe.name)
        archive.write(bundle_root / "support.dll", "support.dll")

    monkeypatch.setattr(installer, "current_app_path", lambda: source_exe)
    monkeypatch.setattr(installer, "recommended_install_dir", lambda: tmp_path / "LocalAppData" / "CodexHandoff")
    monkeypatch.setattr(installer, "bundled_background_zip_path", lambda: zip_path)

    result = installer.install_current_app(
        create_desktop_shortcut=False,
        create_start_menu_shortcut=False,
    )

    assert result.installed_background_exe == tmp_path / "LocalAppData" / "CodexHandoff" / "background" / "CodexHandoffBackground.exe"
    assert result.installed_background_exe.read_bytes() == b"fake-background-exe"
    assert (result.installed_background_exe.parent / "support.dll").exists()


def test_can_self_install_requires_packaged_exe(tmp_path: Path, monkeypatch) -> None:
    source_py = tmp_path / "scripts" / "launch_gui.py"
    source_py.parent.mkdir(parents=True, exist_ok=True)
    source_py.write_text("print('x')", encoding="utf-8")

    monkeypatch.setattr(installer, "current_app_path", lambda: source_py)

    assert installer.can_self_install() is False


def test_is_app_installed_checks_recommended_target(tmp_path: Path, monkeypatch) -> None:
    target_dir = tmp_path / "LocalAppData" / "CodexHandoff"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_exe = target_dir / "CodexHandoff.exe"

    monkeypatch.setattr(installer, "recommended_install_dir", lambda: target_dir)
    assert installer.is_app_installed() is False

    target_exe.write_bytes(b"fake-exe")
    assert installer.installed_app_path() == target_exe
    assert installer.is_app_installed() is True


def test_background_startup_shortcut_detection(tmp_path: Path, monkeypatch) -> None:
    startup_dir = tmp_path / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setattr(
        installer,
        "installed_background_exe_path",
        lambda: tmp_path / "LocalAppData" / "CodexHandoff" / "background" / "CodexHandoffBackground.exe",
    )

    assert installer.is_background_startup_installed() is False

    shortcut = installer.startup_shortcut_path()
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    shortcut.write_bytes(b"fake-shortcut")
    monkeypatch.setattr(installer, "shortcut_target_path", lambda path: tmp_path / "different.exe")

    assert installer.is_background_startup_installed() is False

    monkeypatch.setattr(installer, "shortcut_target_path", lambda path: installer.installed_background_exe_path())

    assert installer.is_background_startup_installed() is True
    assert installer.remove_background_startup_shortcut() is True
    assert not shortcut.exists()
