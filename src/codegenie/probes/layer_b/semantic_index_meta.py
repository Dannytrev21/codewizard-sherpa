"""``SemanticIndexMetaProbe`` (S4-06) — tsconfig metadata for the indexer.

Reads ``<repo.root>/tsconfig.json`` directly via Phase 1's JSONC parser
and surfaces the compiler-options metadata Phase 3 adapters need to
know "what did the indexer actually look at?". This is separate from
B2's freshness check (``IndexHealthProbe``): B2 asks "is the index
up to date?"; this probe asks "what shape does the indexer see?".

**Sibling-slice reads are unavailable.** Phase 0 ADR-0007 freezes
:class:`ProbeContext` — no ``sibling_slices`` field — and
``NodeBuildSystemProbe`` does not write a ``build_system.json``
sidecar. The probe reads ``tsconfig.json`` literally; it does NOT walk
``extends`` chains. When the file has ``extends``, ``has_extends: true``
is set and a warning makes the limitation honest.

``files_count_estimate`` consults the shared
:mod:`codegenie.probes.layer_b._indexable_files` walker — the same
walker ``ScipIndexProbe`` uses — so a divergence between the two
counts is mechanically impossible.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S4-06-layer-b-marker-probes.md``
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Development view" lines 250–253.
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from typing import Any, Final, Literal, TypeAlias

import structlog

from codegenie.errors import (
    DepthCapExceeded,
    MalformedJSONError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.logging import EVENT_PROBE_START, EVENT_PROBE_SUCCESS
from codegenie.parsers import jsonc
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot, Task
from codegenie.probes.language_filter import _admits_node_project
from codegenie.probes.layer_b._indexable_files import _count_indexable_files
from codegenie.probes.registry import register_probe

__all__ = ["SemanticIndexMetaProbe"]


_log = structlog.get_logger(__name__)


_WARNING_IDS: Final[frozenset[str]] = frozenset(
    {
        "semantic_index_meta.no_tsconfig",
        "semantic_index_meta.extends_chain_not_resolved",
    }
)
_ERROR_IDS: Final[frozenset[str]] = frozenset(
    {
        "semantic_index_meta.tsconfig_unparseable",
    }
)
_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
for _id in _WARNING_IDS | _ERROR_IDS:
    if not _ID_PATTERN.match(_id):
        raise AssertionError(f"ADR-0007 violation: {_id!r}")


_TSCONFIG_NAME: Final[str] = "tsconfig.json"
_TSCONFIG_MAX_BYTES: Final[int] = 5 * 1024 * 1024
_TSCONFIG_MAX_DEPTH: Final[int] = 64
_COMPILER_OPTION_KEYS: Final[tuple[str, ...]] = (
    "target",
    "module",
    "moduleResolution",
    "strict",
)

_Confidence: TypeAlias = Literal["high", "medium", "low"]


# ---------------------------------------------------------------------------
# Pure helpers (functional core — no I/O, no ctx)
# ---------------------------------------------------------------------------


def _extract_compiler_option(payload: Mapping[str, Any], key: str, default: Any) -> Any:
    """Return ``payload['compilerOptions'][key]`` when present; *default* else.

    Handles missing ``compilerOptions`` block and non-dict shapes
    defensively — a malformed tsconfig with ``compilerOptions: "bad"``
    falls through to *default* rather than raising at probe runtime.
    """
    opts = payload.get("compilerOptions")
    if not isinstance(opts, Mapping):
        return default
    value = opts.get(key, default)
    return value


def _normalize_string_list(value: Any) -> list[str]:
    """Return *value* as a list of strings when it is a list of strings;
    empty list otherwise. Tolerant of missing keys and wrong shapes."""
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if isinstance(v, str)]


def _build_slice_from_payload(
    payload: Mapping[str, Any],
    files_count_estimate: int,
) -> dict[str, Any]:
    """Compose the success slice from a parsed tsconfig payload."""
    return {
        "tsconfig_path": _TSCONFIG_NAME,
        "has_extends": "extends" in payload,
        "target": _extract_compiler_option(payload, "target", None),
        "module": _extract_compiler_option(payload, "module", None),
        "module_resolution": _extract_compiler_option(payload, "moduleResolution", None),
        "strict": bool(_extract_compiler_option(payload, "strict", False)),
        "include_globs": _normalize_string_list(payload.get("include")),
        "exclude_globs": _normalize_string_list(payload.get("exclude")),
        "files_count_estimate": files_count_estimate,
        "confidence": "high",
    }


# ---------------------------------------------------------------------------
# Probe class (imperative shell)
# ---------------------------------------------------------------------------


@register_probe
class SemanticIndexMetaProbe(Probe):
    """Layer B — semantic-index metadata probe (light heaviness)."""

    name: str = "semantic_index_meta"
    version: str = "0.1.0"
    layer = "B"
    tier = "base"
    applies_to_languages: list[str] = ["javascript", "typescript"]
    applies_to_tasks: list[str] = ["*"]
    requires: list[str] = ["language_detection"]
    timeout_seconds: int = 10
    cache_strategy: Literal["content"] = "content"
    declared_inputs: list[str] = [
        "tsconfig.json",
        "tsconfig.*.json",
        "package.json",
    ]

    def applies(self, repo: RepoSnapshot, task: Task) -> bool:
        return _admits_node_project(self.applies_to_languages, repo.detected_languages, repo.root)

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        _log.info(EVENT_PROBE_START, probe=self.name)
        t0 = time.perf_counter()
        tsconfig_path = repo.root / _TSCONFIG_NAME

        if not tsconfig_path.is_file():
            return self._emit(
                slice_payload={
                    "tsconfig_path": None,
                    "confidence": "medium",
                },
                confidence="medium",
                warnings=["semantic_index_meta.no_tsconfig"],
                errors=[],
                t0=t0,
            )

        try:
            payload = jsonc.load(
                tsconfig_path,
                max_bytes=_TSCONFIG_MAX_BYTES,
                max_depth=_TSCONFIG_MAX_DEPTH,
            )
        except (MalformedJSONError, SizeCapExceeded, DepthCapExceeded, SymlinkRefusedError):
            return self._emit(
                slice_payload={
                    "tsconfig_path": _TSCONFIG_NAME,
                    "confidence": "low",
                },
                confidence="low",
                warnings=[],
                errors=["semantic_index_meta.tsconfig_unparseable"],
                t0=t0,
            )

        files_count = _count_indexable_files(repo.root)
        slice_payload = _build_slice_from_payload(payload, files_count)

        warnings: list[str] = []
        if slice_payload["has_extends"]:
            warnings.append("semantic_index_meta.extends_chain_not_resolved")

        return self._emit(
            slice_payload=slice_payload,
            confidence="high",
            warnings=warnings,
            errors=[],
            t0=t0,
        )

    def _emit(
        self,
        *,
        slice_payload: dict[str, Any],
        confidence: _Confidence,
        warnings: list[str],
        errors: list[str],
        t0: float,
    ) -> ProbeOutput:
        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        _log.info(EVENT_PROBE_SUCCESS, probe=self.name, confidence=confidence)
        return ProbeOutput(
            schema_slice={"semantic_index_meta": slice_payload},
            raw_artifacts=[],
            confidence=confidence,
            duration_ms=duration_ms,
            warnings=sorted(set(warnings)),
            errors=sorted(set(errors)),
        )
