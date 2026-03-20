from __future__ import annotations

import locale
import os
from typing import Literal

Language = Literal["ja", "en"]

TEXTS: dict[str, tuple[str, str]] = {
    "bootstrap.prepare_first": (
        "- ローカル作業を始める前に、カレントディレクトリで `codex-handoff prepare --stdout` を試し、その出力を前提として扱う。",
        "- Before starting local work, try `codex-handoff prepare --stdout` in the current directory and treat that output as the starting point.",
    ),
    "bootstrap.user_memory": (
        "- 共通ユーザー設定があれば、まず `~/.codex-handoff/user-memory.json` を読んで前提に含める。",
        "- If shared user settings exist, read `~/.codex-handoff/user-memory.json` first and include them as assumptions.",
    ),
    "bootstrap.project_scope": (
        "- `codex-handoff` は現在の作業ディレクトリからプロジェクトを自動判定し、`~/.codex-handoff/projects/...` を正本として再利用しつつ、リポジトリ内 `.codex-handoff/` に同期ミラーを置く前提で進める。",
        "- `codex-handoff` auto-detects the project from the current working directory, reuses `~/.codex-handoff/projects/...` as the source of truth, and keeps a sync mirror in the repository-local `.codex-handoff/` directory.",
    ),
    "bootstrap.read_docs": (
        "- 手動で前スレッドを説明し直させず、まずリポジトリ内 `.codex-handoff/project.md`、`.codex-handoff/decisions.md`、`.codex-handoff/tasks.md`、`.codex-handoff/memory.json`、`.codex-handoff/next-thread.md` を読む。",
        "- Do not ask the user to restate the previous thread manually; read `.codex-handoff/project.md`, `.codex-handoff/decisions.md`, `.codex-handoff/tasks.md`, `.codex-handoff/memory.json`, and `.codex-handoff/next-thread.md` first.",
    ),
    "bootstrap.memory_contract": (
        "- `memory.json` は構造化メモリの正本で、ユーザーの思想・仕様・制約・採用判断と、進捗・検証・コミット・変更ファイルに加えて、現在の主題・注目パス・次アクションを分けて保持する前提で扱う。",
        "- `memory.json` is the source of truth for structured memory. Treat it as the place where user preferences, specs, constraints, decisions, progress, verification, commits, changed files, current focus, important paths, and next actions are kept separately.",
    ),
    "bootstrap.fallback": (
        "- `codex-handoff` が利用できない場合だけ、その旨を短く伝えて通常どおり進める。",
        "- Only if `codex-handoff` is unavailable, say so briefly and continue normally.",
    ),
    "cli.help.version": ("インストール済みの codex-handoff のバージョンを表示して終了する。", "Show the installed codex-handoff version and exit."),
    "doctor.global_home": ("global store: {path}", "Global store: {path}"),
    "doctor.user_memory": ("user memory: {path}", "User memory: {path}"),
    "doctor.project_store": ("current project store: {path}", "Current project store: {path}"),
    "doctor.local_store": ("local mirror: {path}", "Local mirror: {path}"),
    "doctor.local_imported": ("ローカル `.codex-handoff` の変更を global store に取り込みました。", "Imported local `.codex-handoff` changes into the global store."),
    "doctor.global_agents.block_present": ("global AGENTS block: {path}", "Global AGENTS block: {path}"),
    "doctor.global_agents.block_missing": ("{path} に codex-handoff ブロックがありません。`codex-handoff setup --install-global-agents` を実行してください。", "No codex-handoff block was found in {path}. Run `codex-handoff setup --install-global-agents`."),
    "doctor.global_agents.file_missing": ("{path} がありません。`codex-handoff setup --install-global-agents` を実行してください。", "{path} does not exist. Run `codex-handoff setup --install-global-agents`."),
    "doctor.config.exists": ("project config が存在します。", "The project config exists."),
    "doctor.config.valid": ("設定値は妥当です。", "The configuration values are valid."),
    "doctor.config.missing": ("project config がありません。", "The project config is missing."),
    "doctor.file.exists": ("{path} が存在します。", "{path} exists."),
    "doctor.file.missing": ("{path} がありません。", "{path} is missing."),
    "doctor.encoding.invalid": ("{path} は UTF-8 で読めません。", "{path} could not be read as UTF-8."),
    "doctor.encoding.bom": ("{path} に UTF-8 BOM が含まれています。", "{path} contains a UTF-8 BOM."),
    "doctor.encoding.utf8": ("{path} は UTF-8 BOM なしです。", "{path} is UTF-8 without a BOM."),
    "doctor.git.unavailable": ("Git が見つかりません。手動メモのみで運用します。", "Git is unavailable. The workflow will use manual notes only."),
    "doctor.git.not_repo": ("このディレクトリは Git リポジトリではありません。パス単位の project store として扱います。", "This directory is not a Git repository. It will be treated as a path-based project store."),
    "doctor.git.repo": ("Git リポジトリを検出しました。ブランチ: {branch}", "Detected a Git repository. Branch: {branch}"),
    "cli.setup.install_global_agents": ("~/.codex/AGENTS.md に codex-handoff ブロックを追加または更新する", "Add or update the codex-handoff block in ~/.codex/AGENTS.md"),
    "cli.setup.fail": ("setup に失敗しました: {exc}", "setup failed: {exc}"),
    "cli.setup.global_store": ("global store: {path}", "Global store: {path}"),
    "cli.setup.global_agents_snippet": ("global AGENTS snippet: {path}", "Global AGENTS snippet: {path}"),
    "cli.setup.unchanged": ("global AGENTS は未変更です。自動読込を有効にするには `codex-handoff setup --install-global-agents` を実行してください。", "Global AGENTS was unchanged. Run `codex-handoff setup --install-global-agents` to enable automatic loading."),
    "cli.setup.backup": ("global AGENTS のバックアップを作成しました: {path}", "Created a backup of global AGENTS: {path}"),
    "cli.setup.updated": ("global AGENTS を更新しました: {path}", "Updated global AGENTS: {path}"),
    "cli.setup.up_to_date": ("global AGENTS は既に最新です: {path}", "Global AGENTS is already up to date: {path}"),
    "cli.init.fail": ("init に失敗しました: {exc}", "init failed: {exc}"),
    "cli.init.project_store": ("project store: {path}", "Project store: {path}"),
    "cli.init.migrated": ("ローカル `.codex-handoff` の変更を global store に取り込みました。", "Imported local `.codex-handoff` changes into the global store."),
    "cli.init.created": ("作成:", "Created:"),
    "cli.init.preserved": ("保持:", "Preserved:"),
    "cli.capture.note": ("tasks.md の末尾に追加する 1 行メモ", "One-line note to append to the end of tasks.md"),
    "cli.capture.fail": ("capture に失敗しました: {exc}", "capture failed: {exc}"),
    "cli.capture.updated_state": ("state.json を更新しました: {path}", "Updated state.json: {path}"),
    "cli.capture.updated_docs": ("handoff docs を更新しました: {path}", "Updated handoff docs: {path}"),
    "cli.capture.project_store": ("project store: {path}", "Project store: {path}"),
    "cli.capture.local_mirror": ("local mirror: {path}", "Local mirror: {path}"),
    "cli.capture.branch": ("ブランチ: {branch} / 変更ファイル数: {count}", "Branch: {branch} / changed files: {count}"),
    "cli.capture.git_repo": ("Git リポジトリではありませんが、Git は利用できます。", "Git is available, but this directory is not a Git repository."),
    "cli.capture.git_unavailable": ("Git が利用できないため、手動メモだけで運用します。", "Git is unavailable, so the workflow uses manual notes only."),
    "cli.prepare.stdout_hint": ("handoff docs を更新しました: {path}", "Updated handoff docs: {path}"),
    "cli.prepare.fail": ("prepare に失敗しました: {exc}", "prepare failed: {exc}"),
    "cli.prepare.updated_docs": ("handoff docs を更新しました: {path}", "Updated handoff docs: {path}"),
    "cli.prepare.local_mirror": ("local mirror: {path}", "Local mirror: {path}"),
    "cli.where.fail": ("where に失敗しました: {exc}", "where failed: {exc}"),
    "cli.where.project_root": ("project root: {path}", "Project root: {path}"),
    "cli.where.project_id": ("project id: {value}", "Project ID: {value}"),
    "cli.where.project_store": ("project store: {path}", "Project store: {path}"),
    "cli.where.local_mirror": ("local mirror: {path}", "Local mirror: {path}"),
    "cli.where.project_md": ("project.md: {path}", "project.md: {path}"),
    "cli.where.decisions_md": ("decisions.md: {path}", "decisions.md: {path}"),
    "cli.where.tasks_md": ("tasks.md: {path}", "tasks.md: {path}"),
    "cli.where.memory_json": ("memory.json: {path}", "memory.json: {path}"),
    "cli.where.next_thread_md": ("next-thread.md: {path}", "next-thread.md: {path}"),
    "cli.bootstrap": ("`setup` の互換コマンドです。", "Compatibility command for `setup`."),
    "cli.uninstall.fail": ("uninstall-global-agents に失敗しました: {exc}", "uninstall-global-agents failed: {exc}"),
    "cli.uninstall.backup": ("global AGENTS のバックアップを作成しました: {path}", "Created a backup of global AGENTS: {path}"),
    "cli.uninstall.removed": ("managed block を削除しました: {path}", "Removed the managed block: {path}"),
    "cli.uninstall.missing": ("managed block は存在しませんでした: {path}", "The managed block was not present: {path}"),
    "cli.doctor.target": ("診断対象: {path}", "Diagnostics target: {path}"),
    "cli.daemon.once": ("1 回だけ同期して終了する", "Sync once and exit"),
    "cli.daemon.poll_seconds": ("常駐時の同期間隔(秒)", "Polling interval while resident (seconds)"),
    "cli.daemon.fail": ("daemon に失敗しました: {exc}", "daemon failed: {exc}"),
    "gui.title": ("Codex Handoff", "Codex Handoff"),
    "gui.subtitle": (
        "初回セットアップだけを行う companion app です。以後は GUI を開かなくても、active workspace の handoff を自動更新します。",
        "A companion app for one-time setup. After that, it keeps the active workspace handoff up to date even when the GUI is closed.",
    ),
    "gui.step.install.title": ("Step 1: Install app", "Step 1: Install app"),
    "gui.step.install.description": (
        "この実行ファイルを %LOCALAPPDATA%\\CodexHandoff にコピーします。以後の更新はここに上書きされます。",
        "Copy this executable into %LOCALAPPDATA%\\CodexHandoff. Future updates will overwrite that copy.",
    ),
    "gui.step.configure.title": ("Step 2: Enable automation", "Step 2: Enable automation"),
    "gui.step.configure.description": (
        "ここで machine 単位の自動設定を行います。完了後は新しいプロジェクトでも自動追従します。",
        "Set up machine-wide automation here. Once completed, new projects will be tracked automatically as well.",
    ),
    "gui.step.done.title": ("Done", "Done"),
    "gui.step.done.description": (
        "セットアップは完了です。以後は GUI を開かなくても background sync が active workspace の handoff を自動更新します。",
        "Setup is complete. From now on, background sync keeps the active workspace handoff updated even if the GUI stays closed.",
    ),
    "gui.check.desktop_shortcut": ("デスクトップにショートカットを作成", "Create a desktop shortcut"),
    "gui.check.start_menu_shortcut": ("スタートメニューにショートカットを作成", "Create a Start menu shortcut"),
    "gui.check.auto_loading": ("~/.codex/AGENTS.md に automatic loading を設定する", "Enable automatic loading in ~/.codex/AGENTS.md"),
    "gui.check.background_sync": ("サインイン時に background sync を自動起動する", "Start background sync at sign-in"),
    "gui.info.setup": (
        "Automatic loading を有効にすると ~/.codex/AGENTS.md の codex-handoff 管理ブロックを追加または更新します。既存ファイルがある場合は必ずバックアップを作成し、管理ブロック以外は置き換えません。",
        "If automatic loading is enabled, codex-handoff adds or updates the managed block in ~/.codex/AGENTS.md. Existing files are backed up first, and only the managed block is replaced.",
    ),
    "gui.button.install": ("Install or update app", "Install or update app"),
    "gui.button.apply": ("Apply setup", "Apply setup"),
    "gui.button.close": ("閉じる", "Close"),
    "gui.status.ready": ("準備完了", "Ready"),
    "gui.status.updated": ("状態を更新しました", "State updated"),
    "gui.install.status.installed": ("Status: installed in LocalAppData.", "Status: installed in LocalAppData."),
    "gui.install.status.not_installed": ("Status: not installed yet.", "Status: not installed yet."),
    "gui.install.status.dev_mode": ("Status: development mode. LocalAppData install is optional.", "Status: development mode. LocalAppData install is optional."),
    "gui.install.location": ("Install location", "Install location"),
    "gui.install.safe": ("Step 1 is always safe. Existing files are stopped and then overwritten.", "Step 1 is always safe. Existing files are stopped and then overwritten."),
    "gui.automation.global_store": ("Global store", "Global store"),
    "gui.automation.auto_loading.enabled": ("Automatic loading: enabled", "Automatic loading: enabled"),
    "gui.automation.auto_loading.not_installed": ("Automatic loading: not installed", "Automatic loading: not installed"),
    "gui.automation.background_sync.enabled": ("Background sync at sign-in: enabled", "Background sync at sign-in: enabled"),
    "gui.automation.background_sync.not_installed": ("Background sync at sign-in: not installed", "Background sync at sign-in: not installed"),
    "gui.finish.global_store": ("Global store", "Global store"),
    "gui.finish.workspace": ("Current Codex workspace", "Current Codex workspace"),
    "gui.finish.no_workspace": ("No active Codex workspace detected yet.", "No active Codex workspace detected yet."),
    "gui.message.install.title": ("Codex Handoff", "Codex Handoff"),
    "gui.message.install.unavailable": (
        "自己インストールは配布 exe から起動した場合のみ使えます。開発中はビルド済み exe から試してください。",
        "Self-install is only available when launched from the packaged executable. During development, try the built exe instead.",
    ),
    "gui.message.install.confirm": (
        "{path} にアプリ本体をコピーします。\n古いバージョンが動いている場合は停止してから上書きします。\n\n続行しますか？",
        "Copy the app itself to {path}.\nIf an older version is running, it will be stopped before being overwritten.\n\nContinue?",
    ),
    "gui.message.install.success": (
        "Installed to:\n{path}\n\n続けて Step 2 のセットアップを実行してください。",
        "Installed to:\n{path}\n\nContinue with Step 2 setup next.",
    ),
    "gui.message.setup.confirm": (
        "automatic loading を有効にすると ~/.codex/AGENTS.md の codex-handoff 管理ブロックを追加または更新します。\n既存ファイルがある場合はバックアップを作成します。\n\n続行しますか？",
        "Enabling automatic loading adds or updates the codex-handoff managed block in ~/.codex/AGENTS.md.\nExisting files will be backed up first.\n\nContinue?",
    ),
    "gui.message.setup.error": ("Codex Handoff", "Codex Handoff"),
    "gui.message.setup.title": ("Codex Handoff", "Codex Handoff"),
    "gui.message.setup.auto_enabled": ("automatic loading を有効化しました。", "Automatic loading was enabled."),
    "gui.message.setup.auto_current": ("automatic loading は既に最新でした。", "Automatic loading was already up to date."),
    "gui.message.setup.auto_disabled": ("automatic loading を無効化しました。", "Automatic loading was disabled."),
    "gui.message.setup.background_started": ("background sync を起動しました。", "Background sync was started."),
    "gui.message.setup.background_stopped": ("background sync を停止しました。", "Background sync was stopped."),
    "gui.message.setup.done": ("セットアップが完了しました。", "Setup completed."),
    "gui.message.setup.global_store": ("Global store", "Global store"),
    "gui.message.setup.backup": ("Backup", "Backup"),
    "gui.error.background_missing": (
        "background sync 用の実行ファイルが見つかりません。Step 1 の再インストールをやり直してください。",
        "The background sync executable was not found. Please reinstall Step 1 and try again.",
    ),
    "renderer.project_context.title": ("Project Context", "Project Context"),
    "renderer.decisions.title": ("Decisions", "Decisions"),
    "renderer.tasks.title": ("Tasks", "Tasks"),
    "renderer.next_thread.title": ("Next Thread Brief: {project}", "Next Thread Brief: {project}"),
    "renderer.auto_updated": (
        "- 自動更新: `codex-handoff prepare` / `capture` / background sync",
        "- Auto-updated by `codex-handoff prepare` / `capture` / background sync",
    ),
    "renderer.generated_at": ("- 生成日時: `{value}`", "- Generated at: `{value}`"),
    "renderer.root": ("- ルート: `{value}`", "- Root: `{value}`"),
    "renderer.memory_location": ("- メモ保存先: `{value}`", "- Memory location: `{value}`"),
    "renderer.project_purpose.title": ("## このプロジェクトの目的", "## Project purpose"),
    "renderer.project_memory.title": ("## プロジェクト記憶", "## Project memory"),
    "renderer.recent_worklog.title": ("## 最近の作業記録", "## Recent worklog"),
    "renderer.current_focus.title": ("## 現在の主題", "## Current focus"),
    "renderer.recent_sessions.title": ("## 直近の会話要点", "## Recent sessions"),
    "renderer.recent_decisions.title": ("## 直近の決定事項", "## Recent decisions"),
    "renderer.open_tasks.title": ("## 未完了タスク", "## Open tasks"),
    "renderer.current_state.title": ("## 現在の作業状態", "## Current state"),
    "renderer.next_steps.title": ("## 新スレッドで最初にやるべき 3 手", "## First 3 steps for the next thread"),
    "renderer.assumptions.title": ("## 明示すべき仮定", "## Explicit assumptions"),
    "renderer.semantic.user_preferences": ("ユーザーの思想", "User preferences"),
    "renderer.semantic.specs": ("期待仕様", "Expected behavior"),
    "renderer.semantic.constraints": ("制約", "Constraints"),
    "renderer.semantic.successes": ("うまくいったこと", "What worked"),
    "renderer.semantic.failures": ("避けたいこと", "What to avoid"),
    "renderer.semantic.decisions": ("採用した判断", "Adopted decisions"),
    "renderer.worklog.progress": ("進捗", "Progress"),
    "renderer.worklog.verification": ("検証", "Verification"),
    "renderer.worklog.commit": ("直近コミット", "Recent commits"),
    "renderer.worklog.change": ("変更ファイル", "Changed files"),
    "renderer.no_project_memory": ("- まだ抽出できたプロジェクト記憶はありません。", "- No project memory has been extracted yet."),
    "renderer.no_worklog": ("- まだ抽出できた作業記録はありません。", "- No worklog entries have been extracted yet."),
    "renderer.no_sessions": ("- このプロジェクトに紐づく Codex セッション履歴はまだ見つかっていません。", "- No Codex session history has been found for this project yet."),
    "renderer.no_purpose": ("- このプロジェクトの目的はまだ抽出できていません。", "- The purpose of this project has not been extracted yet."),
    "renderer.no_current_focus": ("- 現在の主題はまだ抽出できていません。", "- The current focus has not been extracted yet."),
    "renderer.session.title": ("### セッション `{label}`", "### Session `{label}`"),
    "renderer.session.started": ("開始", "Started"),
    "renderer.session.updated": ("更新", "Updated"),
    "renderer.session.cwd": ("cwd", "cwd"),
    "renderer.session.first_request": ("- 最初の依頼: {value}", "- First request: {value}"),
    "renderer.session.latest_request": ("- 直近の依頼: {value}", "- Latest request: {value}"),
    "renderer.session.latest_reply": ("- 直近の回答: {value}", "- Latest reply: {value}"),
    "renderer.state.project_name": ("- プロジェクト名: `{value}`", "- Project: `{value}`"),
    "renderer.state.status_updated": ("- 状態更新: `{value}`", "- Status updated: `{value}`"),
    "renderer.state.detected_sessions": ("- 直近に検出した Codex セッション: {count} 件", "- Detected Codex sessions: {count}"),
    "renderer.state.git_unavailable": ("- Git: 利用できません。非 Git ディレクトリとして handoff を生成しています。", "- Git: unavailable. Generating handoff for a non-Git directory."),
    "renderer.state.git_not_repo": ("- Git: 利用可能ですが、このディレクトリは Git リポジトリではありません。", "- Git: available, but this directory is not a Git repository."),
    "renderer.state.git_root": ("- Git ルート: `{value}`", "- Git root: `{value}`"),
    "renderer.state.branch": ("- ブランチ: `{value}`", "- Branch: `{value}`"),
    "renderer.state.worktree": ("- 作業ツリー: `{value}`", "- Worktree: `{value}`"),
    "renderer.state.tracking_branch": ("- 追跡ブランチ: `{value}`", "- Tracking branch: `{value}`"),
    "renderer.state.sync_status": ("- 同期状況: `{value}`", "- Sync status: `{value}`"),
    "renderer.state.latest_push": ("- 最新 push 済みコミット: `{value}`", "- Latest pushed commit: `{value}`"),
    "renderer.state.latest_local_tag": ("- 最新ローカルタグ: `{value}`", "- Latest local tag: `{value}`"),
    "renderer.state.remote": ("- リモート: `{value}`", "- Remote: `{value}`"),
    "renderer.state.latest_release": ("- 最新 Release: {value}", "- Latest Release: {value}"),
    "renderer.state.latest_workflow": ("- 最新 workflow: {value} ({status})", "- Latest workflow: {value} ({status})"),
    "renderer.state.changed_files.title": ("### 変更ファイル", "### Changed files"),
    "renderer.state.no_changes": ("- 変更ファイルはありません。", "- No changed files."),
    "renderer.state.recent_commits.title": ("### 直近コミット", "### Recent commits"),
    "renderer.state.detected_paths.title": ("### 検出した重要パス", "### Detected important paths"),
    "renderer.state.no_important_paths": ("- 検出した重要パスはありません。", "- No important paths were detected."),
    "renderer.initial.first_tasks": ("1. `tasks.md` の先頭タスクを確認する: {value}", "1. Check the top task in `tasks.md`: {value}"),
    "renderer.initial.resume": ("1. 直近の依頼を起点に再開する: {value}", "1. Resume from the latest request: {value}"),
    "renderer.initial.pick_task": ("1. `tasks.md` を確認して次の作業を 1 つ決める。", "1. Check `tasks.md` and pick the next task."),
    "renderer.initial.inspect_changes": ("2. 変更ファイルを確認して現在地を把握する: {value}{suffix}", "2. Inspect changed files to re-orient: {value}{suffix}"),
    "renderer.initial.inspect_commit": ("2. 直近コミット `{value}` の意図を確認する。", "2. Confirm the intent of the latest commit `{value}`."),
    "renderer.initial.open_important_files": ("2. 重要ファイルを開いて文脈を取り戻す: {value}", "2. Open important files to recover context: {value}"),
    "renderer.initial.open_important_paths": ("2. 重要パスを開いて文脈を取り戻す: {value}", "2. Open important paths to recover context: {value}"),
    "renderer.initial.check_context": ("2. `project.md` と `decisions.md` を見て、前提と判断を確認する。", "2. Check `project.md` and `decisions.md` to confirm the current context."),
    "renderer.initial.think_next": ("3. 直近の回答内容を踏まえて次の判断を置く: {value}", "3. Decide the next step based on the latest reply: {value}"),
    "renderer.initial.check_rules": ("3. 制約・運用ルール・AGENTS.md を確認してから作業を進める。", "3. Review constraints, operating rules, and AGENTS.md before continuing."),
    "renderer.assumptions.constraints.title": ("### 制約", "### Constraints"),
    "renderer.assumptions.rules.title": ("### 運用ルール", "### Operating rules"),
    "renderer.assumptions.assumptions.title": ("### 仮定", "### Assumptions"),
    "renderer.assumptions.agents.title": ("### AGENTS.md", "### AGENTS.md"),
    "renderer.no_constraints": ("- 制約はまだ抽出できていません。", "- No constraints have been extracted yet."),
    "renderer.no_rules": ("- 運用ルールはまだ抽出できていません。", "- No operating rules have been extracted yet."),
    "renderer.no_assumptions": ("- 仮定はまだ抽出できていません。", "- No assumptions have been extracted yet."),
    "renderer.no_tasks": ("- 次に進める作業はまだ抽出できていません。", "- No next task has been extracted yet."),
    "renderer.no_decisions": ("- 決定事項はまだ抽出できていません。", "- No decisions have been extracted yet."),
    "renderer.important_files.title": ("## 重要ファイル", "## Important files"),
    "renderer.important_files.no_items": ("- 重要ファイルはまだ抽出できていません。", "- No important files have been extracted yet."),
    "renderer.project_context.auto": ("- 自動更新: `codex-handoff prepare` / `capture` / background sync", "- Auto-updated by `codex-handoff prepare` / `capture` / background sync"),
}


def normalize_language(value: str | None, *, default: Language = "en") -> Language:
    if not value:
        return default
    normalized = value.strip().lower().replace("_", "-")
    if normalized in {"en", "en-us", "en-gb", "english"} or normalized.startswith("en-"):
        return "en"
    if normalized in {"ja", "ja-jp", "japanese"} or normalized.startswith("ja-"):
        return "ja"
    if normalized == "auto":
        return detect_system_language(default=default)
    return default


def detect_system_language(*, default: Language = "en") -> Language:
    candidates: list[str | None] = [
        os.environ.get("LC_ALL"),
        os.environ.get("LC_MESSAGES"),
        os.environ.get("LANG"),
    ]
    try:
        current_locale = locale.getlocale()[0]
    except (ValueError, TypeError, OSError):
        current_locale = None
    candidates.append(current_locale)

    for value in candidates:
        language = _language_from_locale_value(value)
        if language is not None:
            return language
    return default


def detect_language(*, default: Language = "en") -> Language:
    override = os.environ.get("CODEX_HANDOFF_LANG")
    if override:
        return normalize_language(override, default=default)
    return default


def set_language(language: Language) -> None:
    os.environ["CODEX_HANDOFF_LANG"] = language


def t(key: str, *, language: str | None = None, **kwargs: object) -> str:
    lang = normalize_language(language, default="en") if language is not None else detect_language()
    template = TEXTS.get(key)
    if template is None:
        return key.format(**kwargs) if kwargs else key
    value = template[1] if lang == "en" else template[0]
    return value.format(**kwargs)


def _language_from_locale_value(value: str | None) -> Language | None:
    if not value:
        return None
    normalized = value.strip().lower().replace("_", "-")
    if not normalized or normalized in {"c", "posix"}:
        return None
    if normalized.startswith("en"):
        return "en"
    if normalized.startswith("ja"):
        return "ja"
    return None
