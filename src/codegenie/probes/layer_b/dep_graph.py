"""``DepGraphProbe`` (B-tier, S4-05) — registry-dispatched dep-graph kernel.

The Phase-2 kernel skeleton for the Open/Closed seam Phase 3 fills with
ecosystem strategies (``build_pnpm`` / ``build_npm`` / ``build_yarn`` /
``build_bun``). Phase 2 ships **zero** strategies; every analyzed repo gets
a typed low-confidence slice with ``reason="no_strategy_for_ecosystem"``.

**Three load-bearing disciplines**:

1. **Open/Closed at the file boundary.** ``run()`` contains zero
   ``if ecosystem == "pnpm"`` branches. Every per-ecosystem decision lives
   inside a ``register_dep_graph_strategy(ecosystem)``-decorated function
   in its own Phase-3 plugin module. Adding Maven (Phase 8+) is a new
   strategy + a Phase 1 ADR-0013 amendment to extend ``PackageManager`` —
   never an edit to this file.
2. **Re-detect inline.** S4-01 established the Phase-2 sibling-read
   pattern as on-disk JSON sidecars under ``<output_dir>/raw/``, but
   ``NodeBuildSystemProbe`` does not currently write a
   ``node_build_system.json`` sidecar (S2-02 backlog). S4-05 re-detects
   ``package_manager`` inline on ``repo.root`` using the priority-1/2
   lockfile-precedence logic from
   :mod:`codegenie.probes.node_build_system`. The duplication is
   acknowledged (Rule 7) and recorded as a follow-up — either promote the
   detection to a shared helper module OR amend Phase 1 to emit a sidecar.
3. **Deterministic serialization.** ``raw/dep-graph.json`` is written via
   ``json.dumps(..., sort_keys=True, indent=2)``. Phase 3 cache stability
   depends on byte-identical reruns of the same input graph.

**Functional core / imperative shell** (DP from S4-01 precedent): every
helper is a pure function on ``Path`` + parsed manifests; ``run()`` is the
only impure code — composes the helpers and performs the single
``Path.write_bytes`` + the ``asyncio.to_thread + wait_for`` dispatch.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S4-05-dep-graph-probe.md``
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md`` §"Component
  design" #11, §"Design patterns applied" row 7.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0003-coordinator-heaviness-sort-annotation.md``
- Phase 1 ADR-0013 (``PackageManager`` Literal — re-exported by
  :mod:`codegenie.types.identifiers`).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final, Literal, cast, get_args

import networkx as nx
import structlog

from codegenie.depgraph import (
    DepGraphProbeOutput,
    default_dep_graph_registry,
)
from codegenie.logging import (
    EVENT_PROBE_START,
    EVENT_PROBE_SUCCESS,
)
from codegenie.output.paths import raw_dir
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot, Task
from codegenie.probes.language_filter import _admits_node_project
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import PackageManager

__all__ = ["DepGraphProbe"]


_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Module-level constants (AC-11 — ADR-0007 ID pattern check at import time)
# ---------------------------------------------------------------------------


_WARNING_IDS: Final[frozenset[str]] = frozenset(
    {
        "dep_graph.upstream_build_system_unavailable",
        "dep_graph.unrecognized_package_manager",
        "dep_graph.strategy_timeout",
        "dep_graph.package_manager_field_unparseable",
        "dep_graph.yarn_variant_inferred",
        "dep_graph.no_manifest_detected",
    }
)


_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


for _id in _WARNING_IDS:
    if not _ID_PATTERN.match(_id):
        raise AssertionError(f"ADR-0007 violation: {_id!r}")


# Lockfile precedence — first present wins. Mirrors the priority chain in
# :mod:`codegenie.probes.node_build_system` (Rule 7 acknowledged duplication;
# see module docstring). The ``"yarn"`` entry is RESOLVED to
# ``"yarn-classic"`` or ``"yarn-berry"`` by ``_detect_yarn_variant`` —
# readers grepping for ``"yarn"`` should not mistake this literal for the
# emitted value.
_LOCKFILE_PRECEDENCE: Final[tuple[tuple[str, str], ...]] = (
    ("bun.lockb", "bun"),
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
)


# Berry filesystem markers — priority-ordered ``(name, predicate)``. First
# hit wins; if no marker is present, the variant defaults to ``yarn-classic``
# with a ``dep_graph.yarn_variant_inferred`` warning.
_BERRY_MARKERS: Final[tuple[tuple[str, Callable[[Path], bool]], ...]] = (
    (".yarnrc.yml", lambda p: p.is_file()),
    (".yarn", lambda p: p.is_dir()),
    (".pnp.cjs", lambda p: p.is_file()),
    (".pnp.loader.mjs", lambda p: p.is_file()),
)


# ``package.json#packageManager`` field grammar. Captures ``(name, major)``
# where ``name`` is one of the four known ecosystems. A value that starts
# with one of these prefixes but doesn't match the grammar is
# ``package_manager_field_unparseable``; a value with an unknown prefix
# (e.g. ``deno@2.0.0``) is ``unrecognized_package_manager``.
_PM_FIELD_RE: Final[re.Pattern[str]] = re.compile(r"^(bun|pnpm|npm|yarn)@(\d+)\.")


_KNOWN_PM_PREFIXES: Final[frozenset[str]] = frozenset({"bun", "pnpm", "npm", "yarn"})


_KNOWN_PACKAGE_MANAGERS: Final[frozenset[str]] = frozenset(get_args(PackageManager))


# Manifest files passed to the strategy. The strategy is responsible for
# any further deep traversal (e.g. resolving pnpm-workspace packages).
_MANIFEST_FILENAMES: Final[tuple[str, ...]] = ("package.json", "pnpm-workspace.yaml")


_RAW_FILENAME: Final[str] = "dep-graph.json"


# Priority-anchor discipline (Rule 12). A refactor that flattens the
# precedence chain or reshuffles the head will fail at import time.
assert _LOCKFILE_PRECEDENCE[0][1] == "bun", (
    "S4-05 _LOCKFILE_PRECEDENCE: 'bun' must be the highest-precedence entry "
    f"(got {_LOCKFILE_PRECEDENCE[0]!r})."
)
assert _BERRY_MARKERS[0][0] == ".yarnrc.yml", (
    "S4-05 _BERRY_MARKERS: '.yarnrc.yml' must be the highest-priority Berry "
    f"marker (got {_BERRY_MARKERS[0]!r})."
)


# ---------------------------------------------------------------------------
# Functional core — pure helpers (DP2: functional core / imperative shell)
# ---------------------------------------------------------------------------


def _detect_yarn_variant(
    repo_root: Path,
    parsed_pkg: Mapping[str, Any] | None,
) -> tuple[PackageManager, list[str]]:
    """Resolve ``yarn`` to ``yarn-classic`` or ``yarn-berry``.

    Priority:
    1. ``package.json#packageManager`` matching ``^yarn@(\\d+)\\.``:
       major ``1`` → classic, major ``≥ 2`` → berry.
    2. Any Berry filesystem marker → berry.
    3. Safe default → classic + ``dep_graph.yarn_variant_inferred`` warning.

    Mirrors the priority chain in :mod:`codegenie.probes.node_build_system`'s
    ``_detect_yarn_variant`` (Rule 7 acknowledged duplication).
    """
    warnings: list[str] = []
    if parsed_pkg is not None:
        pm_field = parsed_pkg.get("packageManager")
        if isinstance(pm_field, str):
            m = _PM_FIELD_RE.match(pm_field)
            if m is not None and m.group(1) == "yarn":
                major = int(m.group(2))
                if major == 1:
                    return "yarn-classic", warnings
                if major >= 2:
                    return "yarn-berry", warnings

    for name, predicate in _BERRY_MARKERS:
        if predicate(repo_root / name):
            return "yarn-berry", warnings

    warnings.append("dep_graph.yarn_variant_inferred")
    return "yarn-classic", warnings


def _detect_package_manager(
    repo_root: Path,
    parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None,
) -> tuple[str | None, list[str], bool]:
    """Re-detect ``package_manager`` inline on the repo root.

    Returns ``(ecosystem, warnings, is_known)``:

    - ``ecosystem``: a :data:`PackageManager` Literal value when ``is_known``
      is ``True``; the verbatim ``packageManager`` field value when the
      ecosystem prefix is unknown (e.g. ``"deno@2.0.0"``) and ``is_known``
      is ``False``; ``None`` when no manifest/lockfile was found.
    - ``warnings``: detection-time warning IDs.
    - ``is_known``: ``True`` iff ``ecosystem`` is in :data:`PackageManager`.

    Priority:
    1. ``package.json#packageManager`` field (parsed via
       ``ctx.parsed_manifest``).
    2. Lockfile presence on disk (``_LOCKFILE_PRECEDENCE``); yarn lockfile
       triggers ``_detect_yarn_variant``.

    Pure given inputs except for the filesystem ``.is_file()`` /
    ``.is_dir()`` checks (which are read-only).
    """
    warnings: list[str] = []
    parsed_pkg: Mapping[str, Any] | None = None
    pkg_path = repo_root / "package.json"
    if pkg_path.is_file() and parsed_manifest is not None:
        parsed_pkg = parsed_manifest(pkg_path)

    # Priority-1: package.json#packageManager.
    if parsed_pkg is not None:
        pm_field = parsed_pkg.get("packageManager")
        if isinstance(pm_field, str) and pm_field:
            m = _PM_FIELD_RE.match(pm_field)
            if m is not None:
                name = m.group(1)
                if name == "yarn":
                    variant, yw = _detect_yarn_variant(repo_root, parsed_pkg)
                    return variant, warnings + yw, True
                return name, warnings, True
            head = pm_field.split("@", 1)[0]
            if head in _KNOWN_PM_PREFIXES:
                # Known prefix, unparseable major (e.g. "pnpm@latest").
                # Fall through to lockfile detection with a warning.
                warnings.append("dep_graph.package_manager_field_unparseable")
            else:
                # Unknown ecosystem (e.g. "deno@2.0.0").
                return pm_field, warnings, False

    # Priority-2: lockfile presence.
    present = [name for name, _ in _LOCKFILE_PRECEDENCE if (repo_root / name).is_file()]
    if not present:
        return None, warnings, False

    picked = dict(_LOCKFILE_PRECEDENCE)[present[0]]
    if picked == "yarn":
        variant, yw = _detect_yarn_variant(repo_root, parsed_pkg)
        return variant, warnings + yw, True
    return picked, warnings, True


def _construct_manifests(
    repo_root: Path,
    parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None,
) -> list[Mapping[str, Any]]:
    """Enumerate detected manifest paths and parse each via the closure.

    The probe MUST pass real parsed manifests to the strategy — a probe
    that passed an empty list would silently break Phase 3 adapters.
    Filtering ``None`` results means a malformed manifest doesn't fault
    the strategy; the strategy can still see whichever manifests parsed.
    """
    if parsed_manifest is None:
        return []
    out: list[Mapping[str, Any]] = []
    for name in _MANIFEST_FILENAMES:
        path = repo_root / name
        if not path.is_file():
            continue
        parsed = parsed_manifest(path)
        if parsed is not None:
            out.append(parsed)
    return out


def _serialize_graph(repo_root: Path, ecosystem: str | None, graph: nx.DiGraph) -> Path:
    """Write ``raw/dep-graph.json`` deterministically.

    The wrapper adds ``schema_version`` + ``ecosystem`` around NetworkX's
    native ``node_link_data`` shape so Phase 3 consumers can dispatch on
    ``ecosystem`` without re-reading the slice. ``sort_keys=True``
    canonicalizes dict-key ordering; ``indent=2`` keeps the artifact
    human-grep-friendly. Two consecutive runs against the same input
    graph produce byte-identical output (Phase 3 cache stability).
    """
    raw_path = raw_dir(repo_root) / _RAW_FILENAME
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    payload = nx.node_link_data(graph, edges="edges")
    wrapped: dict[str, Any] = {
        "schema_version": 1,
        "ecosystem": ecosystem,
        "nodes": payload.get("nodes", []),
        "edges": payload.get("edges", []),
    }
    raw_path.write_bytes(json.dumps(wrapped, sort_keys=True, indent=2).encode("utf-8"))
    return raw_path


_Confidence = Literal["high", "medium", "low"]


def _emit(
    *,
    ecosystem: str | None,
    confidence: _Confidence,
    reason: str | None,
    t0: float,
    graph_path: Path | None,
    nodes_count: int,
    edges_count: int,
    warnings: list[str],
) -> ProbeOutput:
    """Compose the :class:`ProbeOutput` from the typed model + slice echo.

    The slice echoes :class:`DepGraphProbeOutput.model_dump` (graph_path,
    confidence, reason) PLUS the count + ecosystem extras the renderer and
    Phase 3 will key on. S4-07's sub-schema pins the slice-dict shape.
    """
    model = DepGraphProbeOutput(
        graph_path=graph_path,
        confidence=confidence,
        reason=reason,
    )
    slice_dict: dict[str, Any] = {
        **model.model_dump(mode="json"),
        "ecosystem": ecosystem,
        "nodes_count": nodes_count,
        "edges_count": edges_count,
    }
    duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
    raw_artifacts: list[Path] = [graph_path] if graph_path is not None else []
    # Always emit ``probe.success`` (with the typed confidence label). Phase-2
    # low-confidence outcomes — no-strategy, unrecognized-pm, no-manifest —
    # are *expected* dispatch results, not probe failures (the coordinator's
    # ``probe.failure`` event is reserved for unhandled exceptions and hard
    # I/O failures, matching :class:`IndexHealthProbe`'s convention).
    _log.info(EVENT_PROBE_SUCCESS, probe="dep_graph", confidence=confidence, reason=reason)
    return ProbeOutput(
        schema_slice={"dep_graph": slice_dict},
        raw_artifacts=raw_artifacts,
        confidence=confidence,
        duration_ms=duration_ms,
        warnings=warnings,
        errors=[],
    )


# ---------------------------------------------------------------------------
# Imperative shell — the probe class
# ---------------------------------------------------------------------------


@register_probe
class DepGraphProbe(Probe):
    """Layer B — dependency-graph kernel probe (B5).

    Dispatches to ``register_dep_graph_strategy``-decorated strategies via
    :data:`codegenie.depgraph.default_dep_graph_registry`. With zero
    strategies registered (the Phase-2 reality), every Node repo emits a
    typed low-confidence slice with ``reason="no_strategy_for_ecosystem"``.

    The probe is registered with default ``heaviness="light"`` and
    ``runs_last=False`` (02-ADR-0003): graph construction is fast O(N).
    """

    name: str = "dep_graph"
    version: str = "0.1.0"
    layer = "B"
    # ``tier="task_specific"`` — runs in coordinator wave 2 (after the
    # language-detection prelude). The story's draft AC-1 specified
    # ``tier="base"`` but Phase 0's wave-1 dispatches with an empty
    # ``detected_languages`` snapshot, which would force every Node-only
    # probe to either spuriously execute on non-Node repos (the
    # :class:`ScipIndexProbe` pattern — fails out with an unhandled
    # ``AttributeError``) or override ``applies()`` to short-circuit. The
    # cleaner precedent is :class:`NodeBuildSystemProbe`
    # (``tier="task_specific"`` + ``applies()`` via ``_admits_node_project``),
    # which lets the coordinator's language filter dispatch us only against
    # repos that actually have Node markers. Rule 7 conflict surfaced:
    # following the better-tested precedent.
    tier = "task_specific"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["javascript", "typescript"]
    # Re-detect inline → no topological dependency on ``node_build_system``.
    # Mirrors S4-01's "reads sibling artifacts but doesn't require them".
    requires: list[str] = []
    timeout_seconds: int = 60

    def applies(self, repo: RepoSnapshot, task: Task) -> bool:
        """Run only when the repo has Node markers.

        Delegates to the shared :func:`_admits_node_project` predicate so the
        admission rule is bit-for-bit consistent with
        :class:`NodeBuildSystemProbe` / :class:`NodeManifestProbe` /
        :class:`TestInventoryProbe`. A repo with ``package.json`` at the root
        but no source files yet still admits — the depgraph is fundamentally
        a manifest-driven artifact.
        """
        return _admits_node_project(self.applies_to_languages, repo.detected_languages, repo.root)

    def __init__(self) -> None:
        super().__init__()
        # ``declared_inputs`` includes a ``dep_graph_strategy_set:<resolved>``
        # token whose value is the sorted comma-joined list of registered
        # ecosystems at probe-init time. A Phase-3 PR registering a new
        # strategy changes ``<resolved>``, which changes the cache key and
        # invalidates the slice — exactly as expected.
        registered = sorted(default_dep_graph_registry.registered_ecosystems())
        strategy_token = "dep_graph_strategy_set:" + ",".join(registered)
        self.declared_inputs = [
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "bun.lockb",
            "pnpm-workspace.yaml",
            strategy_token,
        ]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        _log.info(EVENT_PROBE_START, probe=self.name)
        t0 = time.perf_counter()

        ecosystem, det_warnings, is_known = _detect_package_manager(repo.root, ctx.parsed_manifest)

        if ecosystem is None:
            return _emit(
                ecosystem=None,
                confidence="low",
                reason="no_manifest_detected",
                t0=t0,
                graph_path=None,
                nodes_count=0,
                edges_count=0,
                warnings=det_warnings + ["dep_graph.no_manifest_detected"],
            )

        if not is_known:
            return _emit(
                ecosystem=ecosystem,
                confidence="low",
                reason="unrecognized_package_manager",
                t0=t0,
                graph_path=None,
                nodes_count=0,
                edges_count=0,
                warnings=det_warnings + ["dep_graph.unrecognized_package_manager"],
            )

        # Narrowing: ``is_known`` is True, so ``ecosystem`` is a Literal value.
        pm: PackageManager = cast(PackageManager, ecosystem)

        # Always write an empty graph artifact so Phase 3 consumers can read
        # uniformly (one parse path, not "file absent → empty list" branching).
        empty_graph_path = _serialize_graph(repo.root, pm, nx.DiGraph())

        if not default_dep_graph_registry.has_strategy(pm):
            return _emit(
                ecosystem=pm,
                confidence="low",
                reason="no_strategy_for_ecosystem",
                t0=t0,
                graph_path=empty_graph_path,
                nodes_count=0,
                edges_count=0,
                warnings=det_warnings,
            )

        manifests = _construct_manifests(repo.root, ctx.parsed_manifest)
        try:
            graph = await asyncio.wait_for(
                asyncio.to_thread(default_dep_graph_registry.dispatch, pm, ctx, manifests),
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            return _emit(
                ecosystem=pm,
                confidence="low",
                reason="strategy_timeout",
                t0=t0,
                graph_path=empty_graph_path,
                nodes_count=0,
                edges_count=0,
                warnings=det_warnings + ["dep_graph.strategy_timeout"],
            )

        raw_path = _serialize_graph(repo.root, pm, graph)
        return _emit(
            ecosystem=pm,
            confidence="high",
            reason=None,
            t0=t0,
            graph_path=raw_path,
            nodes_count=graph.number_of_nodes(),
            edges_count=graph.number_of_edges(),
            warnings=det_warnings,
        )
