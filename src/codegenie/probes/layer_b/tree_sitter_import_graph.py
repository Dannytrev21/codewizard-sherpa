"""``TreeSitterImportGraphProbe`` (B3, S4-04) — file-level import edges.

Walks every ``.ts``/``.tsx``/``.js``/``.jsx`` file under the repo, runs a
tree-sitter ``Query`` against the parsed AST, and emits forward-only
``Edge(from, to)`` rows to ``.codegenie/context/raw/import-graph.json``.
Phase 3's ``ImportGraphAdapter`` consumes the JSON; reverse projection
is *not* this probe's job.

Grammar loading goes through :func:`codegenie.grammars.lock.language_for`
(02-ADR-0011 — supersedes the pinned-vendored-``.so`` model of
02-ADR-0002). The probe does NOT import ``tree_sitter_typescript`` /
``tree_sitter_javascript`` directly: the kernel is the single chokepoint
where adding Phase 8's Python grammar is a one-line ``_DISPATCH`` entry
with zero edits on the consumer side.

**Discipline — no internal parallelism.** The probe holds *one* slot
under the coordinator's ``Semaphore(min(cpu_count(), 8))``; hidden
parallelism (``ThreadPoolExecutor`` / ``asyncio.gather`` /
``loop.run_in_executor``) would lie to the budget. Per-file extraction
is a synchronous ``for`` loop inside an ``async def`` shell whose single
``await`` is the :func:`asyncio.wait_for` timeout boundary in
:meth:`TreeSitterImportGraphProbe.run`.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S4-04-tree-sitter-import-graph.md``
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0002-tree-sitter-grammars-phase-2-amendment.md``
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0011-tree-sitter-grammars-via-pypi-wheels.md``
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0003-coordinator-heaviness-sort-annotation.md``
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import time
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, TypeAlias

import structlog
from pydantic import BaseModel, ConfigDict, Field

from codegenie.grammars.lock import GrammarLoadRefused, SupportedLanguage, language_for
from codegenie.logging import EVENT_PROBE_START, EVENT_PROBE_SUCCESS
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot, Task
from codegenie.probes.language_filter import _admits_node_project
from codegenie.probes.layer_b._indexable_files import _NODE_SOURCE_SUFFIXES, _walk_source_files
from codegenie.probes.registry import register_probe

if TYPE_CHECKING:
    from tree_sitter import Language

__all__ = ["Edge", "ImportGraphArtifact", "TreeSitterImportGraphProbe"]


_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Module-level constants (AC-11 — ADR-0007 ID pattern check at import time)
# ---------------------------------------------------------------------------


_WARNING_IDS: Final[frozenset[str]] = frozenset(
    {
        "tree_sitter.file_parse_failed",
        "tree_sitter.parse_failed_count_exceeded",
        "tree_sitter.no_files_to_parse",
        "tree_sitter.file_too_large",
        "tree_sitter.timeout",
    }
)
_ERROR_IDS: Final[frozenset[str]] = frozenset(
    {
        "tree_sitter.grammar_pin_mismatch",
    }
)
_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
for _id in _WARNING_IDS | _ERROR_IDS:
    if not _ID_PATTERN.match(_id):
        raise AssertionError(f"ADR-0007 violation: {_id!r}")


_FILE_MAX_BYTES: Final[int] = 4 * 1024 * 1024
"""Per-file ceiling — skip rather than hand a 50-MB bundled artifact
to tree-sitter and risk OOMing the gather process (would defeat
AC-12 timeout containment)."""

_WARNING_CAP: Final[int] = 5
"""Per-distinct-warning cap — past five files emitting the same
warning we collapse to a single summary record. Without the cap a
broken corpus floods the slice."""


_SOURCE_SUFFIX_TO_LANGUAGE: Final[Mapping[str, SupportedLanguage]] = {
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
}


_GRAMMAR_PACKAGES: Final[Mapping[SupportedLanguage, str]] = {
    "typescript": "tree-sitter-typescript",
    "tsx": "tree-sitter-typescript",
    "javascript": "tree-sitter-javascript",
}


# Tree-sitter Query strings — four patterns total. ``string`` captures
# include quotes; the post-walk strips them. Module-level constants so
# they compile once per (language, query) at run() entry.
_TS_IMPORT_QUERY: Final[str] = """
(import_statement source: (string) @specifier)
(export_statement source: (string) @specifier)
(call_expression
  function: (identifier) @fn
  arguments: (arguments (string) @specifier)
  (#eq? @fn "require"))
(call_expression
  function: (import)
  arguments: (arguments (string) @specifier))
""".strip()

_JS_IMPORT_QUERY: Final[str] = _TS_IMPORT_QUERY


_Confidence: TypeAlias = Literal["high", "medium", "low"]


# ---------------------------------------------------------------------------
# Typed model boundary (AC-5 / AC-6) — newtype discipline for the
# import-graph payload. Pydantic frozen + extra="forbid" so the writer
# chokepoint stays strict and a schema drift fails loud at validation.
# ---------------------------------------------------------------------------


class Edge(BaseModel):
    """One forward-only adjacency row.

    ``from_path`` is the in-repo POSIX path of the importing file;
    ``to`` is the specifier exactly as it appears in source (no
    resolution to a filesystem path — that's Phase 3 territory).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)
    from_path: str = Field(alias="from")
    to: str


class ImportGraphArtifact(BaseModel):
    """The on-disk shape of ``raw/import-graph.json``.

    ``schema_version`` is bumped only by an ADR-amending story. A
    future field-add lives here so callers can pattern-match on shape.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = 1
    edges: list[Edge]


# Sentinel exception types for the per-file shell — never escape ``run()``.
class _PerFileTooLarge(Exception):
    """Raised by the shell helper when a file exceeds :data:`_FILE_MAX_BYTES`."""


class _PerFileParseFailed(Exception):
    """Raised by the shell helper when tree-sitter cannot parse a file."""


# ---------------------------------------------------------------------------
# Pure helpers (functional core — no I/O, no ctx, no logging)
# ---------------------------------------------------------------------------


def _strip_quotes(literal: str) -> str:
    """Strip a single layer of matching JS/TS string quotes."""
    if len(literal) >= 2 and literal[0] == literal[-1] and literal[0] in ("'", '"', "`"):
        return literal[1:-1]
    return literal


def _extract_imports(language: Language, source_bytes: bytes, relative_path: str) -> list[Edge]:
    """Parse *source_bytes* and emit one :class:`Edge` per import-like
    statement. Pure: zero I/O, zero logging.

    The caller owns the shell concerns (file I/O, size gate); this
    helper assumes pre-loaded inputs so it can be unit-tested against
    in-memory byte strings.
    """
    from tree_sitter import Parser, Query, QueryCursor

    parser = Parser(language)
    tree = parser.parse(source_bytes)
    if tree.root_node.has_error:
        raise _PerFileParseFailed
    query = Query(language, _TS_IMPORT_QUERY)
    edges: list[Edge] = []
    seen: set[tuple[str, str]] = set()
    for _match_id, captures in QueryCursor(query).matches(tree.root_node):
        nodes = captures.get("specifier", [])
        for node in nodes:
            node_text = node.text
            if node_text is None:
                continue
            try:
                raw_text = node_text.decode("utf-8")
            except UnicodeDecodeError:
                continue
            specifier = _strip_quotes(raw_text)
            if not specifier:
                continue
            key = (relative_path, specifier)
            if key in seen:
                continue
            seen.add(key)
            edges.append(Edge(**{"from": relative_path, "to": specifier}))
    return edges


def _read_and_extract(path: Path, language: Language, relative_path: str) -> list[Edge]:
    """Shell over :func:`_extract_imports` — owns the per-file IO + size
    gate + parse-error gate. Every failure escalates to a sentinel
    exception the caller maps to one ``failed_files`` increment plus
    one warning-ID accumulation."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise _PerFileParseFailed from exc
    if size > _FILE_MAX_BYTES:
        raise _PerFileTooLarge
    try:
        source_bytes = path.read_bytes()
    except OSError as exc:
        raise _PerFileParseFailed from exc
    try:
        return _extract_imports(language, source_bytes, relative_path)
    except _PerFileParseFailed:
        raise
    except Exception as exc:
        raise _PerFileParseFailed from exc


def _accumulate_warning(counts: dict[str, int], warnings: list[str], warning_id: str) -> None:
    """Per-warning ≤ :data:`_WARNING_CAP` discipline (AC-8 / AC-LARGE).

    Past five distinct ``warning_id`` records, we collapse subsequent
    ones into a single ``tree_sitter.parse_failed_count_exceeded``
    summary warning so the slice stays bounded.
    """
    counts[warning_id] = counts.get(warning_id, 0) + 1
    if counts[warning_id] <= _WARNING_CAP:
        if warning_id not in warnings:
            warnings.append(warning_id)
    elif "tree_sitter.parse_failed_count_exceeded" not in warnings:
        warnings.append("tree_sitter.parse_failed_count_exceeded")


def _derive_confidence(
    parsed_files: int, failed_files: int, *, refused: bool, timed_out: bool
) -> _Confidence:
    """Discrete rubric per AC-7. No thresholds, no arithmetic ratios."""
    if refused or timed_out:
        return "low"
    if parsed_files == 0:
        return "low"
    if failed_files == 0:
        return "high"
    if parsed_files >= failed_files:
        return "medium"
    return "low"


def _grammar_versions() -> dict[str, str]:
    """Read the installed grammar wheel versions via ``importlib.metadata``.

    The wheels carry the supply-chain pin (``pip --require-hashes``);
    surfacing the version in the slice gives Phase 3 a stable provenance
    string.
    """
    versions: dict[str, str] = {}
    for language, package in _GRAMMAR_PACKAGES.items():
        if language == "tsx":
            continue
        try:
            versions[language] = _pkg_version(package)
        except PackageNotFoundError:  # pragma: no cover — wheel is in [project.dependencies]
            continue
    return versions


# ---------------------------------------------------------------------------
# Probe class (imperative shell)
# ---------------------------------------------------------------------------


@register_probe(heaviness="medium")
class TreeSitterImportGraphProbe(Probe):
    """Layer B — file-level import-edge extractor (medium heaviness).

    One probe slot under the coordinator's semaphore; per-file work is
    synchronous; the single asyncio coordination point is
    :func:`asyncio.wait_for` at the :meth:`run` boundary."""

    name: str = "tree_sitter_import_graph"
    version: str = "0.1.0"
    layer = "B"
    tier = "base"
    applies_to_languages: list[str] = ["javascript", "typescript"]
    applies_to_tasks: list[str] = ["*"]
    requires: list[str] = ["language_detection"]
    timeout_seconds: int = 120
    cache_strategy: Literal["content"] = "content"
    declared_inputs: list[str] = [
        "**/*.ts",
        "**/*.tsx",
        "**/*.js",
        "**/*.jsx",
    ]

    def applies(self, repo: RepoSnapshot, task: Task) -> bool:
        return _admits_node_project(self.applies_to_languages, repo.detected_languages, repo.root)

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        _log.info(EVENT_PROBE_START, probe=self.name)
        t0 = time.perf_counter()

        # 1. Grammar load — through the kernel; only failure type is
        #    GrammarLoadRefused. No grammar code runs on refusal.
        try:
            languages: dict[SupportedLanguage, Language] = {
                "typescript": language_for("typescript"),
                "tsx": language_for("tsx"),
                "javascript": language_for("javascript"),
            }
        except GrammarLoadRefused as exc:
            return self._emit_grammar_refused(reason=str(exc), t0=t0)

        # 2. Per-file extraction inside an async-cancellable inner coroutine
        #    so wait_for can cancel us at timeout. The body is synchronous.
        accumulator: _Accumulator = _Accumulator()
        try:
            await asyncio.wait_for(
                self._parse_all(repo, languages, accumulator),
                timeout=self.timeout_seconds,
            )
            timed_out = False
        except TimeoutError:
            timed_out = True
            _accumulate_warning(
                accumulator.warning_counts, accumulator.warnings, "tree_sitter.timeout"
            )

        # 3. Determinism — lex-sort edges by (from, to).
        accumulator.edges.sort(key=lambda e: (e.from_path, e.to))

        # 4. Empty-repo guard (AC-9).
        if accumulator.parsed == 0 and accumulator.failed == 0 and not timed_out:
            _accumulate_warning(
                accumulator.warning_counts,
                accumulator.warnings,
                "tree_sitter.no_files_to_parse",
            )

        # 5. Artifact write — atomic; omitted on zero edges.
        artifact_uri: str | None = None
        artifacts: list[Path] = []
        if accumulator.edges:
            artifact_path = ctx.output_dir / "raw" / "import-graph.json"
            _atomic_write_artifact(artifact_path, ImportGraphArtifact(edges=accumulator.edges))
            artifacts.append(artifact_path)
            artifact_uri = ".codegenie/context/raw/import-graph.json"

        # 6. Slice.
        confidence = _derive_confidence(
            accumulator.parsed, accumulator.failed, refused=False, timed_out=timed_out
        )
        slice_payload: dict[str, Any] = {
            "files_with_imports": len({e.from_path for e in accumulator.edges}),
            "total_edges": len(accumulator.edges),
            "parsed_files": accumulator.parsed,
            "failed_files": accumulator.failed,
            "confidence": confidence,
            "grammar_versions": _grammar_versions(),
        }
        if artifact_uri is not None:
            slice_payload["import_graph_uri"] = artifact_uri

        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        _log.info(
            EVENT_PROBE_SUCCESS,
            probe=self.name,
            parsed_files=accumulator.parsed,
            failed_files=accumulator.failed,
            total_edges=len(accumulator.edges),
            confidence=confidence,
        )
        return ProbeOutput(
            schema_slice={"import_graph": slice_payload},
            raw_artifacts=artifacts,
            confidence=confidence,
            duration_ms=duration_ms,
            warnings=sorted(set(accumulator.warnings)),
            errors=[],
        )

    async def _parse_all(
        self,
        repo: RepoSnapshot,
        languages: Mapping[SupportedLanguage, Language],
        acc: _Accumulator,
    ) -> None:
        """Sequential per-file walk inside an ``async def`` shell so the
        outer ``asyncio.wait_for`` can cancel us at timeout. Mutates
        *acc* in place — partial progress survives cancellation."""
        for path in _walk_source_files(repo.root, _NODE_SOURCE_SUFFIXES):
            language_name = _SOURCE_SUFFIX_TO_LANGUAGE[path.suffix]
            language = languages[language_name]
            relative_path = path.relative_to(repo.root).as_posix()
            try:
                file_edges = _read_and_extract(path, language, relative_path)
            except _PerFileTooLarge:
                acc.failed += 1
                _accumulate_warning(acc.warning_counts, acc.warnings, "tree_sitter.file_too_large")
                continue
            except _PerFileParseFailed:
                acc.failed += 1
                _accumulate_warning(
                    acc.warning_counts, acc.warnings, "tree_sitter.file_parse_failed"
                )
                continue
            acc.edges.extend(file_edges)
            acc.parsed += 1

    def _emit_grammar_refused(self, *, reason: str, t0: float) -> ProbeOutput:
        """AC-3 / AC-10 honest-absence slice. No grammar code executes;
        no artifact is written."""
        _log.warning("probe.failure", probe=self.name, reason=reason)
        slice_payload: dict[str, Any] = {
            "files_with_imports": 0,
            "total_edges": 0,
            "parsed_files": 0,
            "failed_files": 0,
            "confidence": "low",
        }
        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        return ProbeOutput(
            schema_slice={"import_graph": slice_payload},
            raw_artifacts=[],
            confidence="low",
            duration_ms=duration_ms,
            warnings=[],
            errors=["tree_sitter.grammar_pin_mismatch"],
        )


# ---------------------------------------------------------------------------
# Accumulator + atomic-write helper (internal — never observed by callers)
# ---------------------------------------------------------------------------


class _Accumulator:
    """Mutable accumulator for the per-file walk.

    Not a Pydantic model — we need cheap in-place mutation and
    ``run()`` translates it to the typed ``ProbeOutput`` shape at the
    boundary. The discipline (don't leak ``_Accumulator`` past
    ``run()``) is encoded by class privacy + ``__all__`` omission.
    """

    __slots__ = ("edges", "failed", "parsed", "warning_counts", "warnings")

    def __init__(self) -> None:
        self.edges: list[Edge] = []
        self.parsed: int = 0
        self.failed: int = 0
        self.warnings: list[str] = []
        self.warning_counts: dict[str, int] = {}


def _atomic_write_artifact(target: Path, artifact: ImportGraphArtifact) -> None:
    """Write *artifact* to *target* atomically via tempfile + ``os.replace``.

    The intermediate ``.tmp`` is replaced atomically on success; on
    failure the tempfile is unlinked so no half-written sibling
    survives. Phase 3 readers never observe a half-written JSON.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = artifact.model_dump(by_alias=True)
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fd, tmp_path_str = tempfile.mkstemp(
        prefix="import-graph.json.", suffix=".tmp", dir=str(target.parent)
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(rendered)
        os.replace(tmp_path, target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
