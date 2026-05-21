# Story S6-02 — `TrustScorer` with constructor-injected `EventLog` + `SignalKind` open registry (Gap 5 fix)

**Step:** Step 6 — RemediationOrchestrator, TrustScorer, two-stream EventLog, SubgraphNode Protocol, end-to-end happy path
**Status:** Done — GREEN 2026-05-21 (phase-story-executor; see [`_attempts/S6-02.md`](_attempts/S6-02.md) for the per-AC evidence table, the five as-built drift resolutions, and the gate log — `trust_scorer.py` + `signal_kinds.py` both 100% line+branch coverage, `make check` green: 5950 passed + 371 fence, `ruff` + `mypy --strict` + `import-linter` 6/6 all clean). **As-built note (authoritative — supersedes conflicting outline/TDD-plan statements below):** `TrustSignal` / `TrustOutcome` were already shipped by S1-03 in `transforms/outcomes.py` and are **re-exported** from `trust_scorer.py`, not redefined (D1); `EventLog` gained an additive public `workflow_id` attribute (D3, so `events.py` is also touched); the as-built `AdapterDegraded` carries `adapter_name` / `signal` / `detail` (D2).
**Effort:** M
**Depends on:** S6-01
**ADRs honored:** ADR-0001 (`TrustScorer.__init__(event_log)` is the named Phase-5 contract — constructor-injection is mandatory), ADR-0005 (the injected log is the two-stream `EventLog`), ADR-0010 (`TrustOutcome` tagged-union, `SignalKind` newtype), [Phase 5 ADR-0003](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md) (Phase 5 widens via `@register_signal_kind`)

## Validation notes — 2026-05-19

**Verdict:** HARDENED. The Phase-3 commitments (constructor-injection, strict-AND, open registry) were already strong; the executor needs tighter tests + extra ACs so a wrong impl cannot slip through. Changes applied:

- **AC-DUP rewritten.** The previous AC was self-contradictory ("idempotent for the same `(name)` call, but raises … if called twice from different modules"). `PluginRegistry.register` is the named precedent and it **always raises** on duplicate (`src/codegenie/plugins/registry.py:119-122`). The hardened AC pins "always raises; carries `.name`, `.existing_origin`, `.new_origin`" to mirror `PluginAlreadyRegistered(name, existing, duplicate)` in [errors.py:74-78](../../../../src/codegenie/plugins/errors.py).
- **"Decorator-like helper" terminology corrected** → "registration helper / function call." `register_plugin` is explicitly a function call, not a decorator (`plugins/registry.py:10-16`); same applies here. The "decorator" framing in Phase-2 / Phase-3 prose refers to `@register_probe`, not this function-call shape.
- **`failing` ordering pinned** (Coverage F2 + Test-Quality F2). Notes already said "ordered as input"; now an AC + tighter parametrize test (list equality, not set equality) enforces it.
- **`pytest.raises(Exception)` tightened** to `pytest.raises(pydantic.ValidationError)` (Test-Quality F1) — a wrong impl raising `TypeError` would have silently passed.
- **`details` rejection parametrized** over `list`, `None`, `bytes`, `datetime`, nested-dict, raw `object` (Coverage F3). Single-case test let a permissive impl through.
- **Stateless `score()` AC + test** (Coverage F1). Notes mandated this but no AC verified it. The laziest wrong impl caches `_degraded_flag` in `__init__`; the new test emits an `AdapterDegraded` *between* two `score()` calls and asserts the second outcome reflects it.
- **Empty-signals AC** (Coverage F4). Architecture pins Stage 6 to exactly 5 signals; `score([])` is a caller bug. Pin a typed `EmptySignals` raise so a wrong impl can't silently return `passed=True, confidence="high"`.
- **Cross-event-type test** (Coverage F5). Emitting a non-`AdapterDegraded` internal event (`PluginResolved`) with matching `workflow_id` must NOT flip confidence. The previous tests only ruled out cross-workflow leakage, not cross-event-type leakage.
- **`outcome.signals` preservation test** (Coverage F6). AC said "preserved verbatim"; no test asserted list order or membership.
- **Hypothesis property test** (Test-Quality F5). The confidence fold is a clean property — for any sequence of emitted events, `confidence == "degraded" iff any(matching AdapterDegraded)`. Pinning it as Hypothesis future-proofs against subtle filter bugs.
- **Pure-helper discipline added** (Design-Patterns F2 — functional core / imperative shell, CLAUDE.md §Conventions). `_compute_strict_and(signals)` and `_has_adapter_degraded_for_workflow(events, workflow_id)` are pure; `score()` is the imperative shell. An AST-walking AC + a small purity test pin the split (matches the Phase-1 / Phase-2 probe discipline).
- **Import-time registration AC** (Consistency F7). Pins that `import codegenie.transforms.signal_kinds` (or transitively via `trust_scorer`) registers the 5 Phase-3 kinds. Notes-for-implementer adds the obligation that `transforms/__init__.py` imports `signal_kinds` to make the registration unconditional for any `from codegenie.transforms import …` consumer.
- **`test_phase3_five_kinds_registered_at_import` strengthened** (Test-Quality F3). Old test was satisfied by *any* prior import; new assertion equates the module-attr `BUILD` to a registry-lookup result and walks the AST of `signal_kinds.py` to confirm 5 top-level `register_signal_kind(...)` calls — survives the mutation "the registrations moved into a function never called."
- **Notes for the implementer extended** with: (a) the 5th-registry audit anchor + kernel-extract deferral (per `plugins/registry.py:18-49`); (b) the option to use `InMemorySink` from S6-01 for faster tests; (c) the explicit `transforms/__init__.py` import obligation.

Goal, scope, and Phase-5 contract surface unchanged.

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

- [x] **AC-1 (module surface).** `src/codegenie/transforms/trust_scorer.py` exists; `from codegenie.transforms.trust_scorer import TrustScorer, TrustSignal, TrustOutcome, UnregisteredSignalKind, EmptySignals` succeeds.
- [x] **AC-2 (constructor injection mandatory — Gap 5).** `TrustScorer.__init__(self, event_log: EventLog) -> None` requires the `event_log` argument — no default value, no `Optional`. Constructing `TrustScorer()` is a `TypeError`. Per ADR-0001 §Consequences row 5, ambient-state lookup is rejected; no `os.environ` / thread-local / classmethod alternative exists on the class.
- [x] **AC-3 (strict-AND on `passed`).** `score(self, signals: list[TrustSignal]) -> TrustOutcome` computes `outcome.passed = all(s.passed for s in signals)` for **non-empty** `signals`.
- [x] **AC-4 (`failing` is order-preserving, not sorted).** `outcome.failing == [s.kind for s in signals if not s.passed]` — input order is preserved; the implementation MUST NOT sort, deduplicate, or `frozenset`-the list. Pinned because future consumers (Phase 5's gate-runner; the remediation-report writer S5-05) read the order to display the first-failing signal to humans.
- [x] **AC-5 (`signals` preserved verbatim).** `outcome.signals == signals`; each element is the same `TrustSignal` instance (frozen, identity-bearing via Pydantic `model_copy(deep=False)` semantics). The scorer is a fold, not a transformer — it must NOT rebuild signal objects.
- [x] **AC-6 (confidence fold filtered by `workflow_id`).** `outcome.confidence == "degraded"` if **any** event yielded by `self._event_log.replay()` is an `AdapterDegraded` whose `workflow_id == self._event_log.workflow_id`; otherwise `"high"`. The filter is on **both** event-type **and** workflow_id; neither alone flips confidence.
- [x] **AC-7 (`TrustSignal` shape).** `TrustSignal` is a `frozen=True, extra="forbid"` Pydantic model with fields `kind: SignalKind` (the `NewType` from `codegenie.types.identifiers`, not a fresh declaration), `passed: bool`, `details: dict[str, str | int | bool | float]`. Non-primitive `details` values (list, tuple, None, bytes, datetime, nested dict, arbitrary objects) raise `pydantic.ValidationError` at construction. The S1-05 AST fence forbids `dict[str, Any]` anywhere in this module.
- [x] **AC-8 (`TrustOutcome` shape).** `TrustOutcome` is a `frozen=True, extra="forbid"` Pydantic model with fields `passed: bool`, `failing: list[SignalKind]`, `signals: list[TrustSignal]`, `confidence: Literal["high", "degraded"]`. `confidence` is a closed `Literal`, not a sum type — ADR-0010's tagged-union discipline applies only where variants carry payload (Notes for implementer §5).
- [x] **AC-9 (unregistered-kind rejection).** `score(...)` raises `UnregisteredSignalKind(kind)` if any `signal.kind` is not in the `SignalKind` registry at call time. This is the **only** validation `score` performs against signals; registry membership failure is a programming error, not a data error. `UnregisteredSignalKind` is declared in `trust_scorer.py` and carries a typed `.kind: SignalKind` attribute.
- [x] **AC-10 (empty-signals rejection).** `score([])` raises `EmptySignals` (typed, no payload). The architecture pins Stage 6 to exactly 5 signals (`phase-arch-design.md §Control flow` step 8); an empty list is a caller bug. The alternative — silently returning `passed=True, failing=[], confidence="high"` — would mis-report a broken Stage-6 collection as a successful workflow.
- [x] **AC-11 (`signal_kinds` module surface).** `src/codegenie/transforms/signal_kinds.py` exists; exports `SignalKindRegistry`, `SignalKindAlreadyRegistered`, `register_signal_kind(name: str, *, registry: SignalKindRegistry | None = None) -> SignalKind` **registration helper (function call, NOT a class decorator** — mirrors `register_plugin`'s shape per `plugins/registry.py:10-16` module docstring), `signal_kind_registry: Final[SignalKindRegistry]` singleton, and the **5 Phase 3 module-level registrations** in this exact order: `BUILD = register_signal_kind("build")`, `INSTALL = register_signal_kind("install")`, `TESTS = register_signal_kind("tests")`, `LOCKFILE_POLICY = register_signal_kind("lockfile_policy")`, `CVE_DELTA = register_signal_kind("cve_delta")`.
- [x] **AC-12 (import-time registration is the registration mechanism).** Loading `codegenie.transforms.signal_kinds` (directly or transitively via `codegenie.transforms` / `codegenie.transforms.trust_scorer`) registers the 5 Phase-3 kinds. `transforms/__init__.py` imports `signal_kinds` at module-import time so any `from codegenie.transforms import TrustScorer` consumer observes the populated registry. A test asserts the registry contains the 5 names after a fresh `importlib.import_module("codegenie.transforms")` (run in a subprocess so prior-test side effects can't satisfy it).
- [x] **AC-13 (duplicate-name rejection, mirrors `PluginAlreadyRegistered`).** `register_signal_kind(name, registry=r)` raises `SignalKindAlreadyRegistered(name, existing, duplicate)` if `name` is already in `r`. The exception carries a typed `.name: SignalKind` attribute and `.existing` / `.duplicate` string fields naming both `module.qualname` call sites (mirrors `PluginAlreadyRegistered.__init__(name, existing, duplicate)` in [`src/codegenie/plugins/errors.py:74-78`](../../../../src/codegenie/plugins/errors.py)). There is **no idempotent path** — every duplicate raises, regardless of caller. Tests that need re-registration use `signal_kind_registry.fresh()`.
- [x] **AC-14 (per-test isolation).** `SignalKindRegistry.fresh()` is a classmethod returning a clean instance with zero registrations; tests construct fresh registries and pass them through `register_signal_kind(name, registry=fresh)` (matches Phase 3 ADR-0002's `PluginRegistry()` per-test instance discipline — `plugins/registry.py` lines 175-186).
- [x] **AC-15 (functional core / imperative shell).** `trust_scorer.py` exposes two **pure** helpers — `_compute_strict_and(signals: list[TrustSignal]) -> tuple[bool, list[SignalKind]]` and `_has_adapter_degraded_for_workflow(events: Iterable[Event], workflow_id: WorkflowId) -> bool` — and the impure shell `TrustScorer.score`. The pure helpers MUST NOT touch the event log, the filesystem, or any module-level mutable state; a small AST-walk test asserts the helpers do not name `EventLog`, `replay`, `open`, `Path`, or `os` in their bodies (matches the Phase-1 / Phase-2 functional-core discipline noted in CLAUDE.md §Conventions).
- [x] **AC-16 (stateless across calls).** Calling `scorer.score(...)` twice on the same `TrustScorer` instance, with an `AdapterDegraded` event emitted to the injected log **between** the two calls, the second outcome's `confidence` reflects the new event (i.e. flips from `"high"` to `"degraded"`). The scorer MUST NOT cache the degraded flag in `__init__` or memoize across `score()` calls. A test pins this directly.
- [x] **AC-17 (cross-event-type safety).** Emitting a non-`AdapterDegraded` internal event (e.g. `PluginResolved`) with `workflow_id == self._event_log.workflow_id` does NOT flip `confidence` to `"degraded"`. The filter is on event-type AND workflow_id, not workflow_id alone.
- [x] **AC-18 (cross-workflow safety).** An `AdapterDegraded` event with a **different** `workflow_id` in the same log does NOT flip `confidence`. (Sibling of AC-17 on the workflow_id dimension.)
- [x] **AC-19 (strict-AND parametric, list-equality).** Strict-AND across all `2^5 = 32` signal combinations is unit-tested (parametrized over `itertools.product([False, True], repeat=5)`). The test asserts `out.failing == [k for k, p in zip(kinds, combo) if not p]` (list equality, not `set(out.failing) == {...}`) so a sorted-`failing` implementation does NOT pass.
- [x] **AC-20 (no module-level mutable state).** No module-level mutable state outside the registry singleton (`signal_kind_registry`) — no `_cached_*`, no module-level `dict[..., ...] = {}`, no `Final[set[...]] = set()` populated lazily. Pinned by AST-walk + import-purity test.
- [x] **AC-21 (TDD).** TDD red test exists, committed, green.
- [x] **AC-22 (gates clean).** `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. Write `tests/unit/transforms/test_trust_scorer.py` (red); confirm `ImportError`.
2. Create `src/codegenie/transforms/signal_kinds.py`:
   - `class SignalKindRegistry`:
     - `__init__(self) -> None: self._kinds: dict[SignalKind, str] = {}` (value is the `module.qualname` origin string, mirrors `PluginRegistry._origins` at `plugins/registry.py:101`).
     - `register(self, name: str, *, origin: str) -> SignalKind`: collision check then insert; raise `SignalKindAlreadyRegistered(name, existing=..., duplicate=origin)` on duplicate.
     - `__contains__(self, kind: SignalKind) -> bool`.
     - `@classmethod def fresh(cls) -> "SignalKindRegistry"`: returns a new empty instance.
   - `class SignalKindAlreadyRegistered(CodegenieError)`: typed `.name: SignalKind`, `.existing: str`, `.duplicate: str`; message names both call sites (mirrors `PluginAlreadyRegistered` in `plugins/errors.py:74-78`).
   - `signal_kind_registry: Final[SignalKindRegistry] = SignalKindRegistry()`.
   - `def register_signal_kind(name: str, *, registry: SignalKindRegistry | None = None) -> SignalKind`: function call (NOT a class decorator); resolves `origin` via `inspect.stack()[1]`'s frame info (`"<module>.<qualname>"`) so the duplicate error names both call sites without the caller having to pass `origin` explicitly. Delegates to `(registry or signal_kind_registry).register(name, origin=origin)`.
   - The 5 Phase 3 registrations as module-level calls — execute at import time; that is the registration mechanism.
3. Create `src/codegenie/transforms/trust_scorer.py`:
   - Imports: `TrustSignal`, `TrustOutcome` (Pydantic models defined in this file), `EventLog`, `AdapterDegraded` from `codegenie.plugins.events`, `signal_kind_registry` from `codegenie.transforms.signal_kinds`.
   - `class UnregisteredSignalKind(CodegenieError)`: typed `.kind: SignalKind`.
   - `class EmptySignals(CodegenieError)`: no payload.
   - **Pure helpers (functional core; AC-15):**
     - `def _compute_strict_and(signals: list[TrustSignal]) -> tuple[bool, list[SignalKind]]`: returns `(all(s.passed for s in signals), [s.kind for s in signals if not s.passed])`. No I/O, no log reads.
     - `def _has_adapter_degraded_for_workflow(events: Iterable[Event], workflow_id: WorkflowId) -> bool`: returns `any(isinstance(e, AdapterDegraded) and e.workflow_id == workflow_id for e in events)`. Takes an iterable of events; does NOT touch the log.
   - **Imperative shell:** `class TrustScorer`:
     - `__init__(self, event_log: EventLog) -> None: self._event_log = event_log`.
     - `def score(self, signals: list[TrustSignal]) -> TrustOutcome`:
       - If `not signals`: raise `EmptySignals`.
       - Validate every `signal.kind in signal_kind_registry` — raise `UnregisteredSignalKind(kind)` on miss.
       - Call `_compute_strict_and(signals)` for `passed`, `failing`.
       - Call `_has_adapter_degraded_for_workflow(self._event_log.replay(), self._event_log.workflow_id)`; `confidence = "degraded" if … else "high"`.
       - Return `TrustOutcome(passed=passed, failing=failing, signals=signals, confidence=confidence)`.
4. Update `src/codegenie/transforms/__init__.py` to **import `signal_kinds`** (so the registrations land for any `from codegenie.transforms import …` consumer) and re-export `TrustScorer`, `TrustSignal`, `TrustOutcome`, `UnregisteredSignalKind`, `EmptySignals` per ADR-0001 §Consequences. Module-level `import codegenie.transforms.signal_kinds  # noqa: F401  -- module-level registrations` is the canonical pattern.
5. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/test_trust_scorer.py`.

```python
# tests/unit/transforms/test_trust_scorer.py
import ast
import importlib
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from codegenie.plugins.events import (
    AdapterDegraded, EventLog, InMemorySink, PluginResolved,
)
from codegenie.transforms.trust_scorer import (
    EmptySignals, TrustOutcome, TrustScorer, TrustSignal, UnregisteredSignalKind,
)
from codegenie.transforms.signal_kinds import (
    BUILD, CVE_DELTA, INSTALL, LOCKFILE_POLICY, TESTS,
    SignalKindAlreadyRegistered, SignalKindRegistry,
    register_signal_kind, signal_kind_registry,
)
from codegenie.types.identifiers import EventId, PluginId, SignalKind, WorkflowId


WF = WorkflowId("01HFEEDFACE0000000000000000")
OTHER_WF = WorkflowId("01HOTHERWORKFLOW000000000000")


def _log(tmp_path: Path, wf: WorkflowId = WF) -> EventLog:
    # InMemorySink (S6-01 AC-2) keeps tests fast; tmp_path used for dir layout only.
    return EventLog(root=tmp_path, workflow_id=wf, sink=InMemorySink())


def _ad(wf: WorkflowId = WF, eid: str = "01H...01", reason: str = "parse_error") -> AdapterDegraded:
    return AdapterDegraded(
        event_id=EventId(eid), workflow_id=wf,
        timestamp=datetime.now(timezone.utc), adapter="dep_graph", reason=reason)


def _sig(kind: SignalKind, passed: bool = True) -> TrustSignal:
    return TrustSignal(kind=kind, passed=passed, details={})


# --- AC-2: constructor injection mandatory ---------------------------------

def test_constructor_requires_event_log():
    with pytest.raises(TypeError):
        TrustScorer()  # type: ignore[call-arg]


def test_no_ambient_state_alternative_on_class():
    # Defend Gap 5: no classmethod / module-level helper that resolves
    # event_log from os.environ or any thread-local.
    forbidden = {"from_env", "from_ambient", "current", "for_workflow"}
    assert not (forbidden & set(dir(TrustScorer)))


# --- AC-3 / AC-4 / AC-19: strict-AND, list-equality on `failing` -----------

def test_strict_and_all_pass(tmp_path: Path):
    scorer = TrustScorer(event_log=_log(tmp_path))
    signals = [_sig(k, True) for k in (BUILD, INSTALL, TESTS, LOCKFILE_POLICY, CVE_DELTA)]
    out = scorer.score(signals)
    assert out.passed is True
    assert out.failing == []
    assert out.confidence == "high"


@pytest.mark.parametrize("combo", list(product([False, True], repeat=5)))
def test_strict_and_2_to_5_preserves_input_order(tmp_path: Path, combo):
    scorer = TrustScorer(event_log=_log(tmp_path))
    kinds = [BUILD, INSTALL, TESTS, LOCKFILE_POLICY, CVE_DELTA]
    signals = [_sig(k, p) for k, p in zip(kinds, combo)]
    out = scorer.score(signals)
    assert out.passed == all(combo)
    # List equality (NOT set) — a sorted-`failing` implementation must fail.
    assert out.failing == [k for k, p in zip(kinds, combo) if not p]


def test_failing_preserves_caller_order_not_sorted(tmp_path: Path):
    # Pin the no-sort discipline directly: reversed kind order in the input
    # produces a reversed `failing` list.
    scorer = TrustScorer(event_log=_log(tmp_path))
    rev = [CVE_DELTA, LOCKFILE_POLICY, TESTS, INSTALL, BUILD]
    signals = [_sig(k, False) for k in rev]
    out = scorer.score(signals)
    assert out.failing == rev  # NOT sorted alphabetically


# --- AC-5: signals preserved verbatim --------------------------------------

def test_outcome_signals_preserved_verbatim(tmp_path: Path):
    scorer = TrustScorer(event_log=_log(tmp_path))
    signals = [_sig(BUILD, True), _sig(INSTALL, False)]
    out = scorer.score(signals)
    assert out.signals == signals
    assert [id(s) for s in out.signals] == [id(s) for s in signals]


# --- AC-6 / AC-17 / AC-18: confidence fold -----------------------------------

def test_confidence_degrades_when_adapter_degraded_matches_workflow(tmp_path: Path):
    log = _log(tmp_path)
    log.emit_internal(_ad())
    log.flush()
    scorer = TrustScorer(event_log=log)
    out = scorer.score([_sig(BUILD)])
    assert out.confidence == "degraded"


def test_confidence_high_when_adapter_degraded_is_other_workflow(tmp_path: Path):
    log = _log(tmp_path)
    log.emit_internal(_ad(wf=OTHER_WF))
    log.flush()
    scorer = TrustScorer(event_log=log)
    out = scorer.score([_sig(BUILD)])
    assert out.confidence == "high"


def test_confidence_high_when_internal_event_is_not_adapter_degraded(tmp_path: Path):
    # AC-17 — same workflow_id, but the event is PluginResolved, not
    # AdapterDegraded. Confidence must NOT flip.
    log = _log(tmp_path)
    log.emit_internal(PluginResolved(
        event_id=EventId("01H...PR"), workflow_id=WF,
        timestamp=datetime.now(timezone.utc),
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        matched_scope="vulnerability-remediation/node/npm", specificity=3))
    log.flush()
    scorer = TrustScorer(event_log=log)
    out = scorer.score([_sig(BUILD)])
    assert out.confidence == "high"


# --- AC-16: stateless across calls -----------------------------------------

def test_score_is_stateless_across_calls(tmp_path: Path):
    log = _log(tmp_path)
    scorer = TrustScorer(event_log=log)
    out1 = scorer.score([_sig(BUILD)])
    assert out1.confidence == "high"

    log.emit_internal(_ad())  # emit BETWEEN the two score() calls
    log.flush()

    out2 = scorer.score([_sig(BUILD)])
    # A wrong impl that cached the degraded flag in __init__ returns "high"
    # both times. The correct impl re-folds the log on each call.
    assert out2.confidence == "degraded"


# --- AC-9: unregistered kind --------------------------------------------------

def test_unregistered_signal_kind_rejected(tmp_path: Path):
    scorer = TrustScorer(event_log=_log(tmp_path))
    bogus = SignalKind("not_registered_anywhere")
    with pytest.raises(UnregisteredSignalKind) as excinfo:
        scorer.score([TrustSignal(kind=bogus, passed=True, details={})])
    assert excinfo.value.kind == bogus


# --- AC-10: empty signals ---------------------------------------------------

def test_empty_signals_rejected(tmp_path: Path):
    scorer = TrustScorer(event_log=_log(tmp_path))
    with pytest.raises(EmptySignals):
        scorer.score([])


# --- AC-7: details rejects non-primitive values -----------------------------

@pytest.mark.parametrize("bad_value", [
    ["x"],                                    # list
    ("a", "b"),                               # tuple
    None,                                     # None
    b"bytes",                                 # bytes
    datetime.now(timezone.utc),               # datetime
    {"nested": "object"},                     # nested dict
    object(),                                 # arbitrary object
])
def test_trust_signal_details_primitives_only(bad_value):
    with pytest.raises(ValidationError):
        TrustSignal(kind=BUILD, passed=True,
                    details={"k": bad_value})  # type: ignore[dict-item]


# --- AC-13: duplicate-name rejection carries both call sites ----------------

def test_register_signal_kind_rejects_duplicate_with_origin_payload():
    fresh = SignalKindRegistry.fresh()
    register_signal_kind("custom", registry=fresh)
    with pytest.raises(SignalKindAlreadyRegistered) as excinfo:
        register_signal_kind("custom", registry=fresh)
    err = excinfo.value
    assert err.name == SignalKind("custom")
    assert err.existing  # non-empty origin string for the first registration
    assert err.duplicate  # non-empty origin string for the second registration
    assert err.existing != err.duplicate or "test_trust_scorer" in err.existing
    # Message names both for human grep
    assert "custom" in str(err)


# --- AC-14: per-test isolation via fresh() ---------------------------------

def test_fresh_registry_is_empty():
    fresh = SignalKindRegistry.fresh()
    assert SignalKind("build") not in fresh
    assert SignalKind("anything") not in fresh


# --- AC-12: import-time registration is the registration mechanism ---------

def test_phase3_five_kinds_registered_at_import():
    # Direct module-attribute assertion: BUILD === the SignalKind value the
    # registry was asked to register. A wrong impl that exports the constants
    # but skips the register() side effect would fail `BUILD in registry`.
    for name, const in [
        ("build", BUILD), ("install", INSTALL), ("tests", TESTS),
        ("lockfile_policy", LOCKFILE_POLICY), ("cve_delta", CVE_DELTA),
    ]:
        assert const == SignalKind(name)
        assert const in signal_kind_registry


def test_signal_kinds_module_has_5_top_level_register_calls():
    # AST-walk: the registrations must be MODULE-LEVEL calls (not inside a
    # function that nothing invokes). Survives the mutation "moved into init()".
    src = Path(importlib.import_module("codegenie.transforms.signal_kinds").__file__).read_text()
    tree = ast.parse(src)
    top_calls = [
        n for n in tree.body
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Call)
        and getattr(n.value.func, "id", None) == "register_signal_kind"
    ]
    assert len(top_calls) == 5


def test_fresh_subprocess_import_populates_default_registry(tmp_path: Path):
    # Strongest assertion of import-time registration: a *new* Python process
    # importing codegenie.transforms must observe the 5 kinds — proves no
    # other test's side effect is masking a missing module-level call.
    script = textwrap.dedent("""
        import codegenie.transforms  # triggers transforms/__init__.py import side effects
        from codegenie.transforms.signal_kinds import signal_kind_registry
        from codegenie.types.identifiers import SignalKind
        names = ["build", "install", "tests", "lockfile_policy", "cve_delta"]
        missing = [n for n in names if SignalKind(n) not in signal_kind_registry]
        assert not missing, f"missing: {missing}"
    """)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# --- AC-15: pure helpers (functional core / imperative shell) ---------------

def test_pure_helpers_have_no_io_dependencies():
    # AST-walk: _compute_strict_and and _has_adapter_degraded_for_workflow
    # MUST NOT reference EventLog, replay, open, Path, os, or any I/O symbol.
    src = Path(importlib.import_module("codegenie.transforms.trust_scorer").__file__).read_text()
    tree = ast.parse(src)
    forbidden = {"replay", "open", "Path", "os"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "_compute_strict_and", "_has_adapter_degraded_for_workflow",
        ):
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            attrs = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            assert not (forbidden & (names | attrs)), \
                f"{node.name} references forbidden I/O symbol: {forbidden & (names | attrs)}"


def test_compute_strict_and_is_pure():
    # Smoke test the pure helper independently of EventLog.
    from codegenie.transforms.trust_scorer import _compute_strict_and
    signals = [_sig(BUILD, True), _sig(INSTALL, False), _sig(TESTS, False)]
    passed, failing = _compute_strict_and(signals)
    assert passed is False
    assert failing == [INSTALL, TESTS]


# --- Property test: confidence fold is exactly "any AdapterDegraded matching workflow_id" ---

@given(
    events=st.lists(
        st.tuples(
            st.sampled_from(["adapter_degraded", "plugin_resolved"]),
            st.sampled_from([WF, OTHER_WF]),
        ),
        min_size=0, max_size=20,
    ),
)
def test_confidence_property_iff_matching_adapter_degraded(tmp_path: Path, events):
    log = _log(tmp_path)
    for i, (etype, wf) in enumerate(events):
        if etype == "adapter_degraded":
            log.emit_internal(AdapterDegraded(
                event_id=EventId(f"01H..AD{i:02}"), workflow_id=wf,
                timestamp=datetime.now(timezone.utc),
                adapter="dep_graph", reason="x"))
        else:
            log.emit_internal(PluginResolved(
                event_id=EventId(f"01H..PR{i:02}"), workflow_id=wf,
                timestamp=datetime.now(timezone.utc),
                plugin_id=PluginId("p"), matched_scope="s", specificity=1))
    log.flush()
    scorer = TrustScorer(event_log=log)
    out = scorer.score([_sig(BUILD)])
    expected = "degraded" if any(
        etype == "adapter_degraded" and wf == WF for etype, wf in events
    ) else "high"
    assert out.confidence == expected


# --- AC-20: no module-level mutable state outside the singleton -------------

def test_no_module_level_mutable_caches():
    src = Path(importlib.import_module("codegenie.transforms.trust_scorer").__file__).read_text()
    tree = ast.parse(src)
    suspicious = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id.startswith("_"):
                    # private module-level binds are a smell; allow only
                    # explicit Final constants, not mutable containers.
                    if isinstance(node.value, (ast.Dict, ast.Set, ast.List)):
                        suspicious.append(tgt.id)
    assert not suspicious, f"module-level mutable state in trust_scorer.py: {suspicious}"
```

Run; confirm `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

Implement minimally:
- `SignalKindRegistry` is a `dict[SignalKind, str]` under the hood (the str is the `module.qualname` origin used for duplicate error messages). `register(name, *, origin)` returns the typed `SignalKind` for downstream use.
- `register_signal_kind(name, *, registry=None)` introspects its caller frame via `inspect.stack()` to derive `origin` so call-sites stay terse.
- `TrustScorer.score` is the imperative shell — empty-check, kind-validate, call `_compute_strict_and`, call `_has_adapter_degraded_for_workflow(self._event_log.replay(), self._event_log.workflow_id)`, construct `TrustOutcome`. The two pure helpers carry the business logic.

### Refactor — clean up

- Module docstrings cite ADR-0001 + ADR-0005 + Gap 5 + 05-ADR-0003.
- `score` reads `event_log.replay()` once per call (O(N) where N is the workflow's internal-stream event count). For Phase 3's ~50-events-per-workflow envelope this is sub-millisecond; Phase 5+ with more retries will need re-evaluation (left to that phase's perf bench S9-03). **Do not cache the degraded flag on the scorer** — AC-16 forbids it (the cache would break Phase 5's reuse-the-scorer pattern; ADR-0007).
- Add a `__repr__` to `TrustOutcome` that does NOT include `signals` (the list can be long; the repr should be one line for log readability).
- Verify the AST fence (S1-05) catches any `dict[str, Any]` in `details` or anywhere in this module.
- Verify the AST purity test (AC-15) — pure helpers must not name `EventLog`, `replay`, `open`, `Path`, `os`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/trust_scorer.py` | New file — `TrustScorer`, `TrustSignal`, `TrustOutcome`, `UnregisteredSignalKind` |
| `src/codegenie/transforms/signal_kinds.py` | New file — `SignalKindRegistry`, `register_signal_kind`, Phase-3 registrations (`BUILD`, `INSTALL`, `TESTS`, `LOCKFILE_POLICY`, `CVE_DELTA`) |
| `src/codegenie/transforms/__init__.py` | Re-export `TrustScorer`, `UnregisteredSignalKind`, `EmptySignals`; eager `import signal_kinds` side-effect (`TrustSignal` / `TrustOutcome` were already re-exported from `outcomes`) |
| `src/codegenie/plugins/events.py` | **As-built (D3)** — `EventLog` gains an additive public `workflow_id` attribute the scorer reads (AC-6); S6-01 only used the ctor arg to build the internal-stream path |
| `tests/unit/transforms/test_trust_scorer.py` | New file — strict-AND 2^5, confidence propagation, cross-workflow filter, registry semantics |

## Out of scope

- **Phase 5's widening with `trace`, `policy` signal kinds** — Phase 5 (05-ADR-0003) lands the new `register_signal_kind` calls in its own module; zero edits to this story's code.
- **Phase 7's widening with `baseimage`, `shell_presence`** — Phase 7's distroless plugin lands them; zero edits here.
- **Per-signal confidence (where one signal is degraded but others are not)** — Phase 3's `confidence` is whole-workflow; Phase 5+ may amend.
- **`TrustSignal.details` schema validation per-kind** — `details` is a free-form primitive dict; per-kind schemas are a Phase 5 amendment if needed.
- **Retry decision** — `TrustScorer` returns `TrustOutcome`; the orchestrator (S6-04) is the consumer; Phase 3 alone does NOT retry. Phase 5's `GateRunner` is the retry envelope (ADR-0007).
- **Reading the spanning stream** — confidence is folded from the *internal* stream only (`AdapterDegraded` is an internal-stream variant per S6-01); the spanning stream is irrelevant here.

## Notes for the implementer

- **Constructor injection is not negotiable** (Gap 5 fix). A reviewer might suggest "convenience": `TrustScorer.score(signals, *, event_log=None)` with a default ambient lookup. **Reject**. The whole point of Gap 5 is that ambient state is unmockable, hides coupling, and breaks under concurrent workflows in the same process. The constructor argument is the contract. AC-2's forbidden-names list (`from_env`, `from_ambient`, `current`, `for_workflow`) is deliberately structural — anyone adding such a classmethod opens the door back to ambient-state.
- **5th registry — the kernel-extract trigger is met, but the deferral still holds.** `SignalKindRegistry` is the **5th** decorator-/function-call-registry in the codebase (`probes/registry.py`, `indices/registry.py`, `depgraph/registry.py`, `plugins/registry.py`, this one). The audit anchor at `src/codegenie/plugins/registry.py:18-49` makes the trigger explicit: "N=5 OR a registry needing only the common surface" — N=5 fires. **But** the four prior registries have divergent dispatch shapes (`for_task` + LRU + `sorted_for_dispatch`; `dispatch_all`; `has_strategy` query; `resolve(scope)`-with-extends-walk), and `SignalKindRegistry`'s shape is the smallest (`register` + `__contains__` + `fresh()` — no dispatch). Extracting a shared `KernelRegistry[K, V]` base would couple this minimal registry to the four heavyweight ones. **Defer** following the pattern set in `indices/registry.py:26-31` and `depgraph/registry.py:30-38`. Reword the docstring's audit-anchor paragraph to bump the count to 5 and document the new deferral; the 6th registry's author has a clean grep trail.
- **InMemorySink for tests, disk for production.** S6-01's hardened `EventLog` accepts `sink=InMemorySink()` for tests; this story's TDD plan uses it to avoid `tmp_path` zstd round-trips. Production code constructs `EventLog(root=resolved_cache_dir, workflow_id=…)` and gets the default `ZstdAppendingFileSink`. Do NOT export `InMemorySink` outside the test suite — `__all__` in `events.py` controls the surface.
- **`transforms/__init__.py` must import `signal_kinds`.** The 5 module-level registrations only execute when `signal_kinds.py` is imported. If a consumer writes `from codegenie.transforms import TrustScorer` and never reaches into `signal_kinds`, the registry would be empty and `score()` would raise `UnregisteredSignalKind` on the first BUILD signal. The fix is a one-line `import codegenie.transforms.signal_kinds  # noqa: F401` in `transforms/__init__.py` — pin it with the subprocess-import test (AC-12).
- The "mildly cyclical" note in `../phase-arch-design.md §Component design C6` refers to the scorer reading the same workflow's event log it indirectly contributed to. This is fine — `AdapterDegraded` events are written *before* Stage 6 (during bundle build), so the read is from a closed prefix. A test that confirms this (`AdapterDegraded` written → `flush()` → `score()` reads it) is the replay-tested guarantee.
- The 5 module-level registrations in `signal_kinds.py` execute at *import time*. This is the same shape as `register_plugin` (Phase 3 ADR-0002 §Decision — function call, NOT a class decorator) — the import is the registration. Test discipline: tests that need to mutate the registry use `SignalKindRegistry.fresh()` and pass it explicitly to `register_signal_kind(name, registry=fresh)`.
- `SignalKindAlreadyRegistered` and `UnregisteredSignalKind` are **categorically different** errors: the first is a configuration error at import time (two modules registered the same name); the second is a usage error at `score` time (a caller passed a kind no module registered). Don't conflate them under a single `SignalKindError`.
- The `details: dict[str, str | int | bool | float]` constraint is **primitives only** (no `list[str]` even though §C9 allows it on events). Rationale: `details` is consumed by humans reading the `remediation-report.yaml`; nested structures hurt scan-ability. If a signal genuinely needs a list, that's a sign the signal should be split into N signals.
- The `confidence: Literal["high", "degraded"]` field is **not a sum type** — it's a closed Literal. Two values, no payload. ADR-0010 §Decision (3)'s tagged-union pattern applies where the variants carry payload; `confidence` carries none. Don't over-engineer.
- The replay loop in `score()` walks `event_log.replay()` once per call. If a perf bench (S9-03) shows this is a bottleneck for long-running workflows, the right answer is to cache the `AdapterDegraded` count on the `EventLog` itself (an `emit_internal` side-effect); do NOT cache on the `TrustScorer`. AC-16 pins this structurally — the scorer must remain stateless across `score` calls so the orchestrator can call it multiple times safely in Phase 5.
- The `failing` list is **ordered as input**, not sorted (AC-4). Test discipline: prefer `out.failing == [...]` (list equality); use `set(out.failing) == {...}` only when documenting a deliberate order-agnostic case. The validator-strengthened parametrize test (AC-19) uses list equality so a sorted-`failing` implementation FAILS.
- The `score` method's signature matches Phase 5's `StrictAndGate` adapter call site exactly (`../../05-sandbox-trust-gates/final-design.md §6`). Renaming the parameter from `signals` to `inputs` or adding a kwarg breaks Phase 5; the contract snapshot test in S6-06 will catch it but reviewers should catch it first.
