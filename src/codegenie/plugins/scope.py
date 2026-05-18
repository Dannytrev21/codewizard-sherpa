"""Phase 3 S1-02 — ``PluginScope`` sum type, smart constructor, algebra.

``ScopeDim = Concrete | Wildcard`` is the closed sum type that backs every
``PluginScope`` dimension (``task_class``, ``language``, ``build_system``).
Per Phase-3 ADR-0010 §Decision §1 the kernel commits to "make illegal states
unrepresentable": a dim is either a concrete string or a wildcard — never a
magic ``"*"`` string masquerading as a concrete value.

External boundaries (YAML manifest loaders in S2-02, ``extends``-chain readers
in S2-04) parse strings through :meth:`PluginScope.parse`, the **only** safe
entry point. The smart constructor returns ``Result[PluginScope, ParseError]``
so callers handle malformed input at the boundary rather than at every use
site (ADR-0010 §Decision §4).

Module-purity invariant: imports only ``__future__``, ``dataclasses``, ``re``,
``typing``, ``codegenie.result``, ``codegenie.types.errors``. No I/O, no
logger, no sibling-package coupling. AST source-scan tests enforce
(``tests/unit/plugins/test_scope_purity.py``).

Sources:

- Phase-3 ADR-0010 §Decision §1 — exact dataclass shape
  (``frozen=True, slots=True``; ``Concrete.value: str``;
  ``ScopeDim: TypeAlias``).
- Phase-3 ADR-0003 §Decision step 2 — resolver sort key
  ``(specificity desc, precedence desc, name asc)``; ``specificity()``
  defines a total order in ``{0, 1, 2, 3}``.
- Story ``docs/phases/03-vuln-deterministic-recipe/stories/S1-02-plugin-scope-sum-type.md``
  — acceptance criteria, mutation kill-list, parametrized rejection matrix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, TypeAlias, assert_never

from codegenie.result import Err, Ok, Result
from codegenie.types.errors import ParseError

__all__: Final[tuple[str, ...]] = ("Concrete", "PluginScope", "ScopeDim", "Wildcard")

# Per-dim regex and length cap exported for reuse by the S2-02 YAML manifest
# loader (ADR-0010 §Decision §1 — the smart constructor is the only safe
# boundary; loaders re-use the same pattern rather than re-deriving it).
_DIM_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_-]+$")
_DIM_MAX_LEN: Final[int] = 64
_WILDCARD_TOKEN: Final[str] = "*"
_DIM_SEPARATOR: Final[str] = "--"
_EXPECTED_DIMS: Final[int] = 3


@dataclass(frozen=True, slots=True)
class Concrete:
    """A literal scope-dim value (e.g., ``Concrete(value="npm")``).

    ``value`` carries no internal validation — :meth:`PluginScope.parse` is
    the only safe external entry point. Defense-in-depth ``__post_init__``
    validation was deliberately rejected (ADR-0010 §Decision §1).
    """

    value: str


@dataclass(frozen=True, slots=True)
class Wildcard:
    """The universal-fallback marker for a scope-dim (canonicalised as
    ``"*"`` in YAML and by :meth:`PluginScope.__str__`)."""


# Closed sum. Adding a third variant requires updating every consumer's
# ``match`` block — AST tests (``test_scope_exhaustiveness.py``) plus the
# ``assert_never`` arms below promote the variant set into a build-break.
ScopeDim: TypeAlias = Concrete | Wildcard


@dataclass(frozen=True, slots=True)
class PluginScope:
    """A triple of scope-dims — ``task_class``, ``language``, ``build_system``.

    Membership (:meth:`matches`) and ordering (:meth:`specificity`) form the
    algebra the S2-04 resolver iterates over to select a plugin for a given
    repository context.
    """

    task_class: ScopeDim
    language: ScopeDim
    build_system: ScopeDim

    # ---- smart constructor ------------------------------------------------

    @classmethod
    def parse(cls, s: str) -> Result[PluginScope, ParseError]:
        """Parse ``"<task>--<lang>--<build>"`` into a ``PluginScope``.

        Each dim is either ``"*"`` (→ :class:`Wildcard`) or a non-empty
        ``[a-z0-9_-]+`` string of length ≤ 64 (→ :class:`Concrete`). Returns
        ``Ok(value=PluginScope(...))`` on success or
        ``Err(error=ParseError(message=<reason>, value=s))`` on failure —
        never raises. Adversarial input (NUL byte, zero-width space, full-
        width digit, uppercase, whitespace, etc.) rejects; NFKC normalisation
        is deliberately not applied (the call site decides whether to
        normalise its input).
        """

        parts = s.split(_DIM_SEPARATOR)
        if len(parts) != _EXPECTED_DIMS:
            return Err(
                error=ParseError(
                    message=f"expected exactly {_EXPECTED_DIMS} '{_DIM_SEPARATOR}'-separated dims",
                    value=s,
                )
            )

        dims: list[ScopeDim] = []
        for part in parts:
            dim_result = _parse_dim(part, original=s)
            if isinstance(dim_result, Err):
                return dim_result
            dims.append(dim_result.value)

        return Ok(
            value=cls(
                task_class=dims[0],
                language=dims[1],
                build_system=dims[2],
            )
        )

    # ---- algebra ----------------------------------------------------------

    def matches(self, *, task: str, language: str, build: str) -> bool:
        """True iff every dim is ``Wildcard`` or its value equals the supplied
        concrete. ``task`` / ``language`` / ``build`` are ``str`` (not
        newtypes) — the kernel stays task-class-agnostic per ADR-0010
        §Decision §1; newtype call sites wrap before invoking."""

        match (self.task_class, self.language, self.build_system):
            case (t, lng, b):
                return _dim_admits(t, task) and _dim_admits(lng, language) and _dim_admits(b, build)
            case _:  # pragma: no cover — exhaustiveness guarantee
                assert_never(self)

    def specificity(self) -> int:
        """Number of :class:`Concrete` dims in this scope (∈ ``{0, 1, 2, 3}``).

        Defines the total order ADR-0003 §Decision step 2 uses for resolver
        sorting: ``(specificity desc, precedence desc, name asc)``.
        """

        match (self.task_class, self.language, self.build_system):
            case (t, lng, b):
                return _is_concrete(t) + _is_concrete(lng) + _is_concrete(b)
            case _:  # pragma: no cover — exhaustiveness guarantee
                assert_never(self)

    # ---- serialization ----------------------------------------------------

    def __str__(self) -> str:
        """Canonical ``"<task>--<lang>--<build>"`` form — round-trips through
        :meth:`parse` for every constructible ``PluginScope`` (AC-10 / AC-11,
        load-bearing for the S2-02 YAML manifest loader)."""

        return _DIM_SEPARATOR.join(
            _dim_to_str(d) for d in (self.task_class, self.language, self.build_system)
        )


# ---------------------------------------------------------------------------
# Private helpers — pure functions; no module-level mutable state.
# ---------------------------------------------------------------------------


def _parse_dim(part: str, *, original: str) -> Result[ScopeDim, ParseError]:
    if part == _WILDCARD_TOKEN:
        return Ok(value=Wildcard())
    if not part:
        return Err(error=ParseError(message="empty dim", value=original))
    if len(part) > _DIM_MAX_LEN:
        return Err(
            error=ParseError(
                message=f"dim exceeds {_DIM_MAX_LEN} chars",
                value=original,
            )
        )
    if not _DIM_PATTERN.fullmatch(part):
        return Err(
            error=ParseError(
                message="dim must match ^[a-z0-9_-]+$",
                value=original,
            )
        )
    return Ok(value=Concrete(value=part))


def _dim_admits(dim: ScopeDim, candidate: str) -> bool:
    match dim:
        case Wildcard():
            return True
        case Concrete(value=v):
            return v == candidate
        case _:  # pragma: no cover — exhaustiveness guarantee
            assert_never(dim)


def _is_concrete(dim: ScopeDim) -> int:
    match dim:
        case Wildcard():
            return 0
        case Concrete():
            return 1
        case _:  # pragma: no cover — exhaustiveness guarantee
            assert_never(dim)


def _dim_to_str(dim: ScopeDim) -> str:
    match dim:
        case Wildcard():
            return _WILDCARD_TOKEN
        case Concrete(value=v):
            return v
        case _:  # pragma: no cover — exhaustiveness guarantee
            assert_never(dim)
