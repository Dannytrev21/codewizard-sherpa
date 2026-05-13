"""Pydantic ``_ProbeOutputValidator`` — internal trust boundary (ADR-0010).

The coordinator dispatch path (S3-05) calls
``_ProbeOutputValidator.model_validate({"schema_slice": ..., "confidence": ...})``
on every ``ProbeOutput`` after ``probe.run()`` returns and before
``OutputSanitizer.scrub``. This validator structurally enforces "facts, not
judgments" (``production/design.md §2.2``):

- ``schema_slice`` is typed as a recursive :data:`JSONValue` — no ``bytes``,
  no ``Callable``, no ``Any``. Non-JSON-representable values land as
  ``pydantic.ValidationError``.
- A field-validator walks every dict key (at every nesting depth, through
  lists too) and raises :class:`~codegenie.errors.SecretLikelyFieldNameError`
  on any match against :data:`SECRET_FIELD_PATTERN`. ADR-0008 calls this the
  first pass of "same regex, two passes"; the sanitizer's repeat pass
  imports this same compiled pattern.
- ``confidence`` is ``Literal["high", "medium", "low"]`` (ADR-0010 §Decision).

The contract surface — ``ProbeOutput`` (dataclass, ``probes/base.py``) —
intentionally stays decoupled from this validator (ADR-0007 / ADR-0010
§Decision line 33). ``validator.py`` MUST NOT import from
``codegenie.probes``; the coordinator dispatches by passing a dict, not a
dataclass instance. ``_ProbeOutputValidator`` is module-private (leading
underscore) and is never re-exported from ``codegenie.coordinator``.

Pydantic v2 wrapping note: ``@field_validator``-raised exceptions (including
non-``ValueError`` types like ``SecretLikelyFieldNameError``) are wrapped by
Pydantic into a ``ValidationError``. S3-05 unwraps via
``exc.errors()[0]["ctx"]["error"]`` (or ``exc.__cause__`` as a fallback).
"""

from __future__ import annotations

import re
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_core import PydanticCustomError
from typing_extensions import TypeAliasType

from codegenie.errors import SecretLikelyFieldNameError

__all__ = ["JSONValue", "SECRET_FIELD_PATTERN"]


# Named recursive type alias (Pydantic v2's documented pattern — see
# https://docs.pydantic.dev/2.13/concepts/types/#named-recursive-types).
# ``bool`` precedes ``int`` deliberately — Pydantic v2 ``Union`` member-matching
# would otherwise coerce ``True`` to ``1`` (bool subclasses int). AC-13 pins
# this. ``list``/``dict`` recurse through the alias name; the runtime closure
# is exactly: None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue].
JSONValue = TypeAliasType(
    "JSONValue",
    Union[
        None,
        bool,
        int,
        float,
        str,
        "list[JSONValue]",
        "dict[str, JSONValue]",
    ],
)


# Single source of truth for ADR-0008's defense-in-depth repeat pass —
# S3-03's ``output/sanitizer.py`` imports this same compiled object.
SECRET_FIELD_PATTERN: re.Pattern[str] = re.compile(
    r"(?i)^.*(secret|token|password|credential|api[_-]?key|"
    r"auth[_-]?token|bearer|access[_-]?key|private[_-]?key).*$"
)


# Allowed JSON-leaf types. ``bool`` is listed separately from ``int`` because
# ``isinstance(True, int)`` is True (bool subclasses int); we still want both,
# but Pydantic's ``Union`` member order keeps ``True`` typed as ``bool``.
# ``Decimal``, ``datetime``, ``Path``, ``bytes``, callables, etc. are all
# rejected here — strict-mode Pydantic does not reject ``Decimal -> float``
# coercion, so the walker is the authoritative type-policer (AC-2/AC-12).
_ALLOWED_LEAF_TYPES: tuple[type, ...] = (type(None), bool, int, float, str)


def _walk_and_enforce(root: dict[str, Any]) -> None:
    """Iteratively walk ``root`` enforcing two structural rules.

    1. **Secret-shaped key rejection** (AC-4 / AC-11) — every dict key (at
       every depth, including dicts inside lists) is matched against
       :data:`SECRET_FIELD_PATTERN`. First match raises
       :class:`SecretLikelyFieldNameError` whose ``args`` carry the offending
       key and its path from ``root``.
    2. **Non-JSON-representable value rejection** (AC-2 / AC-12) — every
       non-container leaf must be an instance of :data:`_ALLOWED_LEAF_TYPES`.
       Anything else (``bytes``, ``Decimal``, ``datetime``, custom objects,
       callables, ``set``, ``tuple``, ``Path``) raises ``TypeError``. This
       runs as a Pydantic ``mode="before"`` validator so it sees the raw
       value *before* Pydantic's coercion (which would otherwise turn
       ``Decimal('1.0')`` into ``float`` and silently widen the contract).

    Iterative (stack-based) by design — a naive recursive walker overflows
    Python's stack on adversarial deep-nesting inputs (AC-19).
    """
    # Stack entry: (node, path-tuple-from-root).
    stack: list[tuple[Any, tuple[Any, ...]]] = [(root, ())]
    while stack:
        node, path = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and SECRET_FIELD_PATTERN.search(k):
                    raise SecretLikelyFieldNameError(k, path + (k,))
                child_path = path + (k,) if isinstance(k, str) else path
                if isinstance(v, dict) or isinstance(v, list):
                    stack.append((v, child_path))
                elif not isinstance(v, _ALLOWED_LEAF_TYPES):
                    raise ValueError(
                        f"non-JSON-representable leaf {type(v).__name__!r} at {child_path}"
                    )
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                child_path = path + (idx,)
                if isinstance(item, dict) or isinstance(item, list):
                    stack.append((item, child_path))
                elif not isinstance(item, _ALLOWED_LEAF_TYPES):
                    raise ValueError(
                        f"non-JSON-representable leaf {type(item).__name__!r} at {child_path}"
                    )


class _ProbeOutputValidator(BaseModel):
    """Internal trust-boundary validator (ADR-0010).

    Constructed by the coordinator from each ``ProbeOutput`` immediately
    after ``probe.run()`` returns and before ``OutputSanitizer.scrub``. The
    contract direction is one-way: the dataclass contract (``probes/base.py``)
    lifts to the service; this Pydantic wrapper is an internal coordinator
    implementation detail (ADR-0007 §Reversibility).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_slice: dict[str, JSONValue]
    confidence: Literal["high", "medium", "low"]

    @field_validator("schema_slice", mode="before")
    @classmethod
    def _enforce_json_value_closure(cls, v: Any) -> Any:
        """Pre-validation walk — enforces type closure and key-name regex.

        Runs ``mode='before'`` so it sees the raw input prior to Pydantic's
        type coercion (which otherwise widens ``Decimal -> float`` and similar).

        Pydantic v2 does not wrap arbitrary exceptions raised in a
        ``field_validator`` (only ``ValueError``, ``AssertionError``, and
        ``PydanticCustomError``). We raise :class:`PydanticCustomError` so
        ``pydantic.ValidationError.errors()[0]["ctx"]["error"]`` carries the
        typed :class:`SecretLikelyFieldNameError` instance directly — S3-05's
        coordinator dispatch unwraps via the same surface. For non-JSON-leaf
        rejections we raise a plain ``TypeError`` (Pydantic v2 wraps ``TypeError``
        the same way as ``ValueError``).
        """
        if not isinstance(v, dict):
            # Defer top-level type errors to Pydantic's dict[...] validator.
            return v
        try:
            _walk_and_enforce(v)
        except SecretLikelyFieldNameError as exc:
            key = exc.args[0] if exc.args else "<unknown>"
            path = exc.args[1] if len(exc.args) > 1 else (key,)
            raise PydanticCustomError(
                "secret_likely_field_name",
                "secret-shaped key {key!r} at {path}",
                {"error": exc, "key": key, "path": path},
            ) from exc
        return v
