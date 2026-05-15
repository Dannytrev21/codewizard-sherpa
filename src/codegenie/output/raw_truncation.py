"""Pure raw-artifact truncation policy — S1-09 (Gap 2 / ADR-0008 amendment).

Functional core (this module) / imperative shell (``codegenie.cli``) split: this
file is bytes-in, bytes-out + a tagged-union :data:`TruncationOutcome` value.
No I/O, no logging, no filesystem. The CLI's raw-artifact collection loop
invokes :func:`apply_raw_artifact_truncation` and is the sole emitter of the
``probe.raw_artifact.truncated`` structlog event.

Soft vs hard threshold contrast:

- The **hard** ceiling ``ResourceBudget.raw_artifact_mb`` (existing; raises
  via :meth:`codegenie.coordinator.budget.BudgetingContext.report_bytes`)
  defends against **runaway probes** — a probe that writes 200 MB to its
  workspace before the writer ever runs.
- The **soft** truncation ``ResourceBudget.raw_artifact_truncate_mb`` (this
  story) defends against **storage cost at portfolio scale** — a probe writes
  30 MB correctly; we keep only the first 5 MB on disk.

Boundary semantics mirror ``report_bytes``: inclusive at the limit, exclusive
above it (``>`` not ``>=``). A payload of exactly ``truncate_mb * 1 MiB`` is
NOT truncated; one byte past triggers truncation.

On truncation, the helper builds a JSON wrapper in the exact key order::

    {"__truncated_at_budget__": true,
     "original_bytes": <int>,
     "budget_bytes": <int>,
     "data": <parsed-JSON-or-replacement-string>}

The ``data`` field carries the parsed JSON value if the prefix is valid JSON;
otherwise the prefix decoded as ``utf-8`` with ``errors="replace"`` — handles
multi-byte characters straddling the boundary without crashing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

__all__ = [
    "Truncated",
    "TruncationOutcome",
    "Untruncated",
    "apply_raw_artifact_truncation",
]

_ONE_MIB = 1_048_576


@dataclass(frozen=True)
class Untruncated:
    """Outcome: payload was at or under the soft threshold — pass-through."""


@dataclass(frozen=True)
class Truncated:
    """Outcome: payload exceeded the soft threshold — wrapper replaces it."""

    original_bytes: int
    budget_bytes: int


TruncationOutcome = Untruncated | Truncated


def apply_raw_artifact_truncation(
    payload: bytes, truncate_mb: int, *, original_bytes: int | None = None
) -> tuple[bytes, TruncationOutcome]:
    """Apply the soft-truncation policy.

    Pure: no I/O, no logging, no ``os`` or ``pathlib``. The CLI is the sole
    side-effect site.

    Returns ``(payload, Untruncated())`` when ``len(payload) <= truncate_mb *
    1_048_576``. Otherwise replaces ``payload`` with a JSON-serialized
    ``{"__truncated_at_budget__": true, "original_bytes": N, "budget_bytes":
    M, "data": ...}`` wrapper and returns ``(wrapper_bytes,
    Truncated(original_bytes=N, budget_bytes=M))``.

    ``original_bytes`` may be passed when the caller has size-checked the
    file via ``os.fstat`` and read only a prefix (avoiding loading the full
    payload into memory for files known to be over budget). When supplied,
    the wrapper's ``original_bytes`` field carries the supplied size; when
    omitted it defaults to ``len(payload)``. The truncation decision still
    uses ``original_bytes`` if provided (else ``len(payload)``) so a caller
    that reads only the prefix can still trigger truncation correctly.

    Raises:
        ValueError: when ``truncate_mb <= 0`` — silent acceptance of 0 means
            "truncate everything to nothing," an unrecoverable config error
            (Rule 12, fail loud).
        ValueError: when ``original_bytes < 0`` — fail loud on a nonsensical
            override.
    """
    if truncate_mb <= 0:
        raise ValueError(f"truncate_mb must be positive, got {truncate_mb}")
    if original_bytes is not None and original_bytes < 0:
        raise ValueError(f"original_bytes must be >= 0, got {original_bytes}")
    budget_bytes = truncate_mb * _ONE_MIB
    effective_original = original_bytes if original_bytes is not None else len(payload)
    if effective_original <= budget_bytes:
        return payload, Untruncated()
    prefix = payload[:budget_bytes]
    data: object
    try:
        data = json.loads(prefix)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # ``json.loads(bytes)`` autodetects the encoding (utf-8 / utf-16) and
        # raises ``UnicodeDecodeError`` BEFORE any ``JSONDecodeError`` when the
        # prefix contains bytes invalid in the autodetected codec (e.g.,
        # 0xFF in utf-8). Catch both so the fallback is reachable.
        data = prefix.decode("utf-8", errors="replace")
    wrapper = {
        "__truncated_at_budget__": True,
        "original_bytes": effective_original,
        "budget_bytes": budget_bytes,
        "data": data,
    }
    return (
        json.dumps(wrapper, ensure_ascii=False).encode("utf-8"),
        Truncated(original_bytes=effective_original, budget_bytes=budget_bytes),
    )
