"""Phase-4 S7-09 partial — extend the S2-03 canary-bypass test across
every ``SourceKind`` literal.

S2-03 seeded the bypass-via-truncation behavior under
``source_snippet`` (a 16 KB cap). ADR-04-0013 commits the scan-
untruncated-first invariant *for every* ``SourceKind``; this test
parametrizes the canary-firing behavior across all seven literals so a
future-added eighth ``SourceKind`` that forgets the invariant fails
loudly.

The structural form is the same as the original S2-03 test: place the
injection pattern past the truncation cap for the source kind under
test; assert (a) ``canary_fired is True``, (b) the redaction marker
appears in the trimmed body, (c) one ``CanaryCollisionEvent`` is
emitted with the matching ``source_kind`` and ``pattern_id``.

S7-09 corpus growth: the full 200-payload injection corpus +
50-scenario red-team are still pending. This file covers one S7-09
bullet definitively (the canary-bypass extension); the remaining
bullets stay deferred per ``_attempts/S7-10.md``-shape attempt log.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, get_args

import pytest

from codegenie.fallback.fence.canary import CanaryGuard
from codegenie.fallback.fence.wrapper import (
    _TRUNCATION_CAPS,
    CanaryCollision,
    FenceWrapper,
    SourceKind,
)
from codegenie.plugins.events import CanaryCollisionEvent, EventLog
from codegenie.types.identifiers import HexNonce, WorkflowId

# The seven canonical SourceKinds (derived from get_args so a future-
# added eighth automatically participates in this parametrize).
_ALL_SOURCE_KINDS: Final[tuple[SourceKind, ...]] = get_args(SourceKind)


# One representative injection pattern per parametrize row. The
# canary corpus has ~50 patterns; this test picks the load-bearing
# "ignore previous instructions" canonical attack since it's the
# best-documented prompt-injection payload in public threat reports.
_INJECTION_PATTERN_BYTES: Final[bytes] = b"ignore previous instructions"
_INJECTION_PATTERN_ID: Final[str] = "ignore_previous_instructions"


def _build_payload_past_cap(source_kind: SourceKind) -> str:
    """Construct a payload whose injection pattern sits entirely past
    the truncation cap for ``source_kind``."""
    cap = _TRUNCATION_CAPS[source_kind]
    # Filler must exceed the cap so the injection lands in the
    # would-have-been-truncated zone.
    filler_unit = b"BENIGN "
    # Filler length: cap + small margin so the entire injection is past
    # the byte cap.
    needed_bytes = cap + 256
    repeats = (needed_bytes // len(filler_unit)) + 1
    filler = filler_unit * repeats
    payload_bytes = filler + b"\n" + _INJECTION_PATTERN_BYTES
    assert len(filler) >= cap, (
        f"filler must exceed cap for {source_kind}: filler={len(filler)} cap={cap}"
    )
    return payload_bytes.decode("utf-8", errors="ignore")


@pytest.mark.adv
@pytest.mark.parametrize("source_kind", _ALL_SOURCE_KINDS)
def test_canary_fires_past_truncation_for_every_source_kind(
    tmp_path: Path, source_kind: SourceKind
) -> None:
    """For every SourceKind literal, an injection past the truncation
    cap MUST be caught by the canary scanner (scan runs on the
    untruncated bytes per ADR-04-0013). The redaction marker MUST
    appear in the truncated body. Exactly one CanaryCollisionEvent
    MUST be emitted with the matching source_kind + pattern_id.
    """
    payload = _build_payload_past_cap(source_kind)
    fixed_nonce = HexNonce("0" * 32)
    log = EventLog(
        root=tmp_path,
        workflow_id=WorkflowId(f"wf-canary-all-{source_kind}"),
    )
    fence = FenceWrapper(
        scanner=CanaryGuard(),
        event_log=log,
        nonce_source=lambda: fixed_nonce,
    )

    segment = fence.fence(payload, source_kind=source_kind)

    # (i) — canary fired
    assert segment.canary_fired is True, (
        f"canary did not fire for source_kind={source_kind}; "
        f"scan-untruncated-first invariant (ADR-04-0013) is broken"
    )
    # (ii) — collision variant with the expected pattern id
    assert isinstance(segment.canary, CanaryCollision)
    assert segment.canary.pattern_id == _INJECTION_PATTERN_ID

    # (iii) — redaction marker in the trimmed body
    assert "<<redacted: canary collision>>" in segment.content

    # (iv) — exactly one audit event with the matching source_kind
    collisions = [e for e in log.replay() if isinstance(e, CanaryCollisionEvent)]
    assert len(collisions) == 1, (
        f"expected exactly one CanaryCollisionEvent for {source_kind}; got {len(collisions)}"
    )
    assert collisions[0].pattern_id == _INJECTION_PATTERN_ID
    assert collisions[0].source_kind == source_kind


def test_all_seven_source_kinds_covered() -> None:
    """Sanity — :data:`_ALL_SOURCE_KINDS` resolves to the canonical
    seven-element tuple. A future eighth SourceKind would land here
    automatically via ``get_args``; this assertion documents the
    expected count today.
    """
    assert len(_ALL_SOURCE_KINDS) == 7
    expected = {
        "cve_description",
        "repo_readme",
        "transitive_dep_meta",
        "source_snippet",
        "sandbox_stderr",
        "rag_retrieved",
        "prior_attempt_summary",
    }
    assert set(_ALL_SOURCE_KINDS) == expected
