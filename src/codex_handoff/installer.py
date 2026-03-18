from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from codex_handoff.processes import hidden_subprocess_kwargs


APP_FILE_NAME = "CodexHandoff.exe"
APP_DIR_NAME = "CodexHandoff"
BACKGROUND_APP_FILE_NAME = "CodexHandoffBackground.exe"
BACKGROUND_DIR_NAME = "background"
BACKGROUND_ZIP_FILE_NAME = "CodexHandoffBackground.zip"


@dataclass(slots=True)
class InstallResult:
    installed_exe: Path
    installed_background_exe: Path | None
    desktop_shortcut: Path | None
    start_menu_shortcut: Path | None
    startup_shortcut: Path | None = None


def recommended_install_dir() -> Path:
    local_appdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local_appdata / APP_DIR_NAME


def current_app_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(sys.argv[0]).resolve()


def installed_app_path() -> Path:
    return recommended_install_dir() / APP_FILE_NAME


def installed_background_dir() -> Path:
    return recommended_install_dir() / BACKGROUND_DIR_NAME


def installed_background_exe_path() -> Path:
    return installed_background_dir() / BACKGROUND_APP_FILE_NAME


def is_app_installed() -> bool:
    return installed_app_path().exists()


def is_background_app_installed() -> bool:
    return installed_background_exe_path().exists()


def is_installed_in_recommended_dir() -> bool:
    current = current_app_path()
    return current.parent == recommended_install_dir()


def can_self_install() -> bool:
    current = current_app_path()
    return current.exists() and current.suffix.lower() == ".exe"


def install_current_app(
    create_desktop_shortcut: bool = True,
    create_start_menu_shortcut: bool = True,
) -> InstallResult:
    source = current_app_path()
    if not source.exists():
        raise FileNotFoundError(f"Executable not found: {source}")
    if source.suffix.lower() != ".exe":
        raise RuntimeError("Self-install is only available from the packaged Windows executable.")

    target_dir = recommended_install_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / APP_FILE_NAME
    stop_managed_processes(target_dir)
    if source.resolve() != target_path.resolve():
        shutil.copy2(source, target_path)
    installed_background_exe = _install_background_bundle(target_dir)

    desktop_shortcut = None
    start_menu_shortcut = None
    if create_desktop_shortcut:
        desktop_shortcut = desktop_shortcut_path()
        _create_shortcut(desktop_shortcut, target_path)
    if create_start_menu_shortcut:
        start_menu_shortcut = start_menu_shortcut_path()
        _create_shortcut(start_menu_shortcut, target_path)

    return InstallResult(
        installed_exe=target_path,
        installed_background_exe=installed_background_exe,
        desktop_shortcut=desktop_shortcut,
        start_menu_shortcut=start_menu_shortcut,
    )


def desktop_shortcut_path() -> Path:
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    return desktop / "Codex Handoff.lnk"


def start_menu_shortcut_path() -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    start_menu = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return start_menu / "Codex Handoff.lnk"


def startup_shortcut_path() -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    startup = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / "Codex Handoff Background Sync.lnk"


def is_background_startup_installed() -> bool:
    shortcut_path = startup_shortcut_path()
    if not shortcut_path.exists():
        return False

    target = shortcut_target_path(shortcut_path)
    if target is None:
        return False
    return target.resolve() == installed_background_exe_path().resolve()


def install_background_startup_shortcut(target_exe: Path | None = None) -> Path:
    target = (target_exe or installed_background_exe_path()).resolve()
    if target.suffix.lower() != ".exe":
        raise RuntimeError("Background startup is only available from the packaged Windows executable.")
    shortcut_path = startup_shortcut_path()
    _create_shortcut(shortcut_path, target)
    return shortcut_path


def remove_background_startup_shortcut() -> bool:
    shortcut_path = startup_shortcut_path()
    if not shortcut_path.exists():
        return False
    shortcut_path.unlink()
    return True


def launch_installed_app(installed_exe: Path) -> None:
    subprocess.Popen([str(installed_exe)], **hidden_subprocess_kwargs())


def launch_background_sync(target_exe: Path | None = None) -> None:
    target = (target_exe or installed_background_exe_path()).resolve()
    if not target.exists():
        raise FileNotFoundError(f"Background executable not found: {target}")

    subprocess.Popen([str(target)], cwd=str(target.parent), **hidden_subprocess_kwargs())


def stop_managed_processes(target_dir: Path | None = None, timeout_seconds: float = 5.0) -> None:
    target_root = (target_dir or recommended_install_dir()).resolve()
    candidate_paths = [
        target_root / APP_FILE_NAME,
        target_root / BACKGROUND_DIR_NAME / BACKGROUND_APP_FILE_NAME,
    ]
    existing_targets = [path for path in candidate_paths if path.exists()]
    if not existing_targets:
        return

    target_literals = ", ".join(f"'{_ps_path(path)}'" for path in existing_targets)
    script = (
        f"$targets = @({target_literals}); "
        f"$currentPid = {os.getpid()}; "
        "$procs = Get-CimInstance Win32_Process | "
        "Where-Object { $_.ExecutablePath -and ($targets -contains $_.ExecutablePath) -and $_.ProcessId -ne $currentPid }; "
        "$procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **hidden_subprocess_kwargs(),
    )

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not any(path.exists() and _is_process_running_for_path(path) for path in existing_targets):
            return
        time.sleep(0.2)


def _create_shortcut(shortcut_path: Path, target_path: Path, arguments: str = "") -> None:
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_arguments = arguments.replace("'", "''")
    script = (
        "$WshShell = New-Object -ComObject WScript.Shell; "
        f"$Shortcut = $WshShell.CreateShortcut('{_ps_path(shortcut_path)}'); "
        f"$Shortcut.TargetPath = '{_ps_path(target_path)}'; "
        f"$Shortcut.WorkingDirectory = '{_ps_path(target_path.parent)}'; "
        f"$Shortcut.Arguments = '{escaped_arguments}'; "
        f"$Shortcut.IconLocation = '{_ps_path(target_path)},0'; "
        "$Shortcut.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hidden_subprocess_kwargs(),
    )


def _ps_path(path: Path) -> str:
    return str(path).replace("'", "''")


def shortcut_target_path(shortcut_path: Path) -> Path | None:
    if not shortcut_path.exists():
        return None

    script = (
        "$WshShell = New-Object -ComObject WScript.Shell; "
        f"$Shortcut = $WshShell.CreateShortcut('{_ps_path(shortcut_path)}'); "
        "Write-Output $Shortcut.TargetPath"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **hidden_subprocess_kwargs(),
    )
    if result.returncode != 0:
        return None

    output = result.stdout.strip()
    return Path(output) if output else None


def _is_process_running_for_path(target_path: Path) -> bool:
    script = (
        f"$target = '{_ps_path(target_path.resolve())}'; "
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.ExecutablePath -eq $target } | "
        "Select-Object -First 1 -ExpandProperty ProcessId"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **hidden_subprocess_kwargs(),
    )
    return bool(result.stdout.strip())


def bundled_background_zip_path() -> Path:
    runtime_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return runtime_root / "build-assets" / BACKGROUND_ZIP_FILE_NAME


def _install_background_bundle(target_dir: Path) -> Path | None:
    zip_path = bundled_background_zip_path()
    if not zip_path.exists():
        return None

    background_dir = target_dir / BACKGROUND_DIR_NAME
    if background_dir.exists():
        shutil.rmtree(background_dir)
    background_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(background_dir)

    background_exe = background_dir / BACKGROUND_APP_FILE_NAME
    return background_exe if background_exe.exists() else None
