"""S6-02 fence — :meth:`PromptBuilder.build` signature lock.

Pins three invariants about the build signature:

1. ``prior_attempt_summary: str | None`` parameter is present and
   declared as ``str | None`` (not ``FencedSegment``, not ``str``-only).
2. No parameter is annotated as bare ``bool`` — Arch §Anti-patterns
   avoided (line 912) names this as the precedent for "no boolean
   flags". An ``is_retry: bool`` regression would be the canonical bad
   shape; the `bool(prior_attempts)` predicate at the call site IS the
   discriminator.
3. All parameters are keyword-only (``*`` sentinel comes first) —
   prevents positional-arg drift across retries.
"""

from __future__ import annotations

import inspect
from typing import get_type_hints

from codegenie.fallback.fence.prompt_builder import PromptBuilder


def test_prompt_builder_build_has_prior_attempt_summary_param() -> None:
    sig = inspect.signature(PromptBuilder.build)
    assert "prior_attempt_summary" in sig.parameters, (
        "PromptBuilder.build must accept the prior_attempt_summary kwarg — "
        "the retry-bypass branch threads the raw str through this seam."
    )


def test_prompt_builder_build_prior_attempt_summary_is_optional_str() -> None:
    """The annotation must reduce to ``str | None`` — receiving the raw
    string (S2-04 AC-4). A regression to ``FencedSegment`` would break
    S2-04 AC-13's "PromptBuilder is the sole fence-call site"."""
    hints = get_type_hints(PromptBuilder.build)
    annotation = hints["prior_attempt_summary"]
    # str | None reduces to Union[str, NoneType] under get_type_hints.
    import types

    assert isinstance(annotation, types.UnionType) or hasattr(annotation, "__args__"), (
        f"prior_attempt_summary annotation must be a Union; got {annotation!r}"
    )
    args = set(annotation.__args__)
    assert str in args, f"expected str in {annotation!r}"
    assert type(None) in args, f"expected None in {annotation!r}"


def test_prompt_builder_build_has_no_bool_typed_parameters() -> None:
    """Arch §Anti-patterns avoided: no ``is_retry: bool`` regression.
    The ``bool(prior_attempts)`` predicate at the caller IS the
    discriminator; a parallel ``bool`` flag would be redundant and
    invite drift between caller and callee."""
    hints = get_type_hints(PromptBuilder.build)
    bool_typed = [name for name, ann in hints.items() if ann is bool]
    assert not bool_typed, (
        f"PromptBuilder.build must not declare bare-bool parameters; "
        f"found: {bool_typed}. The bool(prior_attempts) caller predicate "
        f"is the only discriminator (ADR-04-0002)."
    )


def test_prompt_builder_build_parameters_are_keyword_only() -> None:
    """All build parameters (besides ``self``) are kw-only — prevents
    positional-arg drift when new optional sources are added."""
    sig = inspect.signature(PromptBuilder.build)
    non_self = [p for name, p in sig.parameters.items() if name != "self"]
    non_kw = [p for p in non_self if p.kind is not inspect.Parameter.KEYWORD_ONLY]
    assert not non_kw, (
        f"PromptBuilder.build parameters must all be keyword-only; "
        f"found positional / positional-or-keyword: {[p.name for p in non_kw]}"
    )
