"""Placeholder for the S2-04 :class:`PluginResolution` sum type.

S2-04 expands this module to the ``ConcreteResolution |
UniversalFallbackResolution`` sum type per Phase-3 ADR-0003. Until then,
the empty class lets the registry's ``resolve()`` return annotation
resolve under ``mypy --strict`` today (Phase-3 ADR-0010 §1 — kernel-tier
types are landed by the kernel-introducing story; the surface tightens
as later stories ship).
"""

from __future__ import annotations


class PluginResolution:
    """Placeholder; S2-04 expands to ``ConcreteResolution |
    UniversalFallbackResolution`` sum type."""
