# Story S1-03 — Add `HumanRequest` and `HumanDecision` HITL contracts

**Step:** Step 1 — Scaffold `graph/` package, ship `VulnLedger` + HITL contracts + structural CI gates
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0008

## Context
`HumanRequest` and `HumanDecision` are the typed payloads that flow through LangGraph's `interrupt()` / `aupdate_state(..., as_node="await_human")` resume dance. They are the **task-class-agnostic contract** that Phase 7 (distroless), Phase 11 (real PR HITL signal source), and Phase 16 (multi-tenant auth) all consume or amend. Ship them as `frozen=True, extra="forbid"` Pydantic models with `HumanDecision.action` as a strict three-Literal Union — the minimal stable surface that ADR-0008 commits Phase 6 to.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Component 6 — HumanRequest / HumanDecision / await_human` (lines 767–816) — exact field shapes, max-length constraints, action Literal.
  - `../phase-arch-design.md §Data model — Contracts` (lines 951–970) — the model bodies in pseudo-code, including the comment "Phase 11 consumes or amends."
  - `../phase-arch-design.md §Edge cases #7` — malformed `HumanDecision(action="approve")` is the canonical adversarial input the contract rejects.
- **Phase ADRs:**
  - `../ADRs/0008-hitl-operator-auth-deferred-to-phase11.md` — ADR-0008 — explicit decision to ship typed contracts with no Ed25519/HMAC; the `note` field is plain text and **never** flowed into LLM prompts.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — "humans always merge" is the production commitment this contract serves.
- **Source design:**
  - `../final-design.md §Component 7 "HITL contract"` and `§Synthesis ledger row 6 "HITL resume authentication"`.

## Goal
Land `src/codegenie/graph/hitl.py` with both `HumanRequest` and `HumanDecision` as frozen Pydantic models so Phase 6's HITL surface is type-validated end-to-end and locked against silent shape drift.

## Acceptance criteria
- [ ] `src/codegenie/graph/hitl.py` defines `HumanRequest` and `HumanDecision`, both with `model_config = ConfigDict(extra="forbid", frozen=True)`.
- [ ] `HumanRequest` carries `reason: Literal["retry_exhausted", "non_retryable_signal"]`, `summary: str = Field(max_length=4096)`, `evidence_paths: dict[str, Path]`, `failing_signals: list[str]`, `chain_head_at_pause: bytes`, `requested_at: datetime`.
- [ ] `HumanDecision` carries `action: Literal["continue", "override", "abort"]`, `operator: str`, `decided_at: datetime`, `note: str = Field(default="", max_length=1024)`.
- [ ] `HumanDecision(action="approve")` raises `ValidationError` (the Phase 6 adversarial canary).
- [ ] `HumanDecision(action="continue", operator="alice", decided_at=...)` is frozen — attempting `decision.action = "abort"` raises (Pydantic v2 frozen semantics).
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/graph/hitl.py`, and `pytest tests/graph/test_hitl.py` all pass.

## Implementation outline
1. Read ADR-0008 in full; confirm the three-action Literal and the absence of any `signature`/`hmac` field.
2. Author `tests/graph/test_hitl.py` red tests covering: malformed action, extra=forbid, frozen-instance mutation, `note` default empty string, `note` max-length enforcement.
3. Write the two models in `hitl.py` per arch §Component 6.
4. Confirm Pydantic v2 frozen-model behavior — attribute assignment raises `ValidationError` (not `FrozenInstanceError` — different from `dataclasses.frozen`).
5. Export `HumanRequest`, `HumanDecision` via `__all__`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/graph/test_hitl.py`

```python
def test_human_decision_rejects_unknown_action() -> None:
    # arrange + act + assert: action="approve" is not in the Literal set
    with pytest.raises(ValidationError) as exc:
        HumanDecision(
            action="approve",  # type: ignore[arg-type]  # deliberately wrong
            operator="alice",
            decided_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
        )
    # error message names the offending field and the allowed values
    msg = str(exc.value)
    assert "action" in msg
    assert "continue" in msg and "override" in msg and "abort" in msg


def test_human_decision_is_frozen() -> None:
    # arrange: a valid HumanDecision
    d = HumanDecision(
        action="continue",
        operator="alice",
        decided_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
    )
    # act + assert: assignment raises (Pydantic v2 frozen)
    with pytest.raises(ValidationError):
        d.action = "abort"  # type: ignore[misc]


def test_human_decision_rejects_extra_field() -> None:
    # arrange + act + assert: extra="forbid" enforced
    with pytest.raises(ValidationError):
        HumanDecision.model_validate({
            "action": "continue",
            "operator": "alice",
            "decided_at": "2026-05-12T00:00:00Z",
            "signature": b"forged",  # Phase 11 may add this; Phase 6 rejects
        })


def test_human_request_summary_max_length_4096() -> None:
    # arrange + act + assert: 4097-char summary raises
    with pytest.raises(ValidationError):
        HumanRequest(
            reason="retry_exhausted",
            summary="x" * 4097,
            evidence_paths={},
            failing_signals=[],
            chain_head_at_pause=b"",
            requested_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
        )


def test_human_decision_note_defaults_to_empty_and_caps_at_1024() -> None:
    # arrange: minimal valid decision (no note)
    d = HumanDecision(
        action="continue",
        operator="alice",
        decided_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
    )
    # assert: note defaulted to ""
    assert d.note == ""
    # act + assert: 1025-char note raises
    with pytest.raises(ValidationError):
        HumanDecision(
            action="continue",
            operator="alice",
            decided_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
            note="x" * 1025,
        )
```

### Green — make it pass
Two `BaseModel` subclasses with `ConfigDict(extra="forbid", frozen=True)`. Add the two `Literal` types, the two `Field(max_length=...)` constraints. No methods, no validators beyond what Pydantic emits from the field declarations.

### Refactor — clean up
- Module docstring: cite ADR-0008 by filename; restate that this contract is exported to `docs/contracts/hitl-v0.6.0.json` (export ships in S7-05).
- Add an inline comment above `HumanDecision.note` explaining why it is plain text — `test_hitl_note_not_in_prompt.py` (S4-05) is the structural enforcement; this comment is the rationale.
- Add `__all__ = ["HumanRequest", "HumanDecision"]` for clean `from codegenie.graph.hitl import *` (used only in tests).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/graph/hitl.py` | Define the two contract models. |
| `tests/graph/test_hitl.py` | Red tests: malformed action, frozen, extra=forbid, max-length, note default. |

## Out of scope
- **`HumanDecision.signature`** — Phase 11's territory per ADR-0008; additive extension when it lands.
- **HITL contract JSON export to `docs/contracts/hitl-v0.6.0.json`** — owned by S7-05.
- **`await_human` node** — owned by S4-08; this story lands only the data shapes.
- **`test_hitl_note_not_in_prompt.py`** — instrumentation test owned by S4-05; the `note` plain-text invariant is structural, not contractual.
- **Operator authentication, HMAC, Ed25519** — Phase 11 / Phase 16 per ADR-0008.

## Notes for the implementer
- **Pydantic v2 frozen semantics differ from dataclasses.** Setting an attribute on a frozen `BaseModel` raises `ValidationError`, not `FrozenInstanceError`. The test must expect `ValidationError`. If the project pins an older Pydantic where this differs, surface the discrepancy via the dep file rather than weakening the test.
- **`Literal["continue", "override", "abort"]` ordering** is the order shown in arch §Component 6 — keep it consistent across `HumanDecision.action`, `route_after_human` (S3-02), and the test error-message assertion above.
- **`evidence_paths: dict[str, Path]`** — keys are short identifiers (e.g., `"sandbox_log"`, `"diff"`), values are `Path` instances. Pydantic serializes `Path` to `str` in JSON mode; the JSON-roundtrip test will need a `mode="json"` dump.
- **`chain_head_at_pause: bytes`** — same warning as `chain_head` in `VulnLedger`: JSON-mode serialization base64-encodes; verify round-trip if you add a serialization test (this story's scope is just construction-and-validation; round-trip is implied by S1-02's roundtrip test once the field is referenced).
- ADR-0008's "the `note` field is plain text and never flowed into LLM prompts" is the load-bearing invariant — there is no test for it in this story (the enforcement test is S4-05), but the module-level comment must record the rule so any future PR author cannot say "I didn't know."
- Do **not** add a `__post_init_post_parse__` or a `model_validator` that does cross-field validation here. The contract is intentionally simple to maximize Phase 11's chance of consuming it unchanged.
