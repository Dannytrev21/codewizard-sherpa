# Story S6-03 — `SubgraphNode` Protocol + `SubgraphState` (Gap 1 fix; reconciliation with shipped `NodeTransition`)

**Step:** Step 6 — RemediationOrchestrator, TrustScorer, two-stream EventLog, SubgraphNode Protocol, end-to-end happy path
**Status:** Done — GREEN 2026-05-21 (phase-story-executor; see [`_attempts/S6-03.md`](_attempts/S6-03.md) for the per-AC evidence table, the seven as-built drift resolutions, and the gate log — 28 tests added, `make check` green: 5971 passed, `mypy --strict` 205 files + `ruff` + `import-linter` 6/6 + per-submodule cold-start fence + pre-commit all clean). Validator HARDENED 2026-05-19 — see [`_validation/S6-03-subgraph-node-protocol.md`](_validation/S6-03-subgraph-node-protocol.md). **As-built note (authoritative — supersedes conflicting outline/TDD-plan statements below):** the five `SubgraphState` field types (`PluginResolution`, `Bundle`, `RecipeOutcome`, `Transform`, `TrustOutcome`) are imported at **runtime**, not under `TYPE_CHECKING` — Pydantic must resolve a field's type at model-build time, so a `TYPE_CHECKING`-only import would make every `SubgraphState(...)` construction raise (D-1); `SubgraphState.model_config` additionally carries `arbitrary_types_allowed=True` because `Transform` is an `abc.ABC` (D-2, mirrors `ConcreteResolution`); `TrustOutcome` is imported from its canonical home `transforms.outcomes`, not `trust_scorer` (D-3).
**Effort:** S–M (was S; +M for the canonical-site amendments to `transforms/outcomes.py`)
**Depends on:** S6-01, S1-03 (already GREEN — ships the canonical `NodeTransition` union this story re-exports + widens), S1-04 (`Transform`), S2-04 (`PluginResolution`), S3-04 (`Bundle`). `TrustOutcome` (S6-02) is `TYPE_CHECKING`-imported as a forward reference; this story does not require S6-02 to have landed on disk.
**ADRs honored:** ADR-0010 (tagged-union sum types — Decision §3, single declaration site per ADR-0010 Amendment 2026-05-18), ADR-0010 Amendment 2026-05-19 (this story widens `Advance.state` to `SubgraphState` and widens `EscalationReason` from 3 → 7 members at the canonical site), [Phase 5 ADR-0006](../../05-sandbox-trust-gates/ADRs/0006-protocol-vs-abc-convention.md) (Protocol vs ABC: Protocol when no shared default behavior; body is `...`), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) (make illegal states unrepresentable), ADR-0001 (S6-06 contract surface — names + signatures are the contract; widening allowed, rename forbidden).

## Validation notes (2026-05-19)

Hardened by `phase-story-validator`. See `_validation/S6-03-subgraph-node-protocol.md` for the full audit. Block-tier closures:

1. **Canonical-site re-export (C-F1).** `NodeTransition`, `Advance`, `ShortCircuit`, `Escalate` already ship GREEN in `src/codegenie/transforms/outcomes.py` (S1-03, 2026-05-18). This story does **not** redefine them — it re-exports from the canonical site and adds the new `SubgraphNode` Protocol + `SubgraphState` Pydantic model. A new AC pins cross-module class identity (`subgraph.Advance is outcomes.Advance`).
2. **`Advance.state` widening (C-F2).** Existing `Advance.state: dict[str, str | int | bool | float]` is replaced at the canonical site with `Advance.state: SubgraphState`. Justified by S1-03 Implementer notes line 407 ("if a node genuinely needs richer state, the right move is a new typed payload model"). The 3 primitive-dict tests in `tests/unit/transforms/test_outcomes.py` migrate to construct a minimal `SubgraphState` (workflow_id + cve only).
3. **`EscalationReason` widening (C-F3).** Existing 3-member Literal extends additively to 7 members — the 4 system-level reasons (`filesystem_race`, `subprocess_jail_unavailable`, `audit_chain_corrupted`, `vuln_index_corrupted`) referenced by S6-04 outline line 102/106 are added. Name stays `EscalationReason` (single declaration site preserved). Test `test_outcomes.py::test_reason_taxonomy_members` (line 323) is updated.
4. **Import-path fix (C-F4).** TDD red test imports `RemediationOutcome` / `RemediationFailed` / `RemediationError` from `codegenie.transforms.outcomes` (not `.transform`).
5. **Discriminator form (C-F5).** Implementation no longer mentions `Discriminator(...)` — re-export side-steps the choice; the canonical site already uses `Field(discriminator="kind")` per repo convention.
6. **TDD-plan fixes (T-Q1/T-Q2/T-Q3/T-Q4).** `_failed_outcome` stub fleshed out (S1-03 has shipped); `asyncio.get_event_loop()` replaced with `asyncio.run(...)`; the self-contradictory `test_sync_run_fails_isinstance` replaced with a documented PEP 544 limitation note + a subprocess-mypy negative test (mirrors S1-03 AC-9a); negative-conformance coverage extended (no `run` member, attribute-not-method).
7. **Coverage closures (C-Cv1..C-Cv6).** New ACs for class-identity round-trip, frozen-mutation rejection, `model_copy(update)` type preservation, unknown-reason rejection, subprocess-mypy exhaustiveness, importability before S6-02 lands, and `__all__` exact-set.

## Context

The architecture spec's **Gap 1** (`../phase-arch-design.md §Gap analysis & improvements §Gap 1`) called out that the synthesis described the 5-node subgraph (`ingest_cve → match_recipe → apply_recipe → stage6_validate → write_branch`) as "typed step functions Phase 6 wraps 1-to-1" but **left the transition contract between nodes implicit**. The fix is a `SubgraphNode` Protocol with a typed return — `async def run(self, state: SubgraphState) -> NodeTransition` where `NodeTransition = Advance(state) | ShortCircuit(outcome) | Escalate(reason)`. The orchestrator's outer loop is a single `match`:

```python
for node in subgraph.nodes:
    match await node.run(state):
        case Advance(state=s):  state = s
        case ShortCircuit(outcome=o):  return self._finalize(o)
        case Escalate(reason=r):  return self._escalate(r)
```

This eliminates implicit ordering knowledge from individual nodes, gives Phase 6's LangGraph wrap a single pattern to lift (the three `match` arms become three edge types), and makes node-level testability trivial.

**Build-order reality (2026-05-18 / 2026-05-19).** S1-03 already shipped the `NodeTransition` discriminated union, all three variants (`Advance`, `ShortCircuit`, `Escalate`), and the `EscalationReason` Literal in `src/codegenie/transforms/outcomes.py`. This story finishes the Gap-1 fix by landing the *missing pieces*:

- `SubgraphNode` Protocol (new — `runtime_checkable`, single-method).
- `SubgraphState` Pydantic model (new — the typed payload `Advance` actually carries).
- Re-exports from `codegenie.plugins.subgraph` so S6-04's imports work (`from codegenie.plugins.subgraph import Advance, ShortCircuit, Escalate` — already referenced by S6-04's red test).
- Amendments to `transforms/outcomes.py`:
  - **Widen `Advance.state`** from `dict[str, str | int | bool | float]` to `SubgraphState` (S1-03 explicitly anticipated this widening in its Implementer notes line 407).
  - **Widen `EscalationReason`** from 3 to 7 members (additive — the existing 3 pre-subgraph reasons keep their meaning; the new 4 cover in-subgraph escalations that S6-04 emits).

This story is **small but load-bearing**: every node in S6-04's orchestrator implements the Protocol; S6-04's outer loop is the `match` block above (verbatim, modulo logging); Phase 6's LangGraph migration depends on the `NodeTransition` tagged union being **the** seam, not one of three competing patterns. ADR-0010 §3 commits to tagged-union sum types on every state machine; the Amendment 2026-05-18 commits to a single canonical declaration site per union.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 1` — the full gap statement + the resolution this story implements. **Required reading.**
  - `../phase-arch-design.md §Component design C1` — `RemediationOrchestrator`'s 5-stage internal structure ("plain async `for` over typed step-functions" — this story makes those step-functions explicit).
  - `../phase-arch-design.md §Design patterns applied` row 5 — "Tagged union (sum type) on every state machine — `... AdapterConfidence, JailedSubprocessResult, Applicability, ScopeDim (Concrete | Wildcard)`" — `NodeTransition` joins this list.
  - `../phase-arch-design.md §Control flow` step 7 — "Plugin subgraph (5 nodes, sequential): `ingest_cve → match_recipe → apply_recipe → stage6_validate → write_branch`" — these five names are the concrete nodes S6-04 implements against this Protocol.
- **Phase ADRs:**
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` §Decision (3) — "Tagged-union sum types on every state machine: ... `Applicability (Applies(plan) | NotApplies(reason))`, `ScopeDim`. Every dispatch site uses `match` + `assert_never`." `NodeTransition` follows the same pattern.
  - ADR-0010 Amendment 2026-05-18 (S1-03 `_validation/`) — single canonical declaration site per union; re-exports are class-identity, not redeclaration.
- **Cross-phase precedent:**
  - `../../05-sandbox-trust-gates/ADRs/0006-protocol-vs-abc-convention.md` — Protocol over ABC when there's no shared default behavior; subgraph nodes are textbook.
  - `../../06.5-per-task-class-eval-harness/stories/S1-04-rubric-protocol.md` — already-shipped precedent for a one-method `@runtime_checkable` Protocol that orchestrator-style code dispatches against.
- **Codebase precedents (load before writing code):**
  - `src/codegenie/transforms/outcomes.py` — the canonical `NodeTransition` site; this story imports from + amends here.
  - `src/codegenie/coordinator/input_snapshot.py:84` — `@runtime_checkable Protocol` precedent.
  - `src/codegenie/plugins/bundle.py:275/293` — two more `@runtime_checkable Protocol` precedents inside the same package.
  - `src/codegenie/plugins/resolver.py:137` — `ConcreteResolution` precedent for a frozen Pydantic state-accumulator with `extra="forbid"`.
  - `tests/unit/transforms/test_outcomes_mypy_negative.py` — subprocess-mypy fence pattern for `assert_never` exhaustiveness; this story's mypy-negative test mirrors it.
  - `tests/unit/transforms/test_outcomes.py:88-90, 323-327` — the existing test fixtures + Literal member assertion this story's amendment ACs update.
- **This phase, parallel stories:**
  - S6-01 — the `EventLog` nodes use to emit per-stage events (`PluginResolved`, `BundleBuilt`, `RecipeMatched`, etc.).
  - S6-04 — the consumer: the orchestrator's 5 nodes implement this Protocol; the outer loop is the `match` block; S6-04's red test imports `from codegenie.plugins.subgraph import Advance, ShortCircuit, Escalate`.
  - S1-03 — defines `NodeTransition`, `Advance`, `ShortCircuit`, `Escalate`, `EscalationReason` (the contract surface this story extends).
  - S7-03 — `UniversalHITLFallbackPlugin.subgraph` returns `ShortCircuit(RemediationOutcome.RequiresHumanReview(...))`; the SubgraphState shape this story lands.

## Goal

Land `src/codegenie/plugins/subgraph.py` adding:

1. The new `SubgraphNode` `@runtime_checkable Protocol`.
2. The new `SubgraphState` Pydantic model (the typed payload `Advance` carries).
3. **Re-exports** of `NodeTransition`, `Advance`, `ShortCircuit`, `Escalate` from `codegenie.transforms.outcomes` (class-identity preserved — do NOT redefine).

Land the *canonical-site amendments* in `src/codegenie/transforms/outcomes.py`:

4. Widen `Advance.state` from `dict[str, str | int | bool | float]` to `SubgraphState`.
5. Widen `EscalationReason` from `Literal["plugin_extends_cycle", "manifest_rejected", "capability_missing"]` to the 7-member set (the existing 3 + `"filesystem_race"`, `"subprocess_jail_unavailable"`, `"audit_chain_corrupted"`, `"vuln_index_corrupted"`).

Cover the Protocol with structural-conformance tests, the union with subprocess-mypy `assert_never` exhaustiveness, and the canonical-site amendments with updated test fixtures.

## Acceptance criteria

### Module surface (new file)

- [x] **AC-1** `src/codegenie/plugins/subgraph.py` exists; `from codegenie.plugins.subgraph import SubgraphNode, SubgraphState, NodeTransition, Advance, ShortCircuit, Escalate` succeeds.
- [x] **AC-2** `set(codegenie.plugins.subgraph.__all__) == {"SubgraphNode", "SubgraphState", "NodeTransition", "Advance", "ShortCircuit", "Escalate"}` (exactly 6 names — 2 new + 4 re-exports). Exact-set assertion mirrors S1-01 / S1-03 discipline.

### Re-export class identity (block-tier; C-F1)

- [x] **AC-3** `from codegenie.plugins.subgraph import Advance as A; from codegenie.transforms.outcomes import Advance as B; assert A is B`. Same identity check for `ShortCircuit`, `Escalate`, `NodeTransition`. Test name pinned: `test_re_exports_are_identity_with_outcomes`.

### `SubgraphNode` Protocol

- [x] **AC-4** `SubgraphNode` is decorated `@runtime_checkable` and inherits from `typing.Protocol`. Single method: `async def run(self, state: SubgraphState) -> NodeTransition: ...`. The Protocol's `run` body is `...` (literal ellipsis) — not `pass`, not `raise NotImplementedError` (Phase 5 ADR-0006 convention).
- [x] **AC-5** A duck-typed class with `async def run(self, state: SubgraphState) -> NodeTransition` passes `isinstance(instance, SubgraphNode)` at runtime, **without explicit inheritance** from `SubgraphNode`.
- [x] **AC-6** A class missing `run` (e.g., only an `evaluate` method) fails `isinstance(instance, SubgraphNode)` at runtime. (Test name: `test_missing_run_fails_isinstance`.)
- [x] **AC-7** **PEP 544 limitation documented.** A class with a *synchronous* `run` (`def run(...)` not `async def run(...)`) — `isinstance(instance, SubgraphNode)` returns `True` (Protocol cannot structurally distinguish async vs sync at runtime). This is documented in the module docstring and a doc-style test confirms the runtime behaviour: `assert isinstance(_SyncRunNode(), SubgraphNode) is True  # PEP 544 limitation; mypy --strict catches the divergence`. The actual sync/async enforcement is type-time (mypy `--strict`).
- [x] **AC-8** A class where `run` is a class attribute (e.g., `run = 42`, not a method) — runtime `isinstance` returns `True` (Protocol checks attribute existence only). Documented; no separate negative test (the mypy strict check is the enforcement).

### `SubgraphState` Pydantic model

- [x] **AC-9** `SubgraphState` is a Pydantic model with `model_config = ConfigDict(frozen=True, extra="forbid")`. Fields:
  - **Required (no default; failure to provide raises `ValidationError`):**
    - `workflow_id: WorkflowId`
    - `cve: CveId`
  - **Accumulator (default `None`; populated by nodes as the subgraph advances):**
    - `resolution: PluginResolution | None = None` (populated by `IngestCveNode`; `PluginResolution = ConcreteResolution | UniversalFallbackResolution` per S2-04)
    - `bundle: Bundle | None = None` (populated by post-resolution build step)
    - `recipe_outcome: RecipeOutcome | None = None` (populated by `MatchRecipeNode` — carries the `Applies(plan)`)
    - `transform: Transform | None = None` (populated by `ApplyRecipeNode`)
    - `trust_outcome: "TrustOutcome | None" = None` (populated by `Stage6ValidateNode`; **forward-reference string** until S6-02 lands)
    - `branch: BranchName | None = None` (populated by `WriteBranchNode`)
- [x] **AC-10 (frozen-mutation rejected — C-Cv2 #1).** `s = SubgraphState(workflow_id=..., cve=...); s.workflow_id = WorkflowId("other")` raises `ValidationError` (or equivalent Pydantic frozen-mutation rejection).
- [x] **AC-11 (`model_copy(update={...})` preserves field types — C-Cv2 #2).** Given `s = SubgraphState(workflow_id=W, cve=C)` and a `resolution_fixture: PluginResolution`:
  - `s2 = s.model_copy(update={"resolution": resolution_fixture})` succeeds.
  - `isinstance(s2, SubgraphState) is True`.
  - `s2.resolution is resolution_fixture`.
  - `s2.workflow_id == s.workflow_id` and `s2.cve == s.cve` (other fields untouched).
- [x] **AC-12 (build-order tolerance — C-Cv5).** `import codegenie.plugins.subgraph` succeeds with no `ModuleNotFoundError` even if `codegenie.transforms.trust_scorer` (S6-02) has not yet been merged. Achieved via `from __future__ import annotations` + `if TYPE_CHECKING:` guard on the `TrustOutcome` import; `SubgraphState.trust_outcome` annotation is a forward-reference string (`"TrustOutcome | None"`).

### Canonical-site amendments (block-tier; C-F2, C-F3)

- [x] **AC-13 (`Advance.state` widened — C-F2).** `src/codegenie/transforms/outcomes.py::Advance` is amended so the `state` field's annotation is `SubgraphState` (replacing `dict[str, str | int | bool | float]`). The `Advance` class continues to live in `outcomes.py` (single declaration site); `subgraph.py` re-exports it. To avoid a circular import (`outcomes.py` would import `SubgraphState` from `subgraph.py`, which re-exports `Advance` from `outcomes.py`):
  - `SubgraphState` is declared in `subgraph.py` (this story's new file).
  - `outcomes.py` uses `from __future__ import annotations` + `if TYPE_CHECKING: from codegenie.plugins.subgraph import SubgraphState`. The `state: SubgraphState` annotation is a forward-reference string; Pydantic's `model_rebuild()` is called from `subgraph.py` after both modules are loaded (`Advance.model_rebuild()`).
  - The `subgraph.py` module ends with `Advance.model_rebuild()` to resolve the forward reference at import time.
- [x] **AC-14 (`Advance.state` accepts `SubgraphState`).** `Advance(state=SubgraphState(workflow_id=W, cve=C))` constructs OK. Tested by name: `test_advance_carries_subgraph_state`.
- [x] **AC-15 (`Advance.state` rejects primitive dict).** `Advance(state={"k": 1})` raises `ValidationError` (the previous primitive-dict variant is fully replaced, not unioned). The 3 existing tests in `tests/unit/transforms/test_outcomes.py` that constructed `Advance(state={"k": 1})` / used `test_advance_state_primitives_only_*` are updated to construct a minimal `SubgraphState`. Specifically:
  - Line 88: `Advance(state={"k": 1})` → `Advance(state=_minimal_subgraph_state())`.
  - Lines 263-275 (`test_advance_state_primitives_only_rejects` + `test_advance_state_primitives_only_accepts`): replaced with `test_advance_rejects_non_subgraph_state_payload` (asserts dict / list / None / int payloads raise) and `test_advance_round_trips_subgraph_state` (asserts a populated SubgraphState round-trips through `TypeAdapter(NodeTransition).dump_json` / `.validate_json`).
- [x] **AC-16 (`EscalationReason` widened — C-F3).** `src/codegenie/transforms/outcomes.py::EscalationReason` is amended to the 7-member union:
  ```python
  EscalationReason = Literal[
      "plugin_extends_cycle",
      "manifest_rejected",
      "capability_missing",
      "filesystem_race",
      "subprocess_jail_unavailable",
      "audit_chain_corrupted",
      "vuln_index_corrupted",
  ]
  ```
  Order in the source preserves the existing 3 first (S1-03 baseline) followed by the 4 new in-subgraph reasons (S6-04 emitters). `tests/unit/transforms/test_outcomes.py::test_reason_taxonomy_members` (current assertion at line 323-327) is updated to `assert members(EscalationReason) == {"plugin_extends_cycle", "manifest_rejected", "capability_missing", "filesystem_race", "subprocess_jail_unavailable", "audit_chain_corrupted", "vuln_index_corrupted"}`.
- [x] **AC-17 (unknown reason rejected — C-Cv3).** `Escalate(reason="bogus_reason")` raises `ValidationError`. Test name: `test_escalate_rejects_unknown_reason`.
- [x] **AC-18 (each new reason constructs).** Four parametrised constructions succeed: `Escalate(reason=r)` for `r in {"filesystem_race", "subprocess_jail_unavailable", "audit_chain_corrupted", "vuln_index_corrupted"}`. Test name: `test_escalate_accepts_in_subgraph_reasons`.

### Exhaustiveness — type-time enforcement (C-Cv4)

- [x] **AC-19 (subprocess-mypy negative — `assert_never`).** `tests/unit/plugins/test_subgraph_mypy_negative.py` ships a subprocess-mypy fixture mirroring `tests/unit/transforms/test_outcomes_mypy_negative.py`:
  - The fixture writes a temp module that `match`-es over `NodeTransition` with one variant arm intentionally missing and a default `case _ as unexpected: assert_never(unexpected)`.
  - `subprocess.run([sys.executable, "-m", "mypy", "--strict", tmp_file])` exits non-zero.
  - `"assert_never"` appears in stdout.
  - Test name: `test_assert_never_catches_missing_arm_node_transition`.

### Runtime exhaustiveness (regression — variant currently covered)

- [x] **AC-20** `tests/unit/plugins/test_subgraph_protocol.py::test_subgraph_outer_loop_match_exhaustive_at_runtime`:
  - Constructs one instance of each variant (`_AdvanceNode()`, `_ShortCircuitNode()`, `_EscalateNode()`).
  - Iterates and `match`-es over `Advance | ShortCircuit | Escalate` + default `case _ as unexpected: assert_never(unexpected)`.
  - Collects a `seen: set[str] = set()` per arm; asserts `seen == {"advance", "short_circuit", "escalate"}` after the loop.
  - Mirrors the S1-03 exhaustiveness-test shape (`tests/unit/transforms/test_exhaustiveness.py`).

### Bar ACs

- [x] **AC-21** TDD red test exists, was committed in a failing state, is now green.
- [x] **AC-22** `ruff format`, `ruff check`, `mypy --strict src/codegenie/plugins/subgraph.py src/codegenie/transforms/outcomes.py` clean.
- [x] **AC-23** Full test suite `pytest` clean (no regressions on the 3 updated `test_outcomes.py` cases, no regressions on the 19 existing `EscalationReason` test).

## Implementation outline

1. Write `tests/unit/plugins/test_subgraph_protocol.py` (red); confirm `ModuleNotFoundError: codegenie.plugins.subgraph`.
2. Write `tests/unit/plugins/test_subgraph_mypy_negative.py` (red); confirm `ModuleNotFoundError` then update once `subgraph.py` exists.
3. Create `src/codegenie/plugins/subgraph.py`:
   - `from __future__ import annotations`.
   - Imports: `from typing import TYPE_CHECKING, Protocol, runtime_checkable`, `from pydantic import BaseModel, ConfigDict`, the identifiers (`WorkflowId`, `CveId`, `BranchName`), and the **re-exports** `from codegenie.transforms.outcomes import Advance, ShortCircuit, Escalate, NodeTransition`.
   - `if TYPE_CHECKING:` guard for the runtime-optional dependencies: `from codegenie.plugins.resolver import PluginResolution`, `from codegenie.plugins.bundle import Bundle`, `from codegenie.transforms.outcomes import RecipeOutcome`, `from codegenie.transforms.transform import Transform`, `from codegenie.transforms.trust_scorer import TrustOutcome` (the last is forward-reference-only until S6-02 lands).
   - Define `SubgraphState` (Pydantic, `frozen=True, extra="forbid"`, fields per AC-9).
   - Define `@runtime_checkable class SubgraphNode(Protocol)` with the single `async def run(self, state: SubgraphState) -> NodeTransition: ...`.
   - Module docstring cites Gap 1 + ADR-0010 + ADR-0010 Amendment 2026-05-19 + Phase 5 ADR-0006. Explicit note documents the PEP 544 sync-vs-async limitation (AC-7).
   - `__all__ = ["SubgraphNode", "SubgraphState", "NodeTransition", "Advance", "ShortCircuit", "Escalate"]`.
   - End-of-module: `Advance.model_rebuild()` (resolves the forward-reference annotation on `Advance.state` per AC-13).
4. Amend `src/codegenie/transforms/outcomes.py`:
   - Add `from __future__ import annotations` at the top (verify it's already there; S1-03 already added it per file inspection line 31).
   - Replace `class Advance(BaseModel): ... state: dict[str, str | int | bool | float]` with `class Advance(BaseModel): ... state: SubgraphState` (using forward-ref string annotation since the `if TYPE_CHECKING:` import is the only way to avoid the circular import).
   - Extend `EscalationReason` to the 7-member Literal per AC-16.
   - The `model_rebuild()` is called from `subgraph.py` (AC-13); `outcomes.py` does NOT call it (avoids forcing `subgraph.py` import at outcomes-import time).
5. Update `src/codegenie/transforms/__init__.py` — verify the existing re-exports of `NodeTransition`, `Advance`, `ShortCircuit`, `Escalate`, `EscalationReason` still resolve. No additional re-exports needed.
6. Update `tests/unit/transforms/test_outcomes.py`:
   - Line 88: `Advance(state={"k": 1})` → `Advance(state=_minimal_subgraph_state())` where `_minimal_subgraph_state()` is a tiny test helper constructing `SubgraphState(workflow_id=WorkflowId("01HFEEDFACE0000000000000000"), cve=CveId("CVE-2024-21501"))`.
   - Lines 263-275: replace `test_advance_state_primitives_only_rejects` + `test_advance_state_primitives_only_accepts` with the two updated tests per AC-15.
   - Lines 323-327: update `EscalationReason` member assertion to the 7-member set per AC-16.
   - Cross-check: any other test referencing `Advance` with a dict literal — none expected per grep, but verify.
7. Update `tests/unit/transforms/test_outcomes_purity.py` if the AST source-scan asserts `EscalationReason` is on a specific line / has a specific length — it should not; verify.
8. Run `mypy --strict src/codegenie/{plugins,transforms}/` + full `pytest`. Confirm green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/plugins/test_subgraph_protocol.py`.

```python
# tests/unit/plugins/test_subgraph_protocol.py
"""S6-03 — SubgraphNode Protocol + SubgraphState + canonical-site reconciliation."""
from __future__ import annotations

import asyncio
from typing import assert_never

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.plugins.subgraph import (
    SubgraphNode, SubgraphState, NodeTransition,
    Advance, ShortCircuit, Escalate,
)
from codegenie.transforms.outcomes import (
    RemediationOutcome, RequiresHumanReview, RemediationError,
    RemediationFailed,
)
from codegenie.types.identifiers import WorkflowId, CveId, ErrorId


def _minimal_subgraph_state() -> SubgraphState:
    return SubgraphState(
        workflow_id=WorkflowId("01HFEEDFACE0000000000000000"),
        cve=CveId("CVE-2024-21501"),
    )


def _failed_outcome() -> RemediationOutcome:
    return RemediationFailed(
        error=RemediationError(
            error_id=ErrorId("test.stub"),
            message="stub failure for tests",
        ),
    )


class _AdvanceNode:
    async def run(self, state: SubgraphState) -> NodeTransition:
        return Advance(state=state.model_copy(update={}))


class _ShortCircuitNode:
    async def run(self, state: SubgraphState) -> NodeTransition:
        return ShortCircuit(outcome=_failed_outcome())


class _EscalateNode:
    async def run(self, state: SubgraphState) -> NodeTransition:
        return Escalate(reason="filesystem_race")


class _MissingRunNode:
    async def evaluate(self, state: SubgraphState) -> NodeTransition: ...


class _SyncRunNode:
    def run(self, state: SubgraphState) -> NodeTransition:  # not async
        return Advance(state=state)


# AC-3 — re-exports are class-identity
def test_re_exports_are_identity_with_outcomes():
    from codegenie.plugins.subgraph import Advance as PA, ShortCircuit as PS
    from codegenie.plugins.subgraph import Escalate as PE, NodeTransition as PN
    from codegenie.transforms.outcomes import Advance as OA, ShortCircuit as OS
    from codegenie.transforms.outcomes import Escalate as OE, NodeTransition as ON
    assert PA is OA
    assert PS is OS
    assert PE is OE
    assert PN is ON


# AC-2 — __all__ exact-set
def test_all_is_exact_set():
    import codegenie.plugins.subgraph as sg
    assert set(sg.__all__) == {
        "SubgraphNode", "SubgraphState", "NodeTransition",
        "Advance", "ShortCircuit", "Escalate",
    }


# AC-5 — duck-typed node passes isinstance
def test_protocol_is_runtime_checkable():
    assert isinstance(_AdvanceNode(), SubgraphNode)
    assert isinstance(_ShortCircuitNode(), SubgraphNode)
    assert isinstance(_EscalateNode(), SubgraphNode)


# AC-6 — missing `run` member fails isinstance
def test_missing_run_fails_isinstance():
    assert not isinstance(_MissingRunNode(), SubgraphNode)


# AC-7 — PEP 544 limitation documented in code; isinstance for sync run returns True
def test_sync_run_passes_runtime_isinstance_pep544_limitation():
    """Protocol cannot structurally distinguish sync from async at runtime.

    The actual sync/async enforcement is mypy --strict (see
    test_subgraph_mypy_negative.py). This test documents the runtime
    behaviour so a future contributor doesn't try to over-strengthen
    the runtime check.
    """
    assert isinstance(_SyncRunNode(), SubgraphNode) is True


@pytest.mark.asyncio
async def test_advance_returns_advance_variant():
    transition = await _AdvanceNode().run(_minimal_subgraph_state())
    assert isinstance(transition, Advance)
    assert transition.kind == "advance"


@pytest.mark.asyncio
async def test_short_circuit_returns_short_circuit_variant():
    transition = await _ShortCircuitNode().run(_minimal_subgraph_state())
    assert isinstance(transition, ShortCircuit)
    assert transition.kind == "short_circuit"


@pytest.mark.asyncio
async def test_escalate_returns_escalate_variant():
    transition = await _EscalateNode().run(_minimal_subgraph_state())
    assert isinstance(transition, Escalate)
    assert transition.kind == "escalate"
    assert transition.reason == "filesystem_race"


# AC-20 — runtime exhaustiveness; mirrors S1-03's test_exhaustiveness shape
@pytest.mark.asyncio
async def test_subgraph_outer_loop_match_exhaustive_at_runtime():
    nodes: list[SubgraphNode] = [_AdvanceNode(), _ShortCircuitNode(), _EscalateNode()]
    seen: set[str] = set()
    for node in nodes:
        transition = await node.run(_minimal_subgraph_state())
        match transition:
            case Advance(state=s):
                seen.add("advance")
                assert s.workflow_id == _minimal_subgraph_state().workflow_id
            case ShortCircuit(outcome=o):
                seen.add("short_circuit")
                assert isinstance(o, RemediationFailed)
            case Escalate(reason=r):
                seen.add("escalate")
                assert r in {
                    "plugin_extends_cycle", "manifest_rejected",
                    "capability_missing", "filesystem_race",
                    "subprocess_jail_unavailable",
                    "audit_chain_corrupted", "vuln_index_corrupted",
                }
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"advance", "short_circuit", "escalate"}


# AC-9 / AC-10 — SubgraphState is frozen
def test_subgraph_state_is_frozen():
    s = _minimal_subgraph_state()
    with pytest.raises(ValidationError):
        s.workflow_id = WorkflowId("other")  # type: ignore[misc]


# AC-9 — required fields raise when omitted
def test_subgraph_state_requires_workflow_id_and_cve():
    with pytest.raises(ValidationError):
        SubgraphState()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        SubgraphState(workflow_id=WorkflowId("x"))  # type: ignore[call-arg]


# AC-9 — accumulator fields default to None
def test_subgraph_state_accumulator_fields_default_none():
    s = _minimal_subgraph_state()
    assert s.resolution is None
    assert s.bundle is None
    assert s.recipe_outcome is None
    assert s.transform is None
    assert s.trust_outcome is None
    assert s.branch is None


# AC-11 — model_copy preserves field types
def test_subgraph_state_model_copy_preserves_workflow_id_and_cve():
    s = _minimal_subgraph_state()
    s2 = s.model_copy(update={"cve": CveId("CVE-9999-9999")})
    assert s2.workflow_id == s.workflow_id
    assert s2.cve == CveId("CVE-9999-9999")
    assert s2.resolution is None


# AC-14 — Advance carries SubgraphState
def test_advance_carries_subgraph_state():
    s = _minimal_subgraph_state()
    a = Advance(state=s)
    assert a.state is s
    assert a.kind == "advance"


# AC-15 — Advance rejects non-SubgraphState payloads
@pytest.mark.parametrize("bad", [
    {"k": 1}, [1, 2], None, 42, "string",
])
def test_advance_rejects_non_subgraph_state_payload(bad):
    with pytest.raises(ValidationError):
        Advance(state=bad)


# AC-15 — Advance round-trips a SubgraphState through JSON
def test_advance_round_trips_subgraph_state():
    s = _minimal_subgraph_state()
    a = Advance(state=s)
    adapter = TypeAdapter(NodeTransition)
    decoded = adapter.validate_json(adapter.dump_json(a))
    assert isinstance(decoded, Advance)
    assert decoded.state.workflow_id == s.workflow_id
    assert decoded.state.cve == s.cve


# AC-17 — unknown reason rejected
def test_escalate_rejects_unknown_reason():
    with pytest.raises(ValidationError):
        Escalate(reason="bogus_reason")  # type: ignore[arg-type]


# AC-18 — each new in-subgraph reason constructs
@pytest.mark.parametrize("reason", [
    "filesystem_race", "subprocess_jail_unavailable",
    "audit_chain_corrupted", "vuln_index_corrupted",
])
def test_escalate_accepts_in_subgraph_reasons(reason):
    e = Escalate(reason=reason)
    assert e.reason == reason


# AC-12 — importability before S6-02 lands
def test_subgraph_module_imports_without_trust_scorer():
    """The TYPE_CHECKING-only forward reference to TrustOutcome means this
    module must import cleanly even if codegenie.transforms.trust_scorer
    has not yet been merged."""
    import importlib
    mod = importlib.import_module("codegenie.plugins.subgraph")
    assert hasattr(mod, "SubgraphState")
    assert hasattr(mod, "SubgraphNode")
```

Run; confirm `ModuleNotFoundError: codegenie.plugins.subgraph` until step 3 of the implementation outline runs.

Test file path: `tests/unit/plugins/test_subgraph_mypy_negative.py` (mirrors `tests/unit/transforms/test_outcomes_mypy_negative.py`):

```python
"""S6-03 AC-19 — subprocess-mypy negative test proving assert_never catches
a missing match arm over NodeTransition."""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

FIXTURE = textwrap.dedent('''
    from typing import assert_never
    from codegenie.plugins.subgraph import (
        NodeTransition, Advance, ShortCircuit,
    )
    # Intentionally missing the `Escalate` arm:
    def describe(t: NodeTransition) -> str:
        match t:
            case Advance():           return "a"
            case ShortCircuit():      return "s"
            case _ as unexpected:     assert_never(unexpected)  # mypy must complain
        return ""
''')


def test_assert_never_catches_missing_arm_node_transition(tmp_path: Path):
    f = tmp_path / "negative.py"
    f.write_text(FIXTURE)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(f)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "assert_never" in result.stdout
```

### Green — make it pass

The body of `subgraph.py` is ~50 lines (with the `if TYPE_CHECKING:` block + the `model_rebuild()` call): one Protocol, one Pydantic model, four re-exports, one `model_rebuild` call.

The amendment to `outcomes.py` is two-line: rewrite `Advance.state` annotation; extend `EscalationReason` Literal. Three test updates in `test_outcomes.py` (one fixture line + two test functions + one Literal assertion).

### Refactor — clean up

- Module docstring on `subgraph.py` cites Gap 1, ADR-0010, ADR-0010 Amendment 2026-05-19 (this story), Phase 5 ADR-0006.
- One-line class docstring on `SubgraphNode` explaining the contract; explicit PEP 544 limitation note inside.
- One-line class docstring on `SubgraphState` listing which node populates which accumulator field.
- Confirm `mypy --strict` resolves the forward reference `Advance.state: SubgraphState` (Pydantic `model_rebuild()` is the trigger).
- Confirm the AST source-scan in `test_outcomes_purity.py` still passes (no new imports under `transforms/`; the `if TYPE_CHECKING:` block is allowed).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/subgraph.py` | **New** — `SubgraphNode` Protocol, `SubgraphState` model, re-exports of `NodeTransition`/`Advance`/`ShortCircuit`/`Escalate`, end-of-module `Advance.model_rebuild()`. |
| `src/codegenie/transforms/outcomes.py` | **Amend** — `Advance.state` annotation widened to `SubgraphState` (forward-ref string); `EscalationReason` Literal widened to 7 members. |
| `tests/unit/plugins/test_subgraph_protocol.py` | **New** — structural conformance + new-member-reason coverage + frozen + model_copy + import-time tolerance + runtime exhaustiveness. |
| `tests/unit/plugins/test_subgraph_mypy_negative.py` | **New** — subprocess-mypy fence over `NodeTransition` with a missing-arm `assert_never` (AC-19). |
| `tests/unit/transforms/test_outcomes.py` | **Amend** — three updates: line 88 (Advance fixture switches to SubgraphState), lines 263-275 (state-rejection tests rewritten), line 323-327 (EscalationReason member set expanded). |

## Out of scope

- **The 5 concrete node implementations** (`IngestCveNode`, `MatchRecipeNode`, `ApplyRecipeNode`, `Stage6ValidateNode`, `WriteBranchNode`) — S6-04 lands them as classes implementing `SubgraphNode`.
- **The orchestrator's outer `match` loop** — S6-04 lands it.
- **LangGraph integration** — Phase 6 wraps these arms as LangGraph edges.
- **`SubgraphState` field additions for Phase 4 (LLM-fallback)** — Phase 4 adds optional fields additively (e.g., `llm_attempts: tuple[LLMAttempt, ...] = ()`); zero edits to this story's code.
- **Cancellation / timeout semantics on `await node.run(state)`** — S6-04 owns timeouts via `asyncio.wait_for`; the Protocol carries no cancellation contract.
- **Per-node retry policy** — Phase 3 alone does NOT retry (ADR-0007); Phase 5's `GateRunner` is the retry envelope.
- **A 5-stage sum type for `SubgraphState`** (e.g., `StagePreResolution | StagePostResolution | ...`) — surfaced in validation as design-pattern-D-P3; deferred per Rule 2 (Simplicity First). Revisit if Phase 6's LangGraph migration motivates it.

## Notes for the implementer

- **This story is deceptively small AND it touches a shipped surface.** The new code in `plugins/subgraph.py` is ~50 LOC; the amendment to `transforms/outcomes.py` is ~5 LOC. But the *shape* is the load-bearing decision: every node in S6-04 implements `SubgraphNode`, every outer-loop `match` arm consumes one of the three transitions, every Phase 6 LangGraph edge is one of the three. Wide influence per LOC.
- **Do NOT redefine `NodeTransition`, `Advance`, `ShortCircuit`, `Escalate`.** They already exist in `src/codegenie/transforms/outcomes.py` (S1-03 GREEN 2026-05-18). The validation-block C-F1 covers this: `subgraph.Advance is outcomes.Advance` is asserted by AC-3. A reviewer suggesting "let's just put them in plugins/subgraph.py since that's where the Protocol lives" is wrong — ADR-0010 Amendment 2026-05-18 mandates a single canonical declaration site per union.
- **Forward-reference dance (AC-13).** `outcomes.py::Advance.state` annotates `SubgraphState` (defined in `subgraph.py`); `subgraph.py` imports `Advance` (defined in `outcomes.py`). This is a circular module-graph requirement. Resolution:
  - Both modules use `from __future__ import annotations` (annotations are strings; not evaluated at class-definition time).
  - `outcomes.py` uses `if TYPE_CHECKING: from codegenie.plugins.subgraph import SubgraphState` — no runtime import.
  - `subgraph.py` calls `Advance.model_rebuild()` at the bottom — this re-evaluates the forward reference now that `SubgraphState` is in scope.
  - The order matters: importing `outcomes.py` alone leaves `Advance.state`'s type unresolved (Pydantic accepts this lazily). Importing `subgraph.py` triggers both `outcomes.py` import + `model_rebuild()`. S6-04 imports from `subgraph.py`; that's the right entry point.
  - Test `test_subgraph_module_imports_without_trust_scorer` confirms the dance works without S6-02 landed.
- **Resist the urge to add methods to `SubgraphNode`.** A reviewer might suggest `name: str` (for logging) or `requires_capabilities: set[Capability]` (for pre-flight checks). **Reject both.** Logging is the orchestrator's concern; node identity comes from `type(node).__name__`. Capability pre-flight is `CapabilityBundle` on `ApplyContext` (S1-04). Widening the Protocol forces every existing node + every future Phase 6 LangGraph edge to update.
- **`NodeTransition` discriminator is `"kind"`.** Same field name as `RecipeOutcome`, `RemediationOutcome`, `PluginResolution`. Uniformity matters (ADR-0010 §Decision). Already canonical in S1-03.
- **Extension by addition (D-P1).** Phase 4 / Phase 7 widen `SubgraphState` by adding NEW Optional fields (`llm_attempts: tuple[LLMAttempt, ...] = ()`, `provenance_signals: ProvenanceSignal | None = None`), never by retyping existing ones. The discriminated union `NodeTransition` widens only via the canonical `transforms/outcomes.py` site + ADR amendment + S6-06 contract-snapshot baseline bump. Two parallel `Advance/ShortCircuit/Escalate` types under `plugins/` are explicitly forbidden — that path produces a class-identity split that breaks every downstream isinstance / TypeAdapter call site.
- **PEP 544 limitation (AC-7).** `isinstance(_SyncRunNode(), SubgraphNode)` returns `True`. Protocol cannot structurally check that `run` is async. The combined enforcement is: (a) mypy `--strict` at type-check time refuses to assign a `_SyncRunNode` instance to a `SubgraphNode`-typed parameter; (b) the subprocess-mypy negative test (`test_subgraph_mypy_negative.py`) verifies the assertion still fires when a variant arm is missed. Do NOT try to add a runtime `inspect.iscoroutinefunction(node.run)` check — Protocols are by-design structural, not behavioural; the runtime cost is non-zero and the test (`test_sync_run_passes_runtime_isinstance_pep544_limitation`) documents the contract.
- **`SubgraphState` field grouping (D-P2).** Required fields (`workflow_id`, `cve`) are constructor-required (no default). The 6 accumulator fields default to None and are populated by specific nodes (per the node-to-field map in AC-9). A reviewer who asks "should we have a SubgraphState builder pattern?" gets pointed at `.model_copy(update={...})` (existing Pydantic idiom, zero new code, matches `ConcreteResolution.composed_tccm` precedent at `src/codegenie/plugins/resolver.py:137`).
- **5-stage sum type alternative (D-P3) — deferred.** A more rigorous design would type SubgraphState as a sum type per pipeline stage (`StagePreResolution | StagePostResolution | ...`), making illegal field combinations unrepresentable. This was surfaced in validation but deferred (Rule 2: Simplicity First). The 6 Optional accumulators with documented producer-nodes is the cheaper-correct shape today. If Phase 6's LangGraph migration finds value in stage-typed state, that's the right time to extract — it's an additive refactor (sum-type → record-of-Optional is a one-way translation).
- **The `EscalationReason` widening (C-F3) is additive.** The 3 existing reasons (`plugin_extends_cycle`, `manifest_rejected`, `capability_missing`) continue to type-check for pre-subgraph escalation paths (resolver / capability mint). The 4 new reasons cover in-subgraph node escalations. A reviewer suggesting two parallel Literals (`PreSubgraphEscalationReason` + `SubgraphEscalationReason`) loses the single-declaration-site discipline of ADR-0010 Amendment 2026-05-18 — reject.
- **The runtime `isinstance(node, SubgraphNode)` check is only used in tests.** Production code (the orchestrator) takes a `SubgraphNode` parameter; mypy `--strict` does the structural verification at type-check time. Do NOT add a registry-time `isinstance` check in S6-04 — the S1-04 precedent explicitly notes this (registries don't `isinstance`-check Protocols).
- **Phase 6's LangGraph wrap is the natural next step.** Each `match` arm becomes an edge: `Advance` → next-node edge; `ShortCircuit` → finalize edge; `Escalate` → error-handler edge. Phase 6's design depends on this story's three-arm shape being the **only** outer-loop shape. Adding a fourth arm later means Phase 6 re-architects.
