# Story S5-01 — `DistrolessLedger`, `TargetImageRecommendation`, `MigrationReport` Pydantic models

**Step:** Step 5 — `DistrolessLedger`, `build_distroless_loop()`, `cli/migrate.py`, and Node.js Express E2E
**Status:** Ready
**Effort:** M
**Depends on:** S3-06, S4-03
**ADRs honored:** ADR-P7-001 (parallel `DistrolessLedger` sibling to `VulnLedger`, no shared base), ADR-P7-006 (`Recipe.engine` Literal extension — referenced in `last_engine` field), Phase 6 ADR-0002 (frozen=False + runtime mutation hook reused verbatim), Phase 6 ADR-0005 (static `schema_version` `Literal` pin — no `blake3(model_json_schema())`)

## Context

This story ships the data contract every distroless-loop node reads from and writes to. It is the foundational state model that every later Step 5 story compiles against — the nodes (S5-02, S5-03), the factory (S5-04), the CLI (S5-05), the E2E test (S5-06), and the replay test (S5-08) all consume `DistrolessLedger` as their core type. Phase 8's supervisor (next phase) will `model_validate_json` both `VulnLedger` and `DistrolessLedger` to dispatch by `task_type`, so the `schema_version: Literal["v0.7.0"]` pin and `extra="forbid"` discipline are load-bearing for the cross-phase contract.

Per ADR-0011 the ledger is a *sibling* of `VulnLedger` — no shared base class, no premature abstraction. ADR-0022 ("Three Strikes And You Refactor") is invoked: vuln is strike one; distroless is strike two; the unification is deferred to Phase 8 or Phase 15 when a third subgraph reveals the right shape.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 6 — DistrolessLedger` (lines 627–681) — exact field list, configs, performance envelope, runtime mutation hook contract.
  - `../phase-arch-design.md §Data model — Contracts` (lines 900–1054) — `TargetImageRecommendation` and `DistrolessLedger` as persisted contracts; producer/consumer annotations as prose comments.
  - `../phase-arch-design.md §Data model — Persisted-on-disk shapes` — `MigrationReport` shape and the `migration-report.yaml` envelope.
  - `../phase-arch-design.md §Harness engineering — Idempotence` — the `id()`-diff hook contract Phase 6 owns; this story makes the new ledger compatible.
- **Phase ADRs:**
  - `../ADRs/0011-distroless-ledger-parallel-to-vuln-ledger.md` — ADR-P7-001 — sibling sibling discipline; no shared base; `last_engine` Literal values differ deliberately.
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006 — `"dockerfile"` is the new engine value; `last_engine` Literal here uses `"dockerfile_recipe"` (post-applied label), not `"dockerfile"` (recipe-engine label).
- **Production ADRs:**
  - `../../../production/adrs/0022-per-subgraph-topology.md` — Three Strikes; honor by *not* extracting a shared base.
- **Source design:**
  - `../final-design.md §Synthesis ledger row 15` — "parallel `DistrolessLedger`; Three Strikes deferred".
- **Existing code:**
  - `src/codegenie/graph/state.py` — the Phase 6 `VulnLedger`; mirror its field-by-field discipline. Read `model_config`, the runtime `id()`-diff hook wiring, and the `__all__` shape.
  - `src/codegenie/graph/hooks.py` (Phase 6) — `_MUTABLE_FIELDS` and the after-node `id()`-diff hook; reuse verbatim, no edits.
  - Phase 3 `RecipeSelection`, Phase 4 `RagHit`, Phase 5 `AttemptSummary`/`GateOutcome`, Phase 6 `HumanRequest`/`HumanDecision`/`GraphEvent`/`PatchRef` — import as **types only**.

## Goal

Land `src/codegenie/graph/state_distroless.py` with `DistrolessLedger`, `TargetImageRecommendation`, and `MigrationReport` Pydantic models — `extra="forbid"`, `schema_version: Literal["v0.7.0"]` pinned, the Phase 6 in-place-mutation hook firing on `events.append(...)`, and a Hypothesis serialization round-trip property green.

## Acceptance criteria

- [ ] `src/codegenie/graph/state_distroless.py` defines `DistrolessLedger(BaseModel)` with `model_config = ConfigDict(extra="forbid", frozen=False)`, every field per arch §Component 6 (identity, task input, routing, gate outcome, HITL, audit); types concrete (no `Any`, no `dict[str, Any]`).
- [ ] `schema_version` is annotated `Literal["v0.7.0"]` exactly; constructing with `"v0.6.0"` or `"v0.7.1"` raises `ValidationError`.
- [ ] `last_engine` is annotated `Literal["dockerfile_recipe", "rag", "phase4_llm"] | None = None` — deliberately *distinct* from `VulnLedger.last_engine`'s value set (`"recipe"|"rag"|"phase4_llm"`) per ADR-P7-001.
- [ ] `TargetImageRecommendation` is `frozen=True`, `extra="forbid"`, with `from_image`, `to_image`, `pinned_digest`, `cve_basis: list[str]`, `confidence_band: Literal["high","medium","low"]`, `resolved_at: datetime`, `catalog_row_age_h: int`.
- [ ] `MigrationReport` is `extra="forbid"`, schema mirrors arch §Data model persisted shape; consumable by Phase 11 (Handoff) and Phase 13 (cost ledger).
- [ ] `DistrolessLedger.model_validate({"unknown_field": "x", ...})` raises `ValidationError` with `"unknown_field"` in the message (extra=forbid).
- [ ] The Phase 6 in-place mutation hook fires when a `DistrolessLedger` node mutates `events.append(...)` or `prior_attempts.append(...)` — same `_MUTABLE_FIELDS` discipline; `LedgerMutatedInPlace` raises.
- [ ] Hypothesis property test `test_distroless_ledger_serialization_round_trip` (`tests/property/test_distroless_ledger_serialization.py`) — `DistrolessLedger.model_validate_json(ledger.model_dump_json()) == ledger` for ≥100 generated instances.
- [ ] `tests/fixtures/checkpoints/v0.7.0/minimal_distroless_ledger.json` is committed; round-trip test loads it, validates, dumps, and canonical-JSON-compares.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/graph/state_distroless.py`, and `pytest tests/graph/test_distroless_state.py tests/property/test_distroless_ledger_serialization.py` all pass.

## Implementation outline

1. Read Phase 6 `src/codegenie/graph/state.py` end-to-end; note field order, `ConfigDict` flags, `Field(default_factory=list)` usage, and forward-reference handling.
2. Define `TargetImageRecommendation` first (frozen contract, no list fields, smallest surface).
3. Define `DistrolessLedger` mirroring `VulnLedger`'s six field groups: identity (`schema_version`, `workflow_id`, `thread_id`, `repo_path`); task input (`target_image_recommendation`, `dockerfile_path`); routing (`recipe_selection`, `last_engine`, `rag_hit`, `patch`, `prior_attempts`); gate outcome (`current_gate_id`, `retry_count`, `max_attempts`, `last_outcome`); HITL (`human_request`, `human_decision`); audit (`chain_head: bytes`, `events: list[GraphEvent]`).
4. Define `MigrationReport` per the persisted shape in arch §Data model — schema-versioned, references `TargetImageRecommendation` and patch refs.
5. Hand-author `tests/fixtures/checkpoints/v0.7.0/minimal_distroless_ledger.json` — every optional field `null`, `prior_attempts=[]`, `events=[]`, `chain_head=""` (base64 zero bytes).
6. Wire the Phase 6 `_MUTABLE_FIELDS` hook for `events` and `prior_attempts` — re-export the hook function from `state_distroless.py` if the Phase 6 module exports a class-decorator; otherwise register at module load.
7. Write the failing tests in the order: extra=forbid → schema-version pin → round-trip golden → in-place mutation hook fires → Hypothesis property.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test files:
- `tests/graph/test_distroless_state.py` (unit)
- `tests/property/test_distroless_ledger_serialization.py` (Hypothesis property)

```python
# tests/graph/test_distroless_state.py
def test_distroless_ledger_round_trip_byte_identical() -> None:
    fixture = (REPO_ROOT / "tests/fixtures/checkpoints/v0.7.0/minimal_distroless_ledger.json").read_text()
    ledger = DistrolessLedger.model_validate_json(fixture)
    dumped = ledger.model_dump_json(by_alias=True, exclude_none=False)
    assert _canonical(json.loads(dumped)) == _canonical(json.loads(fixture))


def test_distroless_ledger_rejects_unknown_field() -> None:
    payload = json.loads((REPO_ROOT / "tests/fixtures/checkpoints/v0.7.0/minimal_distroless_ledger.json").read_text())
    payload["sneaky_field"] = "rejected"
    with pytest.raises(ValidationError) as exc:
        DistrolessLedger.model_validate(payload)
    assert "sneaky_field" in str(exc.value)


def test_distroless_ledger_schema_version_pinned_v070() -> None:
    payload = json.loads((REPO_ROOT / "tests/fixtures/checkpoints/v0.7.0/minimal_distroless_ledger.json").read_text())
    payload["schema_version"] = "v0.6.0"
    with pytest.raises(ValidationError):
        DistrolessLedger.model_validate(payload)


def test_last_engine_literal_distinct_from_vuln_ledger() -> None:
    """ADR-P7-001 — last_engine value sets differ deliberately between ledgers."""
    payload = _valid_payload()
    payload["last_engine"] = "recipe"  # this is vuln's value, not distroless's
    with pytest.raises(ValidationError):
        DistrolessLedger.model_validate(payload)
    payload["last_engine"] = "dockerfile_recipe"  # accepted
    assert DistrolessLedger.model_validate(payload).last_engine == "dockerfile_recipe"


def test_in_place_events_append_raises_ledger_mutated() -> None:
    """The Phase 6 id()-diff hook must fire when a node mutates events in-place."""
    ledger = DistrolessLedger.model_validate_json(_FIXTURE)
    pre_id = id(ledger.events)
    ledger.events.append(_make_graph_event())
    # The hook is invoked at after-node boundary, simulating that path:
    with pytest.raises(LedgerMutatedInPlace):
        _after_node_hook(prev=ledger, curr=ledger.model_copy())  # simulating same id() on events
```

```python
# tests/property/test_distroless_ledger_serialization.py
@given(distroless_ledger_strategy())  # Hypothesis builder
def test_distroless_ledger_json_round_trip_property(ledger: DistrolessLedger) -> None:
    """G14-adjacent: serialize → deserialize is identity for every shape."""
    rebuilt = DistrolessLedger.model_validate_json(ledger.model_dump_json())
    assert rebuilt == ledger
```

Run each test; confirm all fail (ImportError or AttributeError). Commit the red tests.

### Green — make it pass

Author `src/codegenie/graph/state_distroless.py` with the three models defined verbatim per arch §Component 6 + §Data model. Use `from __future__ import annotations` for forward references to `GraphEvent` etc.; resolve via `DistrolessLedger.model_rebuild()` at module bottom or in `graph/__init__.py`. Add `_MUTABLE_FIELDS = ("events", "prior_attempts")` and reuse Phase 6's `_after_node_hook` function — do not copy-paste.

### Refactor — clean up

- Add per-class docstrings naming Producer/Consumer (prose comments — not enforced; documentation only per Phase 6 ADR-0012).
- Add canonical-JSON helper reuse (`from tests.graph._canonical import canonical_json` — already shipped by Phase 6).
- Confirm `model_dump_json` ordering is stable across Pydantic minor bumps (canonical helper guards this).
- Per arch §Edge cases #11, the new Pydantic schemas drift the contract surface — this story regenerates `tools/contract-surface.snapshot.json` *only if no upstream change is detected*; the actual snapshot regen for this addition is owned by S1-07 (Phase 7 initial snapshot) and the addition is named in ADR-P7-001. Do not re-run `--update-contract-snapshot` here.
- Confirm no `random` / no `time` import (fence-CI under `graph/`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/graph/state_distroless.py` | Define `TargetImageRecommendation`, `DistrolessLedger`, `MigrationReport`. NEW file. |
| `tests/graph/test_distroless_state.py` | Unit tests — extra=forbid, schema-version pin, `last_engine` Literal, mutation hook. |
| `tests/property/test_distroless_ledger_serialization.py` | Hypothesis JSON round-trip property. |
| `tests/fixtures/checkpoints/v0.7.0/minimal_distroless_ledger.json` | Hand-authored golden round-trip blob. |
| `src/codegenie/graph/__init__.py` | Export `DistrolessLedger`, `TargetImageRecommendation`, `MigrationReport` from the package. |

## Out of scope

- **`build_distroless_loop()` factory** — handled by S5-04.
- **Distroless graph nodes** — handled by S5-02 (gather half) and S5-03 (execute half).
- **`migration-report.yaml` writer** — `emit_artifact` node owns the serialization; S5-03 wires it.
- **`workflow_id = blake3(...|wf:distroless:...)[:16]` derivation** — handled by `cli/migrate.py` (S5-05).
- **Audit-chain seeding (`chain_head=RetryLedger.head_from_phase5(...)`)** — wired by `cli/migrate.py` (S5-05); this story only types the field.
- **Phase 6 mutation hook itself** — owned by Phase 6 S1-04; this story consumes it, does not redefine.

## Notes for the implementer

- **`schema_version` is `Literal["v0.7.0"]`, not `"v0.7.x"`.** Phase 8's supervisor parses both ledger types by this exact pin; bumping to `v0.7.1` would require a Phase 8 ADR. Keep the Literal frozen for the entire Phase 7 lifetime.
- **`last_engine` Literal divergence from `VulnLedger` is deliberate** (`"dockerfile_recipe"` vs `"recipe"`). Per ADR-P7-001 / `phase-arch-design.md §Acknowledged debt`, Phase 8 sees the divergence as a *signal* about ledger merging — do not "fix" it by aligning the values.
- **`chain_head: bytes`** is base64-encoded in JSON via Pydantic's default codec. The minimal fixture uses `""` (empty bytes); the real seed comes from `RetryLedger.head_from_phase5(...)` and is wired by S5-05. Do not hardcode a non-empty value here.
- **`extra="forbid"` is the only structural-drift guard before Phase 8 ships.** Make the unknown-field test pin both the raise *and* the offending key name — fail loud, per CLAUDE.md Rule 12.
- **Per arch §Edge cases row 8, `events.append(...)` is the canonical in-place mutation case.** The hook from Phase 6 catches it; this story's job is to ensure `events: list[GraphEvent]` is `list[...]` (not `tuple[...]`) so the hook's `_MUTABLE_FIELDS` check finds the field name.
- **`MigrationReport`'s shape is consumed by Phase 11.** Be especially careful with field naming — Phase 11 will sniff the YAML header. Cite arch §Data model §Persisted-on-disk shapes for the canonical names.
- **Per cross-cutting concern: fence-CI under `graph/` denies `anthropic | chromadb | sentence-transformers`** — none of those imports belong here regardless; the assertion is a forever-canary.
