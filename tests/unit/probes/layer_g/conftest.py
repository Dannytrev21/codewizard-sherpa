"""Test fixtures for Layer G scanner probes (S6-06).

Mirrors the inline ``_repo`` / ``_ctx`` helper pattern from
``tests/unit/probes/layer_c/test_sbom.py`` but lifted to a conftest so
the three sibling scanner test files (semgrep / ast_grep /
ripgrep_curated) share the same construction surface verbatim.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from codegenie.probes.base import ProbeContext, RepoSnapshot


def _make_repo(root: Path) -> RepoSnapshot:
    root.mkdir(parents=True, exist_ok=True)
    return RepoSnapshot(
        root=root,
        git_commit=None,
        detected_languages={"typescript": 100},
        config={},
    )


def _make_ctx(tmp_path: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "out",
        workspace=tmp_path / "ws",
        logger=logging.getLogger("layer_g_test"),
        config={},
    )


@pytest.fixture
def repo(tmp_path: Path) -> RepoSnapshot:
    return _make_repo(tmp_path / "repo")


@pytest.fixture
def ctx(tmp_path: Path) -> ProbeContext:
    return _make_ctx(tmp_path)
