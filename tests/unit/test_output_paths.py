"""Pure-function path helpers under ``<repo_root>/.codegenie/context/``.

Pins AC-23 (four pure helpers; deterministic; no IO) from story S3-03.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.output.paths import context_dir, raw_dir, runs_dir, yaml_path


@pytest.mark.parametrize(
    "repo",
    [
        Path("/tmp/repo"),
        Path("/Users/x/y"),
        Path("/var/folders/abc"),
        Path("/home/alice/proj"),
        Path("/root/work"),
    ],
)
def test_paths_are_under_codegenie_context(repo: Path) -> None:
    base = repo / ".codegenie" / "context"
    assert context_dir(repo) == base
    assert raw_dir(repo) == base / "raw"
    assert yaml_path(repo) == base / "repo-context.yaml"
    assert runs_dir(repo) == base / "runs"


def test_paths_are_pure_no_io(tmp_path: Path) -> None:
    fake = tmp_path / "does-not-exist"
    context_dir(fake)
    raw_dir(fake)
    yaml_path(fake)
    runs_dir(fake)
    assert not fake.exists()
