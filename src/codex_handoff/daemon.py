from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from codex_handoff.clock import now_local_iso
from codex_handoff.codex_state import load_codex_workspace_state
from codex_handoff.paths import get_global_paths
from codex_handoff.service import prepare_handoff


DEFAULT_POLL_SECONDS = 15


@dataclass(slots=True)
class BackgroundSyncState:
    active_workspace: str | None = None
    last_synced_at: str | None = None
    last_error: str | None = None


class SingleInstanceLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: BinaryIO | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        try:
            _lock_file(self.handle)
        except OSError:
            self.handle.close()
            self.handle = None
            return False

        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(f"{os.getpid()}\n".encode("ascii"))
        self.handle.flush()
        return True

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            _unlock_file(self.handle)
        finally:
            self.handle.close()
            self.handle = None

    def __enter__(self) -> "SingleInstanceLock":
        if not self.acquire():
            raise RuntimeError("background sync already running")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def run_background_sync(poll_seconds: int = DEFAULT_POLL_SECONDS, once: bool = False) -> None:
    global_paths = get_global_paths()
    global_paths.app_home.mkdir(parents=True, exist_ok=True)
    state_file = global_paths.app_home / "background-sync.json"
    lock = try_acquire_background_lock(global_paths.app_home)
    if lock is None:
        return

    last_workspace: str | None = None
    last_sync_monotonic = 0.0

    try:
        while True:
            preferred_root = load_codex_workspace_state(global_paths.codex_home).preferred_root()
            workspace_text = preferred_root.as_posix() if preferred_root is not None else None

            should_sync = preferred_root is not None and (
                workspace_text != last_workspace or (time.monotonic() - last_sync_monotonic) >= poll_seconds
            )
            if should_sync and preferred_root is not None:
                try:
                    prepare_handoff(preferred_root)
                except Exception as exc:  # pragma: no cover - background resilience
                    write_background_sync_state(
                        state_file,
                        BackgroundSyncState(
                            active_workspace=workspace_text,
                            last_synced_at=now_local_iso(),
                            last_error=str(exc),
                        ),
                    )
                else:
                    last_workspace = workspace_text
                    last_sync_monotonic = time.monotonic()
                    write_background_sync_state(
                        state_file,
                        BackgroundSyncState(
                            active_workspace=workspace_text,
                            last_synced_at=now_local_iso(),
                            last_error=None,
                        ),
                    )
            elif preferred_root is None:
                write_background_sync_state(
                    state_file,
                    BackgroundSyncState(
                        active_workspace=None,
                        last_synced_at=now_local_iso(),
                        last_error="No active Codex workspace detected.",
                    ),
                )

            if once:
                return
            time.sleep(poll_seconds)
    finally:
        lock.release()


def write_background_sync_state(path: Path, state: BackgroundSyncState) -> None:
    payload = {
        "active_workspace": state.active_workspace,
        "last_synced_at": state.last_synced_at,
        "last_error": state.last_error,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def try_acquire_background_lock(app_home: Path) -> SingleInstanceLock | None:
    lock = SingleInstanceLock(app_home / "background-sync.lock")
    return lock if lock.acquire() else None


def _lock_file(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
