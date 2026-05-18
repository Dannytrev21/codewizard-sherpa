"""``ConventionsProbe`` — Layer D, ``heaviness="light"`` (S6-02).

Applies :class:`~codegenie.conventions.loader.ConventionsCatalogLoader`
output to the analyzed-repo :class:`RepoSnapshot` and emits a typed
:class:`ConventionsSlice`. Each rule's outcome is one of
``Pass | Fail | NotApplicable`` — the closed sum type S2-02 ships in
:mod:`codegenie.conventions.model`.

This module is the imperative shell *around* the kernel-side functional
core (``Catalog.apply`` and the four ``_apply_<kind>`` helpers in
:mod:`codegenie.conventions.catalog`). The probe contributes:

- search-path resolution (``ctx.config`` → ``[user_tier, repo_tier]``)
- ``Result`` pattern-matching (``Ok(CatalogLoadOutcome)`` /
  ``Err(FatalLoadError)``)
- three-state confidence policy (``_compute_confidence``)
- slice projection (:class:`ConventionsSlice`)
- atomic raw-artifact write to ``ctx.output_dir / "conventions.json"``

Sources:

- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #10 — loader + apply.
- ``docs/localv2.md`` §5.4 D5 — example catalog with the four
  YAML-pattern types.
- ``docs/phases/02-context-gather-layers-b-g/stories/S6-01-skills-index-probe.md``
  — probe-shape precedent (three-state confidence, ``_PROBE_ID`` Final
  constant, atomic raw artifact).
- ``src/codegenie/probes/layer_b/scip_index.py:114`` — dual-form probe
  identity (``name: str`` ABC attr + module-level ``_PROBE_ID`` Final).

CLAUDE.md disciplines honored:

- "Facts, not judgments" — per-rule outcomes; no aggregation, no
  fix-suggestions, no inference.
- "Extension by addition" — new rule kinds are new ``_apply_*`` helpers
  in the kernel; the probe inherits them automatically.
- "Honest confidence" — three-state policy; ``Catalog.apply`` memo is
  the single source of truth for per-snapshot caching.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from codegenie.conventions.loader import (
    CatalogLoadOutcome,
    ConventionsCatalogLoader,
    ConventionsError,
    FatalLoadError,
)
from codegenie.conventions.model import ConventionResult
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.result import Err, Ok
from codegenie.types.identifiers import ProbeId

__all__ = ["ConventionsProbe", "ConventionsSlice"]


_PROBE_ID: Final[ProbeId] = ProbeId("conventions")
_BASE_VERSION: Final[str] = "0.1.0"
_RAW_ARTIFACT_NAME: Final[str] = "conventions.json"
_WARNING_PER_FILE_ERRORS: Final[str] = "conventions.per_file_errors_present"
_DEFAULT_USER_PATH: Final[str] = "~/.codegenie/conventions/"
_DEFAULT_REPO_PATH: Final[str] = ".codegenie/conventions/"


# ---------------------------------------------------------------------------
# Functional core — pure helpers (no I/O, no instance state).
# ---------------------------------------------------------------------------


def _compute_confidence(
    applied: list[ConventionResult],
    per_file_errors: list[ConventionsError],
) -> Literal["high", "medium", "low"]:
    """Three-state policy: high (clean), medium (partial), low (total).

    The FatalLoadError path is handled at the ``run`` site and always
    maps to ``low`` — this helper covers the Ok branch only.
    """
    if not per_file_errors:
        return "high"
    if applied:
        return "medium"
    return "low"


def _project_results(applied: list[ConventionResult]) -> tuple[ConventionResult, ...]:
    """Preserve loader order; tuple-typed for hash-stability and immutability."""
    return tuple(applied)


def _atomic_write_text(path: Path, blob: str) -> None:
    """Atomic write via sibling ``.tmp`` + :func:`os.replace`.

    The sibling ``.tmp`` lives in the same directory so ``os.replace``
    stays within one filesystem (a cross-fs replace raises ``OSError``).
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(blob)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Imperative shell — slice + probe.
# ---------------------------------------------------------------------------


class ConventionsSlice(BaseModel):
    """Frozen slice; smart-constructor enforces ``rules_checked == len(results)``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    results: tuple[ConventionResult, ...]
    catalog_paths_resolved: tuple[str, ...]
    per_file_errors: tuple[ConventionsError, ...]
    rules_checked: int

    @model_validator(mode="after")
    def _check_count(self) -> ConventionsSlice:
        if self.rules_checked != len(self.results):
            raise ValueError(
                f"rules_checked={self.rules_checked} but len(results)={len(self.results)}"
            )
        return self


@register_probe(heaviness="light")
class ConventionsProbe(Probe):
    """Layer-D conventions probe. See module docstring for invariants."""

    name: str = "conventions"
    version: str = _BASE_VERSION
    layer: Literal["D"] = "D"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 15
    cache_strategy: Literal["content"] = "content"
    declared_inputs: list[str] = [
        "Dockerfile",
        f"conventions_user_search_path:{_DEFAULT_USER_PATH}",
        f"conventions_repo_search_path:{_DEFAULT_REPO_PATH}",
    ]

    def _resolve_search_paths(self, repo: RepoSnapshot, ctx: ProbeContext) -> list[Path]:
        """Pure path resolution — no I/O (filesystem touch happens in load_all)."""
        user_tier = Path(ctx.config.get("conventions.user_path", _DEFAULT_USER_PATH)).expanduser()
        repo_tier = repo.root / Path(ctx.config.get("conventions.repo_path", _DEFAULT_REPO_PATH))
        return [user_tier, repo_tier]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        resolved = self._resolve_search_paths(repo, ctx)
        result = ConventionsCatalogLoader(search_paths=resolved).load_all()

        applied: list[ConventionResult]
        per_file_errors: list[ConventionsError]
        catalog_paths: tuple[str, ...]
        fatal: bool

        if isinstance(result, Ok):
            outcome: CatalogLoadOutcome = result.value
            applied = list(outcome.catalog.apply(repo))
            per_file_errors = list(outcome.per_file_errors)
            catalog_paths = tuple(p.as_posix() for p in resolved)
            fatal = False
        else:
            assert isinstance(result, Err)
            fatal_err: FatalLoadError = result.error
            applied = []
            per_file_errors = []
            catalog_paths = tuple(p.as_posix() for p in fatal_err.paths)
            fatal = True

        slice_ = ConventionsSlice(
            results=_project_results(applied),
            catalog_paths_resolved=catalog_paths,
            per_file_errors=tuple(per_file_errors),
            rules_checked=len(applied),
        )

        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        raw_path = ctx.output_dir / _RAW_ARTIFACT_NAME
        _atomic_write_text(
            raw_path,
            slice_.model_dump_json(indent=2),
        )

        warnings = [_WARNING_PER_FILE_ERRORS] if per_file_errors else []
        confidence: Literal["high", "medium", "low"] = (
            "low" if fatal else _compute_confidence(applied, per_file_errors)
        )

        return ProbeOutput(
            schema_slice=slice_.model_dump(mode="json"),
            raw_artifacts=[raw_path],
            confidence=confidence,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=warnings,
            errors=[],
        )
