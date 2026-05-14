"""yarn.lock parser — pyarn if available at runtime, else hand-rolled scanner.

Yarn classic emits a custom indent-sensitive format ("version 1") that is
neither JSON nor YAML; yarn berry emits a YAML-ish format with custom
tag conventions. This module ships **both** code paths and dispatches at
module load via ``_HAS_PYARN: bool`` (computed via
``importlib.util.find_spec``). The ADR-0003 land-time selection
determines whether ``pyarn`` is listed in ``pyproject.toml``'s ``gather``
extras; either way the hand-rolled scanner ships unconditionally so
contributors without ``pyarn`` installed still parse correctly (arch
§"Edge cases" row 10).

Both dispatch paths receive the same ``body: bytes`` from
:func:`codegenie.parsers._io.open_capped` — ``pyarn`` is never invoked
with a raw ``Path``, so the size-cap + ``O_NOFOLLOW`` defenses hold
regardless of ``pyarn``'s internal file-handling behavior.

Parse failures from either path are translated to
:class:`MalformedLockfileError` (positional message, ``__cause__``
preserved). ``SizeCapExceeded`` and ``SymlinkRefusedError`` from
``open_capped`` propagate unchanged. There is **no fall-back** between
dispatch paths on parse error — the parity test in S3-04 owns the
bidirectional correctness contract, and a silent fall-back would muddy
it (arch §"Edge cases" row 10 covers the *uninstall* fall-back via
``_HAS_PYARN``; it does not cover *parse-error* fall-back).

The hand-rolled scanner is a **line-by-line state machine** — there is
no regex over the full file. Adversarial regex-DoS testing lands in
S5-02 (``tests/adv/test_regex_dos_yarn_lock.py``). Local fuzz before PR
is non-negotiable (S3-03 AC-16; arch's High-level-impl.md §"Step 3"
risk #4).

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #9 — interface and ~80 ms (pyarn) / ~200 ms
  (hand-rolled) p50 budget.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0003-yarn-lock-parser-choice.md`` (the land-time decision rule;
  S3-03 selected hand-rolled — see the ADR's land-time block),
  ``0007-warnings-id-pattern.md`` (WarningId at catch site),
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md`` (caps via
  open_capped), ``0009-no-new-c-extension-parser-dependencies.md``
  (pyarn is the only conditional Phase 1 dep, gated by ADR-0003).

Phase-0 marker invariant: :class:`MalformedLockfileError` accepts a
single positional message string; the path lives in ``args[0]``, the
cause lives on ``__cause__`` via ``raise ... from cause``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Final, TypedDict, cast

from codegenie.errors import (
    MalformedLockfileError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.parsers._io import open_capped

__all__ = ["YarnLock", "YarnLockEntry", "parse"]

YARN_LOCKFILE_MAX_BYTES: Final[int] = 50 * 1024 * 1024
_PARSER_KIND: Final[str] = "yarn_lockfile"

_HAS_PYARN: bool = importlib.util.find_spec("pyarn") is not None


class YarnLockEntry(TypedDict, total=False):
    """One entry from a parsed ``yarn.lock``. ``total=False`` is load-bearing.

    Yarn classic ≤ v1.21 omitted ``integrity``; berry may include fields
    outside this minimum. ``NodeManifestProbe`` (S3-05) reconciles.
    """

    version: str
    resolved: str
    integrity: str
    dependencies: dict[str, str]


class YarnLock(TypedDict, total=False):
    """Parsed ``yarn.lock`` shape — ``total=False`` is load-bearing.

    The ``entries`` keys are raw yarn-lock identifiers (e.g.
    ``"bcrypt@^5.1.0"``), possibly comma-joined for shared resolutions
    like ``"foo@^1.0, foo@^1.1"``. ``NodeManifestProbe`` (S3-05) splits
    on ``, `` when reconciling.
    """

    entries: dict[str, YarnLockEntry]


def _dequote_entry_header(header: str) -> str:
    """Normalize a yarn-classic entry-header to the post-adapter shape.

    Single-spec headers (``lodash@^4.17.21``) round-trip with no change.
    Quoted single-spec headers (``"@types/node@^20"``) strip the outer
    quotes. Comma-joined multi-spec headers (``"foo@^1", "foo@^2"``)
    split on the inner ``", "`` separator and re-join with bare ``, `` so
    parser output matches the ``_pyarn_parse`` adapter shape exercised by
    the S3-04 parity test. Without this, the parity test fails on the
    ``multi_spec_shared_header`` fixture because the hand-rolled path
    leaves the embedded quote-comma-quote intact.
    """
    if header.startswith('"'):
        parts = [piece.strip().strip('"') for piece in header.split('", "')]
        return ", ".join(parts)
    return header.strip('"')


def _parse_handrolled(body: bytes) -> YarnLock:
    """Line-by-line state machine; no regex over the full body.

    Raises:
        UnicodeDecodeError: ``body`` is not valid UTF-8 (translated by
            :func:`parse`).
        ValueError: structural error in the lockfile (translated by
            :func:`parse`).
    """
    entries: dict[str, YarnLockEntry] = {}
    current_key: str | None = None
    current_entry: dict[str, Any] = {}
    current_subblock: str | None = None  # "dependencies" / "optionalDependencies" / None

    # Strict UTF-8 decode — invalid bytes surface as UnicodeDecodeError,
    # which parse() translates to MalformedLockfileError per AC-7. Rule 12:
    # ``errors="replace"`` would substitute U+FFFD and the scanner would
    # chase garbage.
    text = body.decode("utf-8")

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            if current_key is not None:
                entries[current_key] = cast(YarnLockEntry, current_entry)
            if not line.endswith(":"):
                raise ValueError(f"expected entry header ending in ':', got {line!r}")
            current_key = _dequote_entry_header(line[:-1].strip())
            current_entry = {}
            current_subblock = None
        elif line.startswith("    ") and current_subblock is not None:
            k, _, v = line.strip().partition(" ")
            current_entry.setdefault(current_subblock, {})[k.strip('"')] = v.strip('"')
        elif line.startswith("  "):
            stripped = line.strip()
            if stripped in ("dependencies:", "optionalDependencies:"):
                current_subblock = stripped[:-1]
                continue
            current_subblock = None
            k, _, v = stripped.partition(" ")
            current_entry[k.strip('"')] = v.strip('"')

    if current_key is not None:
        entries[current_key] = cast(YarnLockEntry, current_entry)
    # S3-04 fix: a comments-only / blank yarn.lock parses to an empty
    # entries map (not a MalformedLockfileError). Yarn never emits a
    # truly-empty lockfile in practice, but the oracle test's empty
    # corpus fixture pins invariant 3 at the zero-boundary — without
    # it, a parser that always emits one phantom entry would slip
    # invariants 1 and 2 trivially on every non-empty fixture.
    # Malformed bytes (non-comment, non-header lines) still raise
    # ValueError via the "expected entry header" branch above.
    return {"entries": entries}


def _pyarn_parse(body: bytes) -> YarnLock:
    """Adapter around the installed ``pyarn`` package.

    The exact API surface is verified at land-time per S3-03 AC-13 and
    pinned in ADR-0003's "Implementer's land-time selection" block.
    Verified 2026-05-14 against pyarn 0.3.0:
    ``pyarn.lockfile.Lockfile.from_str(body.decode("utf-8")).data`` is
    the public surface; ``data`` is ``dict[str, dict[str, Any]]`` keyed
    by the raw entry header. The S3-04 parity test owns the cross-parser
    correctness contract.

    Any exception from pyarn propagates and is translated to
    :class:`MalformedLockfileError` by :func:`parse`.
    """
    import pyarn.lockfile

    lock = pyarn.lockfile.Lockfile.from_str(body.decode("utf-8"))
    return cast(YarnLock, {"entries": cast(dict[str, YarnLockEntry], lock.data)})


def parse(path: Path) -> YarnLock:
    """Parse a ``yarn.lock`` under the 50 MB cap via the shared kernel.

    Raises:
        SizeCapExceeded: re-raised unchanged from ``open_capped``.
        SymlinkRefusedError: re-raised unchanged from ``open_capped``.
        MalformedLockfileError: translated from any other parse-time
            exception (``UnicodeDecodeError``, ``ValueError`` from the
            hand-rolled scanner; ``pyarn``'s own exception classes on the
            pyarn path). The original is preserved on ``__cause__``. The
            message in ``args[0]`` includes ``str(path)`` so downstream
            ``WarningId`` construction can recover it.
        FileNotFoundError: propagated from the underlying open.
    """
    body = open_capped(path, max_bytes=YARN_LOCKFILE_MAX_BYTES, parser_kind=_PARSER_KIND)
    try:
        if _HAS_PYARN:
            return _pyarn_parse(body)
        return _parse_handrolled(body)
    except (SizeCapExceeded, SymlinkRefusedError):
        raise
    except Exception as cause:
        raise MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause
