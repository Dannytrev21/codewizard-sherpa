"""Unit tests for ``codegenie.report.confidence_section`` (S8-01).

ACs covered:
- AC-1 module surface + closed ``__all__``.
- AC-2 single exhaustive ``match`` covering every ``IndexFreshness`` variant.
- AC-4 deterministic row order + per-variant format.
- AC-5 malformed slice does not raise; surfaces ``slice_malformed`` row.
- AC-8 importing the renderer module loads NO ``codegenie.probes.*``.

AC-3 (``mypy --warn-unreachable`` enforces exhaustiveness on a deleted ``case``)
is a build-time ritual recorded in ``_attempts/S8-01.md``; not unit-testable.
AC-6 (writer integration / atomic write) lives in the integration suite.
AC-7 (``mypy --strict`` + ``ruff``) is enforced by ``make check``.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from typing import Any

import pytest

from codegenie.indices.freshness import (
    CommitsBehind,
    CoverageGap,
    DigestMismatch,
    Fresh,
    IndexerError,
    Stale,
)
from codegenie.report import ConfidenceSectionRenderer, render_confidence_section
from codegenie.report import confidence_section as cs_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap(slices: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Wrap raw ``{<index_name>: {"freshness": ..., ...}}`` into the merged
    envelope shape the renderer expects (matches the post-shallow-merge
    ``envelope["probes"]["index_health"]["index_health"]`` path).
    """
    return {"probes": {"index_health": {"index_health": slices}}}


def _slice_for(freshness_value: Any) -> dict[str, Any]:
    return {"freshness": freshness_value.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# AC-1 — module surface
# ---------------------------------------------------------------------------


def test_module_surface_is_closed() -> None:
    """``__all__`` exports both names; no extras leak."""
    assert set(cs_module.__all__) == {"ConfidenceSectionRenderer", "render_confidence_section"}
    assert callable(render_confidence_section)
    assert isinstance(ConfidenceSectionRenderer, type)


def test_renderer_class_wraps_function() -> None:
    """``ConfidenceSectionRenderer().render(envelope)`` returns the same
    string as ``render_confidence_section(envelope)`` — pure wrapper.
    """
    envelope = _wrap(
        {"idx_a": _slice_for(Fresh(indexed_at=datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)))}
    )
    direct = render_confidence_section(envelope)
    via_class = ConfidenceSectionRenderer().render(envelope)
    assert direct == via_class


# ---------------------------------------------------------------------------
# AC-2 — exhaustive match over every variant
# ---------------------------------------------------------------------------


def test_exhaustive_match_every_variant() -> None:
    """Construct one of each variant; assert every variant-specific marker
    appears in the rendered output. Adding a sixth ``StaleReason`` without
    a case arm would (a) fail mypy in CI and (b) fail this list-build (the
    marker for the new variant would not appear).
    """
    now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    slices = {
        "idx_fresh": _slice_for(Fresh(indexed_at=now)),
        "idx_commits": _slice_for(
            Stale(reason=CommitsBehind(n=3, last_indexed="abc12345deadbeef"))
        ),
        "idx_digest": _slice_for(
            Stale(reason=DigestMismatch(expected="aa" * 32, actual="bb" * 32))
        ),
        "idx_coverage": _slice_for(Stale(reason=CoverageGap(files_indexed=8, files_in_repo=10))),
        "idx_error": _slice_for(Stale(reason=IndexerError(message="scip_unavailable"))),
    }
    out = render_confidence_section(_wrap(slices))

    # One marker per variant.
    assert "[OK]" in out  # Fresh
    assert "commits_behind=3" in out  # CommitsBehind
    assert "digest_mismatch" in out  # DigestMismatch
    assert "coverage_gap" in out  # CoverageGap
    assert "indexer_error" in out  # IndexerError
    # Confidence heading present (AC-6 surface requirement; cheap to assert here).
    assert out.startswith("## Confidence")


# ---------------------------------------------------------------------------
# AC-4 — per-variant row format + deterministic order
# ---------------------------------------------------------------------------


def test_row_format_per_variant_fresh() -> None:
    now = datetime(2026, 5, 18, 12, 34, 56, tzinfo=UTC)
    out = render_confidence_section(_wrap({"idx_a": _slice_for(Fresh(indexed_at=now))}))
    assert "- [OK] idx_a · indexed_at=2026-05-18T12:34:56Z" in out


def test_row_format_per_variant_commits_behind() -> None:
    out = render_confidence_section(
        _wrap(
            {
                "scip": _slice_for(
                    Stale(reason=CommitsBehind(n=7, last_indexed="abc12345deadbeefcafebabe"))
                )
            }
        )
    )
    # short-sha is the first 8 hex chars when ``last_indexed`` is a SHA-shaped string.
    assert "- [STALE] scip · commits_behind=7 · last_indexed=abc12345" in out


def test_row_format_per_variant_digest_mismatch() -> None:
    out = render_confidence_section(
        _wrap(
            {"scip": _slice_for(Stale(reason=DigestMismatch(expected="aa" * 32, actual="bb" * 32)))}
        )
    )
    assert "- [STALE] scip · digest_mismatch · expected=aaaaaaaa… · actual=bbbbbbbb…" in out


def test_row_format_per_variant_coverage_gap() -> None:
    out = render_confidence_section(
        _wrap({"scip": _slice_for(Stale(reason=CoverageGap(files_indexed=8, files_in_repo=10)))})
    )
    assert "- [STALE] scip · coverage_gap · indexed=8/10" in out


def test_row_format_per_variant_indexer_error() -> None:
    out = render_confidence_section(
        _wrap({"scip": _slice_for(Stale(reason=IndexerError(message="upstream_scip_unavailable")))})
    )
    assert "- [STALE] scip · indexer_error · upstream_scip_unavailable" in out


def test_row_order_deterministic() -> None:
    """Rows are sorted ASCII-lex by index name regardless of input dict order."""
    now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    slices = {
        "zebra": _slice_for(Fresh(indexed_at=now)),
        "apple": _slice_for(Fresh(indexed_at=now)),
        "mango": _slice_for(Fresh(indexed_at=now)),
    }
    out = render_confidence_section(_wrap(slices))
    pos_apple = out.index("apple")
    pos_mango = out.index("mango")
    pos_zebra = out.index("zebra")
    assert pos_apple < pos_mango < pos_zebra


def test_ascii_only_no_emoji() -> None:
    """The renderer outputs ASCII-only plus the · separator and the …
    truncation marker. No emoji per CLAUDE.md Rule 11 + AC-4 "ASCII Markdown".
    """
    now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    out = render_confidence_section(_wrap({"a": _slice_for(Fresh(indexed_at=now))}))
    # Markdown-safe ASCII or the explicitly-allowed Unicode separators only.
    allowed_unicode = {"·", "…"}  # · …
    for ch in out:
        assert ch.isascii() or ch in allowed_unicode, f"unexpected char {ch!r}"


# ---------------------------------------------------------------------------
# AC-5 — malformed slice does not crash; surfaces a stable row.
# ---------------------------------------------------------------------------


def test_malformed_slice_does_not_crash() -> None:
    """A slice whose ``freshness`` field fails Pydantic validation against
    ``IndexFreshness`` renders one ``slice_malformed`` row instead of
    raising. Subsequent valid entries still render.
    """
    now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    slices = {
        "bad": {"freshness": {"kind": "not-a-known-kind", "garbage": True}},
        "ok": _slice_for(Fresh(indexed_at=now)),
    }
    out = render_confidence_section(_wrap(slices))
    assert "- [STALE] bad · indexer_error · slice_malformed:" in out
    assert "- [OK] ok ·" in out


def test_malformed_freshness_missing_entirely() -> None:
    """A slice missing the ``freshness`` field falls under the malformed path."""
    out = render_confidence_section(_wrap({"bad": {"confidence": "low"}}))
    assert "- [STALE] bad · indexer_error · slice_malformed:" in out


def test_empty_envelope_returns_heading_only() -> None:
    """Zero registered indices → ``## Confidence`` heading only, no rows."""
    out = render_confidence_section({"probes": {}})
    assert out.startswith("## Confidence")
    assert "[OK]" not in out
    assert "[STALE]" not in out


# ---------------------------------------------------------------------------
# AC-8 — no probe-registry import side effect.
# ---------------------------------------------------------------------------


def test_no_probe_registry_import() -> None:
    """Importing ``codegenie.report.confidence_section`` in a clean
    sub-process must not load any ``codegenie.probes`` module. This is the
    structural guarantee from phase-arch-design.md §"Component design" #2
    §"Why not co-located".
    """
    script = (
        "import sys\n"
        "import codegenie.report.confidence_section\n"
        "probes_loaded = sorted(m for m in sys.modules if m.startswith('codegenie.probes'))\n"
        "print('PROBES:' + ','.join(probes_loaded))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("PROBES:")), "")
    assert line == "PROBES:", f"renderer pulled probe modules: {line!r}; stderr={proc.stderr!r}"


# ---------------------------------------------------------------------------
# Defensive: invariants the renderer must preserve.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "envelope",
    [
        {},
        {"probes": None},
        {"probes": {"index_health": None}},
        {"probes": {"index_health": {"index_health": None}}},
        {"probes": {"index_health": {"index_health": {"x": None}}}},
        {"probes": {"index_health": {"index_health": {"x": "not-a-dict"}}}},
    ],
)
def test_renderer_never_raises_on_random_garbage(envelope: Any) -> None:
    """Pathological envelope shapes (None, non-dict slice, wrong nesting)
    return a string instead of raising. The renderer is the last line of
    defense before user output.
    """
    out = render_confidence_section(envelope)
    assert isinstance(out, str)
    assert out.startswith("## Confidence")
