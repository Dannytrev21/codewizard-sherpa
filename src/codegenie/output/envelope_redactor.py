"""Envelope-level secret-redaction chokepoint (02-ADR-0005, 02-ADR-0010, 02-ADR-0008).

Three-pass composition (envelope-level, post-merge):

    1. ``_redact_known_patterns_pass`` — regex sweep across the merged
       envelope using the S3-01 named pattern table.
    2. ``_redact_entropy_pass`` — Shannon-entropy fallback (S3-01:
       ``len >= 32``, ``>= 4.5`` bits/char) for novel credential shapes
       the named patterns missed.
    3. ``_build_redacted_slice_pass`` — the smart-constructor closure
       that returns :class:`~codegenie.output.redacted_slice.RedactedSlice`
       (02-ADR-0010).

The order is load-bearing: known patterns first (cheap regex hits exit
the leaf early), entropy second (expensive Shannon walk only on
survivors), closure last (immutable model construction). Reordering
would not change the set of findings but would lose the cheap-first
invariant.

Per-probe :meth:`~codegenie.output.sanitizer.OutputSanitizer.scrub`
(Phase 0, 02-ADR-0005) is **upstream** of this module — not a
co-located pass. The merged envelope flows through ``scrub`` per probe,
then through the coordinator's shallow merge, then arrives here as the
chokepoint safety net for any cleartext that survived per-probe
scrubbing.

This module is the **chokepoint** rung of 02-ADR-0005's four-rung
structural-defense ladder:

    1. Runtime — :func:`~codegenie.output.sanitizer.redact_secrets`
       replaces cleartext (S3-01).
    2. Type-system — :class:`RedactedSlice` is a smart-constructor
       (S3-02); ``model_construct`` is banned under
       ``src/codegenie/output/**`` (S1-11).
    3. Chokepoint — :meth:`~codegenie.output.writer.Writer.write` +
       ``_seam_write_envelope`` accept only :class:`RedactedSlice`; the
       ``isinstance`` guard rejects raw ``dict`` at runtime (this module).
    4. Source-level — ``inspect``-based boundary test that no other
       path reaches the writer (deferred to S7-04).

Placeholder idempotence
=======================

Per-probe scrub upstream substitutes redacted strings with the literal
``<REDACTED:fingerprint=<8hex>>``. The entropy pass MUST NOT re-redact
those placeholders (which would double-count findings and corrupt the
fingerprint dedup). The carve-out is structural: the entropy pass skips
any string containing :data:`_PLACEHOLDER_RE`. A 30-char placeholder's
entropy is bounded above by ``log2(24) ≈ 4.58`` bits/char and the
literal prefix ``"<REDACTED:fingerprint="`` lowers the effective
entropy; the explicit skip is defense in depth.

See 02-ADR-0008 for the no-event-stream framing of
``secrets_redacted_count`` — Phase 2 adds **one** new structured-log
field on **one** new event (``envelope.written``), not an event-bus
subscription.

Pure functional core
====================

This module is pure: no I/O, no logging, no filesystem reads, no
``os.environ``, no clock, no subprocess. Per-call state is threaded via
a :class:`contextvars.ContextVar` so the three passes can share an
accumulating :class:`SecretFinding` list without globals or module-
level mutable state. Future contributors must not add I/O here.

Verified by ``tests/unit/output/test_envelope_redactor_composition.py``
and ``tests/unit/output/test_envelope_redactor_integration.py``.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from codegenie.output.redacted_slice import RedactedSlice
from codegenie.output.sanitizer import (
    _ENTROPY_MIN_LEN,
    _ENTROPY_THRESHOLD_BITS_PER_CHAR,
    _PATTERNS,
    SecretFinding,
    _fingerprint,
    _shannon_entropy,
)
from codegenie.parsers import JSONValue
from codegenie.types.identifiers import ProbeId

if TYPE_CHECKING:
    pass

__all__ = ["RedactedSlice", "SecretFinding"]


_ENVELOPE_PROBE_ID: ProbeId = ProbeId("__envelope__")

# Placeholder shape produced by S3-01's ``redact_secrets`` + this module's
# passes. The entropy pass uses this to short-circuit re-scanning previously
# redacted strings (AC-16 placeholder idempotence).
_PLACEHOLDER_RE: re.Pattern[str] = re.compile(r"<REDACTED:fingerprint=[0-9a-f]{8}>")


class SanitizerPass(Protocol):
    """Signature for content-redaction passes (named, entropy)."""

    def __call__(self, slice_: dict[str, JSONValue]) -> dict[str, JSONValue]: ...


class SliceClosurePass(Protocol):
    """Signature for the terminal closure pass that materializes a model."""

    def __call__(self, slice_: dict[str, JSONValue]) -> RedactedSlice: ...


@dataclass
class _PassState:
    """Per-call accumulator threaded across the three passes.

    The findings list grows monotonically across passes; the final pass
    deduplicates fingerprints (stable order) for the
    :class:`RedactedSlice`. The state is bound to a single
    ``_redact_envelope`` call via :data:`_state_var` (a
    :class:`contextvars.ContextVar`), so concurrent gather invocations
    on the same process do not bleed findings into each other.
    """

    findings: list[SecretFinding] = field(default_factory=list)


_state_var: ContextVar[_PassState | None] = ContextVar(
    "_envelope_redactor_pass_state", default=None
)


def _current_state() -> _PassState:
    state = _state_var.get()
    if state is None:
        raise RuntimeError(
            "envelope_redactor pass invoked outside _redact_envelope; "
            "passes must be driven via the _PASSES iteration loop."
        )
    return state


# ---------------------------------------------------------------------------
# Pass 1 — named pattern sweep
# ---------------------------------------------------------------------------


def _redact_named_in_string(s: str) -> str:
    """Apply the S3-01 named-pattern table to ``s``; record findings."""
    state = _current_state()
    out = s
    for pattern_class, pattern in _PATTERNS:

        def repl(m: re.Match[str], _pc: Any = pattern_class) -> str:
            cleartext = m.group(0)
            fp = _fingerprint(cleartext)
            state.findings.append(
                SecretFinding(
                    probe_name=_ENVELOPE_PROBE_ID,
                    fingerprint=fp,
                    pattern_class=_pc,
                    cleartext_len=len(cleartext.encode("utf-8")),
                )
            )
            return f"<REDACTED:fingerprint={fp}>"

        out = pattern.sub(repl, out)
    return out


def _walk(node: JSONValue, leaf_fn: Any) -> JSONValue:
    if isinstance(node, str):
        result: str = leaf_fn(node)
        return result
    if isinstance(node, dict):
        return {k: _walk(v, leaf_fn) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk(item, leaf_fn) for item in node]
    return node


def _redact_known_patterns_pass(slice_: dict[str, JSONValue]) -> dict[str, JSONValue]:
    """Pass 1 — apply the named pattern sweep across every string leaf."""
    out = _walk(slice_, _redact_named_in_string)
    if not isinstance(out, dict):
        raise TypeError("envelope_redactor: pass 1 expects a dict envelope")
    return out


# ---------------------------------------------------------------------------
# Pass 2 — entropy fallback
# ---------------------------------------------------------------------------


def _redact_entropy_in_string(s: str) -> str:
    """Apply the Shannon-entropy fallback to ``s``; record one finding on hit.

    Skips strings that contain a ``<REDACTED:fingerprint=<8hex>>``
    placeholder (AC-16 idempotence) — re-scanning a previously redacted
    leaf would double-count and inflate ``findings_count``.
    """
    if _PLACEHOLDER_RE.search(s):
        return s
    if len(s.encode("utf-8")) < _ENTROPY_MIN_LEN:
        return s
    if _shannon_entropy(s) < _ENTROPY_THRESHOLD_BITS_PER_CHAR:
        return s
    state = _current_state()
    fp = _fingerprint(s)
    state.findings.append(
        SecretFinding(
            probe_name=_ENVELOPE_PROBE_ID,
            fingerprint=fp,
            pattern_class="entropy",
            cleartext_len=len(s.encode("utf-8")),
        )
    )
    return f"<REDACTED:fingerprint={fp}>"


def _redact_entropy_pass(slice_: dict[str, JSONValue]) -> dict[str, JSONValue]:
    """Pass 2 — entropy fallback over strings that survived pass 1."""
    out = _walk(slice_, _redact_entropy_in_string)
    if not isinstance(out, dict):
        raise TypeError("envelope_redactor: pass 2 expects a dict envelope")
    return out


# ---------------------------------------------------------------------------
# Pass 3 — RedactedSlice closure
# ---------------------------------------------------------------------------


def _build_redacted_slice_pass(slice_: dict[str, JSONValue]) -> RedactedSlice:
    """Pass 3 — close the structural ladder by constructing a :class:`RedactedSlice`.

    Fingerprints are deduplicated by insertion order
    (``dict.fromkeys`` over the findings list); ``findings_count`` is
    the total number of replacements (including duplicates of the same
    cleartext at distinct leaves) per the 02-ADR-0010 contract.
    """
    state = _current_state()
    fingerprints = list(dict.fromkeys(f.fingerprint for f in state.findings))
    return RedactedSlice(
        slice=slice_,
        findings_count=len(state.findings),
        fingerprints=fingerprints,
    )


# ---------------------------------------------------------------------------
# _PASSES + _redact_envelope entry point
# ---------------------------------------------------------------------------


# Module-level tuple: a literal three-element registry. The mock-spy test
# in ``test_envelope_redactor_composition.py`` monkeypatches this attribute
# with ``Mock(wraps=...)`` spies to verify the canonical order
# ``("known_patterns", "entropy", "build")`` is invoked. Promoting to a
# decorator registry is deferred until a fourth content pass arrives
# (Phase 4 RAG-scrubber or per-task-class redactor) — rule of three is
# reached but the third pass is the closure, not a content pass, so the
# literal tuple stays Open/Closed-correct for N=3.
_PASSES: tuple[Any, ...] = (
    _redact_known_patterns_pass,
    _redact_entropy_pass,
    _build_redacted_slice_pass,
)


def _redact_envelope(envelope: dict[str, JSONValue]) -> RedactedSlice:
    """Drive the three passes in order; return the closed :class:`RedactedSlice`.

    Per-call state lives in a fresh :class:`_PassState` bound to
    :data:`_state_var` for the duration of one call. Reentrant + thread-
    safe via :class:`contextvars.ContextVar`'s token/reset discipline.
    """
    state = _PassState()
    token = _state_var.set(state)
    try:
        current: Any = envelope
        for pass_ in _PASSES:
            current = pass_(current)
        if not isinstance(current, RedactedSlice):
            raise RuntimeError(
                "envelope_redactor: _PASSES must terminate with a "
                "SliceClosurePass that returns RedactedSlice (02-ADR-0010)."
            )
        return current
    finally:
        _state_var.reset(token)
