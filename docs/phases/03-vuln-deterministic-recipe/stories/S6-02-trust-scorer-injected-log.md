# Story S6-02 — `TrustScorer` with constructor-injected `EventLog` + `SignalKind` open registry (Gap 5 fix)

**Step:** Step 6 — RemediationOrchestrator, TrustScorer, two-stream EventLog, SubgraphNode Protocol, end-to-end happy path
**Status:** Ready
**Effort:** M
**Depends on:** S6-01
**ADRs honored:** ADR-0001 (`TrustScorer.__init__(event_log)` is the named Phase-5 contract — constructor-injection is mandatory), ADR-0005 (the injected log is the two-stream `EventLog`), ADR-0010 (`TrustOutcome` tagged-union, `SignalKind` newtype), [Phase 5 ADR-0003](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md) (Phase 5 widens via `@register_signal_kind`)

## Context

`TrustScorer` is the strict-AND scoring kernel. Phase 3 registers 5 signal kinds (`build`, `install`, `tests`, `lockfile_policy`, `cve_delta`); Phase 5 widens with `trace`, `policy` (05-ADR-0003); Phase 7 widens again with `baseimage`, `shell_presence`. Each addition is a new file with `@register_signal_kind("name")` — no edits to `TrustScorer.score`. The score is **strict-AND**: any `passed=False` signal → `TrustOutcome.passed=False` with `failing=[...kinds...]`.

The architecture spec's **Gap 5** (`../phase-arch-design.md §Gap analysis & improvements §Gap 5`) called out that the three lens designs left "how the orchestrator obtains the EventLog instance the TrustScorer reads" implicit. Two options were on the table:

1. **Ambient state**: `TrustScorer.score(signals)` walks `os.environ["CODEGENIE_WORKFLOW_ID"]` and discovers the per-workflow log on disk.
2. **Constructor injection**: `TrustScorer(event_log)` receives the log explicitly; `score(signals)` reads `event_log.replay()` for `AdapterDegraded` markers and folds `confidence: Literal["high", "degraded"]` into the outcome.

Ambient state is the textbook anti-pattern (hidden coupling, unmockable in tests, breaks under concurrent workflows in the same process). ADR-0001 picks constructor injection explicitly (§Consequences: *"`TrustScorer.__init__(event_log: EventLog)` (constructor-injection per Gap 5 in the architecture spec) — the scorer reads its workflow's event stream to fold `AdapterDegraded` events into `TrustOutcome.confidence`. Ambient-state alternative rejected."*). ADR-0005 §Consequences reasserts: *"`TrustScorer` reads its own workflow's internal stream for `AdapterDegraded` markers — this is the ambient-state alternative rejected in ADR-0001 (constructor-injected EventLog instead)."*

The **open `SignalKind` registry** (`@register_signal_kind("name")`) is the seam Phase 5 and Phase 7 extend. Adding a new signal kind is one decorator call in a new module — no edits here. The registry mirrors the `PluginRegistry` / `RecipeRegistry` / `IndexFreshnessRegistry` shape already established in the codebase (CLAUDE.md §Open/Closed seams).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C6` — `TrustScorer` public interface, `SignalKind` open registry, confidence-propagation semantics, the "this is mildly cyclical — replay-tested" note.
  - `../phase-arch-design.md §Data model` (lines ~832–844) — `TrustSignal`, `TrustOutcome` Pydantic shapes (`extra="forbid"`, `frozen=True`, `details` is primitives-only).
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 5` — the gap this story closes; reads the ambient-state vs. constructor-injection tradeoff.
  - `../phase-arch-design.md §Control flow` step 8 — Stage 6 collects 5 `TrustSignal`s and passes them to `TrustScorer.score(...)`.
- **Phase ADRs:**
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` §Consequences row 5 — constructor injection of `EventLog` is the Phase-5 contract.
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` §Consequences — `TrustScorer` reads the internal stream for `AdapterDegraded` markers.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` §Decision (3) — `TrustOutcome` is a Pydantic discriminated union pattern; `SignalKind` is a `NewType`.
- **Cross-phase precedent:**
  - `../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — Phase 5's widening proves the registry's extension-by-addition shape.
  - `../../05-sandbox-trust-gates/final-design.md §6` — `GateRunner.run` consumes `TrustScorer.score`; the signature shipped here is the signature Phase 5 wraps.
- **Existing code to mirror:**
  - `src/codegenie/probes/registry.py` — `@register_probe` instance-with-default-singleton shape (CLAUDE.md §Registry-dispatched coordinator).
  - `src/codegenie/indices/freshness.py` (Phase 2) — `@register_index_freshness_check(IndexName)` shape; the closest existing analog.
- **This phase, parallel stories:**
  - S6-01 — the `EventLog` this scorer reads from; `AdapterDegraded` is one of the 16 internal-stream variants.
  - S6-04 — the orchestrator constructs `TrustScorer(event_log=self._event_log)` and passes the 5 signals at Stage 6.
  - S5-04 — `LockfilePolicy` generates the `lockfile_policy` `TrustSignal` payload.
  - S1-01 — provides the `SignalKind` newtype.

## Goal

Land `src/codegenie/transforms/trust_scorer.py` exposing `TrustScorer(event_log)` with `score(signals: list[TrustSignal]) -> TrustOutcome`; strict-AND on `passed`; `confidence` folded from `AdapterDegraded` events in `event_log.replay()` filtered to the constructor-supplied `workflow_id`. Also land `src/codegenie/transforms/signal_kinds.py` with the `@register_signal_kind("name")` open registry; Phase 3 registers `build`, `install`, `tests`, `lockfile_policy`, `cve_delta` at import time.

## Acceptance criteria

- [ ] `src/codegenie/transforms/trust_scorer.py` exists; `from codegenie.transforms.trust_scorer import TrustScorer, TrustSignal, TrustOutcome` succeeds.
- [ ] `TrustScorer.__init__(self, event_log: EventLog) -> None` requires the `event_log` argument — no default value, no `Optional`. Constructing `TrustScorer()` is a `TypeError`.
- [ ] `score(self, signals: list[TrustSignal]) -> TrustOutcome` implements strict-AND: `outcome.passed = all(s.passed for s in signals)`; `outcome.failing = [s.kind for s in signals if not s.passed]`; `outcome.signals = signals` (preserved verbatim).
- [ ] `outcome.confidence = "degraded"` if **any** `AdapterDegraded` event in `self._event_log.replay()` carries `workflow_id == self._event_log.workflow_id`; otherwise `"high"`.
- [ ] `TrustSignal` is a `frozen=True, extra="forbid"` Pydantic model with fields `kind: SignalKind`, `passed: bool`, `details: dict[str, str | int | bool | float]` (primitives only — `dict[str, Any]` is forbidden by AST fence).
- [ ] `TrustOutcome` is a `frozen=True, extra="forbid"` Pydantic model with fields `passed: bool`, `failing: list[SignalKind]`, `signals: list[TrustSignal]`, `confidence: Literal["high", "degraded"]`.
- [ ] `score(...)` raises `UnregisteredSignalKind(kind)` if any `signal.kind` is not in the `SignalKind` registry at call time. This is the *only* validation `score` performs — registry membership; passing an unregistered kind is a programming error, not a data error.
- [ ] `src/codegenie/transforms/signal_kinds.py` exists; exports `register_signal_kind(name: str) -> SignalKind` decorator-like helper, `signal_kind_registry: SignalKindRegistry` instance (mirrors `default_registry` shape from `PluginRegistry`), and the **5 Phase 3 registrations** as module-level calls: `BUILD = register_signal_kind("build")`, `INSTALL = register_signal_kind("install")`, `TESTS = register_signal_kind("tests")`, `LOCKFILE_POLICY = register_signal_kind("lockfile_policy")`, `CVE_DELTA = register_signal_kind("cve_delta")`.
- [ ] `register_signal_kind(name)` is **idempotent for the same `(name)` call**, but raises `SignalKindAlreadyRegistered(name)` if called twice from different modules — mirrors `PluginRegistry`'s `PluginAlreadyRegistered` shape.
- [ ] Per-test isolation: `signal_kind_registry` exposes a `fresh()` classmethod for test fixtures (pattern matches Phase 3 ADR-0002's `PluginRegistry()` per-test instance discipline).
- [ ] Strict-AND across all `2^5 = 32` signal combinations is unit-tested (parametrized).
- [ ] Confidence propagation: emitting one `AdapterDegraded` to the injected log before calling `score(...)` flips `confidence` to `"degraded"`; without the event, `"high"`.
- [ ] Cross-workflow safety: an `AdapterDegraded` event with a **different** `workflow_id` in the *same* log does NOT flip `confidence` (the filter is on `workflow_id`).
- [ ] No module-level mutable state outside the registry singleton (per CLAUDE.md §Conventions); the scorer carries `event_log` on the instance only.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. Write `tests/unit/transforms/test_trust_scorer.py` (red); confirm `ImportError`.
2. Create `src/codegenie/transforms/signal_kinds.py`:
   - `class SignalKindRegistry: def register(self, name: str) -> SignalKind; def __contains__(self, kind: SignalKind) -> bool; def fresh(self) -> "SignalKindRegistry"`.
   - Module-level `signal_kind_registry = SignalKindRegistry()`.
   - `def register_signal_kind(name: str, *, registry: SignalKindRegistry | None = None) -> SignalKind: return (registry or signal_kind_registry).register(name)`.
   - The 5 Phase 3 registrations as module-level calls. (These execute at import time — that is the registration mechanism.)
3. Create `src/codegenie/transforms/trust_scorer.py`:
   - Imports: `TrustSignal`, `TrustOutcome` (Pydantic models defined in this file), `EventLog`, `AdapterDegraded` from `codegenie.plugins.events`, `signal_kind_registry`.
   - `class TrustScorer`:
     - `__init__(self, event_log: EventLog) -> None: self._event_log = event_log`.
     - `def score(self, signals: list[TrustSignal]) -> TrustOutcome`:
       - Validate every `signal.kind in signal_kind_registry` — raise `UnregisteredSignalKind` on miss.
       - Compute `passed = all(s.passed for s in signals)`; `failing = [s.kind for s in signals if not s.passed]`.
       - Walk `self._event_log.replay()`; filter to `AdapterDegraded` events with matching `workflow_id`; `confidence = "degraded" if any(...) else "high"`.
       - Return `TrustOutcome(passed=passed, failing=failing, signals=signals, confidence=confidence)`.
4. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/test_trust_scorer.py`.

```python
# tests/unit/transforms/test_trust_scorer.py
from datetime import datetime, timezone
from pathlib import Path
from itertools import product

import pytest

from codegenie.plugins.events import EventLog, AdapterDegraded
from codegenie.transforms.trust_scorer import (
    TrustScorer, TrustSignal, TrustOutcome, UnregisteredSignalKind,
)
from codegenie.transforms.signal_kinds import (
    BUILD, INSTALL, TESTS, LOCKFILE_POLICY, CVE_DELTA,
    register_signal_kind, signal_kind_registry, SignalKindAlreadyRegistered,
)
from codegenie.types.identifiers import WorkflowId, EventId, SignalKind


def _wf() -> WorkflowId:
    return WorkflowId("01HFEEDFACE0000000000000000")


def _log(tmp_path: Path) -> EventLog:
    return EventLog(root=tmp_path, workflow_id=_wf())


def test_constructor_requires_event_log():
    with pytest.raises(TypeError):
        TrustScorer()  # type: ignore[call-arg]


def test_strict_and_all_pass(tmp_path: Path):
    scorer = TrustScorer(event_log=_log(tmp_path))
    signals = [TrustSignal(kind=k, passed=True, details={})
               for k in (BUILD, INSTALL, TESTS, LOCKFILE_POLICY, CVE_DELTA)]
    out = scorer.score(signals)
    assert out.passed is True
    assert out.failing == []
    assert out.confidence == "high"


@pytest.mark.parametrize("combo", list(product([False, True], repeat=5)))
def test_strict_and_2_to_5(tmp_path: Path, combo):
    scorer = TrustScorer(event_log=_log(tmp_path))
    kinds = [BUILD, INSTALL, TESTS, LOCKFILE_POLICY, CVE_DELTA]
    signals = [TrustSignal(kind=k, passed=p, details={})
               for k, p in zip(kinds, combo)]
    out = scorer.score(signals)
    assert out.passed == all(combo)
    assert set(out.failing) == {k for k, p in zip(kinds, combo) if not p}


def test_confidence_degrades_when_adapter_degraded_event_present(tmp_path: Path):
    log = _log(tmp_path)
    log.emit_internal(AdapterDegraded(
        event_id=EventId("01H...01"), workflow_id=_wf(),
        timestamp=datetime.now(timezone.utc), adapter="dep_graph", reason="parse_error"))
    log.flush()
    scorer = TrustScorer(event_log=log)
    out = scorer.score([TrustSignal(kind=BUILD, passed=True, details={})])
    assert out.confidence == "degraded"


def test_confidence_high_when_adapter_degraded_is_other_workflow(tmp_path: Path):
    log = _log(tmp_path)
    other_wf = WorkflowId("01HOTHERWORKFLOW000000000000")
    log.emit_internal(AdapterDegraded(
        event_id=EventId("01H...01"), workflow_id=other_wf,
        timestamp=datetime.now(timezone.utc), adapter="dep_graph", reason="x"))
    log.flush()
    scorer = TrustScorer(event_log=log)
    out = scorer.score([TrustSignal(kind=BUILD, passed=True, details={})])
    assert out.confidence == "high"  # other workflow's degradation does not bleed


def test_unregistered_signal_kind_rejected(tmp_path: Path):
    scorer = TrustScorer(event_log=_log(tmp_path))
    bogus = SignalKind("not_registered_anywhere")
    with pytest.raises(UnregisteredSignalKind):
        scorer.score([TrustSignal(kind=bogus, passed=True, details={})])


def test_register_signal_kind_rejects_duplicate():
    fresh = signal_kind_registry.fresh()
    register_signal_kind("custom", registry=fresh)
    with pytest.raises(SignalKindAlreadyRegistered):
        register_signal_kind("custom", registry=fresh)


def test_phase3_five_kinds_registered_at_import():
    assert BUILD in signal_kind_registry
    assert INSTALL in signal_kind_registry
    assert TESTS in signal_kind_registry
    assert LOCKFILE_POLICY in signal_kind_registry
    assert CVE_DELTA in signal_kind_registry


def test_trust_signal_rejects_dict_str_any_in_details():
    # details is primitives-only; nested objects rejected.
    with pytest.raises(Exception):  # Pydantic ValidationError
        TrustSignal(kind=BUILD, passed=True,
                    details={"nested": {"oops": "object"}})  # type: ignore[dict-item]
```

Run; confirm `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

Implement minimally:
- `SignalKindRegistry` is a `set[SignalKind]` under the hood; `register()` returns the typed `SignalKind` for downstream use.
- `TrustScorer.score` is ~10 lines: validate, compute strict-AND, walk the log filtering on `workflow_id` + `event_type == "adapter_degraded"`, return.

### Refactor — clean up

- Module docstrings cite ADR-0001 + ADR-0005 + Gap 5.
- `score` is pure on `signals` modulo the `event_log` read — the read is bounded to one replay pass; document the O(N) cost (where N is the workflow's internal-stream event count). For Phase 3's ~50-events-per-workflow envelope this is sub-millisecond; Phase 5+ with more retries will need re-evaluation (left to that phase's perf bench).
- Add a `__repr__` to `TrustOutcome` that does NOT include `signals` (the list can be long; the repr should be one line for log readability).
- Verify the AST fence (S1-05) catches any `dict[str, Any]` in `details` or anywhere in this module.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/trust_scorer.py` | New file — `TrustScorer`, `TrustSignal`, `TrustOutcome`, `UnregisteredSignalKind` |
| `src/codegenie/transforms/signal_kinds.py` | New file — `SignalKindRegistry`, `register_signal_kind`, Phase-3 registrations (`BUILD`, `INSTALL`, `TESTS`, `LOCKFILE_POLICY`, `CVE_DELTA`) |
| `src/codegenie/transforms/__init__.py` | Re-export `TrustScorer`, `TrustSignal`, `TrustOutcome` (per ADR-0001 §Consequences) |
| `tests/unit/transforms/test_trust_scorer.py` | New file — strict-AND 2^5, confidence propagation, cross-workflow filter, registry semantics |

## Out of scope

- **Phase 5's widening with `trace`, `policy` signal kinds** — Phase 5 (05-ADR-0003) lands the new `register_signal_kind` calls in its own module; zero edits to this story's code.
- **Phase 7's widening with `baseimage`, `shell_presence`** — Phase 7's distroless plugin lands them; zero edits here.
- **Per-signal confidence (where one signal is degraded but others are not)** — Phase 3's `confidence` is whole-workflow; Phase 5+ may amend.
- **`TrustSignal.details` schema validation per-kind** — `details` is a free-form primitive dict; per-kind schemas are a Phase 5 amendment if needed.
- **Retry decision** — `TrustScorer` returns `TrustOutcome`; the orchestrator (S6-04) is the consumer; Phase 3 alone does NOT retry. Phase 5's `GateRunner` is the retry envelope (ADR-0007).
- **Reading the spanning stream** — confidence is folded from the *internal* stream only (`AdapterDegraded` is an internal-stream variant per S6-01); the spanning stream is irrelevant here.

## Notes for the implementer

- **Constructor injection is not negotiable** (Gap 5 fix). A reviewer might suggest "convenience": `TrustScorer.score(signals, *, event_log=None)` with a default ambient lookup. **Reject**. The whole point of Gap 5 is that ambient state is unmockable, hides coupling, and breaks under concurrent workflows in the same process. The constructor argument is the contract.
- The "mildly cyclical" note in `../phase-arch-design.md §Component design C6` refers to the scorer reading the same workflow's event log it indirectly contributed to. This is fine — `AdapterDegraded` events are written *before* Stage 6 (during bundle build), so the read is from a closed prefix. A test that confirms this (`AdapterDegraded` written → `flush()` → `score()` reads it) is the replay-tested guarantee.
- The 5 module-level registrations in `signal_kinds.py` execute at *import time*. This is the same shape as `@register_probe` (Phase 2 ADR-0003) — the import is the registration. Test discipline: tests that need to mutate the registry use `signal_kind_registry.fresh()` and pass it explicitly to `register_signal_kind(name, registry=fresh)`.
- `SignalKindAlreadyRegistered` and `UnregisteredSignalKind` are **categorically different** errors: the first is a configuration error at import time (two modules registered the same name); the second is a usage error at `score` time (a caller passed a kind no module registered). Don't conflate them under a single `SignalKindError`.
- The `details: dict[str, str | int | bool | float]` constraint is **primitives only** (no `list[str]` even though §C9 allows it on events). Rationale: `details` is consumed by humans reading the `remediation-report.yaml`; nested structures hurt scan-ability. If a signal genuinely needs a list, that's a sign the signal should be split into N signals.
- The `confidence: Literal["high", "degraded"]` field is **not a sum type** — it's a closed Literal. Two values, no payload. ADR-0010 §Decision (3)'s tagged-union pattern applies where the variants carry payload; `confidence` carries none. Don't over-engineer.
- The replay loop in `score()` walks `event_log.replay()` once per call. If a perf bench (S9-03) shows this is a bottleneck for long-running workflows, the right answer is to cache the `AdapterDegraded` count on the `EventLog` itself (an `emit_internal` side-effect); do NOT cache on the `TrustScorer` (the scorer must remain stateless across `score` calls so the orchestrator can call it multiple times safely in Phase 5).
- The `failing` list is **ordered as input**, not sorted. Test discipline: assert `set(out.failing)` when order doesn't matter; assert `out.failing == [...]` when it does (it shouldn't, for Phase 3).
- The `score` method's signature matches Phase 5's `StrictAndGate` adapter call site exactly (`../../05-sandbox-trust-gates/final-design.md §6`). Renaming the parameter from `signals` to `inputs` or adding a kwarg breaks Phase 5; the contract snapshot test in S6-06 will catch it but reviewers should catch it first.
