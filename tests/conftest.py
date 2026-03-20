from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_test_language(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEX_HANDOFF_LANG", "ja")
