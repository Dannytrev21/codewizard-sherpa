"""``ScipIndexProbe`` (B1, S4-03) — SCIP semantic index via ``scip-typescript``.

Produces the binary SCIP index B2 reads to determine "is the index
up-to-date with HEAD?" Phase 2 emits only — the consumption shape (mmap,
re-parse, projection) belongs to Phase 3's ``ScipAdapter`` per
[ADR-0002 §Decision](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md).

**Two load-bearing disciplines** that must not erode:

1. **Tool-version cache-key sensitivity via** ``probe.version`` **property.**
   The performance-lens-original proposal of a
   ``scip-typescript-version:<resolved>`` declared-input token is silently
   dropped by master's ``cache/keys.py::declared_inputs_for`` (rglob-only,
   no token dispatch) and further filtered by
   ``_OUTPUT_NAMESPACE = ".codegenie"``. The escape hatch already in
   the cache-key tuple at ``cache/keys.py:146`` is ``probe.version`` —
   rolling the resolved tool version into the version string
   (``f"0.1.0+scip-typescript-{resolved}"``) closes the gap with zero new
   mechanism.

2. **``scip.json`` sidecar is the LOAD-BEARING hand-off to B2.** The binary
   ``.scip`` blob is Phase-3-opaque; B2's ``read_raw_slices`` reads only
   ``<output_dir>/raw/<index_name>.json`` files. Without the sidecar, B2
   fires ``Stale(IndexerError("upstream_scip_unavailable"))`` on every
   gather — defeating the whole ``index_health`` slice. The sidecar MUST
   be written on EVERY code path including timeout, non-zero exit, and
   tool-missing. The wrong typed signal ("indexer never ran") would mask
   "indexer ran but failed."

**Cross-layer agreement on empty repos.** A TypeScript repo with zero
``.ts/.tsx`` files: probe-side ``confidence="low"`` (the index is not
informative); B2-side ``Fresh`` (``0 == 0`` matches HEAD). The two layers
disagree intentionally; both are correct in their own dimension. Do NOT
add a "no .ts files → don't write scip.json" shortcut — that would make
B2 fire ``upstream_scip_unavailable``, which is wrong (the indexer did
run; it just had no work).

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S4-03-scip-index-probe.md``
- ``docs/phases/02-context-gather-layers-b-g/stories/_validation/S4-03-scip-index-probe.md``
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #3 + #5, §"Edge cases" row 4
- ``docs/phases/02-context-gather-layers-b-g/ADRs/``
  ``0001-add-docker-and-security-cli-tools-to-allowed-binaries.md``
- ``docs/phases/02-context-gather-layers-b-g/ADRs/``
  ``0006-index-freshness-sum-type-location.md``
- ``docs/localv2.md §5.2 B1``
"""

from __future__ import annotations

import datetime as _dt
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final, Literal

import structlog
from pydantic import BaseModel, ConfigDict, ValidationError

from codegenie import exec as _exec
from codegenie.errors import (
    ProbeTimeoutError,
    ToolMissingError,
)
from codegenie.exec.tool_versions import resolve_tool_version_sync
from codegenie.hashing import content_hash, identity_hash
from codegenie.logging import (
    EVENT_PROBE_FAILURE,
    EVENT_PROBE_START,
    EVENT_PROBE_SUCCESS,
)
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.layer_b.scip_slice import SemanticIndexSlice
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = [
    "ScipIndexProbe",
]


_log = structlog.get_logger(__name__)


# Phase 0 forbidden-patterns hook bans bare ``assert`` in src/; this constant
# is verified by a unit test (T-12) rather than at import time. The
# ``raise AssertionError`` precedent from S4-01 is the fallback safety belt.
_WARNING_IDS: Final[frozenset[str]] = frozenset(
    {
        "scip_index.timeout",
        "scip_index.exit_nonzero",
        "scip_index.tool_missing",
        "scip_index.head_unresolvable",
        "scip_index.raw_artifact_dir_unwritable",
        "scip_index.summary_json_unavailable",
    }
)


_INDEXABLE_SUFFIXES: Final[frozenset[str]] = frozenset({".ts", ".tsx"})
_EXCLUDE_DIRS: Final[frozenset[str]] = frozenset({"node_modules", "dist", "build", ".git"})
_PROBE_ID: Final[ProbeId] = ProbeId("scip_index")
_SCIP_BINARY: Final[str] = "scip-typescript"
_GIT_HEAD_TIMEOUT_S: Final[float] = 5.0
_SCIP_TIMEOUT_S: Final[int] = 300
_STDERR_TAIL_BYTES: Final[int] = 4096
_BASE_VERSION: Final[str] = "0.1.0"


# ---------------------------------------------------------------------------
# Pure helpers (functional core)
# ---------------------------------------------------------------------------


def _read_exclude_file(root: Path) -> frozenset[str]:
    """Read ``.codegenie/exclude.txt`` if present; return relative-path
    prefixes to exclude. Tolerant: returns an empty frozenset if the file
    is missing or unreadable."""
    exclude_path = root / ".codegenie" / "exclude.txt"
    if not exclude_path.is_file():
        return frozenset()
    try:
        lines = exclude_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return frozenset()
    return frozenset(line.strip() for line in lines if line.strip() and not line.startswith("#"))


def _walk_indexable_files(root: Path) -> Iterator[Path]:
    """Yield every ``.ts``/``.tsx`` file under *root*, excluding the canonical
    exclude dirs and any path listed in ``.codegenie/exclude.txt``.

    The single shared walker for ``_count_indexable_files`` AND
    ``_compute_indexable_merkle`` — divergence is mechanically impossible
    (AC-9 consistency invariant). Yields paths in sorted order so the
    Merkle and golden-file consumers see a deterministic walk.
    """
    user_excludes = _read_exclude_file(root)
    matches: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in _INDEXABLE_SUFFIXES:
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(part in _EXCLUDE_DIRS for part in rel.parts):
            continue
        rel_str = rel.as_posix()
        if any(rel_str == ex or rel_str.startswith(f"{ex}/") for ex in user_excludes):
            continue
        matches.append(path)
    matches.sort(key=lambda p: p.as_posix())
    yield from matches


def _count_indexable_files(root: Path) -> int:
    """Count ``.ts``/``.tsx`` files under *root* via the shared walker.

    Restricted to TypeScript-only because that is ``scip-typescript``'s
    program scope (per ``localv2.md §5.2 B1``). ``.js``/``.jsx`` are
    S4-04's ``TreeSitterImportGraphProbe`` concern; counting them here
    would make B2's ``Stale(CoverageGap)`` fire on every healthy mixed
    JS+TS repo.
    """
    return sum(1 for _ in _walk_indexable_files(root))


def _compute_indexable_merkle(root: Path) -> str:
    """BLAKE3 over the sorted ``(rel-path, content-hash)`` pairs of every
    indexable file under *root*. Not directly in the cache key (the
    ``content_hash_of_inputs`` channel over ``declared_inputs_for`` already
    covers this) but used as a structural invariant and future-proofing.
    """
    payload: list[str] = []
    for path in _walk_indexable_files(root):
        rel = path.relative_to(root).as_posix()
        payload.append(f"{rel}\x1f{content_hash(path)}")
    return identity_hash(*payload)


def _build_scip_argv(repo_root: Path, blob_path: Path) -> list[str]:
    """Compose the ``scip-typescript`` argv (pure helper for T-02)."""
    return [
        _SCIP_BINARY,
        "index",
        "--cwd",
        str(repo_root),
        "--output",
        str(blob_path),
        "--infer-tsconfig",
    ]


class _ScipSummary(BaseModel):
    """Tolerant parser for ``scip-typescript --summary-json`` stdout.

    All fields are optional; ``extra="ignore"`` so a newer ``scip-typescript``
    version that adds fields will not break the parse. The probe falls back
    to derived counts when fields are absent.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    files_indexed: int | None = None
    indexer_warnings: int | None = None
    any_type_density: float | None = None
    unresolved_dynamic_imports: int | None = None
    unresolved_computed_access: int | None = None
    symbol_count: int | None = None
    exported_symbols: int | None = None


def _parse_summary_json(stdout: bytes) -> _ScipSummary | None:
    """Parse ``--summary-json`` stdout; return ``None`` on parse failure so
    the caller can emit the ``summary_json_unavailable`` warning."""
    if not stdout.strip():
        return None
    try:
        return _ScipSummary.model_validate_json(stdout)
    except ValidationError:
        return None
    except ValueError:  # JSON decode failure
        return None


# ---------------------------------------------------------------------------
# Probe class (imperative shell)
# ---------------------------------------------------------------------------


@register_probe(heaviness="heavy")
class ScipIndexProbe(Probe):
    """Layer B — SCIP semantic-index probe.

    Heavy-tier (dispatched first under the coordinator's semaphore per
    02-ADR-0003). Emits the ``semantic_index`` slice + writes both the
    binary ``.scip`` blob AND the ``scip.json`` sidecar B2 consumes.
    """

    name: str = "scip_index"
    layer = "B"
    tier = "base"
    applies_to_languages: list[str] = ["javascript", "typescript"]
    applies_to_tasks: list[str] = ["*"]
    requires: list[str] = ["language_detection", "node_build_system"]
    timeout_seconds: int = _SCIP_TIMEOUT_S
    cache_strategy: Literal["content"] = "content"
    declared_inputs: list[str] = [
        "**/*.ts",
        "**/*.tsx",
        "tsconfig.json",
        "tsconfig.*.json",
        "package.json",
    ]

    @property
    def version(self) -> str:
        """Version string rolling in the resolved ``scip-typescript`` version.

        Routed through :func:`codegenie.exec.tool_versions.resolve_tool_version_sync`
        so the cache-key tuple at ``cache/keys.py:146`` reflects tool-version
        changes automatically — a ``scip-typescript`` upgrade invalidates
        the cache with zero new mechanism (AC-2 rationale).
        """
        resolved = resolve_tool_version_sync(_SCIP_BINARY)
        return f"{_BASE_VERSION}+{_SCIP_BINARY}-{resolved}"

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        _log.info(EVENT_PROBE_START, probe=self.name)
        t0 = time.perf_counter()
        last_indexed_at = _dt.datetime.now(_dt.UTC).isoformat()
        files_in_repo = _count_indexable_files(repo.root)
        last_indexed_commit = await _resolve_head(repo.root)
        head_warning = last_indexed_commit is None
        commit_str = last_indexed_commit if last_indexed_commit is not None else "unknown"

        raw_dir = ctx.output_dir / "raw"
        try:
            raw_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return self._emit_unwritable_dir(
                files_in_repo=files_in_repo,
                last_indexed_commit=commit_str,
                last_indexed_at=last_indexed_at,
                head_warning=head_warning,
                t0=t0,
            )

        blob_path = raw_dir / "scip-index.scip"
        json_path = raw_dir / "scip.json"
        scip_index_uri = blob_path.relative_to(repo.root).as_posix()
        argv = _build_scip_argv(repo.root, blob_path)

        warnings: list[str] = []
        if head_warning:
            warnings.append("scip_index.head_unresolvable")

        try:
            result = await _exec.run_external_cli(
                _PROBE_ID,
                argv,
                cwd=repo.root,
                timeout_s=_SCIP_TIMEOUT_S,
                max_stdout_bytes=64 * 1024 * 1024,
            )
        except ProbeTimeoutError:
            return self._emit_failure_slice(
                warning_id="scip_index.timeout",
                indexer_version=_safe_indexer_version(),
                files_in_repo=files_in_repo,
                last_indexed_commit=commit_str,
                last_indexed_at=last_indexed_at,
                scip_index_uri=scip_index_uri,
                blob_path=blob_path,
                json_path=json_path,
                extra_warnings=warnings,
                t0=t0,
            )
        except ToolMissingError:
            return self._emit_failure_slice(
                warning_id="scip_index.tool_missing",
                indexer_version="unknown",
                files_in_repo=files_in_repo,
                last_indexed_commit=commit_str,
                last_indexed_at=last_indexed_at,
                scip_index_uri=scip_index_uri,
                blob_path=blob_path,
                json_path=json_path,
                extra_warnings=warnings,
                t0=t0,
            )

        if result.returncode != 0:
            stderr_tail = result.stderr[-_STDERR_TAIL_BYTES:].decode("utf-8", errors="replace")
            _log.warning(
                "scip_index.exit_nonzero",
                returncode=result.returncode,
                stderr_tail=stderr_tail,
            )
            return self._emit_failure_slice(
                warning_id="scip_index.exit_nonzero",
                indexer_version=_safe_indexer_version(),
                files_in_repo=files_in_repo,
                last_indexed_commit=commit_str,
                last_indexed_at=last_indexed_at,
                scip_index_uri=scip_index_uri,
                blob_path=blob_path,
                json_path=json_path,
                extra_warnings=warnings,
                t0=t0,
            )

        summary = _parse_summary_json(result.stdout)
        if summary is None:
            warnings.append("scip_index.summary_json_unavailable")
            files_indexed = files_in_repo
            indexer_warnings = 0
            optional_fields: dict[str, Any] = {}
        else:
            files_indexed = (
                summary.files_indexed if summary.files_indexed is not None else files_in_repo
            )
            indexer_warnings = summary.indexer_warnings or 0
            optional_fields = {
                "any_type_density": summary.any_type_density,
                "unresolved_dynamic_imports": summary.unresolved_dynamic_imports,
                "unresolved_computed_access": summary.unresolved_computed_access,
                "symbol_count": summary.symbol_count,
                "exported_symbols": summary.exported_symbols,
            }

        coverage_pct = round(files_indexed / files_in_repo * 100, 1) if files_in_repo > 0 else 0.0

        slice_ = SemanticIndexSlice(
            scip_index_uri=scip_index_uri,
            indexer="scip-typescript",
            indexer_version=_safe_indexer_version(),
            files_indexed=files_indexed,
            files_in_repo=files_in_repo,
            coverage_pct=coverage_pct,
            last_indexed_commit=commit_str,
            last_indexed_at=last_indexed_at,
            indexer_errors=0,
            indexer_warnings=indexer_warnings,
            **{k: v for k, v in optional_fields.items() if v is not None},
        )

        json_path.write_text(slice_.model_dump_json(exclude_none=True, indent=2), encoding="utf-8")

        confidence: Literal["high", "medium", "low"]
        if files_in_repo == 0 or head_warning:
            confidence = "low"
        else:
            confidence = "high"

        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        _log.info(
            EVENT_PROBE_SUCCESS,
            probe=self.name,
            tool_version=_safe_indexer_version(),
            files_indexed=files_indexed,
            files_in_repo=files_in_repo,
            duration_s=duration_ms / 1000,
        )
        return ProbeOutput(
            schema_slice={"semantic_index": slice_.model_dump(mode="json", exclude_none=True)},
            raw_artifacts=[blob_path, json_path],
            confidence=confidence,
            duration_ms=duration_ms,
            warnings=warnings,
            errors=[],
        )

    # ------------------------------------------------------------------
    # Imperative-shell helpers (kept on the class so they share the slice
    # construction shape; module-level helpers would duplicate the seven-
    # parameter signature).
    # ------------------------------------------------------------------

    def _emit_unwritable_dir(
        self,
        *,
        files_in_repo: int,
        last_indexed_commit: str,
        last_indexed_at: str,
        head_warning: bool,
        t0: float,
    ) -> ProbeOutput:
        warnings: list[str] = []
        if head_warning:
            warnings.append("scip_index.head_unresolvable")
        # See _emit_failure_slice: zero out files_in_repo so B2 reads IndexerError.
        del files_in_repo  # intentionally unused on the dir-unwritable short-circuit
        slice_ = SemanticIndexSlice(
            scip_index_uri="",
            indexer="scip-typescript",
            indexer_version=_safe_indexer_version(),
            files_indexed=0,
            files_in_repo=0,
            coverage_pct=0.0,
            last_indexed_commit=last_indexed_commit,
            last_indexed_at=last_indexed_at,
            indexer_errors=1,
            indexer_warnings=0,
        )
        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        _log.warning(EVENT_PROBE_FAILURE, probe=self.name, reason="raw_artifact_dir_unwritable")
        return ProbeOutput(
            schema_slice={"semantic_index": slice_.model_dump(mode="json", exclude_none=True)},
            raw_artifacts=[],
            confidence="low",
            duration_ms=duration_ms,
            warnings=warnings,
            errors=["scip_index.raw_artifact_dir_unwritable"],
        )

    def _emit_failure_slice(
        self,
        *,
        warning_id: str,
        indexer_version: str,
        files_in_repo: int,
        last_indexed_commit: str,
        last_indexed_at: str,
        scip_index_uri: str,
        blob_path: Path,
        json_path: Path,
        extra_warnings: list[str],
        t0: float,
    ) -> ProbeOutput:
        """Build the failure slice and write the sidecar JSON B2 must read.

        On every failure path we (a) delete any partial ``.scip`` blob so
        Phase 3's adapter never sees corrupt bytes, and (b) write
        ``scip.json`` with ``indexer_errors=1`` so B2's check emits the
        correct typed ``Stale(IndexerError(...))`` rather than the wrong
        ``upstream_scip_unavailable`` signal.
        """
        if blob_path.exists():
            try:
                blob_path.unlink()
            except OSError:
                pass

        # files_in_repo set to 0 on every failure path so B2's scip_freshness
        # check fires the typed Stale(IndexerError(...)) — not Stale(CoverageGap(...)).
        # The freshness check evaluates coverage BEFORE indexer_errors, so a
        # mismatched (0, N) pair would surface as CoverageGap and mask the
        # true "indexer ran but failed" signal AC-6/AC-7/AC-8 require.
        del files_in_repo  # parameter kept for symmetry; intentionally unused on failure
        slice_ = SemanticIndexSlice(
            scip_index_uri=scip_index_uri,
            indexer="scip-typescript",
            indexer_version=indexer_version,
            files_indexed=0,
            files_in_repo=0,
            coverage_pct=0.0,
            last_indexed_commit=last_indexed_commit,
            last_indexed_at=last_indexed_at,
            indexer_errors=1,
            indexer_warnings=0,
        )
        json_path.write_text(slice_.model_dump_json(exclude_none=True, indent=2), encoding="utf-8")
        warnings = [*extra_warnings, warning_id]
        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        _log.warning(EVENT_PROBE_FAILURE, probe=self.name, reason=warning_id)
        return ProbeOutput(
            schema_slice={"semantic_index": slice_.model_dump(mode="json", exclude_none=True)},
            raw_artifacts=[json_path],
            confidence="low",
            duration_ms=duration_ms,
            warnings=warnings,
            errors=[],
        )


# ---------------------------------------------------------------------------
# Module-level helpers (HEAD resolution + safe indexer-version read)
# ---------------------------------------------------------------------------


async def _resolve_head(repo_root: Path) -> str | None:
    """Run ``git rev-parse HEAD`` via the Phase-0 chokepoint; return the SHA
    or ``None`` on any failure surface."""
    try:
        result = await _exec.run_allowlisted(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, timeout_s=_GIT_HEAD_TIMEOUT_S
        )
    except (
        ToolMissingError,
        ProbeTimeoutError,
        FileNotFoundError,
        NotADirectoryError,
    ):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8").strip()


def _safe_indexer_version() -> str:
    """Return the resolved ``scip-typescript`` version suffix (post ``+``)
    or ``"unknown"`` if the resolver returned no recognizable version.

    Always safe to read — the resolver never raises on tool-missing, and
    we strip the ``<base>+<binary>-`` prefix here so the slice's
    ``indexer_version`` field is just the upstream version string.
    """
    resolved = resolve_tool_version_sync(_SCIP_BINARY)
    return resolved if resolved else "unknown"
