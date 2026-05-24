"""Phase-4 S2-04 — behavior tests for ``PromptBuilder``.

Covers AC-4..AC-10 (multiplicity caps, deterministic order, the all-untrusted-
through-fence proof, empty-optional handling, capability-doesn't-flow
signature guard, and the ``PromptAssembled`` event emission).
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from codegenie.fallback.fence.canary import CanaryGuard
from codegenie.fallback.fence.prompt_builder import PromptBuilder
from codegenie.fallback.fence.wrapper import (
    FencedSegment,
    FenceWrapper,
    SourceKind,
)
from codegenie.plugins.events import (
    EventLog,
    PromptAssembled,
    SegmentCountTruncated,
)
from codegenie.types.identifiers import HexNonce, WorkflowId


def _wf(suffix: str = "0000000000000000000000") -> WorkflowId:
    return WorkflowId("01HPRB" + suffix)


def _det_nonces() -> Iterator[HexNonce]:
    return iter(HexNonce(f"{i:032x}") for i in range(100))


def _make_builder(
    tmp_path: Path, *, workflow_suffix: str = "0000000000000000000000"
) -> tuple[PromptBuilder, EventLog]:
    log = EventLog(root=tmp_path, workflow_id=_wf(workflow_suffix))
    nonces = _det_nonces()
    fence = FenceWrapper(scanner=CanaryGuard(), event_log=log, nonce_source=lambda: next(nonces))
    return PromptBuilder(fence=fence, event_log=log), log


# ---------------------------------------------------------------------------
# AC-1 / AC-2 — module + newtype existence
# ---------------------------------------------------------------------------


def test_newtypes_live_in_prompt_builder_module() -> None:
    """AC-2: ``TrustedPrompt`` / ``FencedPromptBody`` are exported from prompt_builder."""
    from codegenie.fallback.fence import prompt_builder as pb

    assert hasattr(pb, "TrustedPrompt")
    assert hasattr(pb, "FencedPromptBody")
    # NewType erases at runtime — the underlying supertype is ``str``.
    assert isinstance(pb.TrustedPrompt("x"), str)
    assert isinstance(pb.FencedPromptBody("y"), str)


# ---------------------------------------------------------------------------
# AC-6 — TrustedPrompt content
# ---------------------------------------------------------------------------


def test_trusted_prompt_is_skill_plus_double_newline_plus_instruction(tmp_path: Path) -> None:
    """AC-6: ``system_prompt = skill + "\\n\\n" + instruction_template`` (no fencing)."""
    builder, _log = _make_builder(tmp_path)
    system, _ = builder.build(
        skill="SKILL",
        instruction_template="INSTRUCTIONS",
        cve_description="CVE-2026-0001",
        repo_readme="readme",
        transitive_dep_meta=[],
        source_snippets=[],
    )
    assert isinstance(system, str)  # NewType erases at runtime
    assert system == "SKILL\n\nINSTRUCTIONS"


# ---------------------------------------------------------------------------
# AC-9 — capability does not flow through PromptBuilder
# ---------------------------------------------------------------------------


def test_build_signature_excludes_budget_token() -> None:
    """AC-9: ``build`` accepts no ``token`` / ``budget_token`` parameter."""
    sig = inspect.signature(PromptBuilder.build)
    params = set(sig.parameters)
    assert "token" not in params
    assert "budget_token" not in params


def test_build_signature_keyword_only_after_self() -> None:
    """Story signature pins keyword-only parameters via ``*,``."""
    sig = inspect.signature(PromptBuilder.build)
    # Drop ``self``; everything else must be keyword-only.
    non_self = [p for name, p in sig.parameters.items() if name != "self"]
    for param in non_self:
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"{param.name} must be keyword-only (kind={param.kind})"
        )


# ---------------------------------------------------------------------------
# AC-4 — multiplicity caps
# ---------------------------------------------------------------------------


def test_transitive_dep_meta_over_16_truncates_with_one_event(tmp_path: Path) -> None:
    """AC-4: 20 deps → keep first 16, emit one ``SegmentCountTruncated``."""
    builder, log = _make_builder(tmp_path)
    overflow = [f"dep-{i}" for i in range(20)]
    _, body = builder.build(
        skill="S",
        instruction_template="I",
        cve_description="CVE",
        repo_readme="R",
        transitive_dep_meta=overflow,
        source_snippets=[],
    )
    # First 16 are kept; dep-16..dep-19 are dropped.
    for kept in (f"dep-{i}" for i in range(16)):
        assert kept in body, f"expected kept dep {kept!r} in body"
    for dropped in (f"dep-{i}" for i in range(16, 20)):
        assert dropped not in body, f"expected dropped dep {dropped!r} NOT in body"
    truncations = [e for e in log.replay() if isinstance(e, SegmentCountTruncated)]
    assert len(truncations) == 1
    assert truncations[0].source_kind == "transitive_dep_meta"
    assert truncations[0].requested == 20
    assert truncations[0].kept == 16


def test_transitive_dep_meta_exactly_16_does_not_emit_truncation(tmp_path: Path) -> None:
    """AC-4 boundary: 16 deps → no ``SegmentCountTruncated`` event."""
    builder, log = _make_builder(tmp_path)
    deps = [f"dep-{i}" for i in range(16)]
    builder.build(
        skill="S",
        instruction_template="I",
        cve_description="CVE",
        repo_readme="R",
        transitive_dep_meta=deps,
        source_snippets=[],
    )
    truncations = [e for e in log.replay() if isinstance(e, SegmentCountTruncated)]
    assert truncations == []


def test_rag_few_shots_over_3_raises_before_fencing(tmp_path: Path) -> None:
    """AC-4: 4 RAG hits → ``ValueError``; no ``PromptAssembled`` emitted, no fence calls."""
    builder, log = _make_builder(tmp_path)

    with pytest.raises(ValueError, match=r"rag_few_shots capped at 3, got 4"):
        builder.build(
            skill="S",
            instruction_template="I",
            cve_description="CVE",
            repo_readme="R",
            transitive_dep_meta=[],
            source_snippets=[],
            rag_few_shots=["a", "b", "c", "d"],
        )
    replayed = list(log.replay())
    assert not any(isinstance(e, PromptAssembled) for e in replayed)


def test_rag_few_shots_exactly_3_is_accepted(tmp_path: Path) -> None:
    """AC-4 boundary: 3 RAG hits → no raise, all three fenced."""
    builder, log = _make_builder(tmp_path)
    _, body = builder.build(
        skill="S",
        instruction_template="I",
        cve_description="CVE",
        repo_readme="R",
        transitive_dep_meta=[],
        source_snippets=[],
        rag_few_shots=["alpha", "beta", "gamma"],
    )
    for hit in ("alpha", "beta", "gamma"):
        assert hit in body
    assembled = [e for e in log.replay() if isinstance(e, PromptAssembled)]
    assert len(assembled) == 1
    assert assembled[0].source_kinds_used.count("rag_retrieved") == 3


# ---------------------------------------------------------------------------
# AC-5 — deterministic assembly order
# ---------------------------------------------------------------------------


def test_same_inputs_with_deterministic_nonces_produce_byte_identical_body(
    tmp_path: Path,
) -> None:
    """AC-5: identical inputs + identical nonces → byte-identical ``FencedPromptBody``."""
    nonces_a = _det_nonces()
    log_a = EventLog(root=tmp_path / "a", workflow_id=_wf("AAAAAAAAAAAAAAAAAAAAAA"))
    builder_a = PromptBuilder(
        fence=FenceWrapper(
            scanner=CanaryGuard(),
            event_log=log_a,
            nonce_source=lambda: next(nonces_a),
        ),
        event_log=log_a,
    )
    _, body_a = builder_a.build(
        skill="S",
        instruction_template="I",
        cve_description="CVE",
        repo_readme="R",
        transitive_dep_meta=["a", "b"],
        source_snippets=["src1"],
    )
    nonces_b = _det_nonces()
    log_b = EventLog(root=tmp_path / "b", workflow_id=_wf("BBBBBBBBBBBBBBBBBBBBBB"))
    builder_b = PromptBuilder(
        fence=FenceWrapper(
            scanner=CanaryGuard(),
            event_log=log_b,
            nonce_source=lambda: next(nonces_b),
        ),
        event_log=log_b,
    )
    _, body_b = builder_b.build(
        skill="S",
        instruction_template="I",
        cve_description="CVE",
        repo_readme="R",
        transitive_dep_meta=["a", "b"],
        source_snippets=["src1"],
    )
    assert body_a == body_b
    assembled = [e for e in log_a.replay() if isinstance(e, PromptAssembled)]
    assert len(assembled) == 1
    assert assembled[0].source_kinds_used == (
        "cve_description",
        "repo_readme",
        "transitive_dep_meta",
        "transitive_dep_meta",
        "source_snippet",
    )


def test_assembly_order_includes_all_optional_segments(tmp_path: Path) -> None:
    """AC-5: full order = cve, readme, deps, snippets, rag, prior, stderr."""
    builder, log = _make_builder(tmp_path)
    builder.build(
        skill="S",
        instruction_template="I",
        cve_description="CVE",
        repo_readme="R",
        transitive_dep_meta=["d1"],
        source_snippets=["snip"],
        rag_few_shots=["rag"],
        prior_attempt_summary="prior",
        sandbox_stderr="err",
    )
    assembled = [e for e in log.replay() if isinstance(e, PromptAssembled)]
    assert len(assembled) == 1
    assert assembled[0].source_kinds_used == (
        "cve_description",
        "repo_readme",
        "transitive_dep_meta",
        "source_snippet",
        "rag_retrieved",
        "prior_attempt_summary",
        "sandbox_stderr",
    )


# ---------------------------------------------------------------------------
# AC-7 — every untrusted byte passes through the fence
# ---------------------------------------------------------------------------


@dataclass
class _RecordingFence:
    """Records every ``(source_kind, payload)`` pair routed through ``fence``."""

    inner: FenceWrapper
    seen: list[tuple[SourceKind, str]] = field(default_factory=list)

    def fence(self, payload: str, source_kind: SourceKind) -> FencedSegment:
        self.seen.append((source_kind, payload))
        return self.inner.fence(payload, source_kind)


def test_every_untrusted_payload_passes_through_fence_in_order(tmp_path: Path) -> None:
    """AC-7: fence sees exact ``(SourceKind, payload)`` sequence in AC-5 order."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    nonces = _det_nonces()
    inner = FenceWrapper(scanner=CanaryGuard(), event_log=log, nonce_source=lambda: next(nonces))
    recording = _RecordingFence(inner=inner)
    builder = PromptBuilder(fence=recording, event_log=log)
    builder.build(
        skill="S",
        instruction_template="I",
        cve_description="CVE-PAYLOAD",
        repo_readme="README-PAYLOAD",
        transitive_dep_meta=["dep-A", "dep-B"],
        source_snippets=["SRC-A"],
        rag_few_shots=["RAG-A", "RAG-B"],
        prior_attempt_summary="PRIOR-A",
        sandbox_stderr="STDERR-A",
    )
    assert recording.seen == [
        ("cve_description", "CVE-PAYLOAD"),
        ("repo_readme", "README-PAYLOAD"),
        ("transitive_dep_meta", "dep-A"),
        ("transitive_dep_meta", "dep-B"),
        ("source_snippet", "SRC-A"),
        ("rag_retrieved", "RAG-A"),
        ("rag_retrieved", "RAG-B"),
        ("prior_attempt_summary", "PRIOR-A"),
        ("sandbox_stderr", "STDERR-A"),
    ]


def test_body_is_concat_of_fenced_segments_with_unique_nonces(tmp_path: Path) -> None:
    """AC-7: body == "".join(segment.content) and no two segments share a nonce."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    nonces = _det_nonces()
    captured: list[FencedSegment] = []

    @dataclass
    class _Capturer:
        inner: FenceWrapper

        def fence(self, payload: str, source_kind: SourceKind) -> FencedSegment:
            seg = self.inner.fence(payload, source_kind)
            captured.append(seg)
            return seg

    inner = FenceWrapper(scanner=CanaryGuard(), event_log=log, nonce_source=lambda: next(nonces))
    builder = PromptBuilder(fence=_Capturer(inner=inner), event_log=log)
    _, body = builder.build(
        skill="S",
        instruction_template="I",
        cve_description="alpha",
        repo_readme="beta",
        transitive_dep_meta=["gamma"],
        source_snippets=["delta"],
    )
    # (ii) byte-for-byte concatenation of FencedSegment.content (in order).
    assert body == "".join(seg.content for seg in captured)
    # (iv) every open/close delimiter appears exactly once per nonce.
    for seg in captured:
        open_delim = f"<UNTRUSTED_INPUT id={seg.nonce}>"
        close_delim = f"</UNTRUSTED_INPUT id={seg.nonce}>"
        assert body.count(open_delim) == 1
        assert body.count(close_delim) == 1
    # (v) no two segments share a nonce.
    nonces_seen = [seg.nonce for seg in captured]
    assert len(nonces_seen) == len(set(nonces_seen))


def test_untrusted_payload_never_appears_outside_fenced_segment(tmp_path: Path) -> None:
    """AC-7(i): each untrusted payload appears only inside a fenced segment.

    Removes every ``FencedSegment.content`` from the body; the remainder must
    contain none of the untrusted payloads.
    """
    log = EventLog(root=tmp_path, workflow_id=_wf())
    nonces = _det_nonces()
    captured: list[FencedSegment] = []

    @dataclass
    class _Capturer:
        inner: FenceWrapper

        def fence(self, payload: str, source_kind: SourceKind) -> FencedSegment:
            seg = self.inner.fence(payload, source_kind)
            captured.append(seg)
            return seg

    inner = FenceWrapper(scanner=CanaryGuard(), event_log=log, nonce_source=lambda: next(nonces))
    builder = PromptBuilder(fence=_Capturer(inner=inner), event_log=log)
    payloads = {
        "UNIQ-CVE-XYZ",
        "UNIQ-README-XYZ",
        "UNIQ-DEP1-XYZ",
        "UNIQ-SRC1-XYZ",
    }
    _, body = builder.build(
        skill="S",
        instruction_template="I",
        cve_description="UNIQ-CVE-XYZ",
        repo_readme="UNIQ-README-XYZ",
        transitive_dep_meta=["UNIQ-DEP1-XYZ"],
        source_snippets=["UNIQ-SRC1-XYZ"],
    )
    remainder = body
    for seg in captured:
        assert seg.content in remainder
        remainder = remainder.replace(seg.content, "", 1)
    for payload in payloads:
        assert payload not in remainder


# ---------------------------------------------------------------------------
# AC-8 — empty optional segments
# ---------------------------------------------------------------------------


def test_omitting_optional_segments_leaves_only_required(tmp_path: Path) -> None:
    """AC-8: ``None`` / empty optionals → body holds only ``cve`` + ``readme`` segments."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    nonces = _det_nonces()
    captured: list[FencedSegment] = []

    @dataclass
    class _Capturer:
        inner: FenceWrapper

        def fence(self, payload: str, source_kind: SourceKind) -> FencedSegment:
            seg = self.inner.fence(payload, source_kind)
            captured.append(seg)
            return seg

    inner = FenceWrapper(scanner=CanaryGuard(), event_log=log, nonce_source=lambda: next(nonces))
    builder = PromptBuilder(fence=_Capturer(inner=inner), event_log=log)
    builder.build(
        skill="S",
        instruction_template="I",
        cve_description="cve",
        repo_readme="readme",
        transitive_dep_meta=[],
        source_snippets=[],
        # rag_few_shots default (), prior_attempt_summary=None, sandbox_stderr=None
    )
    assert [seg.source_kind for seg in captured] == ["cve_description", "repo_readme"]
    assembled = [e for e in log.replay() if isinstance(e, PromptAssembled)]
    assert len(assembled) == 1
    assert assembled[0].source_kinds_used == ("cve_description", "repo_readme")
    assert assembled[0].segment_count == 2


# ---------------------------------------------------------------------------
# AC-10 — PromptAssembled event
# ---------------------------------------------------------------------------


def test_prompt_assembled_event_emitted_once_with_shape_only_payload(
    tmp_path: Path,
) -> None:
    """AC-10: exactly one ``PromptAssembled`` per ``build()``; payload is shape-only."""
    builder, log = _make_builder(tmp_path)
    system, body = builder.build(
        skill="SKILL-X",
        instruction_template="INSTR-X",
        cve_description="cve",
        repo_readme="readme",
        transitive_dep_meta=["a"],
        source_snippets=[],
    )
    assembled = [e for e in log.replay() if isinstance(e, PromptAssembled)]
    assert len(assembled) == 1
    event = assembled[0]
    assert event.event_type == "prompt_assembled"
    assert event.segment_count == 3
    assert event.source_kinds_used == (
        "cve_description",
        "repo_readme",
        "transitive_dep_meta",
    )
    assert event.system_prompt_byte_length == len(system.encode("utf-8"))
    assert event.fenced_body_byte_length == len(body.encode("utf-8"))
    # AC-10: no prompt content / digest fields on the event.
    field_names = set(type(event).model_fields)
    assert "system_prompt" not in field_names
    assert "fenced_body" not in field_names
    assert "prompt_digest" not in field_names
    assert "system_prompt_digest" not in field_names


def test_prompt_assembled_event_is_frozen_extra_forbid() -> None:
    """AC-11 frozen / extra=forbid invariant for ``PromptAssembled``."""
    from pydantic import ValidationError

    from codegenie.types.identifiers import EventId

    event = PromptAssembled(
        event_id=EventId("01HPRBASSEMBLE0000000000000000"),
        workflow_id=_wf(),
        timestamp=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        segment_count=1,
        source_kinds_used=("cve_description",),
        system_prompt_byte_length=10,
        fenced_body_byte_length=20,
    )
    with pytest.raises(ValidationError):
        event.segment_count = 99  # type: ignore[misc]
    with pytest.raises(ValidationError):
        PromptAssembled(
            event_id=EventId("01HPRBASSEMBLE0000000000000001"),
            workflow_id=_wf(),
            timestamp=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            segment_count=1,
            source_kinds_used=("cve_description",),
            system_prompt_byte_length=10,
            fenced_body_byte_length=20,
            bogus="x",  # type: ignore[call-arg]
        )


def test_returned_types_are_runtime_strings(tmp_path: Path) -> None:
    """NewTypes erase at runtime — the returned pair is ``(str, str)``."""
    builder, _ = _make_builder(tmp_path)
    out = builder.build(
        skill="s",
        instruction_template="i",
        cve_description="c",
        repo_readme="r",
        transitive_dep_meta=[],
        source_snippets=[],
    )
    assert isinstance(out, tuple)
    assert len(out) == 2
    system, body = out
    assert isinstance(system, str)
    assert isinstance(body, str)
