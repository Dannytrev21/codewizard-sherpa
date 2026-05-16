"""``RedactedSlice`` — smart-constructor at the writer boundary (02-ADR-0010).

Closes **Gap 4** from ``phase-arch-design.md §"Gap analysis & improvements"``:
the runtime defense in 02-ADR-0005 ("no plaintext persistence") relied on a
convention — every caller of the redactor had to remember to drop the
``list[SecretFinding]`` tuple element before writing to disk. This module
upgrades that convention to a type-level guarantee.

Three rungs of structural defense:

1. **Runtime** — ``SecretRedactor.redact_secrets`` replaces cleartext inline,
   returning the redacted payload + an in-memory findings list that is
   never persisted (02-ADR-0005).
2. **Type-system** — the writer accepts only ``RedactedSlice``; the
   findings list is a sibling tuple element that the writer's signature
   refuses (02-ADR-0010, this module).
3. **Source-level** — ``redact_secrets`` is the only call site that
   constructs a ``RedactedSlice`` anywhere in ``src/`` (deferred to S7-04,
   ``inspect``-based boundary test).

``RedactedSlice`` carries exactly three fields: the redacted slice itself
(a recursive ``JSONValue`` dict), the integer findings count (total
replacements, including duplicates of the same cleartext), and the list of
deduplicated 8-hex BLAKE3 fingerprints. The format invariant
``^[0-9a-f]{8}$`` and the count invariant ``findings_count >=
len(fingerprints)`` are enforced at construction time.

The bypass surface that the smart-constructor pattern names — Pydantic's
``model_construct`` (documented as "skip validation") — is closed at lint
time by ``scripts/check_forbidden_patterns.py`` (S1-11): the
``model_construct`` rule fires under ``src/codegenie/output/**``. See
``scripts/check_forbidden_patterns.py`` and the docstring of
``_PHASE2_BANNED_PACKAGES`` for the exact predicate.

This module is a **pure functional core**: no I/O, no logging, no
filesystem reads, no ``os.environ``, no clock, no subprocess. The
validators are pure functions over their arguments. Future contributors
must not add I/O here.

References:

- ``phase-arch-design.md §"Gap analysis & improvements" Gap 4``
- 02-ADR-0010 (this module)
- 02-ADR-0005 (the runtime defense)
- production ADR-0033 (smart-constructor + newtype discipline)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from codegenie.parsers import JSONValue

if TYPE_CHECKING:
    from typing import Self

__all__ = ["RedactedSlice"]


_FP_PATTERN = re.compile(r"^[0-9a-f]{8}$")


class RedactedSlice(BaseModel):
    """Smart-constructor wrapper around a post-redaction slice payload.

    Field declaration order is load-bearing: ``slice`` first (the payload
    readers want at the top of ``repo-context.yaml``), ``findings_count``
    second (the audit count), ``fingerprints`` last (the BLAKE3 first-8-hex
    fingerprints — deduplicated, stably ordered). Pydantic preserves
    declaration order in both ``model_dump`` and ``model_dump_json``.

    The model is ``frozen=True, extra="forbid"`` — instances are immutable
    and unknown fields are rejected at construction. Mutation of a
    constructed instance raises ``pydantic.ValidationError``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    slice: dict[str, JSONValue]
    findings_count: int = Field(ge=0)
    fingerprints: list[str]

    @field_validator("fingerprints")
    @classmethod
    def _validate_fingerprints(cls, v: list[str]) -> list[str]:
        for fp in v:
            if not isinstance(fp, str) or not _FP_PATTERN.fullmatch(fp):
                raise ValueError(
                    f"fingerprint must match ^[0-9a-f]{{8}}$ (exactly 8 lowercase "
                    f"hex chars); got {fp!r}"
                )
        return v

    @model_validator(mode="after")
    def _count_ge_unique_fingerprints(self) -> Self:
        if self.findings_count < len(self.fingerprints):
            raise ValueError(
                f"findings_count ({self.findings_count}) must be >= "
                f"len(fingerprints) ({len(self.fingerprints)}); fingerprints "
                f"are deduplicated and count is total findings."
            )
        return self
