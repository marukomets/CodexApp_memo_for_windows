from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from codex_handoff.processes import hidden_subprocess_kwargs


APP_HOME_DIR_NAME = ".codex-handoff"
LEGACY_LOCAL_DIR_NAME = ".codex-handoff"
DEFAULT_CODEX_HOME_DIR_NAME = ".codex"


@dataclass(slots=True)
class GlobalPaths:
    app_home: Path
    projects_dir: Path
    codex_home: Path
    global_agents_file: Path
    user_memory_file: Path


@dataclass(slots=True)
class ProjectPaths:
    global_paths: GlobalPaths
    root: Path
    project_id: str
    handoff_dir: Path
    config_file: Path
    project_file: Path
    decisions_file: Path
    tasks_file: Path
    memory_file: Path
    state_file: Path
    next_thread_file: Path
    repo_agents_file: Path
    local_handoff_dir: Path


def get_global_paths() -> GlobalPaths:
    app_home = Path(os.environ.get("CODEX_HANDOFF_HOME", Path.home() / APP_HOME_DIR_NAME)).expanduser().resolve()
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / DEFAULT_CODEX_HOME_DIR_NAME)).expanduser().resolve()
    return GlobalPaths(
        app_home=app_home,
        projects_dir=app_home / "projects",
        codex_home=codex_home,
        global_agents_file=codex_home / "AGENTS.md",
        user_memory_file=app_home / "user-memory.json",
    )


def build_project_paths(start: Path) -> ProjectPaths:
    root = detect_project_root(start.resolve())
    global_paths = get_global_paths()
    project_id = make_project_id(root)
    handoff_dir = global_paths.projects_dir / project_id
    return ProjectPaths(
        global_paths=global_paths,
        root=root,
        project_id=project_id,
        handoff_dir=handoff_dir,
        config_file=handoff_dir / "config.toml",
        project_file=handoff_dir / "project.md",
        decisions_file=handoff_dir / "decisions.md",
        tasks_file=handoff_dir / "tasks.md",
        memory_file=handoff_dir / "memory.json",
        state_file=handoff_dir / "state.json",
        next_thread_file=handoff_dir / "next-thread.md",
        repo_agents_file=root / "AGENTS.md",
        local_handoff_dir=root / LEGACY_LOCAL_DIR_NAME,
    )


def detect_project_root(start: Path) -> Path:
    git_root = _try_git_root(start)
    return git_root or start


def make_project_id(root: Path) -> str:
    slug = slugify(root.name) or "project"
    digest = hashlib.sha256(root.as_posix().encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"


def slugify(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-")


def _try_git_root(start: Path) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **hidden_subprocess_kwargs(),
    )
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    return Path(root).resolve() if root else None
