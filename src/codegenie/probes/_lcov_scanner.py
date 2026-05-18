"""``_lcov_scanner`` — stdlib state-machine scanner for ``coverage/lcov.info`` (S4-03).

The scanner is the load-bearing security primitive of ``TestInventoryProbe``:
``coverage/lcov.info`` is attacker-controllable bytes (a hostile fork or
contributor can craft pathological coverage output, and the file lands in the
repo from CI). A regex with ``.*`` over 50 MB of crafted input is an OOM/CPU
DoS vector. Two structural defenses make this safe:

1. **No regex.** The module must contain ZERO ``import re``. Line dispatch
   is ``str.startswith`` against a closed prefix table (``_LCOV_PREFIX_MAP``).
   Backtracking can only happen with a regex; absent the import, ReDoS is
   structurally impossible. AST-walked by the test suite (S4-03 AC-26).
2. **Single chokepoint for fd lifecycle + size cap.** Body retrieval routes
   through :func:`codegenie.parsers._io.open_capped`, the rule-of-three
   shared kernel that owns ``O_NOFOLLOW`` + ``fstat``-based size enforcement
   for every parser in ``codegenie.parsers``. The lcov scanner is the
   fourth consumer (after ``safe_json``, ``safe_yaml``, ``jsonc``); reuse is
   mandatory (AC-25). No local ``os.open(O_NOFOLLOW)`` re-implementation.

Adding a future lcov prefix (``DA:`` per-line counts, ``BRDA:`` per-branch
detail) is one entry in ``_LCOV_PREFIX_MAP``; zero edits to ``scan``.
Unknown prefixes are silently dropped — lcov dialects (Istanbul, lcov-1.x,
coverage.py-via-converter) all share the same prefix grammar but disagree on
which prefixes appear.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/stories/S4-03-test-inventory-probe.md``
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #7 — 40-LOC stdlib state machine, 50 MB cap.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md``,
  ``0009-no-new-c-extension-parser-dependencies.md``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final, NamedTuple

from codegenie.parsers._io import open_capped

__all__ = ["LcovRecord", "LcovTotals", "scan", "scan_records"]


class LcovTotals(NamedTuple):
    """Six-int summed totals across every record in an lcov tracefile."""

    lines_found: int
    lines_hit: int
    functions_found: int
    functions_hit: int
    branches_found: int
    branches_hit: int


class LcovRecord(NamedTuple):
    """Per-record projection: source file + the ordered set of lines hit.

    Added by S6-08 for ``TestCoverageMappingProbe`` (the second consumer of
    the lcov state machine after the Phase-1 ``TestInventoryProbe``). The
    summed-totals API (:func:`scan`) is unaffected — both APIs share the
    no-regex ``_LCOV_PREFIX_MAP`` prefix dispatch + the ``open_capped``
    chokepoint.

    ``test_file`` is currently always ``None``: lcov dialects do not encode
    per-test attribution at the SF/DA level (Phase-3's
    ``TestInventoryAdapter`` will project per-line attribution against this
    raw evidence). ``lines_covered`` lists only lines with non-zero hit
    counts; zero-hit ``DA:`` rows are excluded.
    """

    test_file: str | None
    source_file: str
    lines_covered: tuple[int, ...]


# Closed dispatch table: prefix → ``LcovTotals`` field name. Adding a future
# prefix is one entry; zero edits to ``scan``. Unknown prefixes are silently
# ignored (lcov-dialect tolerance — Istanbul, lcov-1.x, coverage-converter
# all share this prefix grammar but disagree on which prefixes appear).
_LCOV_PREFIX_MAP: Final[Mapping[str, str]] = {
    "LF:": "lines_found",
    "LH:": "lines_hit",
    "FNF:": "functions_found",
    "FNH:": "functions_hit",
    "BRF:": "branches_found",
    "BRH:": "branches_hit",
}


_LCOV_MAX_BYTES: Final[int] = 50 * 1024 * 1024


def scan(path: Path, *, max_bytes: int | None = None) -> LcovTotals:
    """Scan ``coverage/lcov.info`` returning summed :class:`LcovTotals`.

    Args:
        path: Path to ``coverage/lcov.info``. Symlinks are refused via
            ``open_capped``'s ``O_NOFOLLOW`` open.
        max_bytes: Hard upper bound; exceeding raises
            :class:`codegenie.errors.SizeCapExceeded` from ``open_capped``
            before any ``os.read`` is invoked. ``None`` (the default)
            resolves to the module-level ``_LCOV_MAX_BYTES`` at call
            time so monkeypatching that constant in tests takes effect.

    Returns:
        :class:`LcovTotals` with six summed integer counters. Missing
        prefixes default to 0; unknown prefixes are silently dropped.

    Raises:
        SymlinkRefusedError: ``path``'s final component is a symlink.
        SizeCapExceeded: ``path`` exceeds ``max_bytes``.
        OSError: any other open-time failure (``ENOENT``, ``EISDIR``, …).
    """
    effective_cap = _LCOV_MAX_BYTES if max_bytes is None else max_bytes
    body = open_capped(path, max_bytes=effective_cap, parser_kind="lcov")
    text = body.decode("utf-8", errors="replace")
    accumulator: dict[str, int] = dict.fromkeys(_LCOV_PREFIX_MAP.values(), 0)
    for line in text.splitlines():
        for prefix, field in _LCOV_PREFIX_MAP.items():
            if line.startswith(prefix):
                value_str = line[len(prefix) :]
                try:
                    accumulator[field] += int(value_str)
                except ValueError:
                    # Malformed numeric value — silently drop this entry
                    # (lcov-dialect tolerance: a corrupt counter line is
                    # not a hard parse error; the consumer sees totals
                    # under-counted but no exception).
                    pass
                break
    return LcovTotals(
        lines_found=accumulator["lines_found"],
        lines_hit=accumulator["lines_hit"],
        functions_found=accumulator["functions_found"],
        functions_hit=accumulator["functions_hit"],
        branches_found=accumulator["branches_found"],
        branches_hit=accumulator["branches_hit"],
    )


def scan_records(path: Path, *, max_bytes: int | None = None) -> tuple[LcovRecord, ...]:
    """Scan ``coverage/lcov.info`` returning per-source :class:`LcovRecord`s.

    Additive companion to :func:`scan` (S6-08). Both share the
    ``open_capped`` chokepoint + the no-regex prefix dispatch; only the
    per-line state machine differs (this function tracks ``SF:`` /
    ``DA:`` / ``end_of_record`` rather than summing six counters).

    A record is emitted at every ``end_of_record`` boundary AND for any
    open ``SF:`` block that reaches EOF without an explicit terminator —
    the latter is the dominant shape lcov producers emit when the test
    suite is killed mid-write.

    Lines with non-positive hit counts are excluded from
    ``lines_covered`` (uncovered lines are not coverage facts). Unknown
    prefixes are silently dropped (lcov-dialect tolerance). ``TN:``
    test-name records are not yet wired into ``LcovRecord.test_file``
    because the per-test mapping is a Phase-3 concern; the field stays
    in the signature so a future ``TN:`` extractor lands without an
    API change.
    """
    effective_cap = _LCOV_MAX_BYTES if max_bytes is None else max_bytes
    body = open_capped(path, max_bytes=effective_cap, parser_kind="lcov")
    text = body.decode("utf-8", errors="replace")
    records: list[LcovRecord] = []
    current_source: str | None = None
    current_lines: list[int] = []
    for line in text.splitlines():
        if line.startswith("SF:"):
            if current_source is not None:
                records.append(
                    LcovRecord(
                        test_file=None,
                        source_file=current_source,
                        lines_covered=tuple(current_lines),
                    )
                )
            current_source = line[len("SF:") :]
            current_lines = []
            continue
        if line.startswith("DA:"):
            payload = line[len("DA:") :]
            comma = payload.find(",")
            if comma == -1:
                raise ValueError(f"truncated DA: row: {line!r}")
            try:
                lineno = int(payload[:comma])
                hits = int(payload[comma + 1 :])
            except ValueError as exc:
                raise ValueError(f"malformed DA: row: {line!r}") from exc
            if hits > 0 and current_source is not None:
                current_lines.append(lineno)
            continue
        if line.startswith("end_of_record"):
            if current_source is not None:
                records.append(
                    LcovRecord(
                        test_file=None,
                        source_file=current_source,
                        lines_covered=tuple(current_lines),
                    )
                )
                current_source = None
                current_lines = []
    if current_source is not None:
        records.append(
            LcovRecord(
                test_file=None,
                source_file=current_source,
                lines_covered=tuple(current_lines),
            )
        )
    return tuple(records)
