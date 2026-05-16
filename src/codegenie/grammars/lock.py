"""Typed loader + BLAKE3 verifier for ``tools/grammars.lock`` (S4-03 AC-20).

The vendored tree-sitter grammar binaries (``tools/grammars/{language}.so``)
are reviewed-as-code: each commit that touches them is a binary diff in the
PR and reviewers check the BLAKE3 in ``tools/grammars.lock`` matches the
upstream release. At runtime the consumer (S4-04's
``TreeSitterImportGraphProbe``) must re-verify before loading — a stale
checkout, a tampered file, or a forgotten lock-file update would otherwise
silently load the wrong grammar.

This module is the typed chokepoint both this story's tests AND S4-04
import from. Adding a third consumer (e.g., a future Python tree-sitter
grammar in Phase 8) requires zero edits here — extension by addition via
a new ``GrammarPin`` row in the lock file.

The Pydantic model carries ``frozen=True, extra="forbid"`` so a manual edit
to the lock file that adds a typo'd field or swaps a string for a list
fails parse, not deserialization at use. The blake3 hex format is pinned
by a ``field_validator``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from codegenie.hashing import content_hash

__all__ = [
    "GrammarLockFile",
    "GrammarLoadRefused",
    "GrammarPin",
    "load_and_verify",
]


_BLAKE3_HEX_RE: re.Pattern[str] = re.compile(r"^[0-9a-f]{64}$")
_LANGUAGE_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]*$")
_LOCK_FILENAME: str = "tools/grammars.lock"


class GrammarLoadRefused(RuntimeError):
    """Raised by :func:`load_and_verify` when the lock file is invalid or
    a vendored binary's BLAKE3 does not match the pinned value.

    Message format names the failing language and (where applicable) the
    expected/actual BLAKE3 so an operator grepping logs can locate the
    affected grammar without re-running the verifier.
    """


class GrammarPin(BaseModel):
    """One ``tools/grammars.lock`` row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    language: str
    version: str
    file: str
    blake3: str

    @field_validator("blake3")
    @classmethod
    def _blake3_must_be_64_hex(cls, v: str) -> str:
        if not _BLAKE3_HEX_RE.match(v):
            raise ValueError(f"blake3 must match {_BLAKE3_HEX_RE.pattern!r}, got {v!r}")
        return v

    @field_validator("language")
    @classmethod
    def _language_must_be_lower_snake(cls, v: str) -> str:
        if not _LANGUAGE_RE.match(v):
            raise ValueError(f"language must match {_LANGUAGE_RE.pattern!r}, got {v!r}")
        return v


class GrammarLockFile(BaseModel):
    """Typed ``tools/grammars.lock`` payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    grammars: list[GrammarPin]


def load_and_verify(repo_root: Path) -> GrammarLockFile:
    """Read ``<repo_root>/tools/grammars.lock``, validate, re-hash every
    vendored binary, and return the parsed :class:`GrammarLockFile`.

    Refuses (:class:`GrammarLoadRefused`) on:

    - Missing lock file.
    - YAML parse failure.
    - Pydantic validation failure (unknown fields, bad blake3 shape, …).
    - Missing vendored binary file referenced by a pin's ``file``.
    - BLAKE3 mismatch between the recomputed and the pinned value — the
      message names the failing language and both BLAKE3 strings.

    The ``content_hash`` helper returns ``blake3:<64-hex>``; the pin's
    ``blake3`` is the bare hex, so the prefix is stripped before
    comparison.
    """
    lock_path = repo_root / _LOCK_FILENAME
    if not lock_path.is_file():
        raise GrammarLoadRefused(f"grammars.lock missing at {lock_path}")

    try:
        payload = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise GrammarLoadRefused(f"grammars.lock YAML parse failed: {exc}") from exc

    try:
        lock = GrammarLockFile.model_validate(payload)
    except ValidationError as exc:
        raise GrammarLoadRefused(f"grammars.lock schema invalid: {exc}") from exc

    for pin in lock.grammars:
        binary_path = repo_root / pin.file
        if not binary_path.is_file():
            raise GrammarLoadRefused(
                f"grammars.lock references missing binary "
                f"for language={pin.language!r}: {binary_path}"
            )
        actual = content_hash(binary_path).removeprefix("blake3:")
        if actual != pin.blake3:
            raise GrammarLoadRefused(
                f"BLAKE3 mismatch for language={pin.language!r} "
                f"(file={pin.file}): expected={pin.blake3} actual={actual}"
            )

    return lock
