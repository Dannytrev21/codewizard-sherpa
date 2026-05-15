"""``LanguageDetectionProbe`` — Layer A, prelude-pass anchor (S4-01 + S2-01).

This is the first concrete probe in the system and the Phase 0 bullet-tracer's
"vertical-slice tip". It walks the snapshot root counting files by extension
and emits a ``schema_slice`` shaped as
``{"language_stack": {"counts": {<lang>: <int>, ...}, "primary": <lang-or-None>,
"framework_hints": [...], "monorepo": {...} | None}}``.

S2-01 (Phase 1) extends the Phase 0 probe in place with two additive fields:

- ``framework_hints`` — sorted, deduped seed-dict intersection over
  ``dependencies | devDependencies`` (Express, Next, Fastify, Nest, Koa, Hapi).
- ``monorepo`` — deterministic precedence over ``(pnpm-workspace.yaml,
  turbo.json, nx.json, lerna.json, package.json#workspaces)``. The
  precedence table lives in ``_MONOREPO_PRECEDENCE`` as a single
  precedence-ordered tuple-of-tuples — a new monorepo tool is a one-line
  insertion (Open/Closed at the file boundary; the linear scan in ``run``
  never grows).

The post-walk pass reads ``package.json`` via ``ctx.parsed_manifest`` (the
``ParsedManifestMemo`` seam from S1-07) when available, falling back to
``parsers.safe_json.load`` when the memo is absent (edge case 12). This is the
load-bearing seam S2-02..S3-05 inherit and the warm-path test in S2-04 asserts.

Failure modes (typed parser exceptions) land on ``ProbeOutput.errors`` with the
ADR-0007 ID pattern, never on the slice's forward-compatible ``warnings[]``:

- ``SizeCapExceeded`` → ``package_json.size_cap_exceeded`` + ``confidence: "medium"``
- ``SymlinkRefusedError`` → ``package_json.symlink_refused`` + ``confidence: "low"``
- ``MalformedJSONError`` → ``package_json.malformed`` + ``confidence: "medium"``
- ``DepthCapExceeded`` → ``package_json.depth_cap_exceeded`` + ``confidence: "low"`` (S5-01 AC-12)

(Per arch §"Component design" #1 — covering edge-case rows 2, 3, 11, 12.)

Design pins (each maps to an AC in
``docs/phases/00-bullet-tracer-foundations/stories/S4-01-language-detection-probe.md`` and
``docs/phases/01-context-gather-layer-a-node/stories/S2-01-language-detection-extension.md``):

- **``tier = "base"``** engages the coordinator's prelude pass (Gap 4); every
  Phase 1 probe reads off ``enriched_snapshot.detected_languages``.
- **``declared_inputs`` is additive**: Phase 0 globs remain a contiguous prefix
  (verified by ``tests/unit/test_language_detection_probe.py::test_declared_inputs_additive``);
  S2-01 appends ``package.json`` and the four monorepo marker filenames.
- **The walker uses ``os.scandir`` (NOT ``pathlib.Path.glob``)** so S4-04 can
  monkeypatch invocation count at ``codegenie.probes.language_detection.os.scandir``.
- **Vendor-dir deny-list** (``_SKIP_DIRS``) is checked *before* recursion.
- **Symlinks** are partitioned into in-tree / escaped / broken.
- **``counts`` is cast to a plain ``dict`` before emit** (ADR-0010 trust boundary).
- **Empty repo returns ``primary=None``**.
- **The structlog logger is module-scope** (``_log``).
- **Open/Closed**: ``_MONOREPO_PRECEDENCE`` is the single extension point for new
  monorepo tools; the scan in ``run`` never grows. Compile-time discipline
  (Rule 12) asserts the precedence-tuple invariants and the ADR-0007 ID
  pattern on every entry of ``_ERRORS``.
- **Rule-of-three deferral**: ``_FRAMEWORK_SEED`` is single-use today (this
  probe only); deliberately inline. The right moment to lift it into a
  ``catalogs/frameworks.yaml`` is when Phase 2's polyglot detection adds the
  second consumer.

ADRs honored: ADR-0007 (frozen contract), ADR-0010 (Pydantic trust boundary),
ADR-0013 (layered ``additionalProperties``), ADR-0008 (sanitizer chokepoint),
ADR-0003 (per-probe schema-version cache invalidation; this probe's
``version`` tracks the sub-schema ``$id`` lockstep — body extended additively
within v0.1.1), and Phase 1 ADR-0002 (consumes ``ctx.parsed_manifest``),
ADR-0004 (slice ``additionalProperties: false``), ADR-0007-phase1 (ID pattern).
"""

from __future__ import annotations

import os
import re
import time
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, TypedDict

import structlog

from codegenie.errors import (
    DepthCapExceeded,
    MalformedJSONError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.logging import (
    EVENT_PROBE_FAILURE,
    EVENT_PROBE_START,
    EVENT_PROBE_SUCCESS,
)
from codegenie.parsers import safe_json
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe

__all__ = ["LanguageDetectionProbe"]


_log = structlog.get_logger(__name__)

# Symlink-lifecycle events — kept at module scope so adversarial tests
# can introspect / assert against the exact event names.
_EVENT_SYMLINK_ESCAPED: Final[str] = "probe.symlink.escaped"
_EVENT_SYMLINK_BROKEN: Final[str] = "probe.symlink.broken"


# Walker deny-list. Checked BEFORE recursion (an entry under a skipped dir is
# never ``scandir``-ed).
_SKIP_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".git",
        "node_modules",
        "vendor",
        "dist",
        "build",
        "__pycache__",
        ".venv",
        "target",
        "out",
        ".next",
        ".cache",
    }
)


# Extension → canonical language map (casefolded with leading dot).
_EXT_TO_LANG: Final[dict[str, str]] = {
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".py": "python",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
}


# --- S2-01 constants ---------------------------------------------------------


# Single-use today (LanguageDetectionProbe only); explicit rule-of-three
# deferral per Rule 2. Lifted out only when a second consumer arrives
# (Phase 2 polyglot detection for Python/Go frameworks is the candidate).
_FRAMEWORK_SEED: Final[Mapping[str, str]] = MappingProxyType(
    {
        "@nestjs/core": "nestjs",
        "express": "express",
        "fastify": "fastify",
        "next": "next",
        "koa": "koa",
        "@hapi/hapi": "hapi",
    }
)


# Precedence-ordered table of ``(marker_filename, tool_name)``. The first hit
# wins for the slice's ``tool`` field; ``markers`` is the sorted union of every
# hit. Adding a new monorepo tool is a one-line insertion at the right
# precedence position — the linear scan in ``run`` never grows (Open/Closed at
# the file boundary). The final entry is the ``package.json#workspaces``
# fallback; the compile-time assertion below pins that placement.
_MONOREPO_PRECEDENCE: Final[tuple[tuple[str, str], ...]] = (
    ("pnpm-workspace.yaml", "pnpm-workspaces"),
    ("turbo.json", "turbo"),
    ("nx.json", "nx"),
    ("lerna.json", "lerna"),
    ("package.json", "workspaces"),
)


# Typed-exception IDs this probe can emit on ``ProbeOutput.errors``. Per
# ADR-0007: typed-exception-raised IDs go in ``errors[]``; soft-degrade IDs in
# ``warnings[]``. All three are exception-derived.
_ERRORS: Final[frozenset[str]] = frozenset(
    {
        "package_json.size_cap_exceeded",
        "package_json.symlink_refused",
        "package_json.malformed",
        "package_json.depth_cap_exceeded",
    }
)


# Confidence demote map for typed parser exceptions. Per arch §"Component
# design" #1: symlink is the lower-trust failure; size-cap and malformed are
# medium-trust.
_PKG_JSON_FAILURE: Final[Mapping[type[Exception], tuple[str, str]]] = MappingProxyType(
    {
        SizeCapExceeded: ("package_json.size_cap_exceeded", "medium"),
        SymlinkRefusedError: ("package_json.symlink_refused", "low"),
        MalformedJSONError: ("package_json.malformed", "medium"),
        DepthCapExceeded: ("package_json.depth_cap_exceeded", "low"),
    }
)


# Pre-parse size cap for package.json (5 MiB; aligns with ParsedManifestMemo).
_PKG_JSON_MAX_BYTES: Final[int] = 5 * 1024 * 1024


# ADR-0007 pattern. Compile-time assertions below pin every emittable ID.
_WARNING_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


# Plausible npm package name regex — guard against typo'd keys leaking into
# the seed dict.
_NPM_PKG_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"^(@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$"
)


# Confidence-rank table — used so a post-walk demote never *upgrades* a walk
# failure (e.g., walk OSError → "low" + post-walk size-cap → "medium" must
# stay "low").
_CONFIDENCE_RANK: Final[Mapping[str, int]] = MappingProxyType({"low": 0, "medium": 1, "high": 2})


# --- compile-time discipline (Rule 12: fail loud) ----------------------------

assert all(_WARNING_ID_RE.match(eid) for eid in _ERRORS), (
    "S2-01 _ERRORS contains an ID that does not match the ADR-0007 pattern: "
    f"{[e for e in _ERRORS if not _WARNING_ID_RE.match(e)]}"
)
assert all(_NPM_PKG_NAME_RE.match(key) for key in _FRAMEWORK_SEED), (
    "S2-01 _FRAMEWORK_SEED contains a key that is not a plausible npm package name: "
    f"{[k for k in _FRAMEWORK_SEED if not _NPM_PKG_NAME_RE.match(k)]}"
)
assert _MONOREPO_PRECEDENCE[-1][0] == "package.json", (
    "S2-01 _MONOREPO_PRECEDENCE: the last entry must be the package.json#workspaces fallback; "
    f"got {_MONOREPO_PRECEDENCE[-1]!r}"
)


class MonorepoBlock(TypedDict):
    """Shape of ``schema_slice.language_stack.monorepo`` when not ``None``."""

    tool: str
    markers: list[str]


# --- helpers ----------------------------------------------------------------


def _primary_from(counts: dict[str, int]) -> str | None:
    """Return the language with the highest count, alpha-sorted on ties."""
    if not counts:
        return None
    top = max(counts.values())
    return sorted(c for c, v in counts.items() if v == top)[0]


def _relative_path(entry_path: str, root: Path) -> str:
    try:
        return str(Path(entry_path).relative_to(root))
    except ValueError:
        return Path(entry_path).name


def _classify_symlink(entry: os.DirEntry[str], root_resolved: Path) -> str:
    try:
        resolved = Path(entry.path).resolve(strict=True)
    except (FileNotFoundError, OSError):
        return "broken"
    try:
        if resolved.is_relative_to(root_resolved):
            return "in_tree"
    except ValueError:  # pragma: no cover
        return "escaped"
    return "escaped"


def _count_file(name: str, counter: Counter[str]) -> None:
    ext = Path(name).suffix.casefold()
    lang = _EXT_TO_LANG.get(ext)
    if lang is not None:
        counter[lang] += 1


def _walk(root: Path, counter: Counter[str]) -> None:
    """Walk ``root`` with ``os.scandir``; populate ``counter`` in place."""
    root_resolved = root.resolve()
    stack: list[Path] = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_symlink():
                    classification = _classify_symlink(entry, root_resolved)
                    if classification == "broken":
                        _log.info(
                            _EVENT_SYMLINK_BROKEN,
                            probe=LanguageDetectionProbe.name,
                            path=_relative_path(entry.path, root),
                        )
                        continue
                    if classification == "escaped":
                        _log.info(
                            _EVENT_SYMLINK_ESCAPED,
                            probe=LanguageDetectionProbe.name,
                            path=_relative_path(entry.path, root),
                        )
                        continue
                    _count_file(entry.name, counter)
                    continue

                if entry.is_dir(follow_symlinks=False):
                    if entry.name in _SKIP_DIRS:
                        continue
                    stack.append(Path(entry.path))
                    continue

                if entry.is_file(follow_symlinks=False):
                    _count_file(entry.name, counter)


def _demote(current: str, target: str) -> str:
    """Return the lower of ``current`` and ``target`` per the confidence rank.

    A post-walk failure must never *upgrade* a walk-level demote.
    """
    if _CONFIDENCE_RANK[target] < _CONFIDENCE_RANK[current]:
        return target
    return current


def _read_package_json(pkg_path: Path, ctx: ProbeContext) -> Mapping[str, Any] | None:
    """Read ``package.json`` via the memo when present, else fallback to safe_json.

    Returns ``None`` only when the memo returns ``None`` for non-error
    reasons (sentinel content_hash; not expected in this caller's context).
    Typed parser exceptions propagate to the caller, which maps them to error
    IDs.
    """
    if ctx.parsed_manifest is not None:
        return ctx.parsed_manifest(pkg_path)
    return safe_json.load(pkg_path, max_bytes=_PKG_JSON_MAX_BYTES)


def _framework_hints_from(pkg: Mapping[str, Any]) -> list[str]:
    """Compute the sorted-deduped framework-hint list from a parsed manifest.

    Treats missing or ``None`` dependency blocks as empty; non-dict values are
    rejected (defensive — a malformed ``package.json`` with a string under
    ``"dependencies"`` would otherwise raise).
    """
    deps_obj = pkg.get("dependencies") or {}
    devdeps_obj = pkg.get("devDependencies") or {}
    if not isinstance(deps_obj, dict):
        deps_obj = {}
    if not isinstance(devdeps_obj, dict):
        devdeps_obj = {}
    union = set(deps_obj.keys()) | set(devdeps_obj.keys())
    return sorted({_FRAMEWORK_SEED[name] for name in union if name in _FRAMEWORK_SEED})


def _detect_monorepo(root: Path, pkg: Mapping[str, Any] | None) -> MonorepoBlock | None:
    """Run a single linear scan over the precedence table.

    First hit wins for ``tool``; all hits' filenames union into ``markers``.
    """
    markers_set: set[str] = set()
    first_tool: str | None = None
    for filename, tool_name in _MONOREPO_PRECEDENCE:
        hit = False
        if filename == "package.json":
            if pkg is not None and bool(pkg.get("workspaces")):
                hit = True
        else:
            if (root / filename).exists():
                hit = True
        if hit:
            markers_set.add(filename)
            if first_tool is None:
                first_tool = tool_name
    if not markers_set or first_tool is None:
        return None
    return {"tool": first_tool, "markers": sorted(markers_set)}


@register_probe
class LanguageDetectionProbe(Probe):
    """Layer-A extension-counting probe — the prelude-pass anchor (Gap 4).

    Walks the repo root with ``os.scandir``, skipping ``_SKIP_DIRS``, maps each
    file's casefolded extension to a canonical language, and emits the result
    as a ``language_stack`` slice. ``primary`` is the alpha-sorted-first
    language within the max-count set; empty repo returns ``primary=None``.

    S2-01 adds a post-walk pass that reads ``package.json`` via the memo seam
    (``ctx.parsed_manifest`` from S1-07) — or falls back to direct
    ``safe_json.load`` when the memo is absent — and emits ``framework_hints``
    + ``monorepo``.
    """

    name: str = "language_detection"
    version: str = "0.1.1"  # lockstep with the v0.1.1 sub-schema $id; body additively extended
    layer = "A"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = [
        # Phase 0 entries — contiguous prefix, byte-stable (verified by
        # tests/unit/test_language_detection_probe.py::test_declared_inputs_additive).
        "**/*.js",
        "**/*.mjs",
        "**/*.cjs",
        "**/*.ts",
        "**/*.tsx",
        "**/*.py",
        "**/*.go",
        "**/*.rs",
        "**/*.java",
        "**/*.rb",
        "**/*.php",
        # Phase 1 / S2-01 additions — package.json + monorepo markers.
        "package.json",
        "pnpm-workspace.yaml",
        "lerna.json",
        "nx.json",
        "turbo.json",
    ]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        """Walk ``repo.root`` and produce the extended ``language_stack`` slice."""
        _log.info(EVENT_PROBE_START, probe=self.name)
        counter: Counter[str] = Counter()
        errors: list[str] = []
        confidence: str = "high"
        t0 = time.perf_counter()

        try:
            _walk(repo.root, counter)
        except OSError as exc:
            # PermissionError ⊂ OSError; ENOENT on root etc. all land here.
            errors.append(f"{type(exc).__name__}: {exc}")
            confidence = "low"
            _log.info(
                EVENT_PROBE_FAILURE,
                probe=self.name,
                error=type(exc).__name__,
                reason=str(exc),
            )

        # --- S2-01 post-walk pass ----------------------------------------
        framework_hints: list[str] = []
        monorepo: MonorepoBlock | None = None
        pkg: Mapping[str, Any] | None = None

        pkg_path = repo.root / "package.json"
        if pkg_path.exists():
            try:
                pkg = _read_package_json(pkg_path, ctx)
            except (
                SizeCapExceeded,
                SymlinkRefusedError,
                MalformedJSONError,
                DepthCapExceeded,
            ) as exc:
                error_id, demoted = _PKG_JSON_FAILURE[type(exc)]
                errors.append(error_id)
                confidence = _demote(confidence, demoted)
                pkg = None

            if pkg is not None:
                framework_hints = _framework_hints_from(pkg)

        monorepo = _detect_monorepo(repo.root, pkg)
        # -----------------------------------------------------------------

        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))

        counts: dict[str, int] = dict(counter)
        slice_payload: dict[str, Any] = {
            "language_stack": {
                "counts": counts,
                "primary": _primary_from(counts),
                "framework_hints": framework_hints,
                "monorepo": monorepo,
            }
        }

        if confidence == "high":
            _log.info(
                EVENT_PROBE_SUCCESS,
                probe=self.name,
                confidence=confidence,
                count_total=sum(counts.values()),
            )

        return ProbeOutput(
            schema_slice=slice_payload,
            raw_artifacts=[],
            confidence=confidence,  # type: ignore[arg-type]  # Literal validated at boundary
            duration_ms=duration_ms,
            warnings=[],
            errors=errors,
        )
