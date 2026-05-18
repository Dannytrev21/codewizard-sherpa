# Story S6-05 — `TypecheckTypescriptSignal` collector + `@register_signal_kind("typecheck.typescript")`

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** Ready
**Effort:** M
**Depends on:** S6-04 (`./node_modules/.bin/tsc` admitted to `ALLOWED_BINARIES`)
**ADRs honored:** ADR-04-0015 (`typecheck.typescript` SignalKind; Registry + Open/Closed), production ADR-0037 (layered analysis funnel — first `typecheck.<lang>` lands), production ADR-0031 (plugin scoping — signal is plugin-local)

## Context

Roadmap exit criterion #3 + production ADR-0037 commit Phase 4 to landing the **first** `typecheck.<lang>` SignalKind into Phase 3's open `@register_signal_kind` registry. The signal is `typecheck.typescript`; it runs `tsc --noEmit` inside Phase 3's `SubprocessJail` (30 s cap); strict-AND folds it through Phase-3 `TrustScorer` **with zero edits to Phase 3 code** (registry pattern + Open/Closed). Phase 7's distroless plugin won't have a Node toolchain and won't register the signal.

The signal lives at `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`. Phase 3 already shipped `@register_signal_kind` as a decorator-based open registry (CLAUDE.md §Open/Closed seams), so Phase 4 adds one module + one import line — never edits central dispatch.

Strict-AND with baseline (`.codegenie/typecheck/baseline-<repo-sha>.json`) passes iff `new_errors_after <= new_errors_before` — the LLM only needs to not *introduce* new type errors; pre-existing repo-level errors don't block the gate.

This story lands the *base* collector + registration + strict-AND fold-in; the applicability matrix (`tsconfig.json` + `.ts` files detection per Gap 4) is S6-06's surgical follow-up.

## References — where to look

- **Architecture:** [phase-arch-design.md §Component 11 — TypecheckTypescriptSignal](../phase-arch-design.md) (lines 616–623); §Goals — G10 (line 37); §Deployment view (`tsc --noEmit` inside `SubprocessJail`); §Edge case row 9 (missing `tsc`); §Type contracts (line 759 — `TypecheckNodeSignal` Pydantic model); §Design patterns applied row 9 (Registry + Open/Closed).
- **Phase ADRs:** [ADR-04-0015](../ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md) (the whole story is this ADR's implementation).
- **Production ADRs:** [production ADR-0037](../../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md) (first `typecheck.<lang>` lands here); [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) (TrustSignal shape); [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md) (signal is plugin-local).
- **Source design:** [final-design.md §Component 12 — TypecheckTypescriptSignal](../final-design.md); §Goal "typecheck.typescript SignalKind lands".
- **High-level impl:** [High-level-impl.md §Step 6](../High-level-impl.md) Features delivered (`TypecheckTypescriptSignal` paragraph).
- **Existing code:** Phase 3 `@register_signal_kind` decorator (CLAUDE.md §Open/Closed seams names it); Phase 3 `SubprocessJail` (S6-04 amended its allowlist); Phase 3 `SignalCollector` Protocol; Phase 3 `TrustScorer` strict-AND folder.

## Goal

Ship `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py` defining `TypecheckTypescriptSignal` decorated with `@register_signal_kind("typecheck.typescript")` that runs `tsc --noEmit --pretty false` in `SubprocessJail` (30 s cap), folds into Phase-3 `TrustScorer` strict-AND with zero Phase-3 code edits, and emits `TrustSignal(kind="typecheck.typescript", passed=bool, details=..., confidence=...)`.

## Acceptance criteria

- [ ] **Registered exactly once**: `tests/fence/test_typecheck_signal_registered.py` reads Phase-3 signal-kind registry and asserts `"typecheck.typescript"` is present **exactly once** after Phase-4 plugin import (`exactly one entry whose key starts with "typecheck."`).
- [ ] **Implements `SignalCollector` Protocol**: signature matches Phase 3's `SignalCollector` Protocol exactly — `mypy --strict` accepts it as a `SignalCollector`.
- [ ] **Runs `./node_modules/.bin/tsc --noEmit --pretty false`** inside `SubprocessJail` with 30 s cap. Asserted by a `tests/unit/typecheck/test_signal.py::test_invokes_tsc_correctly` mocking `SubprocessJail.run` and inspecting the call args.
- [ ] **Strict-AND fold-in works without Phase-3 edits**: `tests/unit/trust_scorer/test_typecheck_kind.py` constructs a Phase-3 `TrustScorer`, runs it against a fixture repo with the new signal registered, and asserts the strict-AND `TrustOutcome.passed` is False when the signal returns `passed=False` and True when all signals (including `typecheck.typescript`) return `passed=True`. **No edits to `src/codegenie/` Phase-3 trust-scorer code** (asserted by `tests/fence/test_kernel_frozen.py` from S1-07).
- [ ] **Baseline strict-AND**: `.codegenie/typecheck/baseline-<repo-sha>.json` is the per-repo cache. Signal passes iff `new_errors_after <= new_errors_before`. Asserted by `test_signal_passes_when_no_new_errors` (baseline has 5 errors, post-patch tsc emits 5 errors → pass; baseline 5 errors, post-patch 6 errors → fail).
- [ ] **Output shape matches arch §Type contracts**: emits `TrustSignal(kind="typecheck.typescript", passed: bool, details: dict[str, str|int|bool], confidence: Literal["high","medium","low"])` Pydantic frozen-extra-forbid. Phase-4 does not widen the details `dict[str, str|int|bool]` shape (arch line 763).
- [ ] **Timeout behavior**: 30 s cap exceeded ⇒ `TrustSignal(passed=False, details={"timeout": True}, confidence="medium")`. Asserted via mocked `SubprocessJail` returning a `TimedOut` result.
- [ ] **Missing `tsc` behavior** (edge case row 9): `SubprocessJail.run` returns `Completed(exit_code=127)` or `Missing` ⇒ `TrustSignal(passed=False, details={"degraded_reason": "no_tsconfig_or_tsc"}, confidence="medium")`. (S6-06 lifts this to the applicability matrix; S6-05 ships the degraded path.)
- [ ] **Integration test `tests/integration/test_typecheck_signal_catches_signature_drift.py`**: cassette-driven test where the LLM emits a `callsite_rewrite` `PlanProposal` that calls a *hallucinated* method; `tsc` catches the `TS2339 Property 'X' does not exist on type 'Y'` error; signal returns `passed=False`; **gate fails before `npm test` runs** (event ordering in stream: `LeafReturned → SignalEvaluated(typecheck.typescript, passed=False) → GateBlocked` *before* any `NpmTestStarted` event).
- [ ] **No edits to `src/codegenie/plugins/protocols.py`** (kernel-frozen) — asserted by S1-07 fence test continuing green.
- [ ] **No edits to `TrustScorer`** — strict-AND folds the new kind automatically via registry lookup.
- [ ] `make check`, `make typecheck`, `make lint-imports`, `make fence`, `make test` all green.

## Implementation outline

1. Create `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`:
   ```python
   from typing import Literal
   from codegenie.gates.signals import register_signal_kind, SignalCollector, TrustSignal
   from codegenie.exec import run_allowlisted, SubprocessJail
   # ... etc

   @register_signal_kind("typecheck.typescript")
   class TypecheckTypescriptSignal(SignalCollector):
       async def collect(self, repo: RepoSnapshot, ctx: SignalContext) -> TrustSignal:
           # 1. Resolve ./node_modules/.bin/tsc
           # 2. Run inside SubprocessJail, 30s cap
           # 3. Parse stdout for error count
           # 4. Compare against baseline at .codegenie/typecheck/baseline-<repo-sha>.json
           # 5. Return TrustSignal(kind="typecheck.typescript", passed, details, confidence)
   ```
2. The collector reads/writes the baseline cache at `.codegenie/typecheck/baseline-<repo-sha>.json`. On first run (no baseline file), record current error count as the baseline and return `passed=True` (or the policy preferred by Phase-3 baseline-bootstrap convention — read S6-04 / Phase-3 strict-AND first).
3. Hook the plugin's import path so the `@register_signal_kind` decorator fires at import time. The plugin's `__init__.py` or wherever the plugin's eager import surface lives is the right place.
4. **Verify zero Phase-3 edits**: `git diff --stat src/codegenie/` after this story must show *no changes* to Phase-3 kernel files (probes/coordinator/cache/output/schema/plugins/protocols.py). The `tests/fence/test_kernel_frozen.py` from S1-07 is the load-bearing check.
5. The integration test cassette belongs under `tests/cassettes/anthropic/test_typecheck_signal_catches_signature_drift/`; record via `make refresh-cassettes` (S3-06).

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/fence/test_typecheck_signal_registered.py
def test_typecheck_typescript_registered_exactly_once():
    """ADR-04-0015: signal must be in the open registry post-import.
    Why this matters: roadmap exit #3 + production ADR-0037 fail-loud if absent."""
    from codegenie.gates.signals import SIGNAL_KIND_REGISTRY
    # Force-import the plugin's adapters module
    import plugins.vulnerability_remediation__node__npm.adapters.ts_typecheck_signal  # noqa: F401

    typecheck_kinds = [k for k in SIGNAL_KIND_REGISTRY if k.startswith("typecheck.")]
    assert typecheck_kinds == ["typecheck.typescript"]


# tests/unit/typecheck/test_signal.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from plugins.vulnerability_remediation__node__npm.adapters.ts_typecheck_signal import (
    TypecheckTypescriptSignal,
)

@pytest.mark.asyncio
async def test_signal_passes_when_no_new_errors(tmp_repo_with_baseline_5):
    """ADR-04-0015 strict-AND with baseline: new_errors_after ≤ new_errors_before."""
    sig = TypecheckTypescriptSignal()
    jail_result = MagicMock(exit_code=0, stdout="Found 5 errors in 3 files.\n")
    sig._jail = MagicMock(); sig._jail.run = AsyncMock(return_value=jail_result)

    result = await sig.collect(tmp_repo_with_baseline_5, ctx)

    assert result.kind == "typecheck.typescript"
    assert result.passed is True


@pytest.mark.asyncio
async def test_signal_fails_when_new_errors_introduced(tmp_repo_with_baseline_5):
    sig = TypecheckTypescriptSignal()
    jail_result = MagicMock(exit_code=2, stdout="Found 6 errors in 3 files.\n")
    sig._jail = MagicMock(); sig._jail.run = AsyncMock(return_value=jail_result)

    result = await sig.collect(tmp_repo_with_baseline_5, ctx)

    assert result.passed is False


@pytest.mark.asyncio
async def test_signal_timeout_returns_failed_medium_confidence():
    sig = TypecheckTypescriptSignal()
    sig._jail = MagicMock()
    sig._jail.run = AsyncMock(return_value=TimedOut(elapsed_seconds=30))
    result = await sig.collect(repo, ctx)
    assert result.passed is False
    assert result.details == {"timeout": True}
    assert result.confidence == "medium"


# tests/unit/trust_scorer/test_typecheck_kind.py
def test_trust_scorer_folds_typecheck_without_phase3_edits(monkeypatch):
    """ADR-04-0015 Open/Closed: TrustScorer must fold the new kind from the
    registry with zero Phase-3 edits."""
    # Force plugin import (decorator side-effect)
    import plugins.vulnerability_remediation__node__npm.adapters.ts_typecheck_signal  # noqa: F401
    scorer = TrustScorer()  # Phase 3
    signals = [
        TrustSignal(kind="build", passed=True, details={}, confidence="high"),
        TrustSignal(kind="install", passed=True, details={}, confidence="high"),
        TrustSignal(kind="tests", passed=True, details={}, confidence="high"),
        TrustSignal(kind="lockfile_policy", passed=True, details={}, confidence="high"),
        TrustSignal(kind="cve_delta", passed=True, details={}, confidence="high"),
        TrustSignal(kind="typecheck.typescript", passed=False, details={}, confidence="high"),
    ]
    outcome = scorer.score(signals)
    assert outcome.passed is False  # strict-AND fails on typecheck failure


# tests/integration/test_typecheck_signal_catches_signature_drift.py
@pytest.mark.asyncio
async def test_typecheck_catches_hallucinated_method_before_npm_test(
    fixture_with_bad_llm_cassette, event_stream_capturer,
):
    """ADR-04-0015 §Consequences: tsc catches it before npm test runs.
    Event ordering proves the layered-analysis funnel works as intended."""
    await orchestrator.run(fixture_with_bad_llm_cassette)
    events = event_stream_capturer.recorded
    ts_evt = next(i for i, e in enumerate(events) if e.kind == "SignalEvaluated" and e.signal_kind == "typecheck.typescript")
    npm_evts = [i for i, e in enumerate(events) if e.kind == "NpmTestStarted"]
    assert events[ts_evt].passed is False
    assert all(i > ts_evt for i in npm_evts) or not npm_evts
```

### Green — make it pass

- Land `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py` with the `@register_signal_kind("typecheck.typescript")` decorator.
- Wire the plugin's import surface so the decorator fires.
- Implement baseline read/write at `.codegenie/typecheck/baseline-<repo-sha>.json`.

### Refactor — clean up

- Keep the parser for `tsc --pretty false` output as a small named function (`_parse_tsc_error_count`) — tested in isolation.
- The baseline cache I/O is the imperative shell; the count comparison logic is the pure core. Honor functional-core/imperative-shell discipline (CLAUDE.md).

## Files to touch

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py` | New — the collector + `@register_signal_kind` decoration. |
| `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` | Import the new module so the decorator fires (or wherever the plugin's eager-import surface lives). |
| `tests/fence/test_typecheck_signal_registered.py` | Registry-exactly-once fence. |
| `tests/unit/typecheck/test_signal.py` | Baseline strict-AND, timeout, missing-tsc cases. |
| `tests/unit/trust_scorer/test_typecheck_kind.py` | Phase-3 TrustScorer folds new kind without edits. |
| `tests/integration/test_typecheck_signal_catches_signature_drift.py` | Event-ordering integration. |

## Out of scope

- The applicability matrix (`tsconfig.json` + `.ts` files detection per Gap 4) — **S6-06**.
- Promotion to a shared `vulnerability-remediation--node--*` base plugin — Phase 7 / Phase 6.5 decision (arch open question 3, 8).
- Phase 15 / LSP-richer interactive type signals — per [production ADR-0037](../../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md), out of scope.
- The cassette recording for `test_typecheck_signal_catches_signature_drift` (record via `make refresh-cassettes`).

## Notes for the implementer

- **Zero edits to Phase-3 trust-scorer code.** The strict-AND fold-in is by registry lookup; if you find yourself reaching for `src/codegenie/gates/trust_scorer.py` to add a case arm, you have broken Open/Closed (ADR-0015 §Pattern fit). Surface per Global Rule 7.
- The signal is **plugin-local on purpose** — Phase 7's distroless plugin simply doesn't register it (ADR-0015 §Decision). Don't move the module to `src/codegenie/`.
- Baseline-keyed-on-repo-sha (`baseline-<repo-sha>.json`) means aggressive rebases leave stale baselines; ADR-0015 §Tradeoffs names the recovery path (delete + re-run). Don't try to invalidate baselines cleverly — surfaces complexity disproportionate to value.
- `tsc --pretty false` is the de-facto machine-readable invocation; the output format is `Found N errors in M files.` — the parser is two lines of regex. Don't introduce a TypeScript-output JSON parser dependency.
- The applicability question (`tsconfig.json` + `.ts` files) is deliberately deferred to **S6-06** so this story stays single-purpose. If you find yourself adding `is_typescript_in_scope(repo)` checks here, stop — that's S6-06's surface.
- The integration test's "event ordering proves the funnel" is the load-bearing assurance for ADR-0037's layered-analysis-funnel claim. The cassette must be a *real* recording (S3-06's discipline) — fake cassettes here would invalidate the proof.
