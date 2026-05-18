"""Phase 3 S1-01 — kernel-tier parse-error type.

A frozen Pydantic ``BaseModel`` carried by every Phase-3 smart constructor's
``Err`` branch (``codegenie.result.Err[ParseError]``). Two fields — the
human-readable ``message`` plus the offending ``value`` — give downstream
boundary code a stable shape for logging without re-parsing the input.

The canonical ``Result``/``Ok``/``Err`` sum type lives at
:mod:`codegenie.result` (Phase-2 S1-04, ADR-0033). This module *only* exports
``ParseError`` to preserve Rule-7 (no second ``Result`` definition under
``codegenie.types.result`` — that would fork the canonical home consumed by
``tccm/loader.py``, ``skills/loader.py``, and ``conventions/loader.py``).

ADRs: phase-3 ADR-0010 (domain-modeling discipline — smart-constructor
boundary parsers), production ADR-0033 (newtype every domain identifier).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["ParseError"]


class ParseError(BaseModel):
    """Boundary-parse failure carried by ``Err[ParseError]``.

    Frozen + ``extra="forbid"`` — the shape is part of the contract; extending
    requires an ADR amendment (ADR-0010).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    message: str
    value: str
