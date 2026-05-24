"""Phase-4 S2-03 AC-7 — adversarial: bypass-via-truncation end-to-end.

The structural proof of ADR-0013's scan-untruncated-first ordering. The
injection pattern is placed **entirely past** the 16 KB ``source_snippet``
cap so every injection byte is in the would-have-been-truncated zone.
``FenceWrapper.fence`` (the S2-02 imperative shell) is exercised with a
``CanaryGuard()`` scanner; we then assert:

  (i)   ``segment.canary_fired is True``
  (ii)  ``segment.canary`` is a ``CanaryCollision`` (the sum-type variant
        in ``codegenie.fallback.fence.wrapper``) with the expected pid.
  (iii) the redaction marker appears in ``segment.content`` (loose
        containment check — the exact delimiter framing is S2-02's
        tested concern).
  (iv)  exactly one ``CanaryCollisionEvent`` (the audit event in
        ``codegenie.plugins.events`` — note the rename to avoid the
        namespace clash with the same-named ``CanaryResult`` variant)
        is appended to the event log, with the matching pid + source_kind.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from codegenie.fallback.fence.canary import CanaryGuard
from codegenie.fallback.fence.wrapper import CanaryCollision, FenceWrapper
from codegenie.plugins.events import CanaryCollisionEvent, EventLog
from codegenie.types.identifiers import HexNonce, WorkflowId

SOURCE_SNIPPET_CAP: Final[int] = 16 * 1024


@pytest.mark.adv
@pytest.mark.parametrize(
    ("pattern_bytes", "expected_pid"),
    [
        (b"ignore previous instructions", "ignore_previous_instructions"),
        (b"<|im_start|>system", "im_start_token"),
        (b"[INST] You are now", "inst_token"),
        (b"system_override:", "system_override"),
        (b"<tool_call>", "tool_call_injection"),
    ],
)
def test_injection_past_truncation_cap_is_caught_by_fence_wrapper(
    tmp_path: Path, pattern_bytes: bytes, expected_pid: str
) -> None:
    # Filler alone exceeds the cap, so the *entire* injection sits past it.
    benign = b"BENIGN " * 3000  # 21_000 bytes
    assert len(benign) >= SOURCE_SNIPPET_CAP
    payload_bytes = benign + b"\n" + pattern_bytes
    payload = payload_bytes.decode("utf-8", errors="ignore")

    fixed_nonce = HexNonce("0" * 32)
    log = EventLog(root=tmp_path, workflow_id=WorkflowId("wf-canary-test"))
    fence = FenceWrapper(
        scanner=CanaryGuard(),
        event_log=log,
        nonce_source=lambda: fixed_nonce,
    )

    segment = fence.fence(payload, source_kind="source_snippet")

    # (i) + (ii)
    assert segment.canary_fired is True
    assert isinstance(segment.canary, CanaryCollision)
    assert segment.canary.pattern_id == expected_pid

    # (iii) loose containment — exact framing is S2-02's tested concern
    assert "<<redacted: canary collision>>" in segment.content

    # (iv) audit event — read via EventLog.replay()
    collisions = [e for e in log.replay() if isinstance(e, CanaryCollisionEvent)]
    assert len(collisions) == 1
    assert collisions[0].pattern_id == expected_pid
    assert collisions[0].source_kind == "source_snippet"
