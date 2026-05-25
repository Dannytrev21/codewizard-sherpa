"""Phase-4 S3-05 — ``cassettes.lock`` BLAKE3 manifest module.

Layer 3 of ADR-0014's cassette-discipline stack (sanitize → CI scanner →
manifest → nightly drift): the per-cassette content-addressed lock that
makes "I just regenerated and pushed without re-recording the lock" fail
loudly in CI.

ADRs honored:

- **ADR-0014 §Decision item 4** — exact line format ``<relpath>  <blake3-hex>``
  (two-space separator, sorted, trailing newline when non-empty). This shape
  is locked from Phase 4 onward via S7-10's phase-5 contract snapshot.
- **ADR-0001 (Phase 0)** — BLAKE3 routes through the
  :mod:`codegenie.hashing` chokepoint. ``manifest.py`` never imports
  ``blake3`` directly; :func:`compute_cassette_digest` calls
  :func:`codegenie.hashing.content_hash` and strips the ``blake3:`` prefix.

Module discipline:

- **Functional core / imperative shell.** :func:`compute_cassette_digest`
  and :func:`rebuild_lockfile` read filesystem state; every parser /
  validator is a pure helper. The pure helpers are what the CI scanner
  (``tests/security/test_cassettes_clean.py``) reuses against in-memory
  cassette directories.
- **Bad-state-unrepresentable.** :class:`LockfileMalformedDetail` is the
  frozen Pydantic v2 payload; :class:`LockfileMalformed` is the raised
  wrapper that carries it. The "Pydantic detail + raised wrapper"
  precedent matches the repo (S2-05's ``BudgetExceeded`` etc.). A
  ``BaseModel`` is not directly raiseable; instantiating a malformed
  ``LockfileMalformedDetail`` is *valid* — it's the payload.
- **Smart constructor on the relpath.** Every entry is validated through
  the pure ``_validate_relpath`` predicate so a future scanner cannot be
  duped into resolving an absolute path or a ``..`` escape (AC-21).
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.hashing import content_hash
from codegenie.types.identifiers import BlobDigest, CassetteId

__all__ = (
    "LockfileMalformed",
    "LockfileMalformedDetail",
    "compute_cassette_digest",
    "load_lockfile",
    "rebuild_lockfile",
)


# --- AC-17: module-level warning IDs --------------------------------------


_WARNING_IDS: Final[frozenset[str]] = frozenset(
    {
        "cassette.lock_malformed",
        "cassette.lock_drift",
        "cassette.lock_orphan",
        "cassette.lock_stale",
    }
)
"""Four distinct named diagnostics the scanner emits when the manifest
invariants fail. Validated at import time per Phase-1 ADR-0007 (each ID
matches ``^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$``)."""


_MalformedReason = Literal[
    "missing_lockfile",
    "missing_separator",
    "bad_relpath",
    "bad_hex_length",
    "bad_hex_chars",
    "duplicate_relpath",
    "unsorted_lines",
    "trailing_garbage",
]


# --- Diagnostic payload + raised wrapper (AC-3) ---------------------------


class LockfileMalformedDetail(BaseModel):
    """Frozen-extra-forbid payload carried by :class:`LockfileMalformed`.

    Per Rule 9 (tests verify intent) the reason enum is a closed
    ``Literal`` — any future addition has to land here in the type, in
    the parser, and in the unit-test parametrize block as a tuple. That
    coupling is the load-bearing thing the model enforces.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: _MalformedReason
    line_number: int
    line_content: str


class LockfileMalformed(Exception):
    """Raised wrapper over :class:`LockfileMalformedDetail`.

    Pydantic ``BaseModel`` cannot itself be raised — it is not an
    ``Exception`` subclass. The repo's precedent (``BudgetExceeded`` over
    ``BudgetSnapshot``) is "Pydantic detail + raised wrapper"; this class
    is the wrapper.
    """

    def __init__(self, detail: LockfileMalformedDetail) -> None:
        self._detail = detail
        super().__init__(
            f"cassettes.lock malformed: reason={detail.reason} "
            f"line {detail.line_number}: {detail.line_content!r}"
        )

    @property
    def detail(self) -> LockfileMalformedDetail:
        return self._detail

    @property
    def reason(self) -> _MalformedReason:
        return self._detail.reason

    @property
    def line_number(self) -> int:
        return self._detail.line_number

    @property
    def line_content(self) -> str:
        return self._detail.line_content


# --- Pure helpers (functional core; AC-21) --------------------------------


def _is_safe_relpath(relpath: str) -> bool:
    """Reject absolute paths, ``..`` escapes, backslashes, empty segments.

    The lock entries name cassettes under
    ``tests/cassettes/anthropic/`` — any walker that takes a lock entry and
    builds ``anthropic_dir / relpath`` must not be able to resolve outside
    the directory. Hence AC-21: every relpath must be a forward-only
    POSIX path with no escape components and no empty segments.
    """
    if not relpath:
        return False
    if relpath.startswith("/"):
        return False
    if "\\" in relpath:
        return False
    parts = relpath.split("/")
    if any(p == "" or p == "." or p == ".." for p in parts):
        return False
    return True


def _validate_hex_64(token: str) -> _MalformedReason | None:
    """Return the failure reason if ``token`` is not 64 lowercase hex chars."""
    if len(token) != 64:
        return "bad_hex_length"
    if not all(ch in "0123456789abcdef" for ch in token):
        return "bad_hex_chars"
    return None


def _validate_lock_lines(text: str) -> MappingProxyType[CassetteId, BlobDigest]:
    """Parse + validate the raw lock-file text. PURE. Raises on any malformation.

    Empty string → empty mapping (the bootstrap path). Otherwise each line
    must match ``<relpath>  <blake3-hex>`` (two-space separator); the
    overall file must end in exactly one trailing newline; the relpath
    list must be sorted ascending with no duplicates. Any deviation
    raises :class:`LockfileMalformed` with the named reason.
    """
    if text == "":
        return MappingProxyType({})

    # Trailing-newline + trailing-garbage checks: a valid non-empty file
    # ends in exactly one ``\n`` and no other whitespace. ``splitlines()``
    # would silently swallow a missing trailing newline, so partition on
    # ``\n`` first.
    if not text.endswith("\n"):
        raise LockfileMalformed(
            LockfileMalformedDetail(
                reason="trailing_garbage",
                line_number=text.count("\n") + 1,
                line_content=text.rsplit("\n", 1)[-1],
            )
        )
    # The file body (sans the single trailing ``\n``) must split into N
    # non-empty lines. A double trailing newline or an interior blank line
    # produces an empty entry that the per-line validator rejects.
    body = text[:-1]
    raw_lines = body.split("\n")
    out: dict[CassetteId, BlobDigest] = {}
    previous_relpath: str | None = None
    for idx, line in enumerate(raw_lines, start=1):
        if line == "":
            raise LockfileMalformed(
                LockfileMalformedDetail(
                    reason="trailing_garbage",
                    line_number=idx,
                    line_content=line,
                )
            )
        if "  " not in line:
            raise LockfileMalformed(
                LockfileMalformedDetail(
                    reason="missing_separator",
                    line_number=idx,
                    line_content=line,
                )
            )
        relpath, sep, digest = line.partition("  ")
        # Reject lines that have additional content past the digest token
        # (e.g. trailing whitespace, comment, extra column).
        if " " in digest:
            raise LockfileMalformed(
                LockfileMalformedDetail(
                    reason="trailing_garbage",
                    line_number=idx,
                    line_content=line,
                )
            )
        if not _is_safe_relpath(relpath):
            raise LockfileMalformed(
                LockfileMalformedDetail(
                    reason="bad_relpath",
                    line_number=idx,
                    line_content=line,
                )
            )
        hex_failure = _validate_hex_64(digest)
        if hex_failure is not None:
            raise LockfileMalformed(
                LockfileMalformedDetail(
                    reason=hex_failure,
                    line_number=idx,
                    line_content=line,
                )
            )
        if relpath in out:
            raise LockfileMalformed(
                LockfileMalformedDetail(
                    reason="duplicate_relpath",
                    line_number=idx,
                    line_content=line,
                )
            )
        if previous_relpath is not None and relpath < previous_relpath:
            raise LockfileMalformed(
                LockfileMalformedDetail(
                    reason="unsorted_lines",
                    line_number=idx,
                    line_content=line,
                )
            )
        out[CassetteId(relpath)] = BlobDigest(digest)
        previous_relpath = relpath
    del sep  # silence unused; the partition tag is consumed for clarity
    return MappingProxyType(out)


# --- Public API -----------------------------------------------------------


def compute_cassette_digest(path: Path) -> BlobDigest:
    """Return the unprefixed lowercase 64-hex BLAKE3 digest of ``path``.

    Routes through :func:`codegenie.hashing.content_hash` (ADR-0001
    chokepoint) and strips the ``blake3:`` prefix. The lock-file format
    is ``<relpath>  <blake3-hex>`` per ADR-0014; the stored token is
    unprefixed because the algorithm is already part of the file's
    identity (this is a ``cassettes.lock``). The Phase-4 NewType
    :data:`codegenie.types.identifiers.BlobDigest` keeps the raw-``str``
    fence happy and signals at the type level that this 64-hex token is
    a content-addressed digest, not arbitrary text.
    """
    return BlobDigest(content_hash(path).removeprefix("blake3:"))


def load_lockfile(path: Path) -> MappingProxyType[CassetteId, BlobDigest]:
    """Parse ``path`` into an immutable ``{relpath: blake3_hex}`` mapping.

    Empty file → empty mapping (the bootstrap path; AC-22). Missing file
    raises :class:`LockfileMalformed(reason="missing_lockfile")` (AC-2 +
    AC-8). Any structural violation raises with the matching reason from
    :data:`_MalformedReason` (AC-3).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise LockfileMalformed(
            LockfileMalformedDetail(
                reason="missing_lockfile",
                line_number=0,
                line_content=str(path),
            )
        ) from exc
    return _validate_lock_lines(text)


def rebuild_lockfile(cassettes_dir: Path) -> str:
    """Return formatted lock-file contents from cassettes under ``cassettes_dir``.

    Walks ``cassettes_dir.rglob("*.yaml")``, computes the unprefixed
    BLAKE3 of each cassette, returns a sorted, two-space-separated,
    newline-terminated string. Empty result (no cassettes) → empty
    string. Pure with respect to writes: reads cassette bytes but does
    not write the lock (callers decide whether to write or compare).
    """
    if not cassettes_dir.exists():
        return ""
    rows: list[tuple[str, str]] = []
    for cassette in cassettes_dir.rglob("*.yaml"):
        if not cassette.is_file():
            continue
        relpath = cassette.relative_to(cassettes_dir).as_posix()
        rows.append((relpath, compute_cassette_digest(cassette)))
    if not rows:
        return ""
    rows.sort(key=lambda row: row[0])
    return "".join(f"{relpath}  {digest}\n" for relpath, digest in rows)


# AC-17 import-time validation per Phase-1 ADR-0007 convention.
import re as _re  # noqa: E402, I001 — local-only import; pattern keeps module clean

for _wid in _WARNING_IDS:
    if not _re.match(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$", _wid):
        raise AssertionError(f"manifest._WARNING_IDS: {_wid!r} violates ADR-0007 shape")
del _wid, _re
