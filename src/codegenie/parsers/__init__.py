"""Safe-parse helpers — the in-process parse-with-caps chokepoint.

Every Phase 1 probe that reads JSON/YAML/JSON-with-comments routes through
this package; the three structural defenses — ``O_NOFOLLOW`` open, pre-parse
size cap on the fd, and a post-parse depth walker — close the bulk of the
adversarial-bytes surface without per-probe sandboxes.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #8 — the public interface and rationale.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md`` (ADR-0008)
  ratifies in-process caps as the load-bearing defense.

``JSONValue`` is the recursive type alias shared by every parser; it mirrors
the arch §Data model recursive type and is re-exported from each submodule
so callers can spell ``codegenie.parsers.JSONValue`` or
``codegenie.parsers.safe_json.JSONValue`` interchangeably.
"""

from __future__ import annotations

# JSONValue is a recursive union; ``str`` precedes ``bool|int|float`` only for
# readability — the stdlib ``json`` module decodes to these exact Python types.
JSONValue = bool | int | float | str | None | list["JSONValue"] | dict[str, "JSONValue"]

__all__ = ["JSONValue"]
