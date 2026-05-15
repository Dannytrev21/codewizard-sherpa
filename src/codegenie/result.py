"""``Result[T, E] = Ok[T] | Err[E]`` — frozen Pydantic discriminated union.

The Phase-2 architecturally-named home for the ``Result`` sum type. First
consumer is :class:`codegenie.tccm.TCCMLoader` (S1-04 itself); S2-01's
``SkillsLoader`` and S2-02's ``ConventionsCatalogLoader`` reuse it for
partial-success returns. Phase 1 ships exception-raising parsers; Phase 2
introduces ``Result`` for loaders that need to return *partial* answers
(per-file errors alongside a populated catalog).

Module-purity invariant (mirrors S1-01 ``IndexFreshness`` and S1-03
``AdapterConfidence``): imports only ``__future__``, ``typing``, ``pydantic``.
No I/O, no logger, no sibling Phase-2 modules. AST source-scan tests enforce.

Methods on ``Ok`` / ``Err``: ``is_ok()``, ``is_err()``, ``unwrap()``,
``unwrap_err()``. Monadic helpers (``map``, ``and_then``, ``or_else``) are
deliberately omitted until a third real consumer needs them (Rule 2 —
Simplicity First).

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S1-04-tccm-model-loader.md``
  §"Acceptance criteria" AC-0a..AC-0e — surface, methods, immutability,
  round-trip identity, module purity.
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` — sum-type +
  make-illegal-states-unrepresentable discipline.
"""

from __future__ import annotations

from typing import Annotated, Generic, Literal, NoReturn, TypeVar

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Err", "Ok", "Result"]

T = TypeVar("T")
E = TypeVar("E")


class Ok(BaseModel, Generic[T]):
    """Success variant. ``unwrap()`` returns ``value``; ``unwrap_err()`` raises."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    kind: Literal["ok"] = "ok"
    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_err(self) -> NoReturn:
        raise RuntimeError("Ok has no error")


class Err(BaseModel, Generic[E]):
    """Failure variant. ``unwrap_err()`` returns ``error``; ``unwrap()`` raises."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    kind: Literal["err"] = "err"
    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> NoReturn:
        raise RuntimeError(f"Err: {self.error!r}")

    def unwrap_err(self) -> E:
        return self.error


Result = Annotated[Ok[T] | Err[E], Field(discriminator="kind")]
