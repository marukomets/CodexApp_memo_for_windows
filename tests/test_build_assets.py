from __future__ import annotations

from pathlib import Path

from codex_handoff.build_assets import (
    build_icon_bytes,
    build_version_info_text,
    versioned_executable_name,
    write_build_assets,
)


def test_build_icon_bytes_returns_ico_header() -> None:
    icon = build_icon_bytes()
    assert icon[:4] == b"\x00\x00\x01\x00"
    assert len(icon) > 100


def test_write_build_assets_creates_icon_and_version_file(tmp_path: Path) -> None:
    icon_path, version_path = write_build_assets(tmp_path)
    assert icon_path.exists()
    assert version_path.exists()
    assert icon_path.read_bytes()[:4] == b"\x00\x00\x01\x00"
    text = version_path.read_text(encoding="utf-8")
    assert "Codex Handoff Setup" in text
    assert "ProductVersion" in text


def test_build_version_info_text_accepts_custom_names() -> None:
    text = build_version_info_text(
        internal_name="CodexHandoffSetup-0.5.2",
        original_filename="CodexHandoffSetup-0.5.2.exe",
    )

    assert "InternalName', 'CodexHandoffSetup-0.5.2'" in text
    assert "OriginalFilename', 'CodexHandoffSetup-0.5.2.exe'" in text


def test_versioned_executable_name_uses_current_version() -> None:
    assert versioned_executable_name(version="0.6.9") == "CodexHandoffSetup-0.6.9.exe"
    assert versioned_executable_name("CustomSetup", version="v1.2.3") == "CustomSetup-1.2.3.exe"
