from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from codex_handoff.bootstrap import build_agents_block, ensure_agents_block, has_agents_block, remove_agents_block
from codex_handoff.clock import now_local_iso
from codex_handoff.config import default_config, load_config, render_config, validate_config
from codex_handoff.codex_sessions import CodexSessionSource
from codex_handoff.errors import CodexHandoffError
from codex_handoff.files import has_utf8_bom, read_optional_text, write_text
from codex_handoff.focus import select_user_facing_changed_files
from codex_handoff.localization import t
from codex_handoff.memory import (
    _classify_assistant_semantic_text,
    _is_durable_assistant_semantic,
    _looks_like_user_global_scope_fragment,
    build_memory_snapshot,
    build_user_memory_entries,
    load_memory_snapshot,
    load_user_memory,
    render_memory_json,
    render_user_memory_json,
)
from codex_handoff.models import (
    DoctorFinding,
    HandoffDocument,
    ManualContext,
    MemorySnapshot,
    ProjectConfig,
    ReadmeContext,
    RepoSnapshot,
    SessionRecord,
    VolatileStatus,
)
from codex_handoff.paths import GlobalPaths, ProjectPaths, build_project_paths, get_global_paths
from codex_handoff.relevance import is_transient_review_message, is_transient_review_note
from codex_handoff.renderer import CodexMarkdownRenderer
from codex_handoff.sources import AgentsSource, GitSource, LiveStatusSource, ManualFilesSource, ReadmeSource
from codex_handoff.summaries import split_summary_sentences, summarize_actionable_request, summarize_user_request
from codex_handoff.templates import DECISIONS_TEMPLATE, NEXT_THREAD_TEMPLATE, PROJECT_TEMPLATE, TASKS_TEMPLATE

LOCAL_MIRROR_BOM_FILE_NAMES = {
    "config.toml",
    "project.md",
    "decisions.md",
    "tasks.md",
    "memory.json",
    "state.json",
    "next-thread.md",
}


def setup_global(install_global_agents: bool = False) -> tuple[GlobalPaths, bool, Path | None]:
    global_paths = get_global_paths()
    global_paths.app_home.mkdir(parents=True, exist_ok=True)
    global_paths.projects_dir.mkdir(parents=True, exist_ok=True)
    global_paths.codex_home.mkdir(parents=True, exist_ok=True)
    write_text(global_paths.app_home / "global-agents-snippet.md", build_agents_block())
    if not global_paths.user_memory_file.exists():
        write_text(global_paths.user_memory_file, _initial_user_memory_json())
    if not install_global_agents:
        return global_paths, False, None
    changed, backup_path = ensure_agents_block(global_paths.global_agents_file)
    return global_paths, changed, backup_path


def uninstall_global_agents() -> tuple[GlobalPaths, bool, Path | None]:
    global_paths = get_global_paths()
    changed, backup_path = remove_agents_block(global_paths.global_agents_file)
    return global_paths, changed, backup_path


def initialize_project(start: Path) -> tuple[ProjectPaths, list[Path], list[Path], bool]:
    project_paths = build_project_paths(start)
    _ensure_project_store(project_paths)
    migrated = _sync_local_store_to_global(project_paths)

    config = default_config(project_paths.root)
    created: list[Path] = []
    preserved: list[Path] = []
    for path, content in (
        (project_paths.config_file, render_config(config)),
        (project_paths.project_file, PROJECT_TEMPLATE),
        (project_paths.decisions_file, DECISIONS_TEMPLATE),
        (project_paths.tasks_file, TASKS_TEMPLATE),
        (project_paths.memory_file, _initial_memory_json(project_paths)),
        (project_paths.state_file, _initial_state_json(config.project_name, project_paths)),
        (project_paths.next_thread_file, NEXT_THREAD_TEMPLATE),
    ):
        if path.exists():
            preserved.append(path)
            continue
        write_text(path, content)
        created.append(path)
    _mirror_global_store_to_local(project_paths)
    return project_paths, created, preserved, migrated


def capture_project(start: Path, note: str | None = None) -> tuple[ProjectPaths, ProjectConfig, RepoSnapshot]:
    project_paths, _, _, _ = initialize_project(start)
    config = load_config(project_paths.config_file)
    note_text = _normalize_note(note)
    recent_sessions = CodexSessionSource(project_paths, config).collect()
    operation_time = now_local_iso()
    snapshot, _ = _generate_handoff_outputs(
        project_paths,
        config,
        recent_sessions,
        generated_at=operation_time,
        note_text=note_text,
    )
    return project_paths, config, snapshot


def prepare_handoff(start: Path) -> tuple[ProjectPaths, str]:
    project_paths, _, _, _ = initialize_project(start)
    config = load_config(project_paths.config_file)
    recent_sessions = CodexSessionSource(project_paths, config).collect()
    operation_time = now_local_iso()
    _, markdown = _generate_handoff_outputs(
        project_paths,
        config,
        recent_sessions,
        generated_at=operation_time,
    )
    return project_paths, markdown


def where_project(start: Path) -> ProjectPaths:
    project_paths, _, _, _ = initialize_project(start)
    return project_paths


def run_doctor(start: Path) -> tuple[ProjectPaths, list[DoctorFinding]]:
    project_paths, _, _, migrated = initialize_project(start)
    findings: list[DoctorFinding] = []
    config: ProjectConfig | None = None

    findings.append(DoctorFinding("ok", "global_home", t("doctor.global_home", path=project_paths.global_paths.app_home)))
    findings.append(DoctorFinding("ok", "user_memory", t("doctor.user_memory", path=project_paths.global_paths.user_memory_file)))
    findings.append(DoctorFinding("ok", "project_store", t("doctor.project_store", path=project_paths.handoff_dir)))
    findings.append(DoctorFinding("ok", "local_store", t("doctor.local_store", path=project_paths.local_handoff_dir)))
    if migrated:
        findings.append(DoctorFinding("ok", "local_imported", t("doctor.local_imported")))

    if project_paths.global_paths.global_agents_file.exists():
        if has_agents_block(project_paths.global_paths.global_agents_file):
            findings.append(DoctorFinding("ok", "global_agents", t("doctor.global_agents.block_present", path=project_paths.global_paths.global_agents_file)))
        else:
            findings.append(DoctorFinding("warning", "global_agents_missing", t("doctor.global_agents.block_missing", path=project_paths.global_paths.global_agents_file)))
    else:
        findings.append(DoctorFinding("warning", "global_agents_missing", t("doctor.global_agents.file_missing", path=project_paths.global_paths.global_agents_file)))

    if project_paths.config_file.exists():
        findings.append(DoctorFinding("ok", "config_exists", t("doctor.config.exists")))
        try:
            config = load_config(project_paths.config_file)
        except CodexHandoffError as exc:
            findings.append(DoctorFinding("error", "config_invalid", str(exc)))
        else:
            for issue in validate_config(config):
                findings.append(DoctorFinding("error", "config_invalid", issue))
            if not validate_config(config):
                findings.append(DoctorFinding("ok", "config_valid", t("doctor.config.valid")))
    else:
        findings.append(DoctorFinding("error", "config_missing", t("doctor.config.missing")))

    for name, path in (
        ("project", project_paths.project_file),
        ("decisions", project_paths.decisions_file),
        ("tasks", project_paths.tasks_file),
        ("memory", project_paths.memory_file),
        ("state", project_paths.state_file),
        ("next_thread", project_paths.next_thread_file),
    ):
        if path.exists():
            findings.append(DoctorFinding("ok", f"{name}_exists", t("doctor.file.exists", path=path.name)))
        else:
            findings.append(DoctorFinding("warning", f"{name}_missing", t("doctor.file.missing", path=path.name)))

    for path in (
        project_paths.config_file,
        project_paths.project_file,
        project_paths.decisions_file,
        project_paths.tasks_file,
        project_paths.memory_file,
        project_paths.state_file,
        project_paths.next_thread_file,
    ):
        if not path.exists():
            continue
        try:
            read_optional_text(path)
        except UnicodeDecodeError:
            findings.append(DoctorFinding("error", "encoding_invalid", t("doctor.encoding.invalid", path=path.name)))
            continue
        if has_utf8_bom(path):
            findings.append(DoctorFinding("error", "encoding_bom", t("doctor.encoding.bom", path=path.name)))
        else:
            findings.append(DoctorFinding("ok", "encoding_utf8", t("doctor.encoding.utf8", path=path.name)))

    snapshot = GitSource(project_paths, config).collect() if config else RepoSnapshot(git_available=False, is_repo=False)
    if not snapshot.git_available:
        findings.append(DoctorFinding("warning", "git_unavailable", t("doctor.git.unavailable")))
    elif not snapshot.is_repo:
        findings.append(DoctorFinding("warning", "git_not_repo", t("doctor.git.not_repo")))
    else:
        findings.append(DoctorFinding("ok", "git_repo", t("doctor.git.repo", branch=snapshot.branch or "(detached)")))

    return project_paths, findings


def _generate_handoff_outputs(
    project_paths: ProjectPaths,
    config: ProjectConfig,
    recent_sessions: list[SessionRecord],
    *,
    generated_at: str,
    note_text: str | None = None,
) -> tuple[RepoSnapshot, str]:
    readme_context = ReadmeSource(project_paths).collect()
    existing_context = _load_existing_generated_context(project_paths)
    existing_memory = load_memory_snapshot(project_paths.memory_file)
    agents_markdown = AgentsSource(project_paths).collect().agents_markdown
    user_memory_markdown = _build_user_memory_markdown(project_paths, agents_markdown)
    existing_user_memory = load_user_memory(project_paths.global_paths.user_memory_file)
    snapshot = GitSource(project_paths, config).collect()
    live_status_source = LiveStatusSource(project_paths)
    markdown = ""

    for _ in range(3):
        user_memory_entries = build_user_memory_entries(
            recent_sessions,
            existing_user_memory,
            user_memory_markdown,
            generated_at,
        )
        write_text(
            project_paths.global_paths.user_memory_file,
            render_user_memory_json(user_memory_entries, generated_at),
        )
        memory_snapshot = build_memory_snapshot(
            project_paths.root,
            recent_sessions,
            existing_memory,
            snapshot,
            generated_at,
        )
        volatile_status = live_status_source.collect(snapshot, refreshed_at=generated_at)
        write_text(
            project_paths.memory_file,
            render_memory_json(project_paths, memory_snapshot, generated_at),
        )
        write_text(
            project_paths.state_file,
            _render_state_json(
                config,
                project_paths,
                snapshot,
                recent_sessions,
                volatile_status=volatile_status,
                captured_at=generated_at,
            ),
        )
        document = _build_handoff_document(
            project_paths,
            config,
            snapshot,
            recent_sessions,
            readme_context=readme_context,
            existing_context=existing_context,
            memory_snapshot=memory_snapshot,
            volatile_status=volatile_status,
            user_memory_entries=user_memory_entries,
            agents_markdown=agents_markdown,
            generated_at=generated_at,
            note_text=note_text,
        )
        markdown = _write_generated_documents(project_paths, document)
        _mirror_global_store_to_local(project_paths)

        next_snapshot = GitSource(project_paths, config).collect()
        if next_snapshot == snapshot:
            return snapshot, markdown
        snapshot = next_snapshot

    user_memory_entries = build_user_memory_entries(
        recent_sessions,
        existing_user_memory,
        user_memory_markdown,
        generated_at,
    )
    write_text(
        project_paths.global_paths.user_memory_file,
        render_user_memory_json(user_memory_entries, generated_at),
    )
    memory_snapshot = build_memory_snapshot(
        project_paths.root,
        recent_sessions,
        existing_memory,
        snapshot,
        generated_at,
    )
    volatile_status = live_status_source.collect(snapshot, refreshed_at=generated_at)
    write_text(
        project_paths.memory_file,
        render_memory_json(project_paths, memory_snapshot, generated_at),
    )
    write_text(
        project_paths.state_file,
        _render_state_json(
            config,
            project_paths,
            snapshot,
            recent_sessions,
            volatile_status=volatile_status,
            captured_at=generated_at,
        ),
    )
    document = _build_handoff_document(
        project_paths,
        config,
        snapshot,
        recent_sessions,
        readme_context=readme_context,
        existing_context=existing_context,
        memory_snapshot=memory_snapshot,
        volatile_status=volatile_status,
        user_memory_entries=user_memory_entries,
        agents_markdown=agents_markdown,
        generated_at=generated_at,
        note_text=note_text,
    )
    markdown = _write_generated_documents(project_paths, document)
    _mirror_global_store_to_local(project_paths)
    return snapshot, markdown


def _build_user_memory_markdown(project_paths: ProjectPaths, repo_agents_markdown: str) -> str:
    global_agents_markdown = read_optional_text(project_paths.global_paths.global_agents_file).strip()
    parts = [part for part in (global_agents_markdown, repo_agents_markdown) if part]
    return "\n\n".join(parts)


def _build_handoff_document(
    project_paths: ProjectPaths,
    config: ProjectConfig,
    snapshot: RepoSnapshot,
    recent_sessions: list[SessionRecord],
    *,
    readme_context: ReadmeContext,
    existing_context: ManualContext,
    memory_snapshot: MemorySnapshot,
    volatile_status: VolatileStatus,
    user_memory_entries: list[MemoryEntry],
    agents_markdown: str,
    generated_at: str,
    note_text: str | None = None,
) -> HandoffDocument:
    context = _build_generated_context(
        project_paths,
        readme_context,
        snapshot,
        recent_sessions,
        memory_snapshot,
        user_memory_entries,
        agents_markdown,
        existing_context,
        generated_at=generated_at,
        note_text=note_text,
    )
    return HandoffDocument(
        project_name=config.project_name,
        root_path=project_paths.root.as_posix(),
        handoff_dir=project_paths.handoff_dir.as_posix(),
        generated_at=generated_at,
        manual_context=context,
        repo_snapshot=snapshot,
        memory_snapshot=memory_snapshot,
        volatile_status=volatile_status,
        user_memory_entries=user_memory_entries,
        recent_sessions=recent_sessions,
    )


def _write_generated_documents(project_paths: ProjectPaths, document: HandoffDocument) -> str:
    renderer = CodexMarkdownRenderer()
    project_markdown = renderer.render_project(document)
    decisions_markdown = renderer.render_decisions(document)
    tasks_markdown = renderer.render_tasks(document)
    next_thread_markdown = renderer.render_next_thread(document)
    write_text(project_paths.project_file, project_markdown)
    write_text(project_paths.decisions_file, decisions_markdown)
    write_text(project_paths.tasks_file, tasks_markdown)
    write_text(project_paths.next_thread_file, next_thread_markdown)
    return next_thread_markdown


def _build_generated_context(
    project_paths: ProjectPaths,
    readme_context: ReadmeContext,
    snapshot: RepoSnapshot,
    recent_sessions: list[SessionRecord],
    memory_snapshot: MemorySnapshot,
    user_memory_entries: list[MemoryEntry],
    agents_markdown: str,
    existing_context: ManualContext,
    *,
    generated_at: str,
    note_text: str | None = None,
) -> ManualContext:
    purpose = _derive_purpose(readme_context, recent_sessions)
    constraints = _derive_constraints(readme_context, snapshot, agents_markdown)
    important_files = _derive_important_files(project_paths, snapshot, recent_sessions)
    operating_rules = _derive_operating_rules(readme_context, agents_markdown, user_memory_entries)
    assumptions = _derive_assumptions(snapshot, recent_sessions)
    decisions_markdown = _merge_existing_bullets(
        _derive_decisions(snapshot, memory_snapshot),
        existing_context.decisions_markdown,
        recent_sessions=recent_sessions,
    )
    tasks_markdown = _merge_existing_tasks(
        _derive_tasks(
            project_paths,
            snapshot,
            recent_sessions,
            generated_at=generated_at,
            note_text=note_text,
        ),
        existing_context.tasks_markdown,
        recent_sessions=recent_sessions,
    )
    return ManualContext(
        purpose=purpose or existing_context.purpose,
        constraints=constraints or existing_context.constraints,
        important_files=important_files or existing_context.important_files,
        operating_rules=operating_rules or existing_context.operating_rules,
        assumptions=assumptions or existing_context.assumptions,
        decisions_markdown=decisions_markdown,
        tasks_markdown=tasks_markdown,
        agents_markdown=agents_markdown.strip(),
    )


def _derive_purpose(readme_context: ReadmeContext, recent_sessions: list[SessionRecord]) -> str:
    if readme_context.sections.get("目的"):
        return readme_context.sections["目的"].strip()
    if readme_context.intro:
        return readme_context.intro.strip()

    task = _latest_substantive_user_request(recent_sessions)
    if task:
        return f"- 直近の依頼からみた主題: {task}"
    return "- このプロジェクトの目的はまだ抽出できていません。"


def _derive_constraints(readme_context: ReadmeContext, snapshot: RepoSnapshot, agents_markdown: str) -> str:
    blocks: list[str] = []
    for title in ("現実的な制約", "制約"):
        section = readme_context.sections.get(title)
        if section:
            blocks.append(section.strip())

    dynamic_constraints: list[str] = []
    if not snapshot.git_available:
        dynamic_constraints.append("Git がなくても handoff を継続できる前提で扱う。")
    elif not snapshot.is_repo:
        dynamic_constraints.append("Git リポジトリではなく、作業ディレクトリ単位で文脈を継続する。")

    for line in _extract_rule_lines(agents_markdown):
        if any(keyword in line for keyword in ("確認", "機密", "破壊的", "公開", "課金")):
            dynamic_constraints.append(line)

    if dynamic_constraints:
        blocks.append(_render_bullets(dynamic_constraints))
    return _merge_markdown_blocks(blocks)


def _derive_important_files(
    project_paths: ProjectPaths,
    snapshot: RepoSnapshot,
    recent_sessions: list[SessionRecord],
) -> str:
    items: list[str] = []
    for path in snapshot.detected_important_paths:
        items.append(path)

    for record in recent_sessions:
        for text in (record.latest_user_message, record.latest_assistant_message):
            for candidate in _extract_path_candidates(project_paths.root, text):
                items.append(candidate)

    if project_paths.repo_agents_file.exists():
        items.append("AGENTS.md")
    return _render_code_bullets(_unique(items))


def _derive_operating_rules(
    readme_context: ReadmeContext,
    agents_markdown: str,
    user_memory_entries: list[MemoryEntry],
) -> str:
    blocks: list[str] = []
    for title in ("設計方針", "運用ルール", "Windows PowerShell 互換"):
        section = readme_context.sections.get(title)
        if section:
            blocks.append(section.strip())

    shared_user_rules = _derive_user_memory_rules(user_memory_entries)
    if shared_user_rules:
        blocks.append(_render_bullets(shared_user_rules))

    agent_rules = [
        line
        for line in _extract_rule_lines(agents_markdown)
        if not _matches_user_memory_rule(line, shared_user_rules)
    ]
    if agent_rules:
        blocks.append(_render_bullets(agent_rules))

    if not blocks:
        blocks.append(_render_bullets(["`codex-handoff prepare` / `capture` でメモを最新化してから作業を再開する。"]))
    return _merge_markdown_blocks(blocks)


def _derive_user_memory_rules(user_memory_entries: list[MemoryEntry]) -> list[str]:
    rule_kinds = {"preference", "constraint", "decision"}
    return _unique([entry.summary for entry in user_memory_entries if entry.kind in rule_kinds])


def _matches_user_memory_rule(candidate: str, shared_rules: list[str]) -> bool:
    normalized_candidate = _normalize_rule_line(candidate)
    if not normalized_candidate:
        return False
    return any(normalized_candidate == _normalize_rule_line(rule) for rule in shared_rules)


def _normalize_rule_line(text: str) -> str:
    normalized = text.strip().lower()
    normalized = re.sub(r"[`\s/\\:;,.!?\-\(\)\[\]{}]+", "", normalized)
    return normalized


def _derive_assumptions(snapshot: RepoSnapshot, recent_sessions: list[SessionRecord]) -> str:
    assumptions: list[str] = []
    task = _latest_substantive_user_request(recent_sessions)
    if task:
        assumptions.append(f"直近の主題は「{task}」の継続である。")

    if snapshot.detected_important_paths:
        joined = ", ".join(f"`{path}`" for path in snapshot.detected_important_paths[:3])
        assumptions.append(f"文脈回復は {joined} から始める。")

    if not snapshot.git_available:
        assumptions.append("Git 情報なしでも作業継続に必要なメモを優先する。")
    elif not snapshot.is_repo:
        assumptions.append("Git 管理外なので、差分ではなくファイル構成と会話履歴を基準に再開する。")

    return _render_bullets(_unique(assumptions))


def _derive_decisions(snapshot: RepoSnapshot, memory_snapshot: MemorySnapshot) -> str:
    decisions: list[str] = []
    if not snapshot.git_available:
        decisions.append(f"{now_local_iso()[:10]}: Git 非依存の workspace として handoff を生成する。")
    elif not snapshot.is_repo:
        decisions.append(f"{now_local_iso()[:10]}: Git 管理外のディレクトリとして path 単位で handoff を継続する。")

    for entry in (entry for entry in memory_snapshot.semantic_entries if entry.kind == "decision"):
        date = (entry.updated_at or now_local_iso())[:10]
        decisions.append(f"{date}: {entry.summary}")

    unique_decisions = _unique(decisions)
    if not unique_decisions:
        return "- 決定事項はまだ抽出できていません。"
    return _render_prefixed_lines(unique_decisions)


def _derive_tasks(
    project_paths: ProjectPaths,
    snapshot: RepoSnapshot,
    recent_sessions: list[SessionRecord],
    *,
    generated_at: str,
    note_text: str | None = None,
) -> str:
    primary_tasks: list[str] = []
    secondary_tasks: list[str] = []

    if note_text:
        primary_tasks.append(f"{note_text} (captured {generated_at})")

    for record in recent_sessions[:1]:
        if _session_task_completed(record):
            continue
        task = _display_task_summary(record.latest_substantive_user_summary)
        if not task:
            task = _display_task_summary(record.latest_user_message)
        if not task:
            task = _display_task_summary(record.first_user_message)
        if task:
            primary_tasks.append(task)

    focus_changed_files = select_user_facing_changed_files(snapshot.changed_files, limit=3)
    if focus_changed_files:
        focus_files = ", ".join(f"`{item.path}`" for item in focus_changed_files)
        suffix = " など" if len(focus_changed_files) < len(snapshot.changed_files) else ""
        secondary_tasks.append(f"変更ファイルを確認する: {focus_files}{suffix}")
    elif snapshot.detected_important_paths:
        focus_paths = ", ".join(f"`{path}`" for path in snapshot.detected_important_paths[:3])
        secondary_tasks.append(f"重要ファイルを確認して文脈を戻す: {focus_paths}")

    if not primary_tasks and not secondary_tasks and project_paths.repo_agents_file.exists():
        secondary_tasks.append("`AGENTS.md`、`memory.json`、`next-thread.md` を確認して次の作業を決める。")

    unique_tasks = _rank_tasks(primary_tasks + secondary_tasks)
    if not unique_tasks:
        return "- [ ] 次に進める作業はまだ抽出できていません。"
    return "\n".join(f"- [ ] {item}" for item in unique_tasks[:5])


def _ensure_project_store(project_paths: ProjectPaths) -> None:
    project_paths.global_paths.app_home.mkdir(parents=True, exist_ok=True)
    project_paths.global_paths.projects_dir.mkdir(parents=True, exist_ok=True)
    project_paths.handoff_dir.mkdir(parents=True, exist_ok=True)
    if not project_paths.global_paths.user_memory_file.exists():
        write_text(project_paths.global_paths.user_memory_file, _initial_user_memory_json())


def _load_existing_generated_context(project_paths: ProjectPaths) -> ManualContext:
    if _matches_template(project_paths.project_file, PROJECT_TEMPLATE):
        project_exists = False
    else:
        project_exists = project_paths.project_file.exists()

    if _matches_template(project_paths.decisions_file, DECISIONS_TEMPLATE):
        decisions_exists = False
    else:
        decisions_exists = project_paths.decisions_file.exists()

    if _matches_template(project_paths.tasks_file, TASKS_TEMPLATE):
        tasks_exists = False
    else:
        tasks_exists = project_paths.tasks_file.exists()

    if not any((project_exists, decisions_exists, tasks_exists)):
        return ManualContext()

    context = ManualFilesSource(project_paths).collect()
    if not project_exists:
        context.purpose = ""
        context.constraints = ""
        context.important_files = ""
        context.operating_rules = ""
        context.assumptions = ""
    if not decisions_exists:
        context.decisions_markdown = ""
    if not tasks_exists:
        context.tasks_markdown = ""
    return context


def _sync_local_store_to_global(project_paths: ProjectPaths) -> bool:
    local_dir = project_paths.local_handoff_dir
    if not local_dir.is_dir():
        return False

    imported = False
    for local_path, target_path in _manual_sync_pairs(project_paths):
        if not local_path.exists():
            continue
        if not target_path.exists():
            write_text(target_path, read_optional_text(local_path))
            imported = True
            continue
        local_text = read_optional_text(local_path)
        target_text = read_optional_text(target_path)
        if local_text == target_text:
            continue
        if _prefer_local_content(project_paths, local_path, target_path, local_text, target_text):
            write_text(target_path, local_text)
            imported = True
    return imported


def _mirror_global_store_to_local(project_paths: ProjectPaths) -> None:
    local_dir = project_paths.local_handoff_dir
    local_dir.mkdir(parents=True, exist_ok=True)
    for source_path, mirror_path in _mirror_pairs(project_paths):
        if not source_path.exists():
            continue
        write_text(
            mirror_path,
            read_optional_text(source_path),
            bom=mirror_path.name in LOCAL_MIRROR_BOM_FILE_NAMES,
        )


def _manual_sync_pairs(project_paths: ProjectPaths) -> tuple[tuple[Path, Path], ...]:
    local_dir = project_paths.local_handoff_dir
    return ((local_dir / "config.toml", project_paths.config_file),)


def _mirror_pairs(project_paths: ProjectPaths) -> tuple[tuple[Path, Path], ...]:
    local_dir = project_paths.local_handoff_dir
    return (
        (project_paths.config_file, local_dir / "config.toml"),
        (project_paths.project_file, local_dir / "project.md"),
        (project_paths.decisions_file, local_dir / "decisions.md"),
        (project_paths.tasks_file, local_dir / "tasks.md"),
        (project_paths.memory_file, local_dir / "memory.json"),
        (project_paths.state_file, local_dir / "state.json"),
        (project_paths.next_thread_file, local_dir / "next-thread.md"),
    )


def _prefer_local_content(
    project_paths: ProjectPaths,
    local_path: Path,
    target_path: Path,
    local_text: str,
    target_text: str,
) -> bool:
    if local_path.stat().st_mtime_ns > target_path.stat().st_mtime_ns:
        return True
    return _is_placeholder_content(project_paths, local_path.name, target_text) and not _is_placeholder_content(
        project_paths,
        local_path.name,
        local_text,
    )


def _is_placeholder_content(project_paths: ProjectPaths, file_name: str, content: str) -> bool:
    normalized = content.strip()
    placeholders = {
        "config.toml": render_config(default_config(project_paths.root)).strip(),
    }
    return not normalized or normalized == placeholders.get(file_name, "")


def _matches_template(path: Path, template: str) -> bool:
    if not path.exists():
        return False
    return read_optional_text(path).strip() == template.strip()


def _latest_substantive_user_request(recent_sessions: list[SessionRecord]) -> str | None:
    for record in recent_sessions:
        task = _display_task_summary(record.latest_substantive_user_summary)
        if not task:
            task = _display_task_summary(record.latest_user_message)
        if not task:
            task = _display_task_summary(record.first_user_message)
        if task:
            return task
    return None


def _decision_summary(text: str | None) -> str | None:
    summaries = _decision_summaries(text)
    if not summaries:
        return None
    return summaries[0]


def _decision_summaries(text: str | None) -> list[str]:
    cleaned = _clean_summary_text(text)
    if not cleaned or is_transient_review_note(cleaned):
        return []

    summaries: list[str] = []
    for sentence in _extract_sentences(cleaned):
        if is_transient_review_note(sentence):
            continue
        if not _looks_like_decision(sentence):
            continue
        summaries.append(_truncate(sentence, 140))

    if not summaries and _looks_like_decision(cleaned):
        summaries.append(_truncate(cleaned, 140))
    return _unique(summaries)


def _task_summary(text: str | None) -> str | None:
    cleaned = summarize_user_request(text, limit=160)
    if not cleaned or _is_trivial_message(cleaned):
        return None
    return cleaned


def _display_task_summary(text: str | None) -> str | None:
    cleaned = summarize_actionable_request(text, limit=160)
    if not cleaned or _is_trivial_message(cleaned):
        return None
    return cleaned


def _clean_summary_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    cleaned = " ".join(cleaned.split())
    return cleaned or None


def _extract_sentences(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace(" - ", "。")
    sentences: list[str] = []
    for raw_line in normalized.splitlines():
        line = re.sub(r"^(?:[-*]\s+|\d+\.\s+)", "", raw_line.strip())
        if not line:
            continue
        for part in split_summary_sentences(line):
            sentence = part.strip(" -")
            if sentence:
                sentences.append(sentence)
    return sentences


def _looks_like_decision(text: str) -> bool:
    if _is_trivial_decision_message(text):
        return False

    scope_keywords = (
        "handoff",
        "next-thread",
        "project.md",
        "decisions.md",
        "tasks.md",
        "AGENTS.md",
        ".codex-handoff",
        "global store",
        "local mirror",
        "workspace",
        "Git",
        "同期ミラー",
        "自動更新",
        "自動生成",
        "source of truth",
    )
    if not any(keyword in text for keyword in scope_keywords):
        return False

    keywords = (
        "正本",
        "source of truth",
        "同期ミラー",
        "global store",
        "local mirror",
        "自動更新",
        "自動生成",
        "path 単位",
        "Git 管理外",
        "opt-in",
        "前提",
        "方針",
        "採用",
    )
    if any(keyword in text for keyword in keywords):
        return True

    return bool(
        re.search(
            r"(にする|とする|扱う|継続する|採用する|固定する|切り替える|揃える|統一する|再利用する|書き出す)",
            text,
        )
    )


def _is_trivial_decision_message(text: str) -> bool:
    trivial_starts = (
        "そうです",
        "そうしてください",
        "了解",
        "承知",
        "引き継ぎ自体はできています",
    )
    if any(text.startswith(prefix) for prefix in trivial_starts):
        return True
    return len(text) < 12


def _session_task_completed(record: SessionRecord) -> bool:
    task = record.latest_substantive_user_summary or _task_summary(record.latest_user_message)
    if not task:
        task = _task_summary(record.first_user_message)
    if not task:
        return False
    return _assistant_indicates_completion(record.latest_assistant_message)


def _assistant_indicates_completion(text: str | None) -> bool:
    cleaned = _clean_summary_text(text)
    if not cleaned:
        return False

    completion_markers = (
        "済ませました",
        "完了しました",
        "対応しました",
        "修正しました",
        "実装しました",
        "追加しました",
        "更新しました",
        "再生成しました",
        "作成しました",
        "揃えました",
        "通しました",
        "ビルドしました",
        "除外しました",
        "切り替えました",
    )
    return any(marker in cleaned for marker in completion_markers)


def _extract_path_candidates(root: Path, text: str | None) -> list[str]:
    if not text:
        return []
    candidates: list[str] = []
    for match in re.findall(r"`([^`]+)`", text):
        normalized = _normalize_path_candidate(root, match)
        if normalized:
            candidates.append(normalized)
    return _unique(candidates)


def _normalize_path_candidate(root: Path, value: str) -> str | None:
    candidate = value.strip()
    if not candidate:
        return None
    absolute = Path(candidate)
    if absolute.is_absolute():
        try:
            return absolute.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return None
    relative = (root / candidate).resolve()
    if relative.exists():
        return relative.relative_to(root.resolve()).as_posix()
    return None


def _extract_bullet_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            lines.append(stripped[2:].strip())
        elif stripped.startswith("* "):
            lines.append(stripped[2:].strip())
    return lines


def _extract_rule_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--") or stripped.startswith("## "):
            continue
        if stripped.startswith("- "):
            lines.append(stripped[2:].strip())
            continue
        if stripped.startswith("* "):
            lines.append(stripped[2:].strip())
            continue
        lines.append(stripped)
    return lines


def _merge_existing_bullets(
    current_markdown: str,
    existing_markdown: str,
    *,
    recent_sessions: list[SessionRecord],
) -> str:
    current_items = _extract_bullet_lines(current_markdown)
    existing_items = _extract_existing_decision_lines(
        existing_markdown,
        recent_sessions=recent_sessions,
        current_items=current_items,
    )
    merged = _unique(current_items + existing_items)
    if not merged:
        return "- 決定事項はまだ抽出できていません。"
    return _render_bullets(merged)


def _merge_existing_tasks(
    current_markdown: str,
    existing_markdown: str,
    *,
    recent_sessions: list[SessionRecord],
) -> str:
    current_items = _extract_actionable_task_lines(current_markdown)
    existing_items = _extract_preserved_task_lines(
        existing_markdown,
        current_items=current_items,
        recent_sessions=recent_sessions,
    )
    merged = _rank_tasks(current_items + existing_items)
    if not merged:
        return "- [ ] 次に進める作業はまだ抽出できていません。"
    return "\n".join(f"- [ ] {item}" for item in merged[:5])


def _extract_actionable_task_lines(markdown: str) -> list[str]:
    items: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ] "):
            task = stripped[6:].strip()
            if not is_transient_review_message(task):
                items.append(task)
        elif stripped.startswith("* [ ] "):
            task = stripped[6:].strip()
            if not is_transient_review_message(task):
                items.append(task)
    return items


def _extract_preserved_task_lines(
    markdown: str,
    *,
    current_items: list[str],
    recent_sessions: list[SessionRecord],
) -> list[str]:
    items: list[str] = []
    recent_tasks = [
        task
        for task in (
            _display_task_summary(record.latest_substantive_user_summary)
            or _display_task_summary(record.latest_user_message)
            for record in recent_sessions
        )
        if task
    ]
    for task in _extract_actionable_task_lines(markdown):
        if _is_generated_housekeeping_task(task):
            continue
        normalized_task = _display_task_summary(task) or _task_summary(task) or (_clean_summary_text(task) or task)
        if not _looks_like_preserved_task(normalized_task):
            continue
        if _matches_any_normalized_item(normalized_task, current_items):
            continue
        if _matches_any_normalized_item(normalized_task, recent_tasks):
            continue
        items.append(normalized_task)
    return items


def _is_generated_housekeeping_task(task: str) -> bool:
    return task.startswith(
        (
            "変更ファイルを確認する:",
            "重要ファイルを確認して文脈を戻す:",
            "`AGENTS.md`、`memory.json`、`next-thread.md` を確認して次の作業を決める。",
        )
    )


def _extract_existing_decision_lines(
    markdown: str,
    *,
    recent_sessions: list[SessionRecord],
    current_items: list[str],
) -> list[str]:
    items: list[str] = []
    recent_items = current_items
    for line in _extract_bullet_lines(markdown):
        if line.startswith("自動更新:") or line.startswith("生成日時:"):
            continue
        if re.match(r"\d{4}-\d{2}-\d{2}:", line):
            _, _, body = line.partition(":")
            cleaned_body = body.strip()
            if (
                cleaned_body
                and not is_transient_review_note(cleaned_body)
                and not _is_verbose_generated_decision(cleaned_body)
                and (
                    _looks_like_preservable_generated_decision(cleaned_body)
                    or _looks_like_manual_preserved_decision(cleaned_body)
                )
            ):
                candidate = _truncate(line, 140)
                if not _matches_any_normalized_item(candidate, recent_items):
                    items.append(candidate)
            continue
        if is_transient_review_note(line):
            continue
        if not (
            _looks_like_preservable_generated_decision(line)
            or _looks_like_manual_preserved_decision(line)
        ):
            continue
        candidate = _truncate(line, 140)
        if not _matches_any_normalized_item(candidate, recent_items):
            items.append(candidate)
    return items


def _looks_like_preservable_generated_decision(text: str) -> bool:
    return any(
        _is_durable_assistant_semantic(text, kind)
        for kind in _classify_assistant_semantic_text(text)
        if kind == "decision"
    )


def _looks_like_manual_preserved_decision(text: str) -> bool:
    cleaned = _clean_summary_text(text) or ""
    if not cleaned:
        return False
    if _looks_like_user_global_scope_fragment(cleaned):
        return False
    if len(cleaned) > 40:
        return False
    if any(marker in cleaned for marker in ("`", ".py", ".md", ".json", ".exe", "global store", "memory.json", "next-thread", "staged/unstaged")):
        return False
    return "。" not in cleaned and "、" not in cleaned


def _is_verbose_generated_decision(text: str) -> bool:
    cleaned = _clean_summary_text(text) or ""
    if not cleaned:
        return False
    if cleaned.startswith(
        (
            "方針は固まりました。",
            "実装方針は見えました。",
            "今回で効いた点は",
            "その通りです。",
            "新しいスレッド開始時に",
            "このリポジトリの設定どおり確認します。",
            "まず ",
        )
    ):
        return True
    return cleaned.count("。") >= 2 and len(cleaned) > 90


def _looks_like_preserved_task(task: str) -> bool:
    cleaned = _clean_summary_text(task)
    if not cleaned:
        return False
    if _task_summary(cleaned) is None and not _looks_like_manual_action_task(cleaned):
        return False
    if "？" in cleaned or "?" in cleaned:
        return False
    if cleaned.startswith(("そうだね。", "とりあえず", "かなりいい感じ", "これって")):
        return False
    if any(keyword in cleaned for keyword in ("だよね", "いいね", "かな", "見よう")) and not any(
        action in cleaned for action in ("確認", "更新", "修正", "実装", "追加", "テスト", "配布", "インストール", "ビルド")
    ):
        return False
    return True


def _matches_any_normalized_item(text: str, candidates: list[str]) -> bool:
    normalized = _normalize_merge_item(text)
    if not normalized:
        return False
    for candidate in candidates:
        other = _normalize_merge_item(candidate)
        if not other:
            continue
        if normalized == other or normalized.startswith(other) or other.startswith(normalized):
            return True
    return False


def _normalize_merge_item(text: str) -> str:
    cleaned = _clean_summary_text(text) or ""
    cleaned = re.sub(r"^\d{4}-\d{2}-\d{2}:\s*", "", cleaned)
    cleaned = re.sub(r"^\*\*[^*]+\*\*\s*", "", cleaned)
    cleaned = re.sub(
        r"^(?:方針は固まりました。|実装方針は見えました。|今回で効いた点は \d+ つです。|その通りです。|結論としては|結果としては)\s*",
        "",
        cleaned,
    )
    cleaned = cleaned.replace("…", "")
    cleaned = cleaned.rstrip("。 ")
    return cleaned


def _rank_tasks(tasks: list[str]) -> list[str]:
    unique_items = _dedupe_task_items(tasks)
    ranked = sorted(enumerate(unique_items), key=lambda item: (_task_sort_key(item[1]), item[0]))
    return [task for _, task in ranked]


def _dedupe_task_items(tasks: list[str]) -> list[str]:
    deduped: dict[str, str] = {}
    passthrough: list[str] = []
    for task in tasks:
        cleaned = task.strip()
        if not cleaned:
            continue
        key = _normalize_task_merge_key(cleaned)
        if not key:
            passthrough.append(cleaned)
            continue
        deduped.setdefault(key, cleaned)
    return [*passthrough, *deduped.values()]


def _normalize_task_merge_key(text: str) -> str:
    cleaned = _task_summary(text) or _clean_summary_text(text) or ""
    cleaned = re.sub(r"^(?:- \[ \]\s*)", "", cleaned)
    cleaned = re.sub(r"\b(?:したいな|いいね|かな|でしょ)\b", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _task_sort_key(task: str) -> int:
    housekeeping = _is_generated_housekeeping_task(task)
    manual_action = _looks_like_manual_action_task(task)
    summary = _task_summary(task)
    if summary:
        return 0 if not housekeeping else 2
    if manual_action:
        return 1 if not housekeeping else 3
    return 4


def _looks_like_manual_action_task(task: str) -> bool:
    return any(
        marker in task
        for marker in (
            "確認",
            "更新",
            "修正",
            "実装",
            "追加",
            "テスト",
            "配布",
            "インストール",
            "ビルド",
            "整理",
            "評価",
            "調整",
        )
    )


def _record_date(record: SessionRecord) -> str:
    value = record.updated_at or record.started_at or now_local_iso()
    return value[:10]


def _render_bullets(items: list[str]) -> str:
    if not items:
        return ""
    return "\n".join(f"- {item}" for item in _unique(items))


def _render_code_bullets(items: list[str]) -> str:
    if not items:
        return ""
    return "\n".join(f"- `{item}`" for item in _unique(items))


def _render_prefixed_lines(items: list[str]) -> str:
    if not items:
        return ""
    return "\n".join(f"- {item}" for item in items)


def _merge_markdown_blocks(blocks: list[str]) -> str:
    normalized = [block.strip() for block in blocks if block and block.strip()]
    if not normalized:
        return ""
    return "\n\n".join(normalized)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_items.append(key)
    return unique_items


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _is_trivial_message(text: str) -> bool:
    trivial_starts = (
        "引き継げてる",
        "見れる",
        "どこみれば",
        "できてる",
    )
    if any(text.startswith(prefix) for prefix in trivial_starts):
        return True
    return len(text) < 8


def _initial_state_json(project_name: str, project_paths: ProjectPaths) -> str:
    payload = {
        "project_id": project_paths.project_id,
        "project_name": project_name,
        "root_path": project_paths.root.as_posix(),
        "handoff_dir": project_paths.handoff_dir.as_posix(),
        "captured_at": None,
        "git_available": False,
        "is_repo": False,
        "branch": None,
        "is_dirty": False,
        "changed_files": [],
        "recent_commits": [],
        "detected_important_paths": [],
        "git_root": None,
        "repo_agents_file": "AGENTS.md" if project_paths.repo_agents_file.exists() else None,
        "recent_sessions": [],
        "volatile_status": None,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _initial_memory_json(project_paths: ProjectPaths) -> str:
    payload = {
        "version": 2,
        "project_id": project_paths.project_id,
        "project_name": project_paths.root.name,
        "updated_at": None,
        "semantic_entries": [],
        "worklog_entries": [],
        "current_focus": None,
        "focus_paths": [],
        "next_actions": [],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _initial_user_memory_json() -> str:
    payload = {
        "version": 1,
        "updated_at": None,
        "entries": [],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _render_state_json(
    config: ProjectConfig,
    project_paths: ProjectPaths,
    snapshot: RepoSnapshot,
    recent_sessions: list[SessionRecord],
    *,
    volatile_status: VolatileStatus | None = None,
    captured_at: str,
) -> str:
    payload = {
        "project_id": project_paths.project_id,
        "project_name": config.project_name,
        "root_path": project_paths.root.as_posix(),
        "handoff_dir": project_paths.handoff_dir.as_posix(),
        "captured_at": captured_at,
        "git_available": snapshot.git_available,
        "is_repo": snapshot.is_repo,
        "branch": snapshot.branch,
        "is_dirty": snapshot.is_dirty,
        "changed_files": [asdict(item) for item in snapshot.changed_files],
        "recent_commits": [asdict(item) for item in snapshot.recent_commits],
        "detected_important_paths": snapshot.detected_important_paths,
        "git_root": snapshot.git_root,
        "repo_agents_file": "AGENTS.md" if project_paths.repo_agents_file.exists() else None,
        "recent_sessions": [item.to_dict() for item in recent_sessions],
        "volatile_status": volatile_status.to_dict() if volatile_status else None,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _normalize_note(note: str | None) -> str | None:
    if note is None:
        return None
    single_line = " ".join(segment for segment in note.splitlines() if segment.strip()).strip()
    return single_line or None
