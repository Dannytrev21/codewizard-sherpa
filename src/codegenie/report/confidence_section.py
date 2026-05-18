"""``ConfidenceSection`` renderer — the only Phase-2 consumer of
``IndexFreshness`` (S8-01).

Renders a Markdown ``## Confidence`` section for ``CONTEXT_REPORT.md`` by
exhaustively pattern-matching on every variant of
:class:`codegenie.indices.freshness.IndexFreshness`. The ``match``
statement carries a final ``case _: assert_never(value)`` arm so that:

1. Removing any ``case`` arm causes ``mypy --warn-unreachable`` to flag
   the ``assert_never(value)`` line as unreachable — the **build error**
   that closes the "silent ``Union`` widening" failure mode.
2. Adding a new ``StaleReason`` variant without a matching ``case`` arm is
   caught at type-check time *and* at runtime by ``assert_never``.

The renderer is intentionally outside ``codegenie.probes/**``: importing
it must NOT pull the probe registry (enforced by
``tests/unit/report/test_confidence_section.py::test_no_probe_registry_import``).
Only the typed sum type module (:mod:`codegenie.indices.freshness`) and
stdlib are imported.

**Defense in depth.** The merged envelope ought to carry a well-shaped
``freshness`` payload — the writer chokepoint
(``codegenie.output.writer.Writer``) is the only path from
``ProbeOutput.schema_slice`` to disk, and Pydantic has already validated
the producer at probe-construction time. Even so, the renderer treats a
Pydantic ``ValidationError`` as a stable "slice malformed" row rather
than raising — the renderer is the last line of defense before user
output (AC-5).

**No re-redaction.** Secret redaction is the writer chokepoint's job
(02-ADR-0005 / 02-ADR-0010). ``IndexerError.message`` is rendered
verbatim; the producer guarantees stable identifiers
(``"upstream_scip_unavailable"``, ``"timeout"``, …) — not free-form text.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S8-01-confidence-section-renderer.md``
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #2, §"Logical view", §"Process view".
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md``.
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` §3–4
  (illegal-states-unrepresentable + ``assert_never``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final, assert_never

from pydantic import TypeAdapter, ValidationError

from codegenie.indices.freshness import (
    CommitsBehind,
    CoverageGap,
    DigestMismatch,
    Fresh,
    IndexerError,
    IndexFreshness,
    Stale,
)

__all__ = [
    "ConfidenceSectionRenderer",
    "render_confidence_section",
]


# ``TypeAdapter`` is constructed once at module import — the per-call cost
# would otherwise dominate the renderer's wall-time for envelopes with
# many index sources. ``Final`` makes the bind point obvious to readers.
_INDEX_FRESHNESS_ADAPTER: Final[TypeAdapter[IndexFreshness]] = TypeAdapter(IndexFreshness)


# Section heading is a module-level constant so the integration test's
# substring assertion ("## Confidence") drifts only via an explicit code
# edit, not via copy-paste typo.
_SECTION_HEADING: Final[str] = "## Confidence"

# Placeholder body emitted when the envelope carries no IndexHealth
# slices (non-Node repos, repos where B2 hasn't run, pathological shapes).
# Without it, a degenerate renderer that always returned the heading-only
# string would pass every observable AC — this line makes the empty-state
# explicit to readers AND mutation-resistant.
_NO_INDICES_PLACEHOLDER: Final[str] = "_No index sources registered._"


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def render_confidence_section(envelope: dict[str, Any]) -> str:
    """Render the Confidence section as a Markdown string.

    Extracts ``IndexFreshness`` values from
    ``envelope["probes"]["index_health"]["index_health"][<name>]["freshness"]``
    (the shape produced by ``IndexHealthProbe.run`` after the coordinator's
    shallow-merge). Rows are sorted ASCII-lex by index name. The output
    always starts with ``## Confidence\\n\\n``; if no indices are present
    (non-Node repos, repos where B2 hasn't run, pathological envelope
    shapes), the placeholder ``_No index sources registered._`` is
    emitted in place of rows so the empty state is explicit.

    Never raises — pathological envelope shapes (None, missing keys,
    wrong-typed nesting) yield the heading-only string. Per-entry
    Pydantic validation failures render a stable
    ``slice_malformed:<summary>`` row instead of raising.
    """
    slices = _extract_index_health_slices(envelope)

    parsed: list[tuple[str, IndexFreshness | None, str | None]] = []
    for name, slice_ in slices.items():
        freshness_payload = slice_.get("freshness") if isinstance(slice_, dict) else None
        try:
            freshness: IndexFreshness = _INDEX_FRESHNESS_ADAPTER.validate_python(freshness_payload)
            parsed.append((name, freshness, None))
        except ValidationError as exc:
            parsed.append((name, None, _summarize_validation_error(exc)))

    parsed.sort(key=lambda t: t[0])

    rows: list[str] = []
    for row_name, row_value, row_malformed in parsed:
        if row_malformed is not None:
            rows.append(_malformed_row(row_name, row_malformed))
        else:
            assert row_value is not None  # noqa: S101 — exhaustive on tuple shape
            rows.append(_render_row(row_name, row_value))

    if not rows:
        return f"{_SECTION_HEADING}\n\n{_NO_INDICES_PLACEHOLDER}\n"
    body = "\n".join(rows) + "\n"
    return f"{_SECTION_HEADING}\n\n{body}"


class ConfidenceSectionRenderer:
    """Thin class wrapper that delegates to :func:`render_confidence_section`.

    Exists for diagram alignment (phase-arch-design.md §"Logical view"
    names ``ConfidenceSectionRenderer.render``). Carries no state and is
    safe to construct ad hoc.
    """

    def render(self, envelope: dict[str, Any]) -> str:
        """Render the Confidence section for ``envelope``."""
        return render_confidence_section(envelope)


# ---------------------------------------------------------------------------
# Pure helpers (functional core)
# ---------------------------------------------------------------------------


def _extract_index_health_slices(envelope: dict[str, Any]) -> dict[str, Any]:
    """Drill into the merged envelope to the per-index slice map.

    Tolerant of arbitrary shape mismatches — the renderer never raises.
    """
    probes = envelope.get("probes")
    if not isinstance(probes, dict):
        return {}
    block = probes.get("index_health")
    if not isinstance(block, dict):
        return {}
    inner = block.get("index_health")
    if not isinstance(inner, dict):
        return {}
    return inner


def _render_row(name: str, value: IndexFreshness) -> str:
    """Nested exhaustive ``match`` over every ``IndexFreshness`` variant.

    The outer ``match`` covers the ``Fresh | Stale`` discriminator; the
    inner ``match`` covers the four ``StaleReason`` variants. Each level
    closes with ``case _: assert_never(...)`` so ``mypy
    --warn-unreachable`` flags a removed arm at either level as a build
    error (AC-3). Adding a fifth ``StaleReason`` without a matching arm
    is caught at type-check time AND at runtime.

    This mirrors the codebase convention established by the *producer* —
    ``codegenie.probes.layer_b.index_health._derive_confidence`` (see
    that function's docstring) — and is the structural enforcement at
    BOTH levels that ``mypy`` requires; a flat single-match form would
    leave mypy unable to fully narrow the nested Pydantic discriminator.
    """
    match value:
        case Fresh(indexed_at=ts):
            return f"- [OK] {name} · indexed_at={_iso_utc_z(ts)}"
        case Stale(reason=reason):
            match reason:
                case CommitsBehind(n=n, last_indexed=last_indexed):
                    short = _short_sha(last_indexed)
                    return f"- [STALE] {name} · commits_behind={n} · last_indexed={short}"
                case DigestMismatch(expected=expected, actual=actual):
                    return (
                        f"- [STALE] {name} · digest_mismatch · "
                        f"expected={_short_digest(expected)}… · "
                        f"actual={_short_digest(actual)}…"
                    )
                case CoverageGap(files_indexed=files_indexed, files_in_repo=files_in_repo):
                    return (
                        f"- [STALE] {name} · coverage_gap · indexed={files_indexed}/{files_in_repo}"
                    )
                case IndexerError(message=message):
                    return f"- [STALE] {name} · indexer_error · {message}"
                case _:  # pragma: no cover — exhaustiveness guard
                    assert_never(reason)
        case _:  # pragma: no cover — exhaustiveness guard
            assert_never(value)


def _malformed_row(name: str, summary: str) -> str:
    """Render the defense-in-depth ``slice_malformed`` row (AC-5).

    Kept off the ``match`` arm so the exhaustiveness check is purely on
    ``IndexFreshness`` shape, not on the renderer's error-path overlay.
    """
    return f"- [STALE] {name} · indexer_error · slice_malformed:{summary}"


def _iso_utc_z(ts: datetime) -> str:
    """Render a timezone-aware datetime as ``YYYY-MM-DDTHH:MM:SSZ`` (AC-4).

    The producer (``IndexHealthProbe``) constructs UTC datetimes (per the
    docstring on :class:`codegenie.indices.freshness.Fresh`). Naive
    datetimes are accepted defensively — formatted via ``isoformat`` then
    suffixed ``Z`` so the row remains well-shaped under defense-in-depth.
    """
    s = ts.isoformat()
    if s.endswith("+00:00"):
        return s[:-6] + "Z"
    if "+" in s or s.endswith("Z"):
        return s
    return s + "Z"


def _short_sha(s: str) -> str:
    """First 8 chars when *s* is hex-shaped; otherwise *s* unchanged.

    ``CommitsBehind.last_indexed`` is documented as a raw commit SHA; the
    hex guard exists so a non-SHA producer payload doesn't get silently
    truncated mid-character.
    """
    if len(s) >= 8 and all(c in "0123456789abcdefABCDEF" for c in s[:40]):
        return s[:8]
    return s


def _short_digest(s: str) -> str:
    """First 8 chars of a digest; assumed hex by ``DigestMismatch`` semantics."""
    return s[:8]


def _summarize_validation_error(exc: ValidationError) -> str:
    """Compact single-line summary of a ``ValidationError`` (AC-5).

    The renderer is the last line of defense — the full error structure
    has no place in a human report. We keep the first reported error's
    type tag, which is stable enough to grep for in audits.
    """
    errors = exc.errors()
    if not errors:
        return "validation_error"
    return str(errors[0].get("type", "validation_error"))
