"""Phase-4 S2-02 — ``FenceWrapper`` + ``fence_pure`` unit tests.

Covers AC-2, AC-3, AC-4, AC-5, AC-9, AC-10, AC-14, AC-15, AC-16, AC-17, AC-18.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.fallback.fence.wrapper import (
    _TRUNCATION_CAPS,
    CanaryClean,
    CanaryCollision,
    CanaryResult,
    FencedSegment,
    FenceWrapper,
    Scanner,
    SourceKind,
    fence_pure,
)
from codegenie.plugins.events import (
    CanaryCollisionEvent,
    EventLog,
    FenceApplied,
)
from codegenie.types.identifiers import HexNonce, WorkflowId

# --- Helpers ---------------------------------------------------------------


_FIXED_NONCE = HexNonce("00112233445566778899aabbccddeeff")
_OPEN_DELIM = f"<UNTRUSTED_INPUT id={_FIXED_NONCE}>"
_CLOSE_DELIM = f"</UNTRUSTED_INPUT id={_FIXED_NONCE}>"
_DELIM_OVERHEAD = len(_OPEN_DELIM.encode("utf-8")) + len(_CLOSE_DELIM.encode("utf-8"))


def _wf() -> WorkflowId:
    return WorkflowId("01HFENCEFACE0000000000000000")


def _fixed_nonce_factory() -> Callable[[], HexNonce]:
    return lambda: _FIXED_NONCE


@dataclass(frozen=True)
class _AlwaysCleanScanner:
    def scan(self, payload: str, nonce: HexNonce) -> CanaryResult:
        return CanaryClean()


@dataclass(frozen=True)
class _AlwaysCollideScanner:
    pattern_id: str = "ignore_previous_instructions"

    def scan(self, payload: str, nonce: HexNonce) -> CanaryResult:
        return CanaryCollision(pattern_id=self.pattern_id)


@dataclass
class _RecordingScanner:
    """Records the byte length of every payload it received."""

    seen_byte_lengths: list[int] = field(default_factory=list)

    def scan(self, payload: str, nonce: HexNonce) -> CanaryResult:
        self.seen_byte_lengths.append(len(payload.encode("utf-8")))
        return CanaryClean()


# --- AC-2 — SourceKind literal alias ---------------------------------------


def test_source_kind_literal_is_exactly_the_seven_names() -> None:
    assert set(get_args(SourceKind)) == {
        "cve_description",
        "repo_readme",
        "transitive_dep_meta",
        "source_snippet",
        "sandbox_stderr",
        "rag_retrieved",
        "prior_attempt_summary",
    }


# --- AC-3 — _TRUNCATION_CAPS coverage + value snapshot ---------------------


def test_truncation_caps_cover_every_source_kind() -> None:
    """AC-3 intent: adding to one without the other fails loudly."""
    assert set(_TRUNCATION_CAPS.keys()) == set(get_args(SourceKind))


def test_truncation_caps_byte_values_snapshot_match_adr_0013() -> None:
    """AC-3 snapshot: ADR-0013's table values, byte-exact.

    A value change here must update both this list and ADR-0013 together.
    """
    assert _TRUNCATION_CAPS == {
        "cve_description": 4 * 1024,
        "repo_readme": 2 * 1024,
        "transitive_dep_meta": 1 * 1024,
        "source_snippet": 16 * 1024,
        "sandbox_stderr": 8 * 1024,
        "rag_retrieved": 8 * 1024,
        "prior_attempt_summary": 4 * 1024,
    }


# --- AC-4 — FencedSegment model -------------------------------------------


def test_fenced_segment_is_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        FencedSegment(  # type: ignore[call-arg]
            content="x",
            nonce=_FIXED_NONCE,
            source_kind="repo_readme",
            truncated=False,
            original_byte_length=0,
            canary=CanaryClean(),
            unknown_extra="x",
        )


def test_fenced_segment_is_frozen_cannot_mutate() -> None:
    seg = fence_pure("hi", _FIXED_NONCE, "repo_readme", _AlwaysCleanScanner())
    with pytest.raises(ValidationError):
        seg.truncated = True  # type: ignore[misc]


def test_fenced_segment_canary_fired_is_derived_property_not_field() -> None:
    """AC-4: ``canary_fired`` is derived from ``canary``, not stored."""
    fields = set(FencedSegment.model_fields.keys())
    assert "canary_fired" not in fields
    seg_clean = fence_pure("hi", _FIXED_NONCE, "repo_readme", _AlwaysCleanScanner())
    seg_coll = fence_pure("x", _FIXED_NONCE, "repo_readme", _AlwaysCollideScanner())
    assert seg_clean.canary_fired is False
    assert seg_coll.canary_fired is True


def test_fenced_segment_no_underscore_pattern_id_field() -> None:
    """AC-4: rule out the ``_pattern_id`` anaemic escape-hatch."""
    fields = set(FencedSegment.model_fields.keys())
    assert "_pattern_id" not in fields
    assert "pattern_id" not in fields


# --- AC-5 — Scanner Protocol + CanaryResult tagged union -------------------


def test_canary_result_decodes_collision_variant() -> None:
    parsed = TypeAdapter(CanaryResult).validate_python({"kind": "collision", "pattern_id": "x"})
    assert isinstance(parsed, CanaryCollision)
    assert parsed.pattern_id == "x"


def test_canary_result_decodes_clean_variant() -> None:
    parsed = TypeAdapter(CanaryResult).validate_python({"kind": "clean"})
    assert isinstance(parsed, CanaryClean)


def test_canary_result_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(CanaryResult).validate_python({"kind": "nope"})


def test_canary_result_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(CanaryResult).validate_python({"kind": "clean", "unexpected": "x"})


def test_always_clean_scanner_is_runtime_scanner() -> None:
    assert isinstance(_AlwaysCleanScanner(), Scanner)


# --- AC-9 — Truncation fires exactly at the cap (boundary-pinned) ---------


@pytest.mark.parametrize("source_kind", list(get_args(SourceKind)))
def test_payload_exactly_at_cap_is_not_truncated(source_kind: SourceKind) -> None:
    cap = _TRUNCATION_CAPS[source_kind]
    payload = "A" * cap  # 1 byte per ASCII char
    seg = fence_pure(payload, _FIXED_NONCE, source_kind, _AlwaysCleanScanner())
    assert seg.truncated is False
    body = seg.content[len(_OPEN_DELIM) : -len(_CLOSE_DELIM)]
    assert len(body.encode("utf-8")) == cap


@pytest.mark.parametrize("source_kind", list(get_args(SourceKind)))
def test_payload_one_over_cap_is_truncated(source_kind: SourceKind) -> None:
    cap = _TRUNCATION_CAPS[source_kind]
    payload = "A" * (cap + 1)
    seg = fence_pure(payload, _FIXED_NONCE, source_kind, _AlwaysCleanScanner())
    assert seg.truncated is True
    assert len(seg.content.encode("utf-8")) <= cap + _DELIM_OVERHEAD


@pytest.mark.parametrize("source_kind", list(get_args(SourceKind)))
def test_payload_one_under_cap_is_not_truncated(source_kind: SourceKind) -> None:
    cap = _TRUNCATION_CAPS[source_kind]
    payload = "A" * (cap - 1)
    seg = fence_pure(payload, _FIXED_NONCE, source_kind, _AlwaysCleanScanner())
    assert seg.truncated is False


# --- AC-10 — Canary-collision redaction -----------------------------------


def test_canary_collision_redacts_body_and_preserves_original_length() -> None:
    payload = "A" * 8192  # multi-kilobyte attacker payload
    scanner = _AlwaysCollideScanner(pattern_id="ignore_previous_instructions")
    seg = fence_pure(payload, _FIXED_NONCE, "source_snippet", scanner)
    body = seg.content[len(_OPEN_DELIM) : -len(_CLOSE_DELIM)]
    assert body == "<<redacted: canary collision>>"
    assert isinstance(seg.canary, CanaryCollision)
    assert seg.canary.pattern_id == "ignore_previous_instructions"
    assert seg.canary_fired is True
    assert seg.truncated is False
    assert seg.original_byte_length == 8192


# --- AC-14 — Scan runs on the UNTRUNCATED payload -------------------------


def test_scanner_sees_untruncated_payload() -> None:
    cap = _TRUNCATION_CAPS["transitive_dep_meta"]
    payload = "A" * (cap + 5000)
    scanner = _RecordingScanner()
    seg = fence_pure(payload, _FIXED_NONCE, "transitive_dep_meta", scanner)
    assert scanner.seen_byte_lengths == [cap + 5000]
    assert seg.original_byte_length == cap + 5000


# --- AC-15 — Close/open-delimiter collision in scan-clean body is redacted -


def test_close_delimiter_in_clean_scan_body_is_redacted() -> None:
    payload = f"prefix {_CLOSE_DELIM} suffix"
    seg = fence_pure(payload, _FIXED_NONCE, "source_snippet", _AlwaysCleanScanner())
    assert seg.content.count(_CLOSE_DELIM) == 1
    body = seg.content[len(_OPEN_DELIM) : -len(_CLOSE_DELIM)]
    assert body == "<<redacted: canary collision>>"
    assert isinstance(seg.canary, CanaryCollision)
    assert seg.canary.pattern_id == "fence.delimiter_in_body"
    assert seg.canary_fired is True


def test_open_delimiter_in_clean_scan_body_is_redacted() -> None:
    payload = f"prefix {_OPEN_DELIM} suffix"
    seg = fence_pure(payload, _FIXED_NONCE, "source_snippet", _AlwaysCleanScanner())
    assert seg.content.count(_OPEN_DELIM) == 1
    body = seg.content[len(_OPEN_DELIM) : -len(_CLOSE_DELIM)]
    assert body == "<<redacted: canary collision>>"
    assert isinstance(seg.canary, CanaryCollision)
    assert seg.canary.pattern_id == "fence.delimiter_in_body"


# --- AC-16 — Truncation is byte-exact and codepoint-safe ------------------


def test_truncation_does_not_split_multibyte_codepoint() -> None:
    """Build a payload of 3-byte UTF-8 chars sized to straddle a cap."""
    cap = _TRUNCATION_CAPS["transitive_dep_meta"]  # 1024
    # 342 * 3 = 1026 bytes, two over cap. Cap of 1024 / 3 = 341 remainder 1 —
    # so the 342nd codepoint's first byte sits at byte index 1023 and the cap
    # falls inside that codepoint.
    n = (cap // 3) + 1
    payload = "好" * n
    assert len(payload.encode("utf-8")) == 3 * n
    seg = fence_pure(payload, _FIXED_NONCE, "transitive_dep_meta", _AlwaysCleanScanner())
    body = seg.content[len(_OPEN_DELIM) : -len(_CLOSE_DELIM)]
    body_bytes = body.encode("utf-8")
    assert len(body_bytes) <= cap
    # Round-trip must not raise — no partial codepoint left over.
    assert body_bytes.decode("utf-8") == body
    assert seg.truncated is True


# --- AC-17 — Empty payload -------------------------------------------------


def test_empty_payload_is_fenced_with_empty_body() -> None:
    seg = fence_pure("", _FIXED_NONCE, "repo_readme", _AlwaysCleanScanner())
    assert seg.content == f"{_OPEN_DELIM}{_CLOSE_DELIM}"
    assert seg.truncated is False
    assert seg.original_byte_length == 0
    assert isinstance(seg.canary, CanaryClean)


def test_empty_payload_invokes_scanner() -> None:
    scanner = _RecordingScanner()
    fence_pure("", _FIXED_NONCE, "repo_readme", scanner)
    assert scanner.seen_byte_lengths == [0]


# --- AC-18 — FenceApplied event payload assertions -------------------------


def test_fence_applied_event_carries_input_byte_length_under_cap(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path, workflow_id=_wf())
    wrapper = FenceWrapper(
        scanner=_AlwaysCleanScanner(),
        event_log=log,
        nonce_source=_fixed_nonce_factory(),
    )
    wrapper.fence("hello", "repo_readme")
    log.flush()
    applied = [e for e in log.replay() if isinstance(e, FenceApplied)]
    assert len(applied) == 1
    assert applied[0].original_byte_length == len(b"hello")
    assert applied[0].truncated is False
    assert applied[0].source_kind == "repo_readme"
    assert applied[0].nonce == _FIXED_NONCE


def test_fence_applied_event_carries_input_byte_length_over_cap(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path, workflow_id=_wf())
    wrapper = FenceWrapper(
        scanner=_AlwaysCleanScanner(),
        event_log=log,
        nonce_source=_fixed_nonce_factory(),
    )
    payload = "A" * (_TRUNCATION_CAPS["repo_readme"] + 100)
    wrapper.fence(payload, "repo_readme")
    log.flush()
    applied = [e for e in log.replay() if isinstance(e, FenceApplied)]
    assert len(applied) == 1
    assert applied[0].original_byte_length == len(payload.encode("utf-8"))
    assert applied[0].truncated is True


def test_canary_collision_event_emitted_with_pattern_id(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path, workflow_id=_wf())
    wrapper = FenceWrapper(
        scanner=_AlwaysCollideScanner(pattern_id="ignore_previous_instructions"),
        event_log=log,
        nonce_source=_fixed_nonce_factory(),
    )
    wrapper.fence("attacker payload", "source_snippet")
    log.flush()
    collisions = [e for e in log.replay() if isinstance(e, CanaryCollisionEvent)]
    assert len(collisions) == 1
    assert collisions[0].pattern_id == "ignore_previous_instructions"
    assert collisions[0].source_kind == "source_snippet"
    assert collisions[0].nonce == _FIXED_NONCE
    # The always-emitted FenceApplied also fires alongside.
    applied = [e for e in log.replay() if isinstance(e, FenceApplied)]
    assert len(applied) == 1


def test_canary_clean_scan_emits_only_fence_applied(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path, workflow_id=_wf())
    wrapper = FenceWrapper(
        scanner=_AlwaysCleanScanner(),
        event_log=log,
        nonce_source=_fixed_nonce_factory(),
    )
    wrapper.fence("hello", "repo_readme")
    log.flush()
    collisions = [e for e in log.replay() if isinstance(e, CanaryCollisionEvent)]
    assert collisions == []


# --- FenceWrapper dataclass shape ------------------------------------------


def test_fence_wrapper_is_frozen_dataclass() -> None:
    from dataclasses import fields as dc_fields
    from dataclasses import is_dataclass

    assert is_dataclass(FenceWrapper)
    names = {f.name for f in dc_fields(FenceWrapper)}
    assert names == {"scanner", "event_log", "nonce_source"}


def test_fence_wrapper_default_nonce_is_32_hex_chars(tmp_path: Path) -> None:
    """The default ``nonce_source`` mints a valid HexNonce via secrets."""
    import re

    log = EventLog(root=tmp_path, workflow_id=_wf())
    wrapper = FenceWrapper(scanner=_AlwaysCleanScanner(), event_log=log)
    seg = wrapper.fence("hello", "repo_readme")
    assert re.fullmatch(r"[0-9a-f]{32}", seg.nonce) is not None
