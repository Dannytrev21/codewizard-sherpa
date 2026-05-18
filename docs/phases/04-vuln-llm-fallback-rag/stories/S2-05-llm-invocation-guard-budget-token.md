# Story S2-05 — LlmInvocationGuard + BudgetToken capability issuer

**Step:** Step 2 — Ship trust-boundary primitives: ProvenanceGate, FenceWrapper/CanaryGuard/PromptBuilder, LlmInvocationGuard/BudgetToken
**Status:** Ready
**Effort:** M
**Depends on:** S1-01 (`BudgetTokenId`, `TokenCount` newtypes); S1-04 (`BudgetToken`, `BudgetSnapshot` Pydantic frozen-extra-forbid models — pre-check; if S1-04 only shipped the *model declarations*, this story wires the issuer + state machine that actually mints them)
**ADRs honored:** ADR-0010 (capability-as-function-signature-argument + circuit-breaker + two-frame discipline, this phase), ADR-0003 (path-scoped fence — module under `src/codegenie/fallback/`, this phase), production ADR-0024 (cost observability), production ADR-0025 (per-workflow cost cap pattern)

## Context

ADR-0010 commits Phase 4 to the **Capability pattern** for budget enforcement: `LeafLlm.invoke(...)` accepts a `BudgetToken` as a required keyword argument; calling without one is a `TypeError` caught by `mypy --strict`. The token is minted by `LlmInvocationGuard.precharge(requested_tokens)` after the guard verifies `running_total + requested ≤ max`. If the budget is exhausted, `precharge` raises `BudgetExceeded` *before* any token is minted — the leaf adapter cannot be called.

The critical anti-pattern flagged in ADR-0010 §Pattern fit is "Capability passed through ten frames." The token flows through **exactly two frames**: `FallbackTier → LeafLlm.invoke`. It does **not** flow through `PromptBuilder`, `FenceWrapper`, `EgressGuard`, or `SolvedExampleRetriever`. The `import-linter` contract this story lands is the structural guard: `BudgetToken` may be imported only by `src/codegenie/fallback/tier.py` (S6-01) and `src/codegenie/fallback/leaf/anthropic_adapter.py` (S3-02). Hypothesis property `tests/property/test_budget_token_non_reuse.py` proves token IDs are uuid4-unique and `reconcile(same_token, ...)` twice raises.

The defaults from ADR-0010 §Decision: `max_tokens_per_workflow=250_000`, `max_dollars_per_workflow=$1.50`, `per_call_max_tokens=32_000`. These are configuration knobs (`plugin.yaml` per S7-04); this story ships them as constructor parameters with the documented defaults.

Decimal arithmetic for dollars is exact (`Decimal`, not `float` — surface of S1-04's `BudgetSnapshot` and `BudgetToken.precharged_dollars`). The Hypothesis property `tests/property/test_budget_decimal_exactness.py` (referenced ADR-0010 §Tradeoffs row 5) proves no float drift.

`LlmInvocationGuard.running_total() -> BudgetSnapshot` is the typed projection Phase 5's `GateRunner` reads across retries — it's a load-bearing **contract** for S7-10's `tests/integration/test_phase5_contract_snapshot.py`. Name and shape are stable from this story forward.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 5 — LlmInvocationGuard + BudgetToken` (lines 536-560) — public interface, defaults, two-frame discipline, idempotent reconcile, performance envelope, failure behavior.
  - `../phase-arch-design.md §Goals — G8` (line 25) — "budget cap as capability."
  - `../phase-arch-design.md §Design patterns applied` row 4 (line 879) — Capability + Circuit Breaker; "not a global counter the adapter checks."
  - `../phase-arch-design.md §Anti-patterns avoided` (line 914) — "Capability passed through ten frames" → exactly two frames.
  - `../phase-arch-design.md §Testing strategy` row "tests/property/test_budget_token_non_reuse.py" (line 963).
  - `../phase-arch-design.md §Edge cases row 2` (line 929) — per-workflow budget exhausted.
  - `../phase-arch-design.md §Forward-compat surface` row "LlmInvocationGuard.running_total" (line 1019) — Phase 5 / Phase 13 contract.
- **Phase ADRs:**
  - `../ADRs/0010-llm-invocation-guard-budget-token-capability.md` — decision, defaults, two-frame rule, decimal exactness, override-via-config, no-env-var-escape (key load is via `keyring`-only).
  - `../ADRs/0003-path-scoped-fence-amendment.md` — module path.
- **Production ADRs:**
  - `../../../production/adrs/0024-cost-observability-end-to-end.md` — `cost.llm.call` ledger entries; this story's events compose into Phase 13's eventual ledger.
  - `../../../production/adrs/0025-per-workflow-cost-cap.md` — the pattern this ADR is the Phase 4 instance of.
- **Source design:**
  - `../final-design.md §Component 5 — LlmInvocationGuard`.
- **Existing code:**
  - `src/codegenie/audit.py` — `EventLog` shape.
  - `src/codegenie/types/identifiers.py` + S1-01 — `BudgetTokenId`, `TokenCount` newtypes.
  - S1-04 outputs — `BudgetToken` Pydantic model, `BudgetSnapshot` model (pre-check; if the issuer/reconcile/running_total logic landed in S1-04, this story narrows scope to import-linter contract + property tests).
  - `pyproject.toml [tool.importlinter]` — Phase-4 `import-linter` contracts from S1-06 are extended here with the `BudgetToken` scope rule.

## Goal

Ship `LlmInvocationGuard(max_tokens, max_dollars, per_call_max_tokens, event_log)` with `precharge(requested_tokens) -> BudgetToken`, `reconcile(token, actual_in, actual_out, actual_dollars) -> None` (idempotent on `BudgetTokenId`), and `running_total() -> BudgetSnapshot` — plus a Hypothesis property proving `BudgetTokenId` uniqueness and `reconcile` idempotence, plus an `import-linter` contract pinning `BudgetToken` import scope to exactly `{src/codegenie/fallback/tier.py, src/codegenie/fallback/leaf/anthropic_adapter.py}`.

## Acceptance criteria

- [ ] **AC-1 — Module location.** `src/codegenie/fallback/budget.py` exists. Path-scoped fence test green.
- [ ] **AC-2 — `BudgetToken` Pydantic model.** Frozen-extra-forbid:
   ```python
   class BudgetToken(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       id: BudgetTokenId          # uuid4 string from S1-01
       precharged_tokens: TokenCount
       precharged_dollars: Decimal
       issued_at: datetime
       _marker: Literal["budget_token"] = "budget_token"  # discriminator
   ```
   If S1-04 already shipped this exact model, import it; otherwise this story is the canonical definer. `_marker` is the discriminator that makes hand-forged dicts fail Pydantic validation (defense-in-depth — the import-linter contract is the structural guard, this is the data-shape guard).
- [ ] **AC-3 — `BudgetSnapshot` Pydantic model.** Frozen-extra-forbid; fields per arch §Component 5:
   ```python
   class BudgetSnapshot(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       consumed_tokens: TokenCount
       consumed_dollars: Decimal
       max_tokens: TokenCount
       max_dollars: Decimal
       outstanding_tokens: dict[BudgetTokenId, TokenCount]   # tokens precharged but not yet reconciled
       remaining_tokens: TokenCount    # max - consumed - sum(outstanding)
       remaining_dollars: Decimal
   ```
   `remaining_*` are computed projections (not stored); whether implemented as `@property` or `@computed_field` (Pydantic v2) is the implementer's call.
- [ ] **AC-4 — `LlmInvocationGuard.__init__` signature.**
   ```python
   class LlmInvocationGuard:
       def __init__(
           self,
           *,
           max_tokens: int = 250_000,
           max_dollars: Decimal = Decimal("1.50"),
           per_call_max_tokens: int = 32_000,
           event_log: EventLog,
       ) -> None: ...
   ```
   Defaults match ADR-0010 §Decision. Test asserts the default-construction snapshot has those values.
- [ ] **AC-5 — `precharge(requested_tokens) -> BudgetToken` semantics.**
   - Validates `requested_tokens > 0` (else `ValueError`).
   - Validates `requested_tokens <= per_call_max_tokens` (else `BudgetExceeded(reason="per_call_max_exceeded", requested=..., per_call_max=...)`).
   - Computes `projected = consumed_tokens + sum(outstanding_tokens.values()) + requested_tokens`.
   - If `projected > max_tokens`: emit `BudgetExceeded(reason="workflow_max_tokens_exceeded", projected, max)` event AND raise `BudgetExceeded`.
   - Else: mint a fresh `BudgetTokenId` via `uuid4().hex`; estimate `precharged_dollars` (Phase 4 uses a fixed rate, e.g., `Decimal("0.000003") * requested_tokens` — surface the exact rate to implementer; ADR-0010 §Decision §Consequences row 9 says the rate lives in `plugin.yaml`; for S2-05 use a hard-coded default and document the per-1K rate); add to `outstanding_tokens`; emit `BudgetPrecharged(token_id, precharged_tokens, precharged_dollars)`; return `BudgetToken(...)`.
- [ ] **AC-6 — `reconcile(token, actual_in, actual_out, actual_dollars)` is idempotent on `token.id`.**
   - First call for `token.id`: removes from `outstanding_tokens`; increments `consumed_tokens` by `actual_in + actual_out`; increments `consumed_dollars` by `actual_dollars`; emits `BudgetReconciled(token_id, actual_in, actual_out, actual_dollars)`.
   - Second call for the same `token.id`: **no-op** — does not double-count. Emits `BudgetReconciledDuplicate(token_id)` for the audit trail. (ADR-0010 §Tradeoffs row 3: "duplicate reconcile calls must be safe.")
   - Reconcile with `token.id NOT in outstanding_tokens AND NOT in reconciled_ids`: raises `BudgetReconcileUnknownToken(token_id)` — guard against forged tokens.
   - State tracking: `LlmInvocationGuard` maintains `_reconciled_ids: set[BudgetTokenId]` to enforce idempotence.
- [ ] **AC-7 — `running_total() -> BudgetSnapshot`.** Pure projection over current state; no side effects; can be called arbitrarily many times. Test asserts (i) the returned snapshot's `consumed_tokens + sum(outstanding_tokens.values()) + remaining_tokens == max_tokens`, (ii) Decimal field `consumed_dollars` is exact (`Decimal("0.000123")`, never `0.000122999...`), (iii) calling `running_total()` does not mutate any field.
- [ ] **AC-8 — Hypothesis: `BudgetTokenId` non-reuse.** `tests/property/test_budget_token_non_reuse.py` — `@given(n=st.integers(1, 50))`: construct a fresh guard with large enough budget; mint `n` tokens; assert `len({t.id for t in tokens}) == n` (no collisions). 500+ runs.
- [ ] **AC-9 — Hypothesis: reconcile idempotence.** Same file or sibling — `@given(...)`: mint one token; reconcile with random `(actual_in, actual_out, actual_dollars)`; reconcile again with the **same** token and different actuals; assert (i) snapshot after second reconcile equals snapshot after first (the second call did not apply the new actuals), (ii) `BudgetReconciledDuplicate` event fired.
- [ ] **AC-10 — Hypothesis: decimal exactness.** `tests/property/test_budget_decimal_exactness.py` — `@given(values=st.lists(st.decimals(min_value="0.00001", max_value="0.5", places=6), min_size=10, max_size=50))`: mint+reconcile each value as `actual_dollars`; assert `running_total().consumed_dollars == sum(values)` exactly (Decimal sum, not float-rounded). 500+ runs. Catches `float`-creep.
- [ ] **AC-11 — `import-linter` contract pinning `BudgetToken` import scope.** Extend `pyproject.toml`'s `[tool.importlinter]` (or wherever S1-06 placed Phase-4 contracts) with a contract:
   ```toml
   [[tool.importlinter.contracts]]
   name = "BudgetToken import scope (phase-4)"
   type = "forbidden"
   source_modules = [
       "codegenie.*",
       "plugins.*",
   ]
   forbidden_modules = ["codegenie.fallback.budget.BudgetToken"]
   ignore_imports = [
       "codegenie.fallback.budget -> codegenie.fallback.budget.BudgetToken",
       "codegenie.fallback.tier -> codegenie.fallback.budget.BudgetToken",
       "codegenie.fallback.leaf.anthropic_adapter -> codegenie.fallback.budget.BudgetToken",
   ]
   ```
   (Exact contract type may differ — `import-linter` doesn't directly support "forbidden symbol with allowlist"; the implementer may need to use a `kind="forbidden"` contract on the *module* `codegenie.fallback.budget` and add `ignore_imports` for the two allowed importers, or use a custom contract. Mirror the precedent S1-06 sets — if S1-06 used a `forbidden` contract for `anthropic`-scope-pinning, mirror that pattern. Surface the exact syntax to validator per Global Rule 7.)
- [ ] **AC-12 — Sole-importer test.** `tests/fence/test_budget_token_scope.py` — runs `make lint-imports` (or invokes `lintforbidden` programmatically) and asserts zero violations. Includes a **positive control**: a fixture under `tests/fixtures/violators/forged_budget_import.py` that imports `BudgetToken` outside the allowed scope; the test verifies the contract would fire on that fixture (similar mechanic to S2-04's positive-control fixture for the AST walk).
- [ ] **AC-13 — Event-kind registration.** `BudgetPrecharged`, `BudgetReconciled`, `BudgetReconciledDuplicate`, `BudgetExceeded`, `BudgetReconcileUnknownToken` all registered in audit allowlist. `tests/fence/test_event_kinds_complete.py` extended.
- [ ] **AC-14 — `LlmInvocationGuard.precharge` is async-safe.** Phase 4 is single-event-loop; ADR-0010 §Internal structure says "atomic counter (asyncio-safe; Phase 4 is single-loop, so a simple `int` plus tracked tokens)." No locks needed yet. Test: 50 concurrent `precharge` calls via `asyncio.gather` against a small budget; assert (i) the number of successful precharges + failed (`BudgetExceeded`) precharges equals 50, (ii) `consumed_tokens + sum(outstanding) ≤ max_tokens` is never violated. (This is the simple sanity test; the proper concurrency-safety proof is owned by Phase 9 when Temporal workers introduce multi-loop concerns.)
- [ ] **AC-15 — `LeafLlm.invoke` signature type-check.** A deliberately-failing `mypy` fixture at `tests/fixtures/typecheck/budget_token_missing.py`:
   ```python
   from codegenie.fallback.budget import BudgetToken
   from codegenie.fallback.leaf.protocol import LeafLlm  # S3-01

   async def caller(leaf: LeafLlm) -> None:
       # MISSING token=... — should mypy-error
       await leaf.invoke(system_prompt=..., user_message=..., schema=...)
   ```
   `tests/fence/test_budget_token_typecheck.py` runs `mypy --strict tests/fixtures/typecheck/budget_token_missing.py` via subprocess and asserts a non-zero exit with the missing-argument diagnostic. **This AC is BLOCKED until S3-01 ships `LeafLlm` Protocol** — gate this AC with `pytest.importorskip("codegenie.fallback.leaf.protocol")` so S2-05 ships standalone and S3-01's executor turns this AC green when it lands. Document the gating in the test docstring.
- [ ] **AC-16 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean. `make lint-imports` green.

## Implementation outline

1. **Pre-check S1-04**: does `BudgetToken` already live in `src/codegenie/fallback/budget.py` (model only)? Does `BudgetSnapshot`? Import / extend; do not duplicate.
2. **Implement `LlmInvocationGuard`** as a class (not frozen — it has mutable state). Internal fields: `_consumed_tokens: int`, `_consumed_dollars: Decimal`, `_outstanding_tokens: dict[BudgetTokenId, TokenCount]`, `_reconciled_ids: set[BudgetTokenId]`, `_event_log: EventLog`, plus the immutable config (`_max_tokens`, etc.).
3. **`precharge`**: validate, project, raise-or-mint per AC-5.
4. **`reconcile`**: branch on `token.id ∈ outstanding_tokens` (first call) vs `token.id ∈ _reconciled_ids` (duplicate, no-op) vs neither (unknown, raise).
5. **`running_total`**: build `BudgetSnapshot` from current state.
6. **Add import-linter contract.** Read S1-06's contract syntax precedent.
7. **Write Hypothesis properties** before the unit tests — they are the load-bearing invariants.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/property/test_budget_token_non_reuse.py
from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings, strategies as st

from codegenie.audit import EventLog
from codegenie.fallback.budget import BudgetExceeded, LlmInvocationGuard


@given(n=st.integers(min_value=1, max_value=50))
@settings(max_examples=500, deadline=None)
def test_each_precharge_mints_a_fresh_unique_token_id(n: int) -> None:
    guard = LlmInvocationGuard(
        max_tokens=10_000_000,            # big enough for n×1000
        max_dollars=Decimal("100.00"),
        per_call_max_tokens=32_000,
        event_log=EventLog(),
    )
    tokens = [guard.precharge(requested_tokens=1000) for _ in range(n)]
    assert len({t.id for t in tokens}) == n


@given(actual_pair=st.tuples(st.integers(0, 500), st.integers(0, 500)))
@settings(max_examples=500, deadline=None)
def test_reconcile_is_idempotent_on_token_id(actual_pair: tuple[int, int]) -> None:
    actual_in, actual_out = actual_pair
    log = EventLog()
    guard = LlmInvocationGuard(
        max_tokens=100_000, max_dollars=Decimal("10.0"),
        per_call_max_tokens=32_000, event_log=log,
    )
    token = guard.precharge(requested_tokens=1000)

    guard.reconcile(token, actual_in=actual_in, actual_out=actual_out,
                    actual_dollars=Decimal("0.001"))
    snap_after_first = guard.running_total()

    # Second reconcile with DIFFERENT actuals must not double-count.
    guard.reconcile(token, actual_in=actual_in + 100, actual_out=actual_out + 100,
                    actual_dollars=Decimal("0.999"))
    snap_after_second = guard.running_total()

    assert snap_after_first == snap_after_second
    dupes = [e for e in log.events if type(e).__name__ == "BudgetReconciledDuplicate"]
    assert len(dupes) == 1
```

```python
# tests/property/test_budget_decimal_exactness.py
from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings, strategies as st

from codegenie.audit import EventLog
from codegenie.fallback.budget import LlmInvocationGuard


@given(
    values=st.lists(
        st.decimals(min_value=Decimal("0.000001"),
                    max_value=Decimal("0.5"),
                    places=6, allow_nan=False, allow_infinity=False),
        min_size=10, max_size=50,
    ),
)
@settings(max_examples=200, deadline=None)
def test_consumed_dollars_is_decimal_exact_no_float_drift(values: list[Decimal]) -> None:
    guard = LlmInvocationGuard(
        max_tokens=100_000_000, max_dollars=Decimal("100.0"),
        per_call_max_tokens=32_000, event_log=EventLog(),
    )
    for v in values:
        tok = guard.precharge(requested_tokens=1)
        guard.reconcile(tok, actual_in=1, actual_out=0, actual_dollars=v)
    assert guard.running_total().consumed_dollars == sum(values, Decimal("0"))
```

Run; expect `ModuleNotFoundError`.

### Green — make it pass

Implement `budget.py`. Smallest correct code. Keep the state mutations strictly inside `precharge` / `reconcile`; do not leak `_consumed_tokens` etc. through public methods other than `running_total()`.

### Refactor — clean up

- Extract the "validate requested_tokens" helper if it has more than one branch.
- Verify `reconcile` is at most 25 lines — three branches (first / duplicate / unknown).
- Decimal-rate-per-token constant lives at module scope as `_DEFAULT_DOLLARS_PER_TOKEN: Final[Decimal]`; module docstring documents that S7-04's `plugin.yaml` overrides it.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/budget.py` | `BudgetToken`, `BudgetSnapshot`, `LlmInvocationGuard`, `BudgetExceeded`, `BudgetReconcileUnknownToken` exceptions, `_DEFAULT_DOLLARS_PER_TOKEN`. |
| `src/codegenie/audit.py` | Register five new event kinds. |
| `pyproject.toml` | Add `import-linter` contract for `BudgetToken` scope. |
| `tests/unit/fallback/test_budget_guard.py` | AC-4..AC-7, AC-14 (concurrency sanity). |
| `tests/property/test_budget_token_non_reuse.py` | AC-8 + AC-9. |
| `tests/property/test_budget_decimal_exactness.py` | AC-10. |
| `tests/fence/test_budget_token_scope.py` | AC-11 + AC-12 import-linter assertion. |
| `tests/fixtures/violators/forged_budget_import.py` | Positive-control fixture for AC-12. |
| `tests/fixtures/typecheck/budget_token_missing.py` | AC-15 (gated on S3-01). |
| `tests/fence/test_budget_token_typecheck.py` | AC-15 mypy subprocess assertion. |
| `tests/fence/test_event_kinds_complete.py` | Extend with new event kinds. |

## Out of scope

- `LeafLlm.invoke` Protocol with `BudgetToken` arg — owned by S3-01.
- `AnthropicLeafAdapter`'s consumption of `BudgetToken` — owned by S3-02.
- Wiring `LlmInvocationGuard` into `FallbackTier.run` — owned by S6-01.
- Per-portfolio cap (Phase 13).
- Operator-override audit trail (override events emitted per ADR-0010 §Consequences row 8) — Phase 4 ships the config knob in S7-04, not the runtime override flow.
- `plugin.yaml` token-rate configuration — S7-04 overrides the `_DEFAULT_DOLLARS_PER_TOKEN` constant.
- Phase 5's `GateRunner` consumption of `running_total()` across retries — Phase 5; this story locks the projection shape.

## Notes for the implementer

- **Cross-cutting reminder — capability through two frames only.** ADR-0010 §Pattern fit names the constraint. The `import-linter` contract (AC-11) is the structural guard. The two allowed importers are `src/codegenie/fallback/tier.py` (S6-01) and `src/codegenie/fallback/leaf/anthropic_adapter.py` (S3-02). Neither exists yet — the contract pre-pins the surface. Tests in this story (`test_budget_guard.py`) import `BudgetToken` but they live under `tests/`, not `src/codegenie/` or `plugins/` — the contract's `source_modules` should scope to non-test code only.
- **Cross-cutting reminder — zero LLM tokens before the gate.** `LlmInvocationGuard` does not invoke an LLM; it only enforces the budget envelope. S2-01's `ProvenanceGate` is tier-0 (runs *before* `precharge`). S6-01's `FallbackTier.run` orders the calls: provenance → precharge → leaf-invoke → reconcile. This story is independent — it could ship before S2-01 in execution order if dependencies allow.
- **Cross-cutting reminder — Newtypes.** `BudgetTokenId`, `TokenCount` from S1-01. Decimal (not `float`) for dollars. Pydantic frozen-extra-forbid for `BudgetToken`, `BudgetSnapshot`.
- **`uuid4` not `uuid1`.** uuid4 is random; uuid1 leaks the MAC address. ADR-0010 §Consequences names uuid4 explicitly. Test asserts `BudgetTokenId` is 32 hex characters (uuid4 `.hex`).
- **Default token-rate.** Pick a conservative number for Phase 4 — e.g., Anthropic Sonnet 4.5 input ~$0.003 / 1K tokens, output ~$0.015 / 1K tokens. The `_DEFAULT_DOLLARS_PER_TOKEN` constant blends them (weighted average over expected in:out ratio) OR is two separate constants (input vs output) and `precharge` computes input-only since it's pre-call. Surface to validator per Global Rule 7 if precision matters; ADR-0010 §Tradeoffs row 1 acknowledges defaults are uncalibrated Q1-2026 estimates.
- **Idempotence test is load-bearing.** ADR-0010 §Tradeoffs row 3: "duplicate reconcile calls must be safe." Phase 5's retry envelope may call `reconcile` multiple times if a retry observes the same response (cassette replay scenario); the no-double-count guarantee is what makes `running_total()` a stable contract.
- **`BudgetExceeded` is a typed exception with structured fields.** Not just a message string — `BudgetExceeded(reason: Literal["per_call_max_exceeded", "workflow_max_tokens_exceeded", "workflow_max_dollars_exceeded"], projected: int | Decimal, max: int | Decimal)`. S6-01's `FallbackTier.run` projects it to `RecipeApplication.Refused(reason=BUDGET_EXCEEDED, details={...})`.
- **No environment-variable escape.** ADR-0010 §Consequences row 11: API key load is via `keyring`-only (S3-02's concern, not this story's). For *budget* config, the same principle: no `CODEGENIE_BUDGET_MAX_TOKENS` env var. Configuration flows via `plugin.yaml` only (S7-04). This story uses defaults; do not add env-var reads.
- **Async-safety scope.** Phase 4 is single-event-loop; a plain `int` counter is correct. Do **not** preemptively reach for `asyncio.Lock` — Phase 9 (Temporal multi-worker) is when locking becomes load-bearing. ADR-0010 §Internal structure is explicit. Surface temptation to validator per Global Rule 7.
- **The `running_total()` shape is a contract.** S7-10's `tests/integration/test_phase5_contract_snapshot.py` will snapshot the `BudgetSnapshot` model fields and field types. Adding a field is allowed (additive); removing or renaming is a Phase-amendment ADR. Document this in the model's docstring.
