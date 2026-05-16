"""Pydantic data model for ``codegenie.conventions`` — Phase 2 S2-02.

Two discriminated unions:

* :data:`ConventionRule` — four variants over ``kind``:
  ``dockerfile_pattern``, ``dockerfile_pattern_inverted``, ``file_pattern``,
  ``missing_file``. Each ``pattern``-carrying variant compiles its regex at
  *load* time via a ``model_validator(mode="after")``; uncompilable
  patterns surface as a Pydantic ``ValidationError`` which the loader
  classifies as :class:`codegenie.conventions.loader.SchemaError`. The
  compiled regex is stashed on the model as :attr:`_compiled_pattern` so
  ``Catalog.apply`` never re-compiles.

* :data:`ConventionResult` — three variants over ``kind``: :class:`Pass`,
  :class:`Fail`, :class:`NotApplicable`. ``NotApplicable`` is the
  load-bearing third value (illegal-states-unrepresentable per
  ADR-0033 §4): a rule that did not run because its input is absent is
  *not* a pass, and the Phase 2 Confidence section depends on the
  distinction.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #10, §"Data model".
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` §1, §3, §4.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from codegenie.types.identifiers import ConventionId

__all__ = [
    "ConventionResult",
    "ConventionRule",
    "ConventionRuleDockerfilePattern",
    "ConventionRuleDockerfilePatternInverted",
    "ConventionRuleFilePattern",
    "ConventionRuleMissingFile",
    "Fail",
    "NotApplicable",
    "Pass",
]


# ---------------------------------------------------------------------------
# ConventionRule discriminated union — four variants over ``kind``.
# ---------------------------------------------------------------------------


class ConventionRuleDockerfilePattern(BaseModel):
    """Asserts ``pattern`` MATCHES somewhere in ``Dockerfile``."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["dockerfile_pattern"] = "dockerfile_pattern"
    id: ConventionId
    description: str
    pattern: str
    _compiled_pattern: re.Pattern[str] = None  # type: ignore[assignment]

    @model_validator(mode="after")
    def _compile_pattern(self) -> ConventionRuleDockerfilePattern:
        compiled = _compile_or_raise(self.pattern)
        # ``object.__setattr__`` because ``frozen=True`` blocks attribute writes.
        object.__setattr__(self, "_compiled_pattern", compiled)
        return self


class ConventionRuleDockerfilePatternInverted(BaseModel):
    """Asserts ``pattern`` does NOT match anywhere in ``Dockerfile``."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["dockerfile_pattern_inverted"] = "dockerfile_pattern_inverted"
    id: ConventionId
    description: str
    pattern: str
    _compiled_pattern: re.Pattern[str] = None  # type: ignore[assignment]

    @model_validator(mode="after")
    def _compile_pattern(self) -> ConventionRuleDockerfilePatternInverted:
        compiled = _compile_or_raise(self.pattern)
        object.__setattr__(self, "_compiled_pattern", compiled)
        return self


class ConventionRuleFilePattern(BaseModel):
    """Asserts every file matched by ``file_glob`` matches ``pattern``."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["file_pattern"] = "file_pattern"
    id: ConventionId
    description: str
    file_glob: str
    pattern: str
    _compiled_pattern: re.Pattern[str] = None  # type: ignore[assignment]

    @model_validator(mode="after")
    def _compile_pattern(self) -> ConventionRuleFilePattern:
        compiled = _compile_or_raise(self.pattern)
        object.__setattr__(self, "_compiled_pattern", compiled)
        return self


class ConventionRuleMissingFile(BaseModel):
    """Asserts no file in the repo matches ``file_glob`` (presence-as-assertion).

    The kind is named for what the rule *asserts*, not what it observes:
    the rule **passes** when no file matches the glob, and **fails** when
    one does. A one-line code comment in ``_apply_missing_file`` documents
    this inversion for the next reader.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["missing_file"] = "missing_file"
    id: ConventionId
    description: str
    file_glob: str


ConventionRule = Annotated[
    ConventionRuleDockerfilePattern
    | ConventionRuleDockerfilePatternInverted
    | ConventionRuleFilePattern
    | ConventionRuleMissingFile,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# ConventionResult discriminated union — Pass / Fail / NotApplicable.
# Field sets are deliberately minimal (illegal-states-unrepresentable per
# ADR-0033 §4): Pass has no ``evidence``, NotApplicable has no ``evidence``,
# Fail has no ``reason``.
# ---------------------------------------------------------------------------


class Pass(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["pass"] = "pass"
    rule_id: ConventionId


class Fail(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["fail"] = "fail"
    rule_id: ConventionId
    evidence: str


class NotApplicable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["not_applicable"] = "not_applicable"
    rule_id: ConventionId
    reason: str


ConventionResult = Annotated[
    Pass | Fail | NotApplicable, Field(discriminator="kind")
]


# ---------------------------------------------------------------------------
# Pure helper — regex smart-constructor.
# ---------------------------------------------------------------------------


def _compile_or_raise(pattern: str) -> re.Pattern[str]:
    """Compile ``pattern`` or raise ``ValueError`` for Pydantic to bundle.

    ``re.error`` is re-raised as ``ValueError`` so Pydantic v2 surfaces the
    compilation failure as a ``ValidationError`` row whose ``loc`` ends in
    ``"pattern"``. The loader's ``_classify_validation_error`` reads the
    row and emits a :class:`SchemaError` (S2-02 AC-11a).
    """
    try:
        # ``re.MULTILINE`` so ``^`` and ``$`` anchor to line starts/ends
        # inside multi-line file contents (Dockerfiles, tsconfigs, etc.).
        return re.compile(pattern, flags=re.MULTILINE)
    except re.error as exc:
        raise ValueError(f"invalid regex pattern: {exc}") from exc
