"""Shared comparator body for rule-pack / catalog version freshness (S6-08).

Three Phase-2 freshness sources (``semgrep`` / ``gitleaks`` / ``conventions``)
share the same compare-current-to-prior logic; the *I/O* part lives in
:func:`codegenie.indices._prior_lookup.load_prior_value` and the *per-
scanner version key* is the scanner's concern. This helper crystallizes
the comparator:

- If both ``observed`` and ``expected`` are present and differ →
  :class:`~codegenie.indices.freshness.Stale` with a typed
  :class:`~codegenie.indices.freshness.DigestMismatch` reason.
- Otherwise (bootstrap: no expected; missing observed; equal values) →
  :class:`~codegenie.indices.freshness.Fresh` with the current UTC
  timestamp (the freshness check has no source-of-truth timestamp; the
  scanner that wrote the slice carries the authoritative time elsewhere,
  but the type-level ``indexed_at`` field is non-optional).

When a fourth call site arrives (foreseeable: a future rule-packed
scanner), the helper stays unchanged — the new scanner registers its own
``@register_index_freshness_check`` block that delegates here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from codegenie.indices.freshness import (
    DigestMismatch,
    Fresh,
    IndexFreshness,
    Stale,
)

__all__ = ["compare_versions", "extract_version_pair"]


def extract_version_pair(
    slice_: dict[str, object], scanner_name: str, version_key: str
) -> tuple[str | None, str | None]:
    """Return ``(observed, expected)`` strings from a slice dict.

    Tolerates two on-disk wrappings (sibling-scanner reality, Layer-G
    ``{name: payload}`` wrap vs. Layer-B unwrapped); ``None`` for any
    absent / non-string value. The caller treats either ``None`` as the
    bootstrap path.
    """
    expected_key = f"expected_{version_key}"
    observed = _str_or_none(slice_.get(version_key))
    expected = _str_or_none(slice_.get(expected_key))
    if observed is not None and expected is not None:
        return observed, expected
    inner = slice_.get(scanner_name)
    if isinstance(inner, dict):
        if observed is None:
            observed = _str_or_none(inner.get(version_key))
        if expected is None:
            expected = _str_or_none(inner.get(expected_key))
    return observed, expected


def compare_versions(
    slice_: dict[str, object], scanner_name: str, version_key: str
) -> IndexFreshness:
    """Pure comparator. See module docstring for the bootstrap semantics."""
    observed, expected = extract_version_pair(slice_, scanner_name, version_key)
    if observed is None or expected is None:
        return Fresh(indexed_at=_now())
    if observed != expected:
        return Stale(reason=DigestMismatch(expected=expected, actual=observed))
    return Fresh(indexed_at=_now())


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _now() -> datetime:
    return datetime.now(tz=UTC)
