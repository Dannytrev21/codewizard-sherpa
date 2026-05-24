"""Kernel-tier tz-aware datetime alias — used wherever wall-clock fields
participate in chain-verify / replay / audit (Phase-4 S1-04).

A naive ``datetime`` silently breaks chain-verify across timezone-shifted
CI runners (ADR-0016) and is unsafe to compare across audit-log replays.
``TzAwareDatetime`` is the single annotated type every contract surface
uses; the validator is defined once.

Lives under ``codegenie.types`` (kernel-tier) so both ``codegenie.rag.models``
and ``codegenie.fallback.budget`` can import it without forming a cycle —
the validator is pure stdlib (no Pydantic dependency on either leaf
package).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator


def _require_tz_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be tz-aware (UTC); naive datetimes are rejected")
    return value


TzAwareDatetime = Annotated[datetime, AfterValidator(_require_tz_aware)]
"""Reusable tz-aware datetime alias.

Applied to ``SolvedExample.created_at``, ``RecordProvenance.created_at``,
and ``BudgetToken.issued_at``. A naive ``datetime`` produces a Pydantic
``ValidationError`` at construction time.
"""

__all__ = ("TzAwareDatetime",)
