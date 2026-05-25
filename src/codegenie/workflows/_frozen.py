"""Single canonical home for the ``_FROZEN_FORBID`` Pydantic config constant.

ADR-0010 Amendment 2026-05-18 (Phase 3) ratified a single declaration site
discipline for the ``frozen=True, extra="forbid"`` model config. The Phase 6
S1-01 ``vuln_sut.py`` models import the constant from here; the AC-4 AST
walk fails loud if any ``BaseModel`` subclass in ``vuln_sut.py`` inlines
``ConfigDict(...)`` instead of referencing this name.
"""

from __future__ import annotations

from typing import Final

from pydantic import ConfigDict

__all__ = ["_FROZEN_FORBID"]

_FROZEN_FORBID: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid")
