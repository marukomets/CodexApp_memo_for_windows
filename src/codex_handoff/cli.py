from __future__ import annotations

import sys
from pathlib import Path

import typer

from codex_handoff import __version__
from codex_handoff.errors import CodexHandoffError
from codex_handoff.daemon import run_background_sync
from codex_handoff.service import (
    capture_project,
    initialize_project,
    prepare_handoff,
    run_doctor,
    setup_global,
    uninstall_global_agents,
    where_project,
)

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

app = typer.Typer(help="Codex project handoff helper", no_args_is_help=True)


def _version_callback(value: bool) -> None:
    if not value:
        return
    typer.echo(__version__)
    raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed codex-handoff version and exit.",
    ),
) -> None:
    """Codex project handoff helper."""


@app.command("setup")
def setup_command(
    install_global_agents: bool = typer.Option(
        False,
        "--install-global-agents",
        help="~/.codex/AGENTS.md に codex-handoff ブロックを追加または更新する",
    ),
) -> None:
    """Install global codex-handoff integration once per machine."""

    try:
        global_paths, changed, backup_path = setup_global(install_global_agents=install_global_agents)
    except CodexHandoffError as exc:
        typer.echo(f"setup に失敗しました: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"global store: {global_paths.app_home}")
    typer.echo(f"global AGENTS snippet: {global_paths.app_home / 'global-agents-snippet.md'}")
    if not install_global_agents:
        typer.echo("global AGENTS は未変更です。自動読込を有効にするには `codex-handoff setup --install-global-agents` を実行してください。")
        return

    if backup_path is not None:
        typer.echo(f"global AGENTS のバックアップを作成しました: {backup_path}")
    if changed:
        typer.echo(f"global AGENTS を更新しました: {global_paths.global_agents_file}")
    else:
        typer.echo(f"global AGENTS は既に最新です: {global_paths.global_agents_file}")


@app.command("init")
def init_command() -> None:
    """Optional: create the current project's store immediately."""

    try:
        project_paths, created, preserved, migrated = initialize_project(Path.cwd())
    except CodexHandoffError as exc:
        typer.echo(f"init に失敗しました: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"project store: {project_paths.handoff_dir}")
    if migrated:
        typer.echo("ローカル `.codex-handoff` の変更を global store に取り込みました。")
    if created:
        typer.echo("作成:")
        for path in created:
            typer.echo(f"- {path.name}")
    if preserved:
        typer.echo("保持:")
        for path in preserved:
            typer.echo(f"- {path.name}")


@app.command("capture")
def capture_command(
    note: str | None = typer.Option(None, "--note", help="tasks.md の末尾に追加する 1 行メモ"),
) -> None:
    """Capture current project state into the global store."""

    try:
        project_paths, _, snapshot = capture_project(Path.cwd(), note=note)
    except CodexHandoffError as exc:
        typer.echo(f"capture に失敗しました: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"state.json を更新しました: {project_paths.state_file}")
    typer.echo(f"handoff docs を更新しました: {project_paths.project_file.parent}")
    typer.echo(f"project store: {project_paths.handoff_dir}")
    typer.echo(f"local mirror: {project_paths.local_handoff_dir}")
    if snapshot.is_repo:
        typer.echo(f"ブランチ: {snapshot.branch or '(detached)'} / 変更ファイル数: {len(snapshot.changed_files)}")
    elif snapshot.git_available:
        typer.echo("Git は利用できますが、このディレクトリはリポジトリではありません。")
    else:
        typer.echo("Git が利用できないため、手動メモだけで運用します。")


@app.command("prepare")
def prepare_command(
    stdout: bool = typer.Option(False, "--stdout", help="生成した Markdown を標準出力にも表示する"),
) -> None:
    """Prepare next-thread handoff markdown for the current project."""

    try:
        project_paths, markdown = prepare_handoff(Path.cwd())
    except CodexHandoffError as exc:
        typer.echo(f"prepare に失敗しました: {exc}")
        raise typer.Exit(code=1) from exc

    if stdout:
        typer.echo(f"handoff docs を更新しました: {project_paths.handoff_dir}", err=True)
        typer.echo(f"local mirror: {project_paths.local_handoff_dir}", err=True)
        typer.echo(markdown, nl=False)
        return
    typer.echo(f"handoff docs を更新しました: {project_paths.handoff_dir}")
    typer.echo(f"local mirror: {project_paths.local_handoff_dir}")


@app.command("where")
def where_command() -> None:
    """Show the current project's global store paths."""

    try:
        project_paths = where_project(Path.cwd())
    except CodexHandoffError as exc:
        typer.echo(f"where に失敗しました: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"project root: {project_paths.root}")
    typer.echo(f"project id: {project_paths.project_id}")
    typer.echo(f"project store: {project_paths.handoff_dir}")
    typer.echo(f"local mirror: {project_paths.local_handoff_dir}")
    typer.echo(f"project.md: {project_paths.project_file}")
    typer.echo(f"decisions.md: {project_paths.decisions_file}")
    typer.echo(f"tasks.md: {project_paths.tasks_file}")
    typer.echo(f"memory.json: {project_paths.memory_file}")
    typer.echo(f"next-thread.md: {project_paths.next_thread_file}")


@app.command("bootstrap")
def bootstrap_command() -> None:
    """Backward-compatible alias for `setup`."""

    setup_command(install_global_agents=True)


@app.command("uninstall-global-agents")
def uninstall_global_agents_command() -> None:
    """Remove the managed codex-handoff block from ~/.codex/AGENTS.md."""

    try:
        global_paths, changed, backup_path = uninstall_global_agents()
    except CodexHandoffError as exc:
        typer.echo(f"uninstall-global-agents に失敗しました: {exc}")
        raise typer.Exit(code=1) from exc

    if backup_path is not None:
        typer.echo(f"global AGENTS のバックアップを作成しました: {backup_path}")
    if changed:
        typer.echo(f"managed block を削除しました: {global_paths.global_agents_file}")
    else:
        typer.echo(f"managed block は存在しませんでした: {global_paths.global_agents_file}")


@app.command("doctor")
def doctor_command() -> None:
    """Validate global setup, current project store, encoding, and git availability."""

    project_paths, findings = run_doctor(Path.cwd())
    typer.echo(f"診断対象: {project_paths.root}")
    for finding in findings:
        typer.echo(finding.render())
    exit_code = 1 if any(finding.severity == "error" for finding in findings) else 0
    raise typer.Exit(code=exit_code)


@app.command("daemon")
def daemon_command(
    once: bool = typer.Option(False, "--once", help="1 回だけ同期して終了する"),
    poll_seconds: int = typer.Option(15, "--poll-seconds", min=5, help="常駐時の同期間隔(秒)"),
) -> None:
    """Keep the active Codex workspace handoff updated in the background."""

    try:
        run_background_sync(poll_seconds=poll_seconds, once=once)
    except CodexHandoffError as exc:
        typer.echo(f"daemon に失敗しました: {exc}")
        raise typer.Exit(code=1) from exc
