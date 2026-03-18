from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk

from codex_handoff.bootstrap import has_agents_block
from codex_handoff.codex_state import CodexWorkspaceState, load_codex_workspace_state
from codex_handoff.daemon import run_background_sync
from codex_handoff.installer import (
    can_self_install,
    install_background_startup_shortcut,
    install_current_app,
    installed_background_exe_path,
    is_app_installed,
    is_background_startup_installed,
    recommended_install_dir,
    remove_background_startup_shortcut,
    stop_managed_processes,
    launch_background_sync,
)
from codex_handoff.paths import GlobalPaths, get_global_paths
from codex_handoff.service import setup_global, uninstall_global_agents


@dataclass(slots=True)
class SetupViewState:
    screen: str
    install_status: str
    automation_status: str
    install_button_text: str
    can_run_setup: bool


def main() -> None:
    if "--self-check" in sys.argv:
        print("gui-ok")
        return
    if "--background" in sys.argv:
        run_background_sync()
        return

    app = CodexHandoffDesktop()
    app.mainloop()


class CodexHandoffDesktop(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Codex Handoff")
        self.geometry("860x620")
        self.minsize(780, 560)

        self.global_paths = get_global_paths()
        self.workspace_state = load_codex_workspace_state(self.global_paths.codex_home)
        self.view_state: SetupViewState | None = None

        self.status_var = tk.StringVar(value="準備完了")
        self.install_status_var = tk.StringVar()
        self.automation_status_var = tk.StringVar()
        self.finish_summary_var = tk.StringVar()

        self.auto_loading_var = tk.BooleanVar(value=True)
        self.background_sync_var = tk.BooleanVar(value=True)
        self.create_desktop_shortcut_var = tk.BooleanVar(value=True)
        self.create_start_menu_shortcut_var = tk.BooleanVar(value=True)

        self.screen_container: ttk.Frame | None = None
        self.screens: dict[str, ttk.Frame] = {}
        self.current_screen_name: str | None = None
        self.install_button: ttk.Button | None = None
        self.run_setup_button: ttk.Button | None = None

        self._build_ui()
        self.refresh_state(auto_show=True)

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=20)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container)
        header.pack(fill="x")
        ttk.Label(header, text="Codex Handoff", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text="初回セットアップだけを行う companion app です。以後は GUI を開かなくても、active workspace の handoff を自動更新します。",
            wraplength=780,
        ).pack(anchor="w", pady=(4, 0))

        self.screen_container = ttk.Frame(container)
        self.screen_container.pack(fill="both", expand=True, pady=(20, 16))

        self._build_install_screen()
        self._build_configure_screen()
        self._build_finish_screen()

        footer = ttk.Frame(container)
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status_var).pack(anchor="w")

    def _build_install_screen(self) -> None:
        assert self.screen_container is not None
        frame = ttk.Frame(self.screen_container)
        self.screens["install"] = frame

        ttk.Label(frame, text="Step 1: Install app", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="この実行ファイルを %LOCALAPPDATA%\\CodexHandoff にコピーします。以後の更新はここに上書きされます。",
            wraplength=760,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, textvariable=self.install_status_var, wraplength=760, justify="left").pack(anchor="w", pady=(14, 0))

        shortcuts = ttk.Frame(frame)
        shortcuts.pack(anchor="w", pady=(18, 0))
        ttk.Checkbutton(shortcuts, text="デスクトップにショートカットを作成", variable=self.create_desktop_shortcut_var).pack(side="left")
        ttk.Checkbutton(
            shortcuts,
            text="スタートメニューにショートカットを作成",
            variable=self.create_start_menu_shortcut_var,
        ).pack(side="left", padx=(12, 0))

        actions = ttk.Frame(frame)
        actions.pack(anchor="w", pady=(24, 0))
        self.install_button = ttk.Button(actions, text="Install to LocalAppData", command=self.install_app_to_local_appdata)
        self.install_button.pack(side="left")

    def _build_configure_screen(self) -> None:
        assert self.screen_container is not None
        frame = ttk.Frame(self.screen_container)
        self.screens["configure"] = frame

        ttk.Label(frame, text="Step 2: Enable automation", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="ここで machine 単位の自動設定を行います。完了後は新しいプロジェクトでも自動追従します。",
            wraplength=760,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, textvariable=self.automation_status_var, wraplength=760, justify="left").pack(anchor="w", pady=(14, 0))

        ttk.Checkbutton(
            frame,
            text="~/.codex/AGENTS.md に automatic loading を設定する",
            variable=self.auto_loading_var,
        ).pack(anchor="w", pady=(18, 0))
        ttk.Checkbutton(
            frame,
            text="サインイン時に background sync を自動起動する",
            variable=self.background_sync_var,
        ).pack(anchor="w", pady=(8, 0))

        ttk.Label(
            frame,
            text=(
                "Automatic loading を有効にすると ~/.codex/AGENTS.md の codex-handoff 管理ブロックを追加または更新します。"
                "既存ファイルがある場合は必ずバックアップを作成し、管理ブロック以外は置き換えません。"
            ),
            wraplength=760,
            justify="left",
        ).pack(anchor="w", pady=(18, 0))

        actions = ttk.Frame(frame)
        actions.pack(anchor="w", pady=(24, 0))
        self.run_setup_button = ttk.Button(actions, text="Apply setup", command=self.run_guided_setup)
        self.run_setup_button.pack(side="left")

    def _build_finish_screen(self) -> None:
        assert self.screen_container is not None
        frame = ttk.Frame(self.screen_container)
        self.screens["finish"] = frame

        ttk.Label(frame, text="Done", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="セットアップは完了です。以後は GUI を開かなくても background sync が active workspace の handoff を自動更新します。",
            wraplength=760,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, textvariable=self.finish_summary_var, wraplength=760, justify="left").pack(anchor="w", pady=(16, 0))

        actions = ttk.Frame(frame)
        actions.pack(anchor="w", pady=(24, 0))
        ttk.Button(actions, text="閉じる", command=self.destroy).pack(side="left")

    def refresh_state(self, auto_show: bool = False) -> None:
        self.global_paths = get_global_paths()
        self.workspace_state = load_codex_workspace_state(self.global_paths.codex_home)

        agents_enabled = self.global_paths.global_agents_file.exists() and has_agents_block(self.global_paths.global_agents_file)
        background_enabled = is_background_startup_installed()
        installed = is_app_installed()
        setup_started = self.global_paths.app_home.exists()

        self.view_state = build_setup_view_state(
            can_install=can_self_install(),
            installed=installed,
            setup_started=setup_started,
            agents_enabled=agents_enabled,
            background_enabled=background_enabled,
            desired_auto_loading=self.auto_loading_var.get(),
            desired_background_sync=self.background_sync_var.get(),
        )

        self.install_status_var.set(
            render_install_status(
                installed=installed,
            )
        )
        self.automation_status_var.set(
            render_automation_status(
                global_paths=self.global_paths,
                agents_enabled=agents_enabled,
                background_enabled=background_enabled,
            )
        )
        self.finish_summary_var.set(
            render_finish_summary(
                global_paths=self.global_paths,
                workspace_state=self.workspace_state,
                agents_enabled=agents_enabled,
                background_enabled=background_enabled,
            )
        )

        if self.install_button is not None:
            self.install_button.configure(text=self.view_state.install_button_text)
        if self.run_setup_button is not None:
            set_widget_enabled(self.run_setup_button, self.view_state.can_run_setup)

        if auto_show or self.current_screen_name is None:
            self.show_screen(self.view_state.screen)
        self.status_var.set("状態を更新しました")

    def show_screen(self, screen_name: str) -> None:
        for name, frame in self.screens.items():
            if name == screen_name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        self.current_screen_name = screen_name

    def install_app_to_local_appdata(self) -> None:
        if not can_self_install():
            messagebox.showinfo(
                "Codex Handoff",
                "自己インストールは配布 exe から起動した場合のみ使えます。開発中はビルド済み exe から試してください。",
            )
            return

        confirmed = messagebox.askyesno(
            "Install app",
            f"{recommended_install_dir()} にアプリ本体をコピーします。\n"
            "古いバージョンが動いている場合は停止してから上書きします。\n\n"
            "続行しますか？",
        )
        if not confirmed:
            return

        result = install_current_app(
            create_desktop_shortcut=self.create_desktop_shortcut_var.get(),
            create_start_menu_shortcut=self.create_start_menu_shortcut_var.get(),
        )
        self.refresh_state()
        self.show_screen("configure")
        messagebox.showinfo(
            "Codex Handoff",
            f"Installed to:\n{result.installed_exe}\n\n続けて Step 2 のセットアップを実行してください。",
        )

    def run_guided_setup(self) -> None:
        install_auto = self.auto_loading_var.get()
        install_background = self.background_sync_var.get()

        if install_auto:
            confirmed = messagebox.askyesno(
                "Apply setup",
                "automatic loading を有効にすると ~/.codex/AGENTS.md の codex-handoff 管理ブロックを追加または更新します。\n"
                "既存ファイルがある場合はバックアップを作成します。\n\n"
                "続行しますか？",
            )
            if not confirmed:
                return

        try:
            if install_auto:
                global_paths, changed, backup_path = setup_global(install_global_agents=True)
            else:
                global_paths, changed, backup_path = uninstall_global_agents()

            if install_background:
                target_exe = self._background_target_exe()
                if target_exe is None or not target_exe.exists():
                    raise RuntimeError("background sync 用の実行ファイルが見つかりません。Step 1 の再インストールをやり直してください。")
                stop_managed_processes(recommended_install_dir())
                install_background_startup_shortcut(target_exe)
                launch_background_sync(target_exe)
            else:
                remove_background_startup_shortcut()
                stop_managed_processes(recommended_install_dir())
        except Exception as exc:
            messagebox.showerror("Codex Handoff", str(exc))
            self.refresh_state()
            return

        self.refresh_state()
        self.show_screen("finish")

        if install_auto:
            auto_text = "automatic loading を有効化しました。" if changed else "automatic loading は既に最新でした。"
        else:
            auto_text = "automatic loading を無効化しました。"
        background_text = "background sync を起動しました。" if install_background else "background sync を停止しました。"

        if backup_path is not None:
            backup_text = f"\nBackup: {backup_path}"
        else:
            backup_text = ""

        messagebox.showinfo(
            "Codex Handoff",
            f"セットアップが完了しました。\n\n{auto_text}\n{background_text}\nGlobal store: {global_paths.app_home}{backup_text}",
        )

    def _background_target_exe(self) -> Path | None:
        target = installed_background_exe_path()
        return target if target.exists() else None


def set_widget_enabled(widget: ttk.Widget, enabled: bool) -> None:
    if enabled:
        widget.state(["!disabled"])
    else:
        widget.state(["disabled"])


def build_setup_view_state(
    *,
    can_install: bool,
    installed: bool,
    setup_started: bool,
    agents_enabled: bool,
    background_enabled: bool,
    desired_auto_loading: bool,
    desired_background_sync: bool,
) -> SetupViewState:
    automation_complete = (not desired_auto_loading or agents_enabled) and (
        not desired_background_sync or background_enabled
    )

    if can_install:
        screen = "install"
    elif not setup_started or not automation_complete:
        screen = "configure"
    else:
        screen = "finish"

    if installed:
        install_status = "Status: installed in LocalAppData."
        install_button_text = "Install or update app"
    elif can_install:
        install_status = "Status: not installed yet."
        install_button_text = "Install or update app"
    else:
        install_status = "Status: development mode. LocalAppData install is optional."
        install_button_text = "Install or update app"

    automation_parts = [
        f"Automatic loading: {'enabled' if agents_enabled else 'not installed'}",
        f"Background sync at sign-in: {'enabled' if background_enabled else 'not installed'}",
    ]
    automation_status = "\n".join(automation_parts)

    return SetupViewState(
        screen=screen,
        install_status=install_status,
        automation_status=automation_status,
        install_button_text=install_button_text,
        can_run_setup=installed,
    )


def render_install_status(*, installed: bool) -> str:
    recommended = recommended_install_dir() / "CodexHandoff.exe"
    return "\n".join(
        [
            f"Current status: {'Installed' if installed else 'Not installed'}",
            f"Install location: {recommended}",
            "Step 1 is always safe. Existing files are stopped and then overwritten.",
        ]
    )


def render_automation_status(
    *,
    global_paths: GlobalPaths,
    agents_enabled: bool,
    background_enabled: bool,
) -> str:
    return "\n".join(
        [
            f"Global store: {global_paths.app_home}",
            f"Automatic loading: {'enabled' if agents_enabled else 'not installed'}",
            f"Background sync at sign-in: {'enabled' if background_enabled else 'not installed'}",
        ]
    )


def render_finish_summary(
    *,
    global_paths: GlobalPaths,
    workspace_state: CodexWorkspaceState,
    agents_enabled: bool,
    background_enabled: bool,
) -> str:
    preferred = workspace_state.preferred_root()
    workspace_text = str(preferred) if preferred is not None else "No active Codex workspace detected yet."
    return "\n".join(
        [
            f"Global store: {global_paths.app_home}",
            f"Current Codex workspace: {workspace_text}",
            f"Automatic loading: {'enabled' if agents_enabled else 'not installed'}",
            f"Background sync at sign-in: {'enabled' if background_enabled else 'not installed'}",
        ]
    )
