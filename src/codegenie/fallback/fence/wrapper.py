"""Phase-4 S2-02 — ``fence_pure`` pure core + ``FenceWrapper`` shell.

The functional core (:func:`fence_pure`) is stdlib + Pydantic only — no I/O,
no event emission, no global state. The imperative shell
(:class:`FenceWrapper`) mints the nonce, emits ``FenceApplied`` /
``CanaryCollision`` audit events, and delegates to the core. A pure/shell
parity test in ``tests/unit/fallback/test_fence_pure_shell_parity.py``
prevents drift across the three execution branches (clean under-cap, clean
over-cap, collision).

Per ADR-0013 §Decision the ordering inside :func:`fence_pure` is:

1. ``scanner.scan(payload, nonce)`` on the **untruncated** payload.
2. On scanner collision **or** in-body delimiter collision: body becomes
   ``<<redacted: canary collision>>``; ``canary`` is :class:`CanaryCollision`.
3. Truncate the (possibly-redacted) body to ``_TRUNCATION_CAPS[source_kind]``
   **UTF-8 bytes** (codepoint-safe — multi-byte sequences are not split).
4. Wrap in the per-nonce open/close delimiter and return.

The truncation cap table is data, not branches — adding a ``SourceKind`` is
one ``Literal`` member + one ``_TRUNCATION_CAPS`` row; the
``get_args(SourceKind) == set(_TRUNCATION_CAPS)`` import-time check (AC-3)
is the loud guard against a half-added kind.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Final, Literal, Protocol, TypeAlias, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from codegenie.plugins.events import CanaryCollisionEvent, EventLog, FenceApplied
from codegenie.types.identifiers import EventId, HexNonce

__all__ = [
    "CanaryClean",
    "CanaryCollision",
    "CanaryResult",
    "FenceWrapper",
    "FencedSegment",
    "Scanner",
    "SourceKind",
    "fence_pure",
]


# --- SourceKind + truncation caps ------------------------------------------

SourceKind: TypeAlias = Literal[
    "cve_description",
    "repo_readme",
    "transitive_dep_meta",
    "source_snippet",
    "sandbox_stderr",
    "rag_retrieved",
    "prior_attempt_summary",
]
"""The seven untrusted-input source kinds Phase-4 admits. Adding an eighth is
one ``Literal`` member + one ``_TRUNCATION_CAPS`` row — AC-3's import-time
``get_args(SourceKind) == set(_TRUNCATION_CAPS)`` check fails loudly when
only one of the two is touched."""


_TRUNCATION_CAPS: Final[dict[SourceKind, int]] = {
    "cve_description": 4 * 1024,
    "repo_readme": 2 * 1024,
    "transitive_dep_meta": 1 * 1024,
    "source_snippet": 16 * 1024,
    "sandbox_stderr": 8 * 1024,
    "rag_retrieved": 8 * 1024,
    "prior_attempt_summary": 4 * 1024,
}
"""Per-segment UTF-8 byte caps from ADR-0013's table. ``transitive_dep_meta``'s
"× max 16" and ``rag_retrieved``'s "× max 3" multiplicities are *per-segment
count* and live in S2-04 ``PromptBuilder`` — this dict carries the per-segment
byte cap only."""


_REDACTION: Final[str] = "<<redacted: canary collision>>"
_DELIM_OPEN_FMT: Final[str] = "<UNTRUSTED_INPUT id={nonce}>"
_DELIM_CLOSE_FMT: Final[str] = "</UNTRUSTED_INPUT id={nonce}>"
_DELIMITER_COLLISION_PATTERN_ID: Final[str] = "fence.delimiter_in_body"


# --- CanaryResult tagged union ---------------------------------------------


class CanaryClean(BaseModel):
    """Scanner verdict: no injection pattern detected in the payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["clean"] = "clean"


class CanaryCollision(BaseModel):
    """Scanner verdict: an injection pattern (or the per-nonce delimiter)
    was detected; the payload was redacted by :func:`fence_pure`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["collision"] = "collision"
    pattern_id: str


CanaryResult: TypeAlias = Annotated[CanaryClean | CanaryCollision, Field(discriminator="kind")]
"""Discriminated tagged-union over the scanner's two verdicts. The
``Annotated[..., Field(discriminator="kind")]`` wrapper is load-bearing —
without it, ``TypeAdapter`` round-trip and ``match``/``assert_never``
exhaustiveness break."""


# --- Scanner Protocol -------------------------------------------------------


@runtime_checkable
class Scanner(Protocol):
    """Dependency-inverted port that :func:`fence_pure` consumes.

    S2-03 ships the production ``CanaryGuard`` implementation; tests use
    the trivial ``_AlwaysCleanScanner`` / ``_RecordingScanner`` doubles.
    """

    def scan(self, payload: str, nonce: HexNonce) -> CanaryResult:
        """Scan ``payload`` for injection patterns or nonce collisions.

        Pure — no I/O, no event emission. The implementation must not
        mutate ``payload`` or ``nonce``.
        """


# --- FencedSegment model ---------------------------------------------------


class FencedSegment(BaseModel):
    """One fenced + (possibly) truncated payload bound for the LLM prompt.

    ``canary_fired`` is a derived ``@property`` over ``canary`` — there is no
    stored ``_pattern_id`` escape-hatch; the two illegal states
    ``canary_fired=True, pattern_id=None`` and ``canary_fired=False,
    pattern_id="x"`` are structurally unrepresentable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    content: str
    nonce: HexNonce
    source_kind: SourceKind
    truncated: bool
    original_byte_length: int
    canary: CanaryResult

    @property
    def canary_fired(self) -> bool:
        """``True`` iff the scanner (or the structural delimiter backstop)
        reported a collision and the body was redacted."""
        return isinstance(self.canary, CanaryCollision)


# --- fence_pure: the functional core ---------------------------------------


def fence_pure(
    payload: str,
    nonce: HexNonce,
    source_kind: SourceKind,
    scanner: Scanner,
) -> FencedSegment:
    """Scan untruncated → redact-on-collision → truncate → wrap in delimiter.

    Pure: stdlib + Pydantic only. No I/O. No event emission. The shell
    (:meth:`FenceWrapper.fence`) wraps this with nonce minting + audit
    events.
    """
    original_byte_length = len(payload.encode("utf-8"))
    scanner_verdict = scanner.scan(payload, nonce)

    open_delim = _DELIM_OPEN_FMT.format(nonce=nonce)
    close_delim = _DELIM_CLOSE_FMT.format(nonce=nonce)
    delimiter_in_body = (open_delim in payload) or (close_delim in payload)

    canary: CanaryResult
    if isinstance(scanner_verdict, CanaryCollision):
        body = _REDACTION
        canary = scanner_verdict
        truncated = False
    elif delimiter_in_body:
        body = _REDACTION
        canary = CanaryCollision(pattern_id=_DELIMITER_COLLISION_PATTERN_ID)
        truncated = False
    else:
        body, truncated = _truncate_utf8_safe(payload, _TRUNCATION_CAPS[source_kind])
        canary = scanner_verdict

    content = open_delim + body + close_delim
    return FencedSegment(
        content=content,
        nonce=nonce,
        source_kind=source_kind,
        truncated=truncated,
        original_byte_length=original_byte_length,
        canary=canary,
    )


def _truncate_utf8_safe(payload: str, cap_bytes: int) -> tuple[str, bool]:
    """Truncate ``payload`` to ``cap_bytes`` UTF-8 bytes without splitting a
    multi-byte codepoint.

    Returns ``(body, truncated)``. ``truncated`` is ``True`` iff the cap
    actually fired (the comparison is strict ``>`` — a payload of exactly
    ``cap_bytes`` bytes is not truncated).
    """
    encoded = payload.encode("utf-8")
    if len(encoded) <= cap_bytes:
        return payload, False
    return encoded[:cap_bytes].decode("utf-8", errors="ignore"), True


# --- FenceWrapper: the imperative shell ------------------------------------


def _default_nonce_source() -> HexNonce:
    """Mint a 32-hex-char :data:`HexNonce` via ``secrets.token_hex(16)``.

    ``secrets.token_hex(16)`` is guaranteed to produce exactly 32 lower-case
    hex chars satisfying ``^[0-9a-f]{32}$`` — the one sanctioned raw cast.
    ``random`` is forbidden by ``tests/security/forbidden-patterns``.
    """
    return HexNonce(secrets.token_hex(16))


def _new_event_id() -> EventId:
    """Mint a deterministic-shape event id for one fence emission.

    Mirrors :func:`codegenie.fallback.provenance_gate._new_event_id` — the
    exact id is not pinned by tests; the ``01HFNC`` prefix is operator-
    friendly grep bait.
    """
    return EventId("01HFNC" + secrets.token_hex(10).upper())


@dataclass(frozen=True, slots=True)
class FenceWrapper:
    """Imperative shell over :func:`fence_pure`: mints the nonce, emits
    ``FenceApplied`` on every call, plus ``CanaryCollision`` on the
    collision branch.

    Holds three collaborators: the ``Scanner`` (S2-03 supplies the
    production implementation), the ``EventLog``, and the ``nonce_source``
    factory (seam for deterministic-nonce tests in AC-8/AC-11/AC-14/AC-15).
    """

    scanner: Scanner
    event_log: EventLog
    nonce_source: Callable[[], HexNonce] = field(default=_default_nonce_source)

    def fence(self, payload: str, source_kind: SourceKind) -> FencedSegment:
        """Mint a nonce, delegate to :func:`fence_pure`, emit audit events.

        ``FenceApplied`` is emitted on every call. ``CanaryCollisionEvent``
        is emitted only on the collision branch (read off
        ``result.canary`` structurally — there is no separate
        ``_pattern_id`` field).
        """
        nonce = self.nonce_source()
        result = fence_pure(payload, nonce, source_kind, self.scanner)
        match result.canary:
            case CanaryCollision(pattern_id=pid):
                self.event_log.emit_internal(
                    CanaryCollisionEvent(
                        event_id=_new_event_id(),
                        workflow_id=self.event_log.workflow_id,
                        timestamp=datetime.now(UTC),
                        source_kind=source_kind,
                        nonce=nonce,
                        pattern_id=pid,
                    )
                )
            case CanaryClean():
                pass
        self.event_log.emit_internal(
            FenceApplied(
                event_id=_new_event_id(),
                workflow_id=self.event_log.workflow_id,
                timestamp=datetime.now(UTC),
                source_kind=source_kind,
                nonce=nonce,
                truncated=result.truncated,
                original_byte_length=result.original_byte_length,
            )
        )
        return result
