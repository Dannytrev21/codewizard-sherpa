"""``LanguageDetectionProbe`` — Layer A, prelude-pass anchor (S4-01).

This is the first concrete probe in the system and the Phase 0 bullet-tracer's
"vertical-slice tip". It walks the snapshot root counting files by extension
and emits a ``schema_slice`` shaped as
``{"language_stack": {"counts": {<lang>: <int>, ...}, "primary": <lang-or-None>}}``.

Design pins (each maps to an AC in
``docs/phases/00-bullet-tracer-foundations/stories/S4-01-language-detection-probe.md``):

- **``tier = "base"``** engages the coordinator's prelude pass (Gap 4); every
  Phase 1 probe reads off ``enriched_snapshot.detected_languages``.
- **``declared_inputs`` is extension-scoped (glob form)**, never ``["**/*"]``
  and never bare extensions. ``cache/keys.py:declared_inputs_for`` uses
  ``snapshot.root.rglob(pattern)``; ``rglob(".js")`` matches files literally
  named ``.js`` (none in normal repos), so bare extensions silently resolve to
  an empty input set and the cache key collapses to a constant. The glob form
  ``["**/*.js", ...]`` matches files at any depth and is what makes S4-04's
  "edit README.md between two gathers, second run is a cache hit" assertion
  work.
- **The walker uses ``os.scandir`` (NOT ``pathlib.Path.glob``)** so S4-04 can
  monkeypatch invocation count at ``codegenie.probes.language_detection.os.scandir``
  to assert zero scandir calls on the cache-hit path. The module uses
  ``import os`` (not ``from os import scandir``) deliberately — the monkeypatch
  target is unambiguous.
- **Vendor-dir deny-list** (``_SKIP_DIRS``) is checked *before* recursion, not
  after. Real repos have ``node_modules`` 100× the size of source; without the
  deny-list ``primary`` becomes whatever the largest vendor tree contains.
- **Symlinks** are partitioned into three cases (in-tree → follow,
  out-of-tree → skip + ``probe.symlink.escaped``, broken → skip +
  ``probe.symlink.broken``). Event payloads use *relative* paths because
  ``OutputSanitizer.scrub`` (ADR-0008) is a chokepoint on ``RepoContext`` emit,
  **not** a structlog processor — anything logged here ships unscrubbed.
- **``counts`` is cast to a plain ``dict`` before emit** so the
  ``_ProbeOutputValidator`` (ADR-0010) sees a vanilla JSON-leaf-closed tree
  rather than a ``Counter`` subclass.
- **Empty repo returns ``primary=None``** (not ``""``). The in-PR-amended
  sub-schema (``v0.1.1``) declares ``primary: {"type": ["string", "null"]}``.
- **The structlog logger is module-scope** (``_log``); ``probe.start`` /
  ``probe.success`` / ``probe.failure`` events match the constants in
  ``codegenie.logging`` so Phase 6's state ledger and Phase 8's Trust-Aware
  gates subscribe to the same event names.

ADRs honored: ADR-0007 (frozen contract), ADR-0010 (Pydantic trust boundary),
ADR-0013 (layered ``additionalProperties``), ADR-0008 (sanitizer chokepoint),
ADR-0003 (per-probe schema-version cache invalidation; this probe's
``version`` tracks the sub-schema ``$id`` lockstep).
"""

from __future__ import annotations

import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Final

import structlog

from codegenie.logging import (
    EVENT_PROBE_FAILURE,
    EVENT_PROBE_START,
    EVENT_PROBE_SUCCESS,
)
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe

__all__ = ["LanguageDetectionProbe"]


_log = structlog.get_logger(__name__)

# Symlink-lifecycle events — kept at module scope so adversarial tests
# can introspect / assert against the exact event names.
_EVENT_SYMLINK_ESCAPED: Final[str] = "probe.symlink.escaped"
_EVENT_SYMLINK_BROKEN: Final[str] = "probe.symlink.broken"


# Walker deny-list. Checked BEFORE recursion (an entry under a skipped dir is
# never ``scandir``-ed). Phase 0 ships this as a frozen module-level constant;
# Phase 1 may add a user-defined-glob layer per the story's "Out of scope".
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


# Extension → canonical language map. Keys are *casefolded* (lowercase) with
# the leading dot. ``FOO.JS`` is looked up as ``.js`` after
# ``Path(...).suffix.casefold()``. Unknown extensions are silently skipped.
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


def _primary_from(counts: dict[str, int]) -> str | None:
    """Return the language with the highest count, alpha-sorted on ties.

    ``max(counts, key=counts.get)`` is insertion-order-tie-broken and would
    silently flip between runs — explicit alpha tie-break is what makes the
    output reproducible across walks.
    """
    if not counts:
        return None
    top = max(counts.values())
    return sorted(c for c, v in counts.items() if v == top)[0]


def _relative_path(entry_path: str, root: Path) -> str:
    """Render a directory-entry path relative to ``root`` for log payloads.

    Falls back to the entry basename if the path is not under ``root`` (which
    only happens with broken inputs — symlink targets are NEVER passed here).
    """
    try:
        return str(Path(entry_path).relative_to(root))
    except ValueError:
        return Path(entry_path).name


def _classify_symlink(entry: os.DirEntry[str], root_resolved: Path) -> str:
    """Return one of ``"in_tree"`` / ``"escaped"`` / ``"broken"``.

    ``Path.resolve(strict=True)`` is the authoritative "does the target
    exist?" probe. ``FileNotFoundError`` (and the broader ``OSError`` family)
    means "broken"; otherwise we check whether the resolved target is under
    ``root_resolved``. The resolved target is never returned — callers log
    only the original (relative) entry path.
    """
    try:
        resolved = Path(entry.path).resolve(strict=True)
    except (FileNotFoundError, OSError):
        return "broken"
    try:
        # ``is_relative_to`` (3.9+) — true iff resolved is at or below root.
        if resolved.is_relative_to(root_resolved):
            return "in_tree"
    except ValueError:  # pragma: no cover — is_relative_to only raises for ambiguous bases
        return "escaped"
    return "escaped"


def _count_file(name: str, counter: Counter[str]) -> None:
    """Increment ``counter`` if ``name``'s extension is a known language."""
    ext = Path(name).suffix.casefold()
    lang = _EXT_TO_LANG.get(ext)
    if lang is not None:
        counter[lang] += 1


def _walk(root: Path, counter: Counter[str]) -> None:
    """Walk ``root`` with ``os.scandir``; populate ``counter`` in place.

    Iterative (explicit stack) rather than recursive — keeps the call-stack
    flat for deep trees and matches the iterative pattern used by
    ``coordinator.validator._walk_and_enforce``.
    """
    root_resolved = root.resolve()
    stack: list[Path] = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as it:
            for entry in it:
                # 1. Symlinks first — they may point at dirs, files, or nothing.
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
                    # In-tree symlink → follow as a regular file (count its
                    # extension). We do NOT recurse into symlinked directories
                    # because that re-opens the "vendor-loop" failure mode the
                    # deny-list closes.
                    _count_file(entry.name, counter)
                    continue

                # 2. Directories — apply the deny-list, then recurse.
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in _SKIP_DIRS:
                        continue
                    stack.append(Path(entry.path))
                    continue

                # 3. Regular files — count by extension.
                if entry.is_file(follow_symlinks=False):
                    _count_file(entry.name, counter)


@register_probe
class LanguageDetectionProbe(Probe):
    """Layer-A extension-counting probe — the prelude-pass anchor (Gap 4).

    Walks the repo root with ``os.scandir``, skipping
    ``_SKIP_DIRS`` (vendor / build / cache dirs), maps each file's
    casefolded extension to a canonical language, and emits the result as a
    ``language_stack`` slice. ``primary`` is the alpha-sorted-first language
    within the max-count set; empty repo returns ``primary=None``.

    The class attributes below are pinned by AC-1 of S4-01 — drift fails the
    contract-conformance test in ``tests/unit/test_language_detection_probe.py``.
    """

    name: str = "language_detection"
    version: str = "0.1.1"  # lockstep with the v0.1.1 sub-schema $id (ADR-0003)
    layer = "A"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    # NOTE: bare extensions (``[".js", ...]``) are forbidden — see module
    # docstring for the cache-key collapse rationale. The glob form below is
    # what makes the cache-hit test in S4-04 exit through the warm path.
    declared_inputs: list[str] = [
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
    ]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        """Walk ``repo.root`` and produce the ``language_stack`` slice."""
        _log.info(EVENT_PROBE_START, probe=self.name)
        counter: Counter[str] = Counter()
        errors: list[str] = []
        confidence: str = "high"
        t0 = time.perf_counter()
        try:
            _walk(repo.root, counter)
        except OSError as exc:
            # ``PermissionError`` is an ``OSError`` subclass — the single clause
            # captures both the AC-5 happy-path case and other walk-failure
            # modes (e.g., ENOENT on the root). The probe never re-raises a
            # non-``CodegenieError`` (AC-5); confidence demotes to ``"low"``
            # so the audit ledger surfaces the gap loudly (Rule 12).
            errors.append(f"{type(exc).__name__}: {exc}")
            confidence = "low"
            _log.info(
                EVENT_PROBE_FAILURE,
                probe=self.name,
                error=type(exc).__name__,
                reason=str(exc),
            )
        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))

        counts: dict[str, int] = dict(counter)
        slice_payload: dict[str, Any] = {
            "language_stack": {"counts": counts, "primary": _primary_from(counts)}
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
