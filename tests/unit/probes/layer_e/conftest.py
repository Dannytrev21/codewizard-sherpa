"""Shared helpers for Layer-E tests (S6-05).

``ProbeContext`` is a stdlib ``@dataclass`` with no ``for_test`` classmethod;
constructing it in every test is verbose, so these helpers (mirroring
``tests/unit/probes/layer_c/test_dockerfile.py:61-74``) are the canonical
construction point for Layer-E unit tests.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from codegenie.probes.base import ProbeContext, RepoSnapshot


@pytest.fixture
def _make_repo():  # type: ignore[no-untyped-def]
    def _factory(tmp_path: Path, *, config: dict[str, Any] | None = None) -> RepoSnapshot:
        return RepoSnapshot(
            root=tmp_path,
            git_commit=None,
            detected_languages={},
            config=config or {},
        )

    return _factory


@pytest.fixture
def _make_ctx():  # type: ignore[no-untyped-def]
    def _factory(tmp_path: Path) -> ProbeContext:
        workspace = tmp_path / "_ws"
        workspace.mkdir(parents=True, exist_ok=True)
        out_dir = tmp_path / "_out"
        out_dir.mkdir(parents=True, exist_ok=True)
        return ProbeContext(
            cache_dir=tmp_path / "_cache",
            output_dir=out_dir,
            workspace=workspace,
            logger=logging.getLogger("test"),
            config={},
        )

    return _factory
