"""``VulnIndexLookupError`` + ``VulnIndexConfigError`` + ``VulnIndexException``.

Mirrors the S3-01 ``TCCMParseError`` resolution: frozen Pydantic
``BaseModel`` carries the typed ``reason`` payload, ``VulnIndexException``
is the thin ``Exception`` wrapper that production raise sites use. Tests
assert ``exc.value.model.reason == "..."``. Markers-only
:class:`codegenie.errors.CodegenieError` subclasses cannot carry the
typed-reason state these call sites need.

Adding a new reason variant = one entry in the ``Literal[...]`` + one new
test parameter (ADR-0010 §closed-set discipline).
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "VulnIndexConfigError",
    "VulnIndexException",
    "VulnIndexLookupError",
]


class VulnIndexLookupError(BaseModel):
    """Lookup / lifecycle failure with a typed ``reason`` payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: Literal["cve_not_found", "closed"]
    details: dict[str, str | int] = {}


class VulnIndexConfigError(BaseModel):
    """Environment / configuration failure with a typed ``reason`` payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: Literal["invalid_max_age", "non_positive_max_age"]
    details: dict[str, str | int] = {}


class VulnIndexException(Exception):
    """Production raise wrapper.

    Production code constructs the Pydantic model (frozen, typed reason)
    then raises ``VulnIndexException(model)``. Tests assert
    ``exc.value.model.reason == "<lit>"``.
    """

    def __init__(self, model: VulnIndexLookupError | VulnIndexConfigError) -> None:
        super().__init__(
            f"{type(model).__name__}: reason={model.reason!r} details={model.details!r}"
        )
        self.model: VulnIndexLookupError | VulnIndexConfigError = model


# S6-04 import target — keep the literal in one place to avoid drift between
# this module and the orchestrator's event-emission call site.
_STALE_VULN_INDEX_EVENT_TYPE: Final[Literal["stale_vuln_index"]] = "stale_vuln_index"
