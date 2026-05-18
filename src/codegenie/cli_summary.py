"""Phase 2 CLI stdout summary block — pure formatter (S8-02).

The three-line stdout summary printed at the end of ``codegenie gather``
is the operator-facing observability surface for Phase 2's secret
redaction and skill shadowing:

```
secrets_redacted_count=<N>
fingerprints=[<8hex>, <8hex>, ...]
skill_shadowed=[<skill_id>:<shadowed_tier>, ...]
```

This module is the **pure functional core** of that surface. It carries
zero I/O, no logger, no clock, no env reads — the only impure caller
lives in :mod:`codegenie.cli` (the ``_emit_phase2_summary`` helper that
calls :func:`print` three times). The split mirrors the S8-01 pattern:
:func:`codegenie.report.confidence_section.render_confidence_section`
is pure; the writer's ``_publish_context_report`` shell does the I/O.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S8-02-cli-summary-line.md``
  §"Goal" — the three-line format.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0005-secret-findings-no-plaintext-persistence.md``
  — fingerprints are 8 lowercase hex of BLAKE3; never plaintext, never
  longer than 8 hex.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0008-no-event-stream-in-phase-2.md``
  — no new structlog events; this module emits to stdout only.
- 02-ADR-0010 (smart-constructor at writer boundary) —
  ``RedactedSlice.fingerprints`` is the persisted-by-construction field
  the CLI reads; this module re-sorts ASCII-lex for determinism (the
  upstream dedup is insertion-order, not lex-order).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from codegenie.skills.model import ShadowedSkill

__all__ = ["SummaryBlock", "summary_block"]


@dataclass(frozen=True)
class SummaryBlock:
    """Three rendered stdout lines, in order.

    ``count_line`` / ``fingerprints_line`` / ``shadowed_line`` are the
    *rendered* strings — sort + dedup has already happened in
    :func:`summary_block`. This is the carrier shape the impure shell
    consumes; it carries no logic of its own.
    """

    count_line: str
    fingerprints_line: str
    shadowed_line: str

    def as_lines(self) -> tuple[str, str, str]:
        """Return the three lines in stdout-emission order."""
        return (self.count_line, self.fingerprints_line, self.shadowed_line)


def summary_block(
    count: int,
    fingerprints: Iterable[str],
    shadowed: Iterable[ShadowedSkill],
) -> SummaryBlock:
    """Pure formatter — build a :class:`SummaryBlock` from in-scope values.

    - ``count`` is rendered verbatim as the right-hand side of
      ``secrets_redacted_count=<count>``.
    - ``fingerprints`` is deduplicated then ASCII-lex sorted; the empty
      iterable renders as ``fingerprints=[]``.
    - ``shadowed`` is rendered one entry per :class:`ShadowedSkill` as
      ``<skill_id>:<shadowed_tier>``, ASCII-lex sorted by the same
      ``(skill_id, shadowed_tier)`` key; the empty iterable renders as
      ``skill_shadowed=[]``.

    The function is total and pure: same inputs → same output, no I/O,
    no clock, no env. Idempotence is a property of the deterministic
    sort+dedup; supplying the same multiset of fingerprints or shadows
    in any order produces the same :class:`SummaryBlock`.
    """
    unique_fps = sorted(set(fingerprints))
    fps_body = ", ".join(unique_fps)
    shadowed_sorted = sorted(shadowed, key=lambda s: (s.skill_id, s.shadowed_tier))
    shadowed_body = ", ".join(f"{s.skill_id}:{s.shadowed_tier}" for s in shadowed_sorted)
    return SummaryBlock(
        count_line=f"secrets_redacted_count={count}",
        fingerprints_line=f"fingerprints=[{fps_body}]",
        shadowed_line=f"skill_shadowed=[{shadowed_body}]",
    )
