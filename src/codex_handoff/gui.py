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
    installed_cli_path,
    installed_background_exe_path,
    is_app_installed,
    is_background_startup_installed,
    is_install_dir_on_user_path,
    recommended_install_dir,
    remove_background_startup_shortcut,
    stop_managed_processes,
    launch_background_sync,
)
from codex_handoff.localization import detect_language, set_language, t
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
        self.language = detect_language()
        set_language(self.language)
        self.title("Codex Handoff")
        self.geometry("860x620")
        self.minsize(780, 560)

        self.global_paths = get_global_paths()
        self.workspace_state = load_codex_workspace_state(self.global_paths.codex_home)
        self.view_state: SetupViewState | None = None

        self.status_var = tk.StringVar(value=t("gui.status.ready", language=self.language))
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

    def _text(self, key: str, **kwargs: object) -> str:
        return t(key, language=self.language, **kwargs)

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=20)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container)
        header.pack(fill="x")
        ttk.Label(header, text="Codex Handoff", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text=self._text("gui.subtitle"),
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

        ttk.Label(frame, text=self._text("gui.step.install.title"), font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=self._text("gui.step.install.description"),
            wraplength=760,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, textvariable=self.install_status_var, wraplength=760, justify="left").pack(anchor="w", pady=(14, 0))

        shortcuts = ttk.Frame(frame)
        shortcuts.pack(anchor="w", pady=(18, 0))
        ttk.Checkbutton(shortcuts, text=self._text("gui.check.desktop_shortcut"), variable=self.create_desktop_shortcut_var).pack(side="left")
        ttk.Checkbutton(
            shortcuts,
            text=self._text("gui.check.start_menu_shortcut"),
            variable=self.create_start_menu_shortcut_var,
        ).pack(side="left", padx=(12, 0))

        actions = ttk.Frame(frame)
        actions.pack(anchor="w", pady=(24, 0))
        self.install_button = ttk.Button(actions, text=self._text("gui.button.install"), command=self.install_app_to_local_appdata)
        self.install_button.pack(side="left")

    def _build_configure_screen(self) -> None:
        assert self.screen_container is not None
        frame = ttk.Frame(self.screen_container)
        self.screens["configure"] = frame

        ttk.Label(frame, text=self._text("gui.step.configure.title"), font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=self._text("gui.step.configure.description"),
            wraplength=760,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, textvariable=self.automation_status_var, wraplength=760, justify="left").pack(anchor="w", pady=(14, 0))

        ttk.Checkbutton(
            frame,
            text=self._text("gui.check.auto_loading"),
            variable=self.auto_loading_var,
        ).pack(anchor="w", pady=(18, 0))
        ttk.Checkbutton(
            frame,
            text=self._text("gui.check.background_sync"),
            variable=self.background_sync_var,
        ).pack(anchor="w", pady=(8, 0))

        ttk.Label(
            frame,
            text=self._text("gui.info.setup"),
            wraplength=760,
            justify="left",
        ).pack(anchor="w", pady=(18, 0))

        actions = ttk.Frame(frame)
        actions.pack(anchor="w", pady=(24, 0))
        self.run_setup_button = ttk.Button(actions, text=self._text("gui.button.apply"), command=self.run_guided_setup)
        self.run_setup_button.pack(side="left")

    def _build_finish_screen(self) -> None:
        assert self.screen_container is not None
        frame = ttk.Frame(self.screen_container)
        self.screens["finish"] = frame

        ttk.Label(frame, text=self._text("gui.step.done.title"), font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=self._text("gui.step.done.description"),
            wraplength=760,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, textvariable=self.finish_summary_var, wraplength=760, justify="left").pack(anchor="w", pady=(16, 0))

        actions = ttk.Frame(frame)
        actions.pack(anchor="w", pady=(24, 0))
        ttk.Button(actions, text=self._text("gui.button.close"), command=self.destroy).pack(side="left")

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
            language=self.language,
        )

        self.install_status_var.set(render_install_status(installed=installed, language=self.language))
        self.automation_status_var.set(
            render_automation_status(
                global_paths=self.global_paths,
                agents_enabled=agents_enabled,
                background_enabled=background_enabled,
                language=self.language,
            )
        )
        self.finish_summary_var.set(
            render_finish_summary(
                global_paths=self.global_paths,
                workspace_state=self.workspace_state,
                agents_enabled=agents_enabled,
                background_enabled=background_enabled,
                language=self.language,
            )
        )

        if self.install_button is not None:
            self.install_button.configure(text=self.view_state.install_button_text)
        if self.run_setup_button is not None:
            set_widget_enabled(self.run_setup_button, self.view_state.can_run_setup)

        if auto_show or self.current_screen_name is None:
            self.show_screen(self.view_state.screen)
        self.status_var.set(self._text("gui.status.updated"))

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
                self._text("gui.message.install.title"),
                self._text("gui.message.install.unavailable"),
            )
            return

        confirmed = messagebox.askyesno(
            self._text("gui.message.install.title"),
            self._text("gui.message.install.confirm", path=recommended_install_dir()),
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
            self._text("gui.message.install.title"),
            self._text(
                "gui.message.install.success",
                path=result.installed_exe,
                cli_path=result.installed_cli_exe or installed_cli_path(),
            ),
        )

    def run_guided_setup(self) -> None:
        install_auto = self.auto_loading_var.get()
        install_background = self.background_sync_var.get()

        if install_auto:
            confirmed = messagebox.askyesno(
                self._text("gui.button.apply"),
                self._text("gui.message.setup.confirm"),
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
                    raise RuntimeError(self._text("gui.error.background_missing"))
                stop_managed_processes(recommended_install_dir())
                install_background_startup_shortcut(target_exe)
                launch_background_sync(target_exe)
            else:
                remove_background_startup_shortcut()
                stop_managed_processes(recommended_install_dir())
        except Exception as exc:
            messagebox.showerror(self._text("gui.message.setup.error"), str(exc))
            self.refresh_state()
            return

        self.refresh_state()
        self.show_screen("finish")

        if install_auto:
            auto_text = self._text("gui.message.setup.auto_enabled") if changed else self._text("gui.message.setup.auto_current")
        else:
            auto_text = self._text("gui.message.setup.auto_disabled")
        background_text = self._text("gui.message.setup.background_started") if install_background else self._text("gui.message.setup.background_stopped")

        if backup_path is not None:
            backup_text = f"\n{self._text('gui.message.setup.backup')}: {backup_path}"
        else:
            backup_text = ""

        messagebox.showinfo(
            self._text("gui.message.setup.title"),
            (
                f"{self._text('gui.message.setup.done')}\n\n"
                f"{auto_text}\n"
                f"{background_text}\n"
                f"{self._text('gui.message.setup.global_store')}: {global_paths.app_home}{backup_text}"
            ),
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
    language: str | None = None,
) -> SetupViewState:
    lang = language or detect_language()
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
        install_status = t("gui.install.status.installed", language=lang)
        install_button_text = t("gui.button.install", language=lang)
    elif can_install:
        install_status = t("gui.install.status.not_installed", language=lang)
        install_button_text = t("gui.button.install", language=lang)
    else:
        install_status = t("gui.install.status.dev_mode", language=lang)
        install_button_text = t("gui.button.install", language=lang)

    automation_parts = [
        t("gui.automation.auto_loading.enabled" if agents_enabled else "gui.automation.auto_loading.not_installed", language=lang),
        t("gui.automation.background_sync.enabled" if background_enabled else "gui.automation.background_sync.not_installed", language=lang),
    ]
    automation_status = "\n".join(automation_parts)

    return SetupViewState(
        screen=screen,
        install_status=install_status,
        automation_status=automation_status,
        install_button_text=install_button_text,
        can_run_setup=installed,
    )


def render_install_status(*, installed: bool, language: str | None = None) -> str:
    recommended = recommended_install_dir() / "CodexHandoff.exe"
    cli_path = installed_cli_path()
    lang = language or detect_language()
    path_text = t(
        "gui.install.path.present" if is_install_dir_on_user_path() else "gui.install.path.missing",
        language=lang,
    )
    return "\n".join(
        [
            t("gui.install.status.installed" if installed else "gui.install.status.not_installed", language=lang),
            f"{t('gui.install.location', language=lang)}: {recommended}",
            f"{t('gui.install.cli_location', language=lang)}: {cli_path}",
            path_text,
            t("gui.install.safe", language=lang),
        ]
    )


def render_automation_status(
    *,
    global_paths: GlobalPaths,
    agents_enabled: bool,
    background_enabled: bool,
    language: str | None = None,
) -> str:
    lang = language or detect_language()
    return "\n".join(
        [
            f"{t('gui.automation.global_store', language=lang)}: {global_paths.app_home}",
            t("gui.automation.auto_loading.enabled" if agents_enabled else "gui.automation.auto_loading.not_installed", language=lang),
            t("gui.automation.background_sync.enabled" if background_enabled else "gui.automation.background_sync.not_installed", language=lang),
        ]
    )


def render_finish_summary(
    *,
    global_paths: GlobalPaths,
    workspace_state: CodexWorkspaceState,
    agents_enabled: bool,
    background_enabled: bool,
    language: str | None = None,
) -> str:
    lang = language or detect_language()
    preferred = workspace_state.preferred_root()
    workspace_text = str(preferred) if preferred is not None else t("gui.finish.no_workspace", language=lang)
    return "\n".join(
        [
            f"{t('gui.finish.global_store', language=lang)}: {global_paths.app_home}",
            f"{t('gui.finish.workspace', language=lang)}: {workspace_text}",
            t("gui.automation.auto_loading.enabled" if agents_enabled else "gui.automation.auto_loading.not_installed", language=lang),
            t("gui.automation.background_sync.enabled" if background_enabled else "gui.automation.background_sync.not_installed", language=lang),
            t("gui.finish.restart_hint", language=lang),
        ]
    )
