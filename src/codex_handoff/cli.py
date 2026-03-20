from __future__ import annotations

import sys
from pathlib import Path

import typer

from codex_handoff import __version__
from codex_handoff.errors import CodexHandoffError
from codex_handoff.daemon import run_background_sync
from codex_handoff.localization import t
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
        help="Add or update the codex-handoff block in ~/.codex/AGENTS.md",
    ),
) -> None:
    """Install global codex-handoff integration once per machine."""

    try:
        global_paths, changed, backup_path = setup_global(install_global_agents=install_global_agents)
    except CodexHandoffError as exc:
        typer.echo(t("cli.setup.fail", exc=exc))
        raise typer.Exit(code=1) from exc

    typer.echo(t("cli.setup.global_store", path=global_paths.app_home))
    typer.echo(t("cli.setup.global_agents_snippet", path=global_paths.app_home / "global-agents-snippet.md"))
    if not install_global_agents:
        typer.echo(t("cli.setup.unchanged"))
        return

    if backup_path is not None:
        typer.echo(t("cli.setup.backup", path=backup_path))
    if changed:
        typer.echo(t("cli.setup.updated", path=global_paths.global_agents_file))
    else:
        typer.echo(t("cli.setup.up_to_date", path=global_paths.global_agents_file))


@app.command("init")
def init_command() -> None:
    """Optional: create the current project's store immediately."""

    try:
        project_paths, created, preserved, migrated = initialize_project(Path.cwd())
    except CodexHandoffError as exc:
        typer.echo(t("cli.init.fail", exc=exc))
        raise typer.Exit(code=1) from exc

    typer.echo(t("cli.init.project_store", path=project_paths.handoff_dir))
    if migrated:
        typer.echo(t("cli.init.migrated"))
    if created:
        typer.echo(t("cli.init.created"))
        for path in created:
            typer.echo(f"- {path.name}")
    if preserved:
        typer.echo(t("cli.init.preserved"))
        for path in preserved:
            typer.echo(f"- {path.name}")


@app.command("capture")
def capture_command(
    note: str | None = typer.Option(None, "--note", help="One-line note to append to the end of tasks.md"),
) -> None:
    """Capture current project state into the global store."""

    try:
        project_paths, _, snapshot = capture_project(Path.cwd(), note=note)
    except CodexHandoffError as exc:
        typer.echo(t("cli.capture.fail", exc=exc))
        raise typer.Exit(code=1) from exc

    typer.echo(t("cli.capture.updated_state", path=project_paths.state_file))
    typer.echo(t("cli.capture.updated_docs", path=project_paths.project_file.parent))
    typer.echo(t("cli.capture.project_store", path=project_paths.handoff_dir))
    typer.echo(t("cli.capture.local_mirror", path=project_paths.local_handoff_dir))
    if snapshot.is_repo:
        typer.echo(t("cli.capture.branch", branch=snapshot.branch or "(detached)", count=len(snapshot.changed_files)))
    elif snapshot.git_available:
        typer.echo(t("cli.capture.git_repo"))
    else:
        typer.echo(t("cli.capture.git_unavailable"))


@app.command("prepare")
def prepare_command(
    stdout: bool = typer.Option(False, "--stdout", help="Also print the generated Markdown to standard output"),
) -> None:
    """Prepare next-thread handoff markdown for the current project."""

    try:
        project_paths, markdown = prepare_handoff(Path.cwd())
    except CodexHandoffError as exc:
        typer.echo(t("cli.prepare.fail", exc=exc))
        raise typer.Exit(code=1) from exc

    if stdout:
        typer.echo(t("cli.prepare.stdout_hint", path=project_paths.handoff_dir), err=True)
        typer.echo(t("cli.prepare.local_mirror", path=project_paths.local_handoff_dir), err=True)
        typer.echo(markdown, nl=False)
        return
    typer.echo(t("cli.prepare.updated_docs", path=project_paths.handoff_dir))
    typer.echo(t("cli.prepare.local_mirror", path=project_paths.local_handoff_dir))


@app.command("where")
def where_command() -> None:
    """Show the current project's global store paths."""

    try:
        project_paths = where_project(Path.cwd())
    except CodexHandoffError as exc:
        typer.echo(t("cli.where.fail", exc=exc))
        raise typer.Exit(code=1) from exc

    typer.echo(t("cli.where.project_root", path=project_paths.root))
    typer.echo(t("cli.where.project_id", value=project_paths.project_id))
    typer.echo(t("cli.where.project_store", path=project_paths.handoff_dir))
    typer.echo(t("cli.where.local_mirror", path=project_paths.local_handoff_dir))
    typer.echo(t("cli.where.project_md", path=project_paths.project_file))
    typer.echo(t("cli.where.decisions_md", path=project_paths.decisions_file))
    typer.echo(t("cli.where.tasks_md", path=project_paths.tasks_file))
    typer.echo(t("cli.where.memory_json", path=project_paths.memory_file))
    typer.echo(t("cli.where.next_thread_md", path=project_paths.next_thread_file))


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
        typer.echo(t("cli.uninstall.fail", exc=exc))
        raise typer.Exit(code=1) from exc

    if backup_path is not None:
        typer.echo(t("cli.uninstall.backup", path=backup_path))
    if changed:
        typer.echo(t("cli.uninstall.removed", path=global_paths.global_agents_file))
    else:
        typer.echo(t("cli.uninstall.missing", path=global_paths.global_agents_file))


@app.command("doctor")
def doctor_command() -> None:
    """Validate global setup, current project store, encoding, and git availability."""

    project_paths, findings = run_doctor(Path.cwd())
    typer.echo(t("cli.doctor.target", path=project_paths.root))
    for finding in findings:
        typer.echo(finding.render())
    exit_code = 1 if any(finding.severity == "error" for finding in findings) else 0
    raise typer.Exit(code=exit_code)


@app.command("daemon")
def daemon_command(
    once: bool = typer.Option(False, "--once", help="Sync once and exit"),
    poll_seconds: int = typer.Option(15, "--poll-seconds", min=5, help="Polling interval while resident (seconds)"),
) -> None:
    """Keep the active Codex workspace handoff updated in the background."""

    try:
        run_background_sync(poll_seconds=poll_seconds, once=once)
    except CodexHandoffError as exc:
        typer.echo(t("cli.daemon.fail", exc=exc))
        raise typer.Exit(code=1) from exc
