# Story S2-01 — ProvenanceGate as explicit tier-0 short-circuit

**Step:** Step 2 — Ship trust-boundary primitives: ProvenanceGate, FenceWrapper/CanaryGuard/PromptBuilder, LlmInvocationGuard/BudgetToken
**Status:** Ready
**Effort:** S
**Depends on:** S1-02 (`PlanProposal` union — supplies `Refused(reason=...)` shape consumers compose against)
**ADRs honored:** ADR-0012 (tier-0 explicit gate, this phase), ADR-0003 (path-scoped fence — module lives under `src/codegenie/fallback/`, this phase), production ADR-0038 (`vuln.provenance` primitive — the seven-variant sum type this gate dispatches over)

## Context

ADR-0012 lifts production ADR-0038's `vuln.provenance` refuse-mode from "implicit Phase 3 return path" to an **explicit tier-0 step** that runs *before* any LLM tokens are spent, any RAG record is queried, or any recipe is matched. S2-01 ships the named primitive — a single `classify(advisory, repo_ctx) -> Provenance` call plus a Phase-4-scoped `_APP_LAYER_PROVENANCE_KINDS` constant — so S6-01's `FallbackTier.run` can call it as the first decision, and S7-06's E2E `test_phase4_provenance_short_circuits.py` can prove **by event-absence** that a base-image CVE never reaches the leaf adapter.

The gate is a thin adapter over the plugin-resolved `NpmVulnProvenanceAdapter` (Phase 3 generalised in S7-03); this story ships the **primitive shape** only — a `ProvenanceGate` class that takes a `VulnProvenanceAdapter` Protocol at construction time. The adapter is mocked in this story's tests; S6-01 wires the real plugin adapter; S7-03 generalises Phase 3's npm refuse-mode into the full seven-variant classifier.

Phase 7 will extend `_APP_LAYER_PROVENANCE_KINDS` for distroless migrations (`BaseImage` becomes actionable for the Chainguard plugin); the Specification-pattern wrapper `is_app_layer(provenance) -> bool` is the named seam that move flows through.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 6 — ProvenanceGate` (lines 562-569) — public interface, internal structure, performance envelope, failure behavior.
  - `../phase-arch-design.md §Goals — G7` (line 24) — "zero LLM tokens spent on non-app-layer CVEs" event-absence proof.
  - `../phase-arch-design.md §Scenarios — Scenario 3` (line 419+) — sequence diagram of the gate refuse path.
  - `../phase-arch-design.md §Edge cases row 1` (line 928) — `Unknown` glibc-on-Node case.
  - `../phase-arch-design.md §Decision points` row 1 (line 803) — `ProvenanceGate.classify` is the first decision point.
- **Phase ADRs:**
  - `../ADRs/0012-provenance-gate-explicit-tier-zero.md` — tier-0 commitment; Specification-pattern fit; `_APP_LAYER_PROVENANCE_KINDS: Final[frozenset]` constant decided here; reversibility `Low`.
  - `../ADRs/0003-path-scoped-fence-amendment.md` — `src/codegenie/fallback/` admitted; new module lives inside that path.
- **Production ADRs:**
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — the seven-variant `Provenance` sum type (`AppDirect | AppTransitive | AppVendored | BaseImage | RuntimeBundled | Both | Unknown`) and the refuse-mode semantics this gate enforces.
- **Source design:**
  - `../final-design.md §Component 6 — ProvenanceGate`.
- **Existing code:**
  - `src/codegenie/types/identifiers.py` — newtypes substrate (S1-01 added `ProvenanceKind` literal types if applicable; otherwise this story uses `Literal[...]` directly).
  - `src/codegenie/audit.py` — `EventLog` / event-emission pattern to mirror.
  - `src/codegenie/probes/base.py` — Protocol idiom (`@runtime_checkable`) to mirror for `VulnProvenanceAdapter`.
  - `plugins/vulnerability-remediation--node--npm/adapters/` — Phase 3 NPM adapter the real wiring will delegate to (S7-03 generalisation, NOT modified here).

## Goal

Ship `ProvenanceGate.classify(advisory, repo_ctx) -> Provenance` plus an `is_app_layer(provenance) -> bool` Specification predicate over the frozen `_APP_LAYER_PROVENANCE_KINDS = frozenset({"AppDirect", "AppTransitive", "AppVendored", "Both"})` set, with table-driven coverage over all seven `Provenance` variants and an `EventLog`-mediated `ProvenanceClassified(kind)` emission that fires on **every** classification regardless of outcome — so S6-01's `FallbackTier.run` can refuse non-app-layer CVEs as the first dispatch step with zero token spend.

## Acceptance criteria

- [ ] **AC-1 — Module location & path-scoped fence.** `src/codegenie/fallback/provenance_gate.py` exists. `tests/fence/test_pyproject_fence_phase4.py` (landed S1-05) remains green; this module imports only stdlib + `codegenie.*` symbols (no `anthropic`, `chromadb`, `fastembed`, `onnxruntime`).
- [ ] **AC-2 — `VulnProvenanceAdapter` Protocol.** A `@runtime_checkable` `Protocol` is defined with one method: `def classify(self, advisory: CveAdvisory, repo_ctx: RepoContext) -> Provenance`. Lives in the same module (or `src/codegenie/fallback/provenance_protocol.py` if a sibling file is cleaner — implementer chooses; either passes import-linter). `Provenance` is a `Literal["AppDirect", "AppTransitive", "AppVendored", "BaseImage", "RuntimeBundled", "Both", "Unknown"]` (or the equivalent sum-type alias already established in S1-04 — implementer reads the Step-1 substrate first and matches it).
- [ ] **AC-3 — `_APP_LAYER_PROVENANCE_KINDS` is module-level `Final[frozenset]`.** Exactly `frozenset({"AppDirect", "AppTransitive", "AppVendored", "Both"})`. Mutating it raises `AttributeError` (frozenset is immutable). Test asserts the membership set is exactly those four — adding `BaseImage` to that frozenset would fail the assertion loudly.
- [ ] **AC-4 — `is_app_layer(provenance) -> bool` predicate.** Pure function; `is_app_layer(p) is True` for each of `{AppDirect, AppTransitive, AppVendored, Both}`; `is_app_layer(p) is False` for each of `{BaseImage, RuntimeBundled, Unknown}`. Table-driven test enumerates all seven variants — adding a Phase-7 variant must touch this table.
- [ ] **AC-5 — `ProvenanceGate.classify` dispatches and emits.** `ProvenanceGate(adapter: VulnProvenanceAdapter, event_log: EventLog).classify(advisory, repo_ctx)` delegates to `adapter.classify(...)`; before returning, emits exactly one `ProvenanceClassified(kind=<variant>)` audit event. Test asserts the event fires for every variant (table-driven), regardless of `is_app_layer` outcome.
- [ ] **AC-6 — Adapter exception → `Refused(PROVENANCE_ADAPTER_FAILED)` framing.** If `adapter.classify(...)` raises any `Exception`, the gate emits `ProvenanceClassified(kind="Unknown", adapter_error=<str>)` and returns `"Unknown"`. Caller (`FallbackTier.run` in S6-01) projects `Unknown` → `Refused(reason=PROVENANCE_NOT_APP_LAYER)` via `is_app_layer`; **the gate itself never raises**. Test patches the adapter to raise `RuntimeError("npm registry timeout")` and asserts gate returns `"Unknown"` plus the structured event.
- [ ] **AC-7 — Zero-token / zero-budget invariant (load-bearing — Step-2 cross-cutting reminder).** A test constructs a gate over a non-app-layer-returning adapter, calls `classify`, and asserts a `LlmInvocationGuard` constructed in the same test reports `running_total().consumed_tokens == 0`. The gate does NOT accept a `BudgetToken` argument — the type signature of `classify` excludes `BudgetToken` entirely (the capability isn't even available before this step runs). This test is the unit-level expression of G7 — S7-06's E2E `test_phase4_provenance_short_circuits.py` proves the same property end-to-end via event-absence; this AC proves it at the primitive boundary.
- [ ] **AC-8 — Table-driven coverage over all seven `Provenance` variants.** `tests/unit/fallback/test_provenance_gate.py` parametrizes over `[("AppDirect", True), ("AppTransitive", True), ("AppVendored", True), ("Both", True), ("BaseImage", False), ("RuntimeBundled", False), ("Unknown", False)]` and asserts (i) `is_app_layer(kind) == expected`, (ii) `gate.classify(...)` returns `kind`, (iii) `ProvenanceClassified(kind=kind)` is emitted exactly once.
- [ ] **AC-9 — Event-kind allowlist registration.** `ProvenanceClassified` is added to the existing event-kind allowlist (Phase 0 / 1 establishes the mechanism — implementer reads `src/codegenie/audit.py` and matches the convention; if a `_PHASE4_EVENT_KINDS: Final[frozenset]` is the right placement, that's the right placement). `tests/fence/test_event_kinds_complete.py` (referenced ADR-0012 §Tradeoffs row 4) — if it exists, it must remain green; if it does not yet exist, this story creates the minimal stub asserting the kind is registered. Renaming the event later silently passes the wrong test — explicit registration prevents that.
- [ ] **AC-10 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on the new module + tests. `import-linter` (S1-06) remains green — `provenance_gate.py` does not import from `src/codegenie/probes/`, `coordinator/`, `cache/`, `output/`, `schema/`, or `plugins/protocols.py` (kernel-frozen guard from S1-07).

## Implementation outline

1. **Read the Phase-1 substrate** (`src/codegenie/audit.py`, `src/codegenie/probes/base.py`) for `EventLog` shape + `@runtime_checkable Protocol` idiom. Match the conventions; do not fork.
2. **Verify S1-04 supplied `Provenance`** — if a `Provenance: TypeAlias = Literal[...]` or equivalent already lives under `src/codegenie/fallback/types.py` / `src/codegenie/rag/models.py`, import it. If not (the manifest's S1-04 covers `RetrievalOutcome` + `BudgetSnapshot` + `BudgetToken` + `TypecheckNodeSignal` — `Provenance` might land here as the first user), define it adjacent to `_APP_LAYER_PROVENANCE_KINDS` in `provenance_gate.py` and add it to the Step-1 substrate retroactively only if needed (surface to implementer per Global Rule 7).
3. **Define `VulnProvenanceAdapter` Protocol** (one method, `classify`). Mark `@runtime_checkable`.
4. **Define `_APP_LAYER_PROVENANCE_KINDS: Final[frozenset[Provenance]]`** at module scope.
5. **Define `is_app_layer(provenance: Provenance) -> bool`** as `return provenance in _APP_LAYER_PROVENANCE_KINDS`. One line; module-level pure function.
6. **Define `ProvenanceGate`** as `@dataclass(frozen=True, slots=True)` with `adapter: VulnProvenanceAdapter` and `event_log: EventLog`. Method `classify(advisory: CveAdvisory, repo_ctx: RepoContext) -> Provenance`:
   - `try: kind = self.adapter.classify(advisory, repo_ctx)`.
   - `except Exception as exc: self.event_log.emit(ProvenanceClassified(kind="Unknown", adapter_error=str(exc))); return "Unknown"`.
   - `self.event_log.emit(ProvenanceClassified(kind=kind)); return kind`.
7. **Register `ProvenanceClassified` event kind** per `src/codegenie/audit.py` convention.
8. **Write tests** (red-first per TDD plan below).
9. Run `make check`. Resolve any `mypy --strict` complaints by tightening types — do not relax with `Any`.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/fallback/test_provenance_gate.py
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from codegenie.audit import EventLog  # established convention
from codegenie.fallback.provenance_gate import (
    ProvenanceGate,
    VulnProvenanceAdapter,
    _APP_LAYER_PROVENANCE_KINDS,
    is_app_layer,
)


# AC-3
def test_app_layer_kinds_is_exactly_the_four_named() -> None:
    assert _APP_LAYER_PROVENANCE_KINDS == frozenset(
        {"AppDirect", "AppTransitive", "AppVendored", "Both"}
    )


# AC-4 + AC-8 (the is_app_layer half)
@pytest.mark.parametrize(
    "kind, expected",
    [
        ("AppDirect", True),
        ("AppTransitive", True),
        ("AppVendored", True),
        ("Both", True),
        ("BaseImage", False),
        ("RuntimeBundled", False),
        ("Unknown", False),
    ],
)
def test_is_app_layer_table(kind: str, expected: bool) -> None:
    assert is_app_layer(kind) is expected  # type: ignore[arg-type]


# AC-5 + AC-8 (the gate-emits half)
@pytest.mark.parametrize(
    "kind",
    ["AppDirect", "AppTransitive", "AppVendored", "Both",
     "BaseImage", "RuntimeBundled", "Unknown"],
)
def test_classify_emits_event_for_every_variant(kind: str) -> None:
    adapter = MagicMock(spec=VulnProvenanceAdapter)
    adapter.classify.return_value = kind
    log = EventLog()
    gate = ProvenanceGate(adapter=adapter, event_log=log)

    result = gate.classify(advisory=_fixture_advisory(), repo_ctx=_fixture_ctx())

    assert result == kind
    events = [e for e in log.events if type(e).__name__ == "ProvenanceClassified"]
    assert len(events) == 1
    assert events[0].kind == kind


# AC-6
def test_adapter_exception_returns_unknown_and_emits_structured_event() -> None:
    adapter = MagicMock(spec=VulnProvenanceAdapter)
    adapter.classify.side_effect = RuntimeError("npm registry timeout")
    log = EventLog()
    gate = ProvenanceGate(adapter=adapter, event_log=log)

    result = gate.classify(advisory=_fixture_advisory(), repo_ctx=_fixture_ctx())

    assert result == "Unknown"
    events = [e for e in log.events if type(e).__name__ == "ProvenanceClassified"]
    assert len(events) == 1
    assert events[0].kind == "Unknown"
    assert events[0].adapter_error == "npm registry timeout"


# AC-7 — the load-bearing zero-token invariant
def test_classify_spends_no_budget_tokens() -> None:
    from decimal import Decimal
    from codegenie.fallback.budget import LlmInvocationGuard

    log = EventLog()
    budget = LlmInvocationGuard(
        max_tokens=250_000,
        max_dollars=Decimal("1.50"),
        per_call_max_tokens=32_000,
        event_log=log,
    )
    adapter = MagicMock(spec=VulnProvenanceAdapter)
    adapter.classify.return_value = "BaseImage"
    gate = ProvenanceGate(adapter=adapter, event_log=log)

    gate.classify(advisory=_fixture_advisory(), repo_ctx=_fixture_ctx())

    assert budget.running_total().consumed_tokens == 0
    assert budget.running_total().outstanding_tokens == {}
```

Run; expect `ModuleNotFoundError: codegenie.fallback.provenance_gate`.

### Green — make it pass

Implement `provenance_gate.py` per the outline. Smallest change that makes every test pass. Do not add features the ACs don't name (no `confidence` field, no `pattern_matched`, no caching — those are Phase 7+).

### Refactor — clean up

- Pull `_APP_LAYER_PROVENANCE_KINDS` literal into a `Final` annotation.
- If the event class shape can mirror an existing Phase-0 event (e.g., `IndexClassified`), match the field-naming convention.
- Verify `is_app_layer` is a one-line `return provenance in _APP_LAYER_PROVENANCE_KINDS`; resist temptation to add early-returns or assertions.
- `assert_never` on the variant tuple inside the parametrized test fixture so adding an 8th Phase-7 variant fails this story's test loudly — surface it to the implementer per Global Rule 7.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/__init__.py` | Package init for the Phase-4 substrate (likely created by S1-04 or this story — first writer wins; empty file). |
| `src/codegenie/fallback/provenance_gate.py` | The gate primitive — `VulnProvenanceAdapter` Protocol, `_APP_LAYER_PROVENANCE_KINDS`, `is_app_layer`, `ProvenanceGate` class. |
| `src/codegenie/audit.py` | Register `ProvenanceClassified` event kind (additive — one row in the existing event-kind allowlist or registry). |
| `tests/unit/fallback/__init__.py` | Test package init (empty). |
| `tests/unit/fallback/test_provenance_gate.py` | All ACs except AC-9 + AC-10. |
| `tests/fence/test_event_kinds_complete.py` | AC-9 — assert `ProvenanceClassified` is in the registered allowlist (extend if exists, create minimal stub if not). |

## Out of scope

- The real `NpmVulnProvenanceAdapter` generalisation — owned by S7-03.
- Wiring into `FallbackTier.run` — owned by S6-01.
- Phase-7 base-image adapter (`DockerfileBaseImageAdapter`) — owned by Phase 7.
- Widening `_APP_LAYER_PROVENANCE_KINDS` to admit `BaseImage` — Phase 7 amendment to ADR-0012.
- The E2E event-absence test (`tests/integration/test_phase4_provenance_short_circuits.py`) — owned by S7-06.
- Any caching of classification results — not in ADR-0012's contract; Phase 3 file reads are already cached.

## Notes for the implementer

- **Specification-pattern naming.** `is_app_layer` is the named rule. Resist inlining the membership check into `ProvenanceGate.classify` — the predicate is the seam Phase 7 widens, and S6-01's `FallbackTier.run` may call it directly without going through the gate (idempotent defense-in-depth on retry).
- **Frozen-dataclass over class with `__init__`.** `@dataclass(frozen=True, slots=True)` for `ProvenanceGate` — no mutable state, fits the ADR-0012 "deterministic, side-effect-free primitive" framing.
- **`MagicMock(spec=VulnProvenanceAdapter)` vs hand-rolled fake.** This story uses `MagicMock(spec=...)` because the adapter is one method and the Protocol is in this story. If S6-01's integration test needs a richer fake, that story builds it; do not pre-build the abstraction here (Global Rule 2).
- **Cross-cutting reminder #1 — zero LLM tokens.** AC-7 is the load-bearing invariant. The pre-existing `LlmInvocationGuard` from S2-05 (this same step) is the assertion surface — there is a story ordering question: if S2-05 hasn't landed yet, AC-7's test imports a not-yet-existing module. The two stories can land in either order; if S2-01 lands first, AC-7's test is skipped with a `pytest.importorskip("codegenie.fallback.budget")` until S2-05 lands, **and** the story-status is `Ready` not `Done` until AC-7 is green. Surface this to the executor.
- **Cross-cutting reminder #2 — Newtypes.** `CveAdvisory` and `RepoContext` are existing Phase-0/3 types — import them, do not redefine. `Provenance` is from S1-04 (RAG-side Pydantic models story) if it lives there; otherwise this story is the first definer and Step 1 should retroactively absorb it. Pre-check Step 1 before writing.
- **Event-kind registration is load-bearing.** ADR-0012 §Tradeoffs row 4 explicitly calls out: renaming `LeafInvoked` to `LeafCalled` would silently make the S7-06 event-absence E2E test pass falsely. The same applies to `ProvenanceClassified` — the allowlist is the structural guard. If `tests/fence/test_event_kinds_complete.py` does not exist, this story creates the minimal stub asserting the kind is registered, and Phase 7 / later stories grow it.
- **No state at all.** `ProvenanceGate` has no fields beyond `adapter` and `event_log`. No caching. No counters. No retry policy. The classification is purely a dispatch over the adapter's return.
