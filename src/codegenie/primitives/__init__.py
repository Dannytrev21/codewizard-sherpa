"""Bounded additive core primitives — the named home for ADR-0039 primitives.

Phase 7 ADR-0004 establishes `src/codegenie/primitives/` as the directory
future bounded primitives (per production ADR-0039's criteria) land under
without further architectural debate. Each primitive ships as a sibling
subpackage; this top-level `__init__.py` is intentionally empty so the
public surface is the sub-package's own `__init__.py`.

Current subpackages:
- ``vuln_provenance`` — production ADR-0038 vulnerability-provenance primitive
  (Phase 7 ships this seed; later phases extend the seven-variant union and
  adapter registry).
"""

from __future__ import annotations
