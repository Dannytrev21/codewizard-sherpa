"""Phase 0 ``Config`` frozen dataclass + declared-field helpers.

Sources:

- ``docs/phases/00-bullet-tracer-foundations/phase-arch-design.md``
  §Component design / Config (line 422) — plain dataclass (not Pydantic).
- ``docs/phases/00-bullet-tracer-foundations/final-design.md`` §2.13 —
  three-field shape, additive across phases.
- ``docs/phases/00-bullet-tracer-foundations/High-level-impl.md`` Step 3 —
  default values pinned.

The dataclass is **additive across phases**; later phases will add fields
without breaking S3-04. Keep this module light: no third-party imports at
module top level (AC-18 cold-start budget).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

__all__ = ["Config", "_defaults", "_known_fields"]


@dataclass(frozen=True)
class Config:
    """Phase 0 runtime configuration. Frozen so coordinator code can rely on
    instance immutability without defensive copying."""

    max_concurrent_probes: int = 8
    cache_ttl_hours: int = 24
    enable_audit: bool = True


def _defaults() -> dict[str, Any]:
    """Map declared field name → its default value."""
    return {f.name: f.default for f in fields(Config)}


def _known_fields() -> frozenset[str]:
    """Set of declared ``Config`` field names. Used by the loader's
    unknown-key check."""
    return frozenset(f.name for f in fields(Config))
