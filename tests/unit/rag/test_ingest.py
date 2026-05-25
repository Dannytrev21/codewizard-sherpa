"""Phase-4 S4-06 — ``ingest_solved_example`` + ``ValidatedPlanOutcome``
+ ``_solved_example_id_for`` unit tests.

Covers the writer-side ACs S4-06 hardens:

- AC-1 — ``ValidatedPlanOutcome`` frozen, extra-forbid, exact field shape.
- AC-2 — ``ingest_solved_example`` keyword-only signature; exactly one
  ``embedder.model_digest()`` call, exactly one ``embedder.embed(...)``
  call, exactly one ``store.add(example, capability)`` call; returns the
  ``SolvedExampleId`` the store returned; **does not** instantiate
  ``EventLog`` or call ``emit_internal``; **does not** read
  ``TrustOutcome.confidence`` (the outcome projection carries none).
- AC-3 — ``_solved_example_id_for`` is deterministic over the five
  identity fields (``cve_id``, ``advisory_digest``, ``transform_digest``,
  ``trust_outcome_digest``, ``embedding_model``); excludes
  ``workflow_id``, ``chain_head``, ``created_at``, ``query_text``,
  ``response_id``.
- AC-4 — AST/source guard against stale S1-04 ``RecordProvenance`` field
  names ever leaking back into ``ingest.py``.
- AC-8 — a hand-forged ``SolvedExampleWriteCapability`` is accepted
  in-process (documented intentional Module-Boundary-not-runtime-cap
  limitation).
- AC-10 — writer never reaches ``EventLog`` / ``emit_internal``.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import pytest
from pydantic import ValidationError

from codegenie.fallback.plan_proposal import PlanProposalDepBump
from codegenie.rag.ingest import (
    ValidatedPlanOutcome,
    _solved_example_id_for,
    ingest_solved_example,
)
from codegenie.rag.store import SolvedExampleWriteCapability
from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    CveId,
    EmbeddingVector,
    Language,
    LeafResponseId,
    ModelId,
    PackageId,
    SemverVersion,
    SolvedExampleId,
    TaskClassId,
    WorkflowId,
)

# ---------------------------------------------------------------------------
# Helpers — minimal deterministic ValidatedPlanOutcome + fakes
# ---------------------------------------------------------------------------


_VECTOR_LEN: Final[int] = 384


def _plan_proposal() -> PlanProposalDepBump:
    return PlanProposalDepBump(
        manifest_path="package.json",  # type: ignore[arg-type]
        package=PackageId("left-pad"),
        target_version=SemverVersion("1.3.0"),
        rationale="bump left-pad past advisory range",
    )


def _outcome(
    *,
    cve_id: str = "CVE-2024-0001",
    transform_digest: str = "a" * 64,
    trust_outcome_digest: str = "b" * 64,
    advisory_digest: str = "c" * 64,
    chain_head: str = "d" * 64,
    response_id: str = "01HRES000000000000000000RES",
    query_text: str = "left-pad RCE in 1.2.3",
) -> ValidatedPlanOutcome:
    return ValidatedPlanOutcome(
        query_text=query_text,
        plan_proposal=_plan_proposal(),
        transform_digest=BlobDigest(transform_digest),
        trust_outcome_digest=BlobDigest(trust_outcome_digest),
        task_class=TaskClassId("vuln_remediation"),
        language=Language("javascript"),
        build_system="npm",
        cve_id=CveId(cve_id),
        advisory_digest=BlobDigest(advisory_digest),
        response_id=LeafResponseId(response_id),
        chain_head=ChainHead(chain_head),
    )


def _vector() -> EmbeddingVector:
    return EmbeddingVector(tuple(float(i) / 384.0 for i in range(_VECTOR_LEN)))


def _capability() -> SolvedExampleWriteCapability:
    return SolvedExampleWriteCapability(workflow_id=WorkflowId("01HWF00000000000000000WFLOW"))


def _model_digest() -> BlobDigest:
    return BlobDigest("9" * 64)


class _RecordingEmbedder:
    """Counts ``embed`` / ``model_digest`` calls so AC-2's "exactly once"
    contract is mechanically asserted."""

    def __init__(self, vec: EmbeddingVector) -> None:
        self._vec = vec
        self.embed_calls: list[str] = []
        self.digest_calls = 0

    def embed(self, text: str) -> EmbeddingVector:
        self.embed_calls.append(text)
        return self._vec

    def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
        return [self._vec for _ in texts]

    def model_digest(self) -> BlobDigest:
        self.digest_calls += 1
        return _model_digest()


class _RecordingStore:
    """Single-method fake that records the ``add()`` payload + returns the
    example's id verbatim (chromadb's behavior on success)."""

    def __init__(self) -> None:
        self.adds: list[tuple[Any, SolvedExampleWriteCapability]] = []

    async def add(self, example: Any, capability: SolvedExampleWriteCapability) -> SolvedExampleId:
        self.adds.append((example, capability))
        return SolvedExampleId(example.id)


# ---------------------------------------------------------------------------
# AC-1 — ValidatedPlanOutcome shape
# ---------------------------------------------------------------------------


def test_validated_plan_outcome_is_frozen_extra_forbid() -> None:
    """AC-1: ``ValidatedPlanOutcome`` rejects mutation and unknown keys."""
    outcome = _outcome()
    with pytest.raises(ValidationError):
        outcome.query_text = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ValidatedPlanOutcome(
            query_text="x",
            plan_proposal=_plan_proposal(),
            transform_digest=BlobDigest("a" * 64),
            trust_outcome_digest=BlobDigest("b" * 64),
            task_class=TaskClassId("t"),
            language=Language("javascript"),
            build_system="npm",
            cve_id=CveId("CVE-2024-0001"),
            advisory_digest=BlobDigest("c" * 64),
            response_id=LeafResponseId("01HX"),
            chain_head=ChainHead("d" * 64),
            bogus="x",  # type: ignore[call-arg]
        )


def test_validated_plan_outcome_carries_every_required_field() -> None:
    """AC-1: the 11 fields S4-06 names are all present and typed.

    Without this, a future "tidy" edit could drop ``advisory_digest`` or
    silently widen one of the typed fields to ``Any``.
    """
    expected: set[str] = {
        "query_text",
        "plan_proposal",
        "transform_digest",
        "trust_outcome_digest",
        "task_class",
        "language",
        "build_system",
        "cve_id",
        "advisory_digest",
        "response_id",
        "chain_head",
    }
    assert set(ValidatedPlanOutcome.model_fields) == expected


def test_validated_plan_outcome_has_no_dict_any_escape_hatch() -> None:
    """AC-1: no field is a ``dict[str, Any]``-shaped escape hatch."""
    for field_name, field_info in ValidatedPlanOutcome.model_fields.items():
        annotation = field_info.annotation
        rendered = repr(annotation)
        assert "Any" not in rendered, f"ValidatedPlanOutcome.{field_name!r} leaks Any: {rendered}"


def test_validated_plan_outcome_uses_no_stale_name_aliases() -> None:
    """AC-1: stale type names ``TaskClassName`` / ``LanguageName`` /
    ``BuildSystemName`` never appear in ``ingest.py`` source.

    The S1-04 hardening renamed these to ``TaskClassId`` / ``Language`` /
    ``PackageManager``; a silent revert would re-fork the kernel.
    """
    src = (Path(__file__).resolve().parents[3] / "src/codegenie/rag/ingest.py").read_text(
        encoding="utf-8"
    )
    for stale in ("TaskClassName", "LanguageName", "BuildSystemName"):
        assert stale not in src, f"stale identifier {stale!r} present in rag/ingest.py"


# ---------------------------------------------------------------------------
# AC-2 — ingest_solved_example signature + behavior
# ---------------------------------------------------------------------------


def test_ingest_solved_example_signature_is_keyword_only() -> None:
    """AC-2: every parameter is keyword-only and the four expected ones
    are present in exact name."""
    sig = inspect.signature(ingest_solved_example)
    params = sig.parameters
    assert set(params) == {"outcome", "store", "embedder", "capability"}
    for name, param in params.items():
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"parameter {name!r} must be keyword-only (got {param.kind})"
        )


async def test_ingest_calls_embedder_and_store_each_exactly_once() -> None:
    """AC-2: exactly one ``model_digest()`` + one ``embed()`` + one
    ``store.add(...)`` per call."""
    embedder = _RecordingEmbedder(_vector())
    store = _RecordingStore()
    outcome = _outcome()
    cap = _capability()

    sid = await ingest_solved_example(
        outcome=outcome, store=store, embedder=embedder, capability=cap
    )

    assert embedder.digest_calls == 1
    assert embedder.embed_calls == [outcome.query_text]
    assert len(store.adds) == 1
    persisted_example, persisted_cap = store.adds[0]
    assert persisted_cap is cap
    assert sid == persisted_example.id


async def test_ingest_builds_solved_example_with_exact_field_shape() -> None:
    """AC-2: every ``SolvedExample`` field carries the projected value
    from the outcome / embedder / capability; the four
    ``RecordProvenance`` fields are populated correctly."""
    embedder = _RecordingEmbedder(_vector())
    store = _RecordingStore()
    outcome = _outcome()
    cap = _capability()
    before = datetime.now(UTC)

    await ingest_solved_example(outcome=outcome, store=store, embedder=embedder, capability=cap)

    after = datetime.now(UTC)
    example, _ = store.adds[0]
    assert example.task_class == outcome.task_class
    assert example.language == outcome.language
    assert example.build_system == outcome.build_system
    assert example.cve_id == outcome.cve_id
    assert example.advisory_digest == outcome.advisory_digest
    assert example.plan_proposal == outcome.plan_proposal
    assert example.plan_kind == outcome.plan_proposal.kind
    assert example.transform_digest == outcome.transform_digest
    assert example.trust_outcome_digest == outcome.trust_outcome_digest
    assert example.embedding_model == ModelId(str(_model_digest()))
    assert tuple(example.embedding_vector) == tuple(_vector())
    assert example.origin == "llm_solved"

    prov = example.provenance
    assert prov.workflow_id == cap.workflow_id
    assert prov.event_chain_head == outcome.chain_head
    assert prov.signing_method == "hmac_sha256_chain"
    assert before <= prov.created_at <= after
    assert prov.created_at.tzinfo is not None  # AC-2: UTC-aware
    assert before <= example.created_at <= after


async def test_ingest_does_not_check_confidence_or_emit_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2 + AC-10: writer never touches ``EventLog.emit_internal`` and
    never references ``confidence`` on its inputs.

    The first assertion is the load-bearing one: any spy hit on
    ``emit_internal`` would mean the writer started gating + emitting
    instead of staying silent for S6-03.
    """
    import codegenie.plugins.events as ev_mod

    hits: list[str] = []

    def _explode(self: Any, event: Any) -> Any:  # noqa: ANN401
        hits.append(type(event).__name__)
        raise AssertionError("writer must not call EventLog.emit_internal — S6-03 owns emission")

    monkeypatch.setattr(ev_mod.EventLog, "emit_internal", _explode)

    embedder = _RecordingEmbedder(_vector())
    store = _RecordingStore()
    await ingest_solved_example(
        outcome=_outcome(), store=store, embedder=embedder, capability=_capability()
    )
    assert hits == []


def test_ingest_module_does_not_import_eventlog() -> None:
    """AC-10: ``ingest.py`` does not import ``EventLog`` /
    ``emit_internal`` / ``SolvedExampleHarvested``.

    AST-based (not substring) so a docstring referencing those names by
    way of explaining S6-03's responsibility does NOT trip the guard.
    The real risk is a real import / a real ``emit_internal`` call, both
    of which are AST-visible.
    """
    src = (Path(__file__).resolve().parents[3] / "src/codegenie/rag/ingest.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    forbidden_names: set[str] = {"EventLog", "emit_internal", "SolvedExampleHarvested"}
    leaks: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in forbidden_names:
                    leaks.append(f"import from {node.module!r}: {alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[-1] in forbidden_names:
                    leaks.append(f"import {alias.name}")
        elif isinstance(node, ast.Attribute):
            if node.attr in forbidden_names:
                leaks.append(f"attribute access: .{node.attr}")
        elif isinstance(node, ast.Name):
            if node.id in forbidden_names:
                leaks.append(f"name reference: {node.id}")
    assert not leaks, f"ingest.py contains forbidden runtime refs (S4-06 AC-10): {leaks}"


# ---------------------------------------------------------------------------
# AC-3 — deterministic id helper
# ---------------------------------------------------------------------------


def test_solved_example_id_is_deterministic() -> None:
    """AC-3: two calls with the same identity fields produce the same id."""
    outcome = _outcome()
    a = _solved_example_id_for(outcome=outcome, embedding_model=ModelId("m"))
    b = _solved_example_id_for(outcome=outcome, embedding_model=ModelId("m"))
    assert a == b


@pytest.mark.parametrize(
    "field_kwarg",
    [
        {"cve_id": "CVE-2099-9999"},
        {"transform_digest": "e" * 64},
        {"trust_outcome_digest": "f" * 64},
        {"advisory_digest": "9" * 64},
    ],
)
def test_solved_example_id_changes_with_identity_field(field_kwarg: dict[str, str]) -> None:
    """AC-3: mutating any one identity-set field changes the id."""
    base = _outcome()
    mutated = _outcome(**field_kwarg)
    a = _solved_example_id_for(outcome=base, embedding_model=ModelId("m"))
    b = _solved_example_id_for(outcome=mutated, embedding_model=ModelId("m"))
    assert a != b


def test_solved_example_id_changes_with_embedding_model() -> None:
    """AC-3: the embedding model is part of the identity (S5-03
    model-mismatch exclusion gets the right per-model id)."""
    outcome = _outcome()
    a = _solved_example_id_for(outcome=outcome, embedding_model=ModelId("m1"))
    b = _solved_example_id_for(outcome=outcome, embedding_model=ModelId("m2"))
    assert a != b


@pytest.mark.parametrize(
    "context_field_kwarg",
    [
        {"chain_head": "1" * 64},
        {"response_id": "01HOTHER0000000000000000000"},
        {"query_text": "different surface text"},
    ],
)
def test_solved_example_id_excludes_workflow_context_fields(
    context_field_kwarg: dict[str, str],
) -> None:
    """AC-3: workflow-context fields (``chain_head``, ``response_id``,
    ``query_text``) are intentionally NOT in the identity set; mutating
    them must NOT change the id."""
    base = _outcome()
    mutated = _outcome(**context_field_kwarg)
    a = _solved_example_id_for(outcome=base, embedding_model=ModelId("m"))
    b = _solved_example_id_for(outcome=mutated, embedding_model=ModelId("m"))
    assert a == b


# ---------------------------------------------------------------------------
# AC-4 — stale S1-04 ``RecordProvenance`` field guard
# ---------------------------------------------------------------------------


def test_ingest_py_does_not_use_stale_recordprovenance_fields() -> None:
    """AC-4: stale ``RecordProvenance`` constructor kwargs and stale
    attribute reads never appear in ``rag/ingest.py``.

    AST-based: only real attribute reads (``obj.<name>``) and constructor
    kwargs (``Foo(<name>=...)``) count. Docstring prose mentioning
    "confidence" or "model" in an explanation of S6-03 responsibility
    does NOT trip the guard — the runtime risk is a real silent kwarg
    leak, not the English word.
    """
    src = (Path(__file__).resolve().parents[3] / "src/codegenie/rag/ingest.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    stale: set[str] = {
        "record_chain_head",
        "model_id",
        "embedding_dim",
        "trust_outcome_passed",
        "confidence",
        "harvested_at",
        "solved_example_id",
    }
    leaks: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in stale:
            leaks.append(f"kwarg {node.arg!r}")
        elif isinstance(node, ast.Attribute) and node.attr in stale:
            leaks.append(f"attr .{node.attr}")
    assert not leaks, f"stale S1-04 RecordProvenance refs in ingest.py: {leaks}"


# ---------------------------------------------------------------------------
# AC-8 — forged-capability limitation is documented + asserted
# ---------------------------------------------------------------------------


async def test_hand_forged_capability_is_accepted_in_process() -> None:
    """AC-8: capability unforgeability is a lint/test enforced module
    boundary, not a runtime guarantee.

    This test PROVES the limitation rather than papering over it: a
    hand-built ``SolvedExampleWriteCapability`` (no mint involved) is
    accepted by ``ingest_solved_example`` and reaches ``store.add(...)``.
    If a future story adds runtime detection, surface per Rule 7 and
    update this docstring instead of silently flipping the assertion.
    """
    embedder = _RecordingEmbedder(_vector())
    store = _RecordingStore()
    forged = SolvedExampleWriteCapability(workflow_id=WorkflowId("hand-forged"))
    sid = await ingest_solved_example(
        outcome=_outcome(), store=store, embedder=embedder, capability=forged
    )
    assert len(store.adds) == 1
    _, persisted_cap = store.adds[0]
    assert persisted_cap is forged
    assert sid == store.adds[0][0].id
