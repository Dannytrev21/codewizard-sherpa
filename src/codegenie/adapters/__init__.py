"""``codegenie.adapters`` — typed surfaces Phase 3 plugins implement.

Phase 2 ships exactly two modules:

- :mod:`codegenie.adapters.confidence` — the
  :data:`AdapterConfidence` discriminated union
  (:class:`Trusted` | :class:`Degraded` | :class:`Unavailable`).
- :mod:`codegenie.adapters.protocols` — four ``@runtime_checkable``
  ``Protocol`` classes plus :class:`Occurrence` and :data:`TestId`.

No implementations, no factories, no plugin loader (02-ADR-0007). Phase
3's first plugin ships the real adapters in its own source tree per
production ADR-0032.
"""

from codegenie.adapters.confidence import (
    AdapterConfidence,
    Degraded,
    Trusted,
    Unavailable,
)
from codegenie.adapters.protocols import (
    DepGraphAdapter,
    ImportGraphAdapter,
    Occurrence,
    ScipAdapter,
    TestId,
    TestInventoryAdapter,
)

__all__ = [
    "AdapterConfidence",
    "Degraded",
    "DepGraphAdapter",
    "ImportGraphAdapter",
    "Occurrence",
    "ScipAdapter",
    "TestId",
    "TestInventoryAdapter",
    "Trusted",
    "Unavailable",
]
