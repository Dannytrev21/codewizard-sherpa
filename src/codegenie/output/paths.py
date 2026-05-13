"""On-disk layout helpers for ``<repo_root>/.codegenie/context/``.

Pure functions: no IO, no side effects, deterministic. The writer (S3-03)
and the CLI (S4-02) both compute their target paths via these helpers so
the layout stays in one place.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["context_dir", "raw_dir", "runs_dir", "yaml_path"]


def context_dir(repo_root: Path) -> Path:
    """Return ``<repo_root>/.codegenie/context/`` (no IO)."""
    return repo_root / ".codegenie" / "context"


def raw_dir(repo_root: Path) -> Path:
    """Return ``<repo_root>/.codegenie/context/raw/`` (no IO)."""
    return context_dir(repo_root) / "raw"


def yaml_path(repo_root: Path) -> Path:
    """Return ``<repo_root>/.codegenie/context/repo-context.yaml`` (no IO)."""
    return context_dir(repo_root) / "repo-context.yaml"


def runs_dir(repo_root: Path) -> Path:
    """Return ``<repo_root>/.codegenie/context/runs/`` (no IO)."""
    return context_dir(repo_root) / "runs"
