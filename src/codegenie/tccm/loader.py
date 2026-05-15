"""``TCCMLoader`` — single impure module in the ``codegenie.tccm`` package.

Routes every YAML read through :func:`codegenie.parsers.safe_yaml.load` with
an explicitly-pinned ``max_bytes`` cap. The loader has **no ``__init__``**
(pure-data-at-construction discipline mirrors ``SkillsLoader`` arch §9); the
first I/O is :meth:`TCCMLoader.load`. No file handles cached, no logger
attribute on the instance.

Reason-prefix contract — ``LoaderReason: Literal["parse", "schema",
"unknown_query_primitive"]`` — is the public catch-site contract. Consumers
parse the prefix from ``err.args[0]``; the marker carries **no** structured
``.reason`` attribute (markers-only convention, S1-04 AC-25). A fourth reason
requires extending :data:`LoaderReason`, :func:`_classify`, and this
docstring's translation table — not an ad-hoc string prefix.

Pydantic-v2 translation table for :func:`_classify` (public contract;
pin against minor-version upgrades):

- ``union_tag_invalid`` or ``literal_error`` at a ``compute`` location →
  ``unknown_query_primitive``.
- Everything else → ``schema``.

Audit-log field allowlist: ``{event, path, derived_queries_count, reason}``.
No YAML body, no validation-error detail string, no secret-shaped substring
of ``path`` is logged (AC-22).

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S1-04-tccm-model-loader.md``
  §"Acceptance criteria" AC-4..AC-23 — reason prefixes, chokepoint, audit
  log, AST defenses.
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #8 — public interface, internal structure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Literal, TypeAlias

import structlog
from pydantic import ValidationError

from codegenie.errors import (
    DepthCapExceeded,
    MalformedYAMLError,
    SizeCapExceeded,
    TCCMLoadError,
)
from codegenie.parsers import safe_yaml
from codegenie.result import Err, Ok, Result
from codegenie.tccm.model import TCCM

# Phase-arch §8: TCCMs are documented "< 10 KB"; 6× headroom defends against
# operator edits without inviting drift.
_TCCM_MAX_BYTES: Final[int] = 64 * 1024

_logger = structlog.get_logger(__name__)

LoaderReason: TypeAlias = Literal["parse", "schema", "unknown_query_primitive"]


def _classify(ve: ValidationError) -> LoaderReason:
    """Translate a Pydantic v2 ``ValidationError`` into a ``LoaderReason``.

    Pinned translation table (public contract; pin this docstring against
    Pydantic minor-version upgrades):

    - ``type == "union_tag_invalid"`` with ``ctx.discriminator == "'compute'"``
      → ``"unknown_query_primitive"`` (Pydantic 2.13: ``loc`` ends with the
      list index, not the discriminator field name, so the discriminator
      identity is read from ``ctx``).
    - ``type == "literal_error"`` with ``loc[-1] == "compute"`` →
      ``"unknown_query_primitive"`` (defensive: Pydantic's union-tag fallback
      path for non-default-bearing discriminator literals).
    - Everything else → ``"schema"``.

    Fail-loud (Rule 12): if a Pydantic upgrade breaks AC-8, fix the
    translation here — do not relax the test.
    """
    for err in ve.errors():
        etype = err.get("type")
        if etype == "union_tag_invalid":
            ctx = err.get("ctx", {})
            # Pydantic renders the discriminator name with single-quotes in ctx.
            if ctx.get("discriminator") in {"'compute'", "compute"}:
                return "unknown_query_primitive"
        elif etype == "literal_error":
            loc = err.get("loc", ())
            if loc and loc[-1] == "compute":
                return "unknown_query_primitive"
    return "schema"


class TCCMLoader:
    """Load a TCCM YAML and return :class:`Result` — no ``__init__`` on purpose."""

    def load(self, path: Path) -> Result[TCCM, TCCMLoadError]:
        """Read ``path`` via the safe-YAML chokepoint and return a typed Result.

        ``Ok(value=tccm)`` on a well-formed manifest. ``Err(error=TCCMLoadError(...))``
        with a prefixed positional message on the three failure classes:

        - ``"parse: …"`` — :class:`MalformedYAMLError`, :class:`SizeCapExceeded`,
          or :class:`DepthCapExceeded` from the safe-YAML chokepoint.
        - ``"schema: …"`` — Pydantic ``ValidationError`` other than the
          unknown-discriminator path.
        - ``"unknown_query_primitive: …"`` — Pydantic discriminator failure on
          a ``DerivedQuery`` variant's ``compute`` field.
        """
        try:
            data = safe_yaml.load(path, max_bytes=_TCCM_MAX_BYTES)
        except (MalformedYAMLError, SizeCapExceeded, DepthCapExceeded) as exc:
            err = TCCMLoadError(f"parse: {type(exc).__name__}: {exc}")
            _logger.warning("tccm.load.err", path=str(path), reason="parse")
            return Err(error=err)
        try:
            tccm = TCCM.model_validate(data)
        except ValidationError as ve:
            reason = _classify(ve)
            errors = ve.errors()
            detail = str(errors[0]["msg"]) if errors else "invalid"
            err = TCCMLoadError(f"{reason}: {detail}")
            _logger.warning("tccm.load.err", path=str(path), reason=reason)
            return Err(error=err)
        _logger.info(
            "tccm.load.ok",
            path=str(path),
            derived_queries_count=len(tccm.derived_queries),
        )
        return Ok(value=tccm)
