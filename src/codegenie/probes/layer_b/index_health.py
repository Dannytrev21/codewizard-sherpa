"""``IndexHealthProbe`` (B2, S4-01) — registry-dispatched freshness loop.

Phase 2's load-bearing citizen. Silent index staleness is the worst failure
mode of the entire system: a ``RepoContext`` slice that *says* it's current
but isn't propagates wrong evidence through every downstream consumer (the
Planner, the renderer, the Phase-3 plugin, every adapter). B2 is what makes
the architecture's "honest confidence" commitment (``docs/production/design.md
§2.3``) real.

**Two load-bearing disciplines** (must not erode):

1. ``cache_strategy="none"``. B2 observes a *moving* fact (``git rev-parse
   HEAD`` vs. each sibling's recorded ``last_indexed_commit``). Caching that
   is "the same bug as caching ``Date.now()``" — the
   ``scripts/check_forbidden_patterns.py`` rule scoped to this file bans the
   four mtime-derived signals (``getmtime``, ``stat`` / ``lstat`` ``mtime``
   property accesses). Mtime is not a freshness signal.
2. ``runs_last=True``. B2 reads sibling slices from
   ``<repo>/.codegenie/context/raw/*.json``; those siblings must have written
   their raw artifacts before B2 reads them. Enforced by the registry's
   ``runs_last`` annotation (02-ADR-0003), not by ``requires=`` topology —
   B2 depends on sibling *outputs*, not sibling *execution*.

**Open/Closed at the file boundary** (Gap 3 / DP1). The ``run()`` body
contains zero ``if index_name == "..."`` branches. Every per-index decision
lives inside a registered ``@register_index_freshness_check`` function in
its own owning module:

- ``scip``: colocated here (S4-01).
- ``runtime_trace``: ``codegenie.probes.layer_c.runtime_trace`` (S5-05).
- ``semgrep`` / ``gitleaks`` / ``conventions``: their owning probe modules
  (S6-08).

Adding a Phase-3 index source is a new module + a new ``@register_index_
freshness_check`` decoration — **never** an edit to this file.

**Producer / consumer ``assert_never`` ladder** (DP3). This module is the
*producer* of :class:`~codegenie.indices.freshness.IndexFreshness`;
``codegenie.report.confidence_section`` (S8-01) is the *consumer*. Both ends
``match`` exhaustively with ``assert_never``; ``mypy --warn-unreachable``
enforces the discipline. Adding a new ``StaleReason`` variant requires an
ADR amendment to 02-ADR-0006 *and* coordinated edits at both ends.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S4-01-index-health-probe.md``
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md`` §"Component
  design" #1, §"Process view", §"Gap analysis" Gap 3
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0003-coordinator-heaviness-sort-annotation.md``
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md``
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import time
from pathlib import Path
from typing import Final, Literal, assert_never

import structlog

from codegenie import exec as _exec
from codegenie.errors import (
    DisallowedSubprocessError,
    ProbeTimeoutError,
    ToolMissingError,
)
from codegenie.indices.freshness import (
    CommitsBehind,
    CoverageGap,
    DigestMismatch,
    Fresh,
    IndexerError,
    IndexFreshness,
    Stale,
)
from codegenie.indices.registry import (
    default_freshness_registry,
    register_index_freshness_check,
)
from codegenie.logging import (
    EVENT_PROBE_FAILURE,
    EVENT_PROBE_START,
    EVENT_PROBE_SUCCESS,
)
from codegenie.output.paths import raw_dir
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import IndexName

__all__ = [
    "IndexHealthProbe",
    "raw_dir",
    "read_raw_slices",
    "scip_freshness",
]


_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Module-level constants (AC-14 — ADR-0007 ID pattern check at import time)
# ---------------------------------------------------------------------------


_WARNING_IDS: Final[frozenset[str]] = frozenset(
    {
        "index_health.head_unresolvable",
        "index_health.no_sources_registered",
        "index_health.commits_behind_count_unknown",
    }
)


_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


for _id in _WARNING_IDS:
    if not _ID_PATTERN.match(_id):
        raise AssertionError(f"ADR-0007 violation: {_id!r}")


_SCIP_REQUIRED_KEYS: Final[tuple[str, ...]] = (
    "last_indexed_commit",
    "files_indexed",
    "files_in_repo",
    "indexer_errors",
    "last_indexed_at",
)

_Confidence = Literal["high", "medium", "low"]
_CONFIDENCE_RANK: Final[dict[_Confidence, int]] = {"low": 0, "medium": 1, "high": 2}


# ---------------------------------------------------------------------------
# SCIP freshness check (AC-5) — registered at module import
# ---------------------------------------------------------------------------


@register_index_freshness_check(IndexName("scip"))
def scip_freshness(slice_: dict[str, object], head: str) -> IndexFreshness:
    """Pure ``(slice, head) -> IndexFreshness`` for the SCIP index source.

    Six branches per AC-5:

    - ``(a)`` empty dict (registry sentinel for absent sibling JSON) →
      ``Stale(IndexerError("upstream_scip_unavailable"))``.
    - ``(b)`` every required key present + correct types + commit matches +
      coverage matches + no indexer errors → ``Fresh(indexed_at=…)``.
    - ``(c)`` commit differs → ``Stale(CommitsBehind(n=1, last_indexed=…))``.
      ``n=1`` is the load-bearing minimum (AC-6); B2's imperative shell may
      upgrade ``n`` via ``git rev-list`` post-dispatch.
    - ``(d)`` coverage gap (commit matches but files_indexed < files_in_repo).
    - ``(e)`` indexer reported errors (commit + coverage match).
    - ``(f)`` any required key missing or wrong type →
      ``Stale(IndexerError("scip_slice_malformed"))``.

    Never raises — every code path returns a typed value.
    """
    # AC-5(a): empty dict sentinel — distinguish from "non-empty but malformed".
    if not slice_:
        return Stale(reason=IndexerError(message="upstream_scip_unavailable"))

    # AC-5(f): missing required keys or wrong types.
    last_commit = slice_.get("last_indexed_commit")
    files_indexed = slice_.get("files_indexed")
    files_in_repo = slice_.get("files_in_repo")
    indexer_errors = slice_.get("indexer_errors")
    last_indexed_at = slice_.get("last_indexed_at")

    if (
        not isinstance(last_commit, str)
        or not isinstance(files_indexed, int)
        or isinstance(files_indexed, bool)
        or not isinstance(files_in_repo, int)
        or isinstance(files_in_repo, bool)
        or not isinstance(indexer_errors, int)
        or isinstance(indexer_errors, bool)
        or not isinstance(last_indexed_at, str)
    ):
        return Stale(reason=IndexerError(message="scip_slice_malformed"))

    # AC-5(c): commit differs — return the pure default; B2 may upgrade n.
    if last_commit != head:
        return Stale(reason=CommitsBehind(n=1, last_indexed=last_commit))

    # AC-5(d): coverage gap.
    if files_indexed < files_in_repo:
        return Stale(reason=CoverageGap(files_indexed=files_indexed, files_in_repo=files_in_repo))

    # AC-5(e): indexer reported errors.
    if indexer_errors > 0:
        return Stale(reason=IndexerError(message=f"indexer_reported_{indexer_errors}_errors"))

    # AC-5(b): fresh. ``fromisoformat`` may raise on a malformed ISO string;
    # we catch that into the malformed branch so the function never raises.
    try:
        indexed_at = _dt.datetime.fromisoformat(last_indexed_at)
    except ValueError:
        return Stale(reason=IndexerError(message="scip_slice_malformed"))
    return Fresh(indexed_at=indexed_at)


# ---------------------------------------------------------------------------
# Pure helpers (functional core — DP2)
# ---------------------------------------------------------------------------


def read_raw_slices(raw_artifacts_dir: Path) -> dict[IndexName, dict[str, object]]:
    """Read every ``<index_name>.json`` under *raw_artifacts_dir*.

    Pure-by-construction: the only I/O is the directory listing + per-file
    read; the function returns a fully-realized dict. Each file that fails
    to parse OR does not decode to a top-level dict is silently omitted —
    the registered check function is responsible for its own malformed-slice
    semantics (AC-5(a) vs AC-5(f)).

    Missing *raw_artifacts_dir* returns an empty dict (defensive — happens
    on first gather before any sibling has written).
    """
    out: dict[IndexName, dict[str, object]] = {}
    if not raw_artifacts_dir.is_dir():
        return out
    for path in sorted(raw_artifacts_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        # Cast keys to str for the value type; JSON keys are already strings.
        out[IndexName(path.stem)] = {str(k): v for k, v in payload.items()}
    return out


def _derive_confidence(freshness: IndexFreshness) -> _Confidence:
    """Map a typed freshness value to a confidence label (AC-9).

    Nested exhaustive ``match`` with ``assert_never`` on each default arm so
    ``mypy --warn-unreachable`` enforces handling of every variant at BOTH
    levels (``IndexFreshness`` and ``StaleReason``). Adding a new
    ``StaleReason`` variant (ADR amendment to 02-ADR-0006) flips this
    function red until the new arm is added — the structural enforcement.
    """
    match freshness:
        case Fresh():
            return "high"
        case Stale(reason=reason):
            match reason:
                case CoverageGap(files_indexed=i, files_in_repo=t):
                    if t > 0 and (i / t) >= 0.90:
                        return "medium"
                    return "low"
                case CommitsBehind():
                    return "medium"
                case DigestMismatch():
                    return "medium"
                case IndexerError():
                    return "low"
                case _:  # pragma: no cover - exhaustiveness guard
                    assert_never(reason)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(freshness)


def _last_indexed_at(freshness: IndexFreshness) -> str | None:
    """Return the ISO-8601 ``indexed_at`` for ``Fresh``; ``None`` for every
    ``Stale`` variant (AC-10) — once stale, the recorded timestamp is no
    longer authoritative."""
    match freshness:
        case Fresh(indexed_at=ts):
            return ts.isoformat()
        case Stale():
            return None
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(freshness)


def _demote_min(confidences: list[_Confidence]) -> _Confidence | None:
    """Return the minimum confidence (``"low" < "medium" < "high"``).

    Returns ``None`` on the empty list (so callers can apply the
    "no-degraded-source-observed" default).
    """
    if not confidences:
        return None
    return min(confidences, key=lambda c: _CONFIDENCE_RANK[c])


# ---------------------------------------------------------------------------
# Imperative shell (DP2 — composes the three pure helpers + registry)
# ---------------------------------------------------------------------------


@register_probe(runs_last=True)
class IndexHealthProbe(Probe):
    """Layer B — index-freshness probe (B2).

    Dispatches to every ``@register_index_freshness_check`` function via
    :meth:`FreshnessRegistry.dispatch_all`; folds the typed results into the
    ``index_health`` slice. ``runs_last=True`` ensures B2 reads after every
    sibling has written its raw artifact.
    """

    name: str = "index_health"
    version: str = "0.1.0"
    layer = "B"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 10
    # Literal[\"none\"] is load-bearing (AC-2); the forbidden-patterns hook
    # backstops this declaration in case a contributor relaxes the annotation.
    cache_strategy: Literal["none"] = "none"
    declared_inputs: list[str] = [
        ".codegenie/context/raw/*.json",
        ".git/HEAD",
        "<scip-index-output>",
        "<image-digest-token>",
    ]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        _log.info(EVENT_PROBE_START, probe=self.name)
        t0 = time.perf_counter()

        # (1) Resolve HEAD via the Phase 0 chokepoint. Every failure is typed.
        head_result = await _resolve_head(repo.root)
        if head_result is None:
            return _emit_head_unresolvable(t0)
        head: str = head_result

        # (2) Build per-source slice dict via the pure helper (functional core).
        slices = read_raw_slices(raw_dir(repo.root))

        # (3) Dispatch — single-call no-branches enforcement (AC-4 / DP1).
        try:
            freshness_by_name = default_freshness_registry.dispatch_all(slices, head)
        except Exception:  # noqa: BLE001 — wrapping every check exception per AC-8
            freshness_by_name = _dispatch_per_name_isolated(slices, head)

        # (4) Imperative-shell enrichment: upgrade CommitsBehind.n where the
        # rev-list call succeeds. Per AC-6 a failure leaves n untouched (=1)
        # AND adds the commits_behind_count_unknown warning.
        commits_behind_warning_needed = False
        for name, freshness in list(freshness_by_name.items()):
            if isinstance(freshness, Stale) and isinstance(freshness.reason, CommitsBehind):
                upgraded_n = await _resolve_commits_behind_count(
                    repo.root, freshness.reason.last_indexed, head
                )
                if upgraded_n is None:
                    commits_behind_warning_needed = True
                else:
                    freshness_by_name[name] = Stale(
                        reason=CommitsBehind(
                            n=upgraded_n, last_indexed=freshness.reason.last_indexed
                        )
                    )

        # (5) Shape the slice (AC-10).
        results: dict[str, dict[str, object]] = {}
        per_source_confidences: list[_Confidence] = []
        for name, freshness in freshness_by_name.items():
            conf = _derive_confidence(freshness)
            per_source_confidences.append(conf)
            results[str(name)] = {
                "freshness": freshness.model_dump(mode="json"),
                "confidence": conf,
                "current_commit": head,
                "last_indexed_at": _last_indexed_at(freshness),
            }
            _log.info(
                "index_health.source",
                index_name=str(name),
                kind=freshness.kind,
                reason_kind=(freshness.reason.kind if isinstance(freshness, Stale) else None),
            )

        warnings: list[str] = []
        if not results:
            warnings.append("index_health.no_sources_registered")
        if commits_behind_warning_needed:
            warnings.append("index_health.commits_behind_count_unknown")

        envelope_confidence: _Confidence = _demote_min(per_source_confidences) or "high"

        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        _log.info(
            EVENT_PROBE_SUCCESS,
            probe=self.name,
            confidence=envelope_confidence,
            sources=len(results),
        )
        return ProbeOutput(
            schema_slice={"index_health": results},
            raw_artifacts=[],
            confidence=envelope_confidence,
            duration_ms=duration_ms,
            warnings=warnings,
            errors=[],
        )


# ---------------------------------------------------------------------------
# Imperative-shell helpers (module-level so they are independently testable
# AND so the ``run`` body stays ≤ 40 LOC + branch-free)
# ---------------------------------------------------------------------------


async def _resolve_head(repo_root: Path) -> str | None:
    """Run ``git rev-parse HEAD`` and return the SHA, or ``None`` on every
    failure surface (AC-7). The caller short-circuits on ``None``."""
    try:
        result = await _exec.run_allowlisted(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, timeout_s=5
        )
    except (
        ToolMissingError,
        ProbeTimeoutError,
        DisallowedSubprocessError,
        FileNotFoundError,
        NotADirectoryError,
    ):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8").strip()


async def _resolve_commits_behind_count(
    repo_root: Path, last_indexed: str, head: str
) -> int | None:
    """Run ``git rev-list --count <last>..<head>`` and return the parsed
    count, or ``None`` on any failure surface (AC-6 fallback signals to the
    caller to leave the structural minimum ``n=1`` and emit the warning).
    """
    try:
        result = await _exec.run_allowlisted(
            ["git", "rev-list", "--count", f"{last_indexed}..{head}"],
            cwd=repo_root,
            timeout_s=5,
        )
    except (
        ToolMissingError,
        ProbeTimeoutError,
        DisallowedSubprocessError,
        FileNotFoundError,
        NotADirectoryError,
    ):
        return None
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.decode("utf-8").strip())
    except ValueError:
        return None


def _emit_head_unresolvable(t0: float) -> ProbeOutput:
    """Build a ``ProbeOutput`` for the ``HEAD unresolvable`` short-circuit
    (AC-7). Every registered source gets the same ``IndexerError`` value;
    per-source AND envelope confidence are ``low``."""
    results: dict[str, dict[str, object]] = {}
    for name in default_freshness_registry.registered_names():
        freshness: IndexFreshness = Stale(reason=IndexerError(message="repo_not_a_git_workdir"))
        results[str(name)] = {
            "freshness": freshness.model_dump(mode="json"),
            "confidence": "low",
            "current_commit": "",
            "last_indexed_at": None,
        }
    duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
    _log.info(EVENT_PROBE_FAILURE, probe="index_health", reason="head_unresolvable")
    return ProbeOutput(
        schema_slice={"index_health": results},
        raw_artifacts=[],
        confidence="low",
        duration_ms=duration_ms,
        warnings=["index_health.head_unresolvable"],
        errors=[],
    )


def _dispatch_per_name_isolated(
    slices: dict[IndexName, dict[str, object]], head: str
) -> dict[IndexName, IndexFreshness]:
    """Per-name fallback for AC-8: ``dispatch_all`` raised, so re-dispatch
    each registered check inside its own ``try`` and substitute a typed
    ``Stale(IndexerError(...))`` for the failures. The successful checks
    keep their values, so a single misbehaving check cannot poison the map.
    """
    out: dict[IndexName, IndexFreshness] = {}
    for name in default_freshness_registry.registered_names():
        try:
            out[name] = default_freshness_registry.dispatch_one(name, slices, head)
        except Exception as exc:  # noqa: BLE001 — typed-wrap per AC-8
            out[name] = Stale(
                reason=IndexerError(
                    message=f"freshness_construction_failed_{name}_{type(exc).__name__}"
                )
            )
    return out
