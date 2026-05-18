"""Shared test helpers for Layer-D probe tests (S6-03; rule-of-three).

S6-01 (``test_skills_index.py``) and S6-02 (``test_conventions.py``)
each introduced inline ``_make_repo`` / ``_make_context`` helpers; this
story is the third Layer-D probe family, so the helpers extract here
per the rule-of-three trigger. The two existing test modules continue
to use their bespoke variants — touching them is out-of-scope for
S6-03 (surgical-changes discipline). Future Layer-D test modules
import ``_make_repo`` / ``_make_context`` from this conftest.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from codegenie.probes.base import ProbeContext, RepoSnapshot


def _make_repo(tmp_path: Path, *, name: str = "myrepo") -> RepoSnapshot:
    """Construct a minimal ``RepoSnapshot`` rooted under ``tmp_path``."""
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    return RepoSnapshot(
        root=root,
        git_commit=None,
        detected_languages={},
        config={},
    )


def _make_context(
    tmp_path: Path, *, config_overrides: dict[str, Any] | None = None
) -> ProbeContext:
    """Construct a ``ProbeContext`` with every required field explicit.

    ``output_dir`` is pre-created so probes can write raw artifacts
    without first calling ``mkdir(parents=True)``.
    """
    output_dir = tmp_path / ".codegenie" / "context"
    output_dir.mkdir(parents=True, exist_ok=True)
    return ProbeContext(
        cache_dir=tmp_path / ".codegenie" / "cache",
        output_dir=output_dir,
        workspace=tmp_path / ".codegenie" / "workspace",
        logger=logging.getLogger("test"),
        config=config_overrides or {},
    )
