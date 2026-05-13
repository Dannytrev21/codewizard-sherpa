# Story S1-02 — Add `VulnLedger` Pydantic model

**Step:** Step 1 — Scaffold `graph/` package, ship `VulnLedger` + HITL contracts + structural CI gates
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0002, ADR-0005

## Context
`VulnLedger` is the single Pydantic-typed state contract every node reads from and writes to (`phase-arch-design.md §Component 1`). It is the data contract every later story in Phase 6 — checkpointer, edges, nodes, CLI — anchors on. Ship it with `extra="forbid"`, `frozen=False`, a static `schema_version: Literal["v0.6.0"]`, all 18 fields enumerated by the arch design, and a committed round-trip golden fixture so any accidental field rename / removal in any future PR breaks loudly at CI time.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Component 1 — VulnLedger` (lines 513–561) — exact field list, configs, performance envelope.
  - `../phase-arch-design.md §Data model — Contracts` (lines 906–950) — reads/writes annotations as prose comments (NOT enforced — ADR-0012).
  - `../phase-arch-design.md §Edge cases #8` — `state.events.append(e)` is the canonical in-place-mutation case ADR-0002 catches; this story makes the field shape compatible with that hook.
- **Phase ADRs:**
  - `../ADRs/0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md` — ADR-0002 — sets `frozen=False` + `extra="forbid"`; this story implements the model side of that decision.
  - `../ADRs/0005-static-schema-version-literal-pin.md` — ADR-0005 — `schema_version: Literal["v0.6.0"]` exactly; not `blake3(model_json_schema())`.
- **Production ADRs:**
  - `../../../production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md` — "use LangGraph's mature tooling for free" is the reason `frozen=False`.
- **Source design:**
  - `../final-design.md §Synthesis ledger row 1 "frozen on state ledger"` and `row 10 "schema_version encoding"`.
- **Existing code:**
  - `src/codegenie/recipes/` / Phase 3 — find `AdvisoryRef`, `RecipeSelection`, `PatchRef`, `RemediationReport` (import as **types only**; this story must not invoke any Phase 3 behavior).
  - `src/codegenie/planner/rag/` / Phase 4 — find `RagHit`.
  - `src/codegenie/gates/` / Phase 5 — find `AttemptSummary`, `GateOutcome`.

## Goal
Land `src/codegenie/graph/state.py` with the complete `VulnLedger` Pydantic model and a committed JSON-roundtrip golden fixture so the contract is validated, schema-pinned, and protected against accidental shape changes.

## Acceptance criteria
- [ ] `src/codegenie/graph/state.py` defines `VulnLedger(BaseModel)` with `model_config = ConfigDict(extra="forbid", frozen=False)`, all 18 fields per arch §Component 1, every field type concrete (no `Any`, no `dict[str, Any]`, no `Mapping`).
- [ ] `schema_version` is annotated `Literal["v0.6.0"]` — exact spelling — and any construction with another value raises `ValidationError`.
- [ ] `VulnLedger.model_validate(known_good_json)` round-trips byte-identical through `model_dump_json(by_alias=True, exclude_none=False)` after canonicalization (sorted keys); the comparison test pins the rule.
- [ ] `VulnLedger.model_validate({"unknown_field": "x", ...})` raises `ValidationError` (extra=forbid enforced) — explicit test.
- [ ] `tests/fixtures/checkpoints/v0.6.0/minimal_ledger.json` is committed; round-trip test loads it, validates, dumps, and compares canonical bytes.
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/graph/state.py`, and `pytest tests/graph/test_state.py` all pass.

## Implementation outline
1. Read the existing Phase 3/4/5 type definitions; confirm each is `BaseModel`-derived and JSON-serializable end-to-end. Surface any non-JSON-native field (e.g., `Path`, `bytes`, `set`) as a Step-1 risk before writing `state.py`.
2. Define `VulnLedger` per arch §Component 1: identity (5 fields), routing (2), work-in-progress (4), gate outcome (4), HITL (2), audit (2) — count them to 18.
3. Author `tests/fixtures/checkpoints/v0.6.0/minimal_ledger.json` by hand: a valid minimum-field instance (only required fields populated; `None` for all optional fields; `prior_attempts=[]`, `events=[]`).
4. Write the failing tests (round-trip, extra=forbid, schema_version literal enforcement, mutable-list-is-truly-list).
5. Make tests green by adding the model. Add `Field(default_factory=list)` where the arch design specifies.
6. Add module-level `__all__` exporting only `VulnLedger`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/graph/test_state.py`

```python
def test_vuln_ledger_round_trip_byte_identical() -> None:
    # arrange: load the committed v0.6.0 fixture
    fixture = (REPO_ROOT / "tests/fixtures/checkpoints/v0.6.0/minimal_ledger.json").read_text()
    # act: validate then dump
    ledger = VulnLedger.model_validate_json(fixture)
    dumped = ledger.model_dump_json(by_alias=True, exclude_none=False)
    # assert: canonical-json round-trip is byte-identical (sorted-key compare)
    assert _canonical(json.loads(dumped)) == _canonical(json.loads(fixture))


def test_vuln_ledger_rejects_unknown_field() -> None:
    # arrange: minimal valid blob + one extra key
    payload = json.loads((REPO_ROOT / "tests/fixtures/checkpoints/v0.6.0/minimal_ledger.json").read_text())
    payload["sneaky_field"] = "should be rejected"
    # act + assert
    with pytest.raises(ValidationError) as exc:
        VulnLedger.model_validate(payload)
    assert "sneaky_field" in str(exc.value)
    assert "extra" in str(exc.value).lower()


def test_vuln_ledger_schema_version_is_literal_v060() -> None:
    # arrange + act + assert: assigning v0.5.x or v0.7.x is rejected at construction
    payload = json.loads((REPO_ROOT / "tests/fixtures/checkpoints/v0.6.0/minimal_ledger.json").read_text())
    payload["schema_version"] = "v0.5.99"
    with pytest.raises(ValidationError):
        VulnLedger.model_validate(payload)


def test_vuln_ledger_no_any_or_untyped_dict_in_fields() -> None:
    # arrange: introspect __fields__ (or model_fields in v2)
    # act: gather annotations
    # assert: none of the field annotations are typing.Any or dict[str, Any]
    # — closes ADR-0005 "no Any" CI gate
    ...
```

### Green — make it pass
Define the model. The minimum to pass:
- Class body listing all 18 fields with types per arch §Component 1.
- `model_config = ConfigDict(extra="forbid", frozen=False)`.
- `Field(default_factory=list)` for `prior_attempts` and `events`.
- A hand-authored `minimal_ledger.json` whose `prior_attempts`/`events` are empty lists, `last_engine`/`recipe_selection`/`rag_hit`/`patch`/`current_gate_id`/`last_outcome`/`human_request`/`human_decision` are `null`, `chain_head` is `""` (base64 of zero bytes).

### Refactor — clean up
- Add `Reads:` / `Writes:` prose comments per arch §Data model — explicitly note in a class-level docstring that these are documentation only (ADR-0012 — they are **not** enforced).
- Confirm `model_dump_json` ordering is stable across Pydantic minor bumps by adding a canonical-json helper in `tests/graph/_canonical.py` (sort keys recursively, `separators=(",", ":")`).
- Pin import order: stdlib → third-party (`pydantic`) → Phase 3/4/5 types. Per project convention.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/graph/state.py` | Define `VulnLedger`. |
| `tests/graph/test_state.py` | Round-trip, extra=forbid, schema-version-literal, no-Any introspection tests. |
| `tests/fixtures/checkpoints/v0.6.0/minimal_ledger.json` | Hand-authored golden round-trip blob. |
| `tests/graph/_canonical.py` (or similar) | Canonical-JSON helper for byte-identical compares. |

## Out of scope
- **`HumanRequest` / `HumanDecision`** — owned by S1-03. The `human_request: HumanRequest | None` annotation in `VulnLedger` is a forward reference resolved when S1-03 lands `hitl.py`.
- **`GraphEvent`** — owned by S1-04. The `events: list[GraphEvent]` annotation is forward-referenced.
- **Runtime in-place-mutation hook** — owned by S1-04 (`hooks.py`).
- **Layer-0 introspection tests** (`test_no_self_confidence_in_loopstate.py`, `test_pydantic_no_any.py`) — owned by S1-05; this story just makes the model conform.
- **Migration registry** — empty per ADR-0005; the `migrations/__init__.py` from S1-01 is sufficient.

## Notes for the implementer
- **Forward references are unavoidable**: `GraphEvent` and `HumanRequest`/`HumanDecision` types are owned by later stories in this same Step 1. Use `from __future__ import annotations` and stub imports under `if TYPE_CHECKING:` so this story can land independently of S1-03/S1-04 wall-clock ordering. Resolve the forward refs with `VulnLedger.model_rebuild()` once those modules exist — but that call lives in `__init__.py`, not here.
- **`Path` and `bytes` are not JSON-native.** Pydantic v2 serializes `Path` as a string and `bytes` as base64 by default with `mode="json"`, but `model_dump_json` uses the JSON codec. Verify round-trip explicitly for `repo_path` (`Path`) and `chain_head` (`bytes`) — these are the two fields most likely to trip up a careless `model_dump_json`.
- **`schema_version` is a `Literal`, not a `Field` with a default.** Pydantic v2 requires `Literal["v0.6.0"]` to be the type annotation. Some implementations want `= "v0.6.0"` as well to make it optional at construction; arch §Component 1 leaves this implementation detail open — pick one and document the choice in the test.
- **`prior_attempts` and `events` are `list[...]`** — these are the two fields ADR-0002's runtime hook watches via `_MUTABLE_FIELDS`. Do not switch them to `tuple[...]` "for safety" — that breaks the hook contract.
- **`chain_head: bytes`** is the BLAKE3 digest carried from Phase 5; arch §Data model line 946 names `RetryLedger.head_from_phase5(...)` as its source. Phase 5's actual accessor may not yet be public (Gap 2 of the arch design). Leave the field type as `bytes` regardless — the producer wiring is Step 2's problem.
- **`extra="forbid"` is the only place "no schema drift" is structurally enforced** before the checkpointer lands. Make the unknown-field test pin both the *raise* and the *which field* — fail loud, per CLAUDE.md Rule 12.
