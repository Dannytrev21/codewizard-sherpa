# ruff: noqa: I001
"""Frozen probe-contract surface — byte-for-byte ``docs/localv2.md §4`` (ADR-0007).

Every probe in this POC and the eventual service implements the same
``Probe`` ABC declared below. Drift between this file and ``localv2.md §4``
is caught in CI by ``tests/unit/test_probe_contract.py``; resolution is
**always** "change code to match doc, never the inverse" (ADR-0007). The
amendment workflow lives in ``templates/adr-amendment.md``.

This module is stdlib-only on purpose: the contract surface must not pull
Pydantic / attrs / third-party validators into Phase 0. The Pydantic
trust-boundary wrapper is an internal coordinator concern (ADR-0010) and
lands in S3-02, not here.
"""

# TODO(S5-02): CODEOWNERS entry required for src/codegenie/probes/base.py, docs/localv2.md, tests/snapshots/ — see ADR-0007 §Reversibility

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping  # ADR-0002 (Phase 1) — admitted by ALLOWED_BASE_PY_IMPORTS widening
from dataclasses import dataclass
from typing import Literal, Any, NamedTuple
from pathlib import Path
from logging import Logger

@dataclass
class RepoSnapshot:
    root: Path
    git_commit: str | None
    detected_languages: dict[str, int]   # populated after LanguageDetectionProbe runs
    config: dict[str, Any]                # ~/.codegenie/config.yaml merged with repo .codegenie/config.yaml

@dataclass
class Task:
    type: str                # "distroless_migration", "vuln_remediation", etc.
    options: dict[str, Any]  # task-specific parameters

# Phase 1 contract type (ADR-0002, phase-arch-design.md §"Gap analysis" Gap 1).
# NamedTuple gives auto-hash + value-equality for frozenset membership.
class InputFingerprint(NamedTuple):
    path: str
    mtime_ns: int
    size: int
    content_hash: str

@dataclass
class ProbeContext:
    cache_dir: Path
    output_dir: Path           # where probe writes raw artifacts
    workspace: Path            # ephemeral workspace for the probe
    logger: Logger
    config: dict[str, Any]
    # Phase 1 additions (ADR-0002). No further extensions without ADR amendment.
    parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None = None
    input_snapshot: frozenset["InputFingerprint"] | None = None

@dataclass
class ProbeOutput:
    schema_slice: dict[str, Any]   # what gets merged into RepoContext
    raw_artifacts: list[Path]      # files written under output_dir
    confidence: Literal["high", "medium", "low"]
    duration_ms: int
    warnings: list[str]
    errors: list[str]


class Probe(ABC):
    name: str
    layer: Literal["A", "B", "C", "D", "E", "F", "G"]
    tier: Literal["base", "task_specific"]
    applies_to_tasks: list[str]                 # ["*"] = all
    applies_to_languages: list[str]             # ["*"] = all
    requires: list[str]                          # other probe names that must run first
    declared_inputs: list[str]                   # glob patterns or special tokens
    timeout_seconds: int = 300
    cache_strategy: Literal["content", "none"] = "content"

    def applies(self, repo: RepoSnapshot, task: Task) -> bool:
        """Skip-detection beyond simple metadata matching."""
        return True

    def cache_key(self, repo: RepoSnapshot, task: Task) -> str:
        """Content-addressed cache key. Default: hash of declared_inputs contents."""
        ...

    @abstractmethod
    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        """Produce the schema slice this probe owns."""
        ...
