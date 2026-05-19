"""Concrete CVE-feed implementations — registered into :data:`default_feed_registry`.

Three modules, each ships exactly one :class:`Feed` decorated with
``@register_vuln_feed(...)``: :mod:`.nvd`, :mod:`.ghsa`, :mod:`.osv`. The
``vuln_index/__init__.py`` explicit-import wiring is what triggers
registration; Phase 4+ adds a feed by landing a sibling module + one new
explicit-import line.
"""

from __future__ import annotations
