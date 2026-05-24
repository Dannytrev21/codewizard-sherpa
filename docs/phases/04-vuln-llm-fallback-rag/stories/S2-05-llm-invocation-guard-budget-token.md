# Story S2-05 — LlmInvocationGuard + BudgetToken capability issuer

**Step:** Step 2 — Ship trust-boundary primitives: ProvenanceGate, FenceWrapper/CanaryGuard/PromptBuilder, LlmInvocationGuard/BudgetToken
**Status:** Done — GREEN 2026-05-24 (phase-story-executor; see [`_attempts/S2-05.md`](_attempts/S2-05.md) for the per-AC evidence table + gate log — `LlmInvocationGuard` financial circuit breaker lands as four collaborating pieces: `src/codegenie/fallback/budget_token.py` (dedicated `BudgetToken` submodule so the `import-linter` `forbidden` contract can express the two-frame discipline at module-level granularity), `src/codegenie/fallback/budget.py` (refactored `BudgetSnapshot` with the S2-05 prescribed shape + `BudgetExceeded` with `reason: Literal` and per-reason `int`/`Decimal` typing + `BudgetReconcileUnknownToken` + `LlmInvocationGuard` with `__slots__`, full-`BudgetToken` `_outstanding` dict, cap-check order pinned, dollar cap now load-bearing-enforced), `src/codegenie/plugins/events.py` (5 new internal events; union + `_INTERNAL_CLASSES` + `__all__` grow 21 → 26), and `pyproject.toml` (new `[[tool.importlinter.contracts]]` block "ADR-0010: BudgetToken is two-frame scoped" with the source list pinned by a shape test). 96 story-scoped tests pass: 27 `test_budget_guard.py`, 3 Hypothesis properties (500/500/200 examples), 16 `test_budget_models.py` (rewritten for the new shape; S1-04 conflicts surfaced per Rule 7 in the attempt log), 4 `test_budget_token_scope.py` (incl. planted-leak positive control), 50 `test_events.py` (+2 new — round-trip + unregistered-class rejection). Gates green: 6542 unit+integration, 419 fence (1 skipped = AC-15 gated on S3-01 per the story's own allowance), `mypy --strict src/` (219 files), `ruff check`/`format --check`, `lint-imports` (11 contracts kept / 0 broken). Two pre-existing local-env failures (`tsconfig_pathological` timing flake; `lint_imports_canary` PATH issue) verified by stashing the change set — recurring from S2-01/02/03/04; CI Linux runners are clean.)
**Effort:** M
**Depends on:** S1-01 (`BudgetTokenId`, `TokenCount` newtypes); S1-04 (`BudgetToken`, `BudgetSnapshot` Pydantic frozen-extra-forbid models — pre-check; if S1-04 only shipped the *model declarations*, this story wires the issuer + state machine that actually mints them)
**ADRs honored:** ADR-0010 (capability-as-function-signature-argument + circuit-breaker + two-frame discipline, this phase), ADR-0003 (path-scoped fence — module under `src/codegenie/fallback/`, this phase), production ADR-0024 (cost observability), production ADR-0025 (per-workflow cost cap pattern)

## Validation notes

Validated 2026-05-21 — verdict **HARDENED**. Full report: `_validation/S2-05-llm-invocation-guard-budget-token.md`. Changes applied:

1. **Stale `codegenie.audit.EventLog` API corrected (block).** Same recurring Phase-4 mistake hardened in S2-01/02/03/04. The real event-sourcing surface is `codegenie.plugins.events.EventLog`, constructed `EventLog(root: Path, workflow_id: WorkflowId)`, emitted via `emit_internal(event)` with **typed Pydantic event models**, and read via `replay()` — not `audit.py`, not `EventLog()`, not `.events`. References, AC-13, TDD plan, Files-to-touch, and Notes all corrected.
2. **Event registration corrected (block).** `tests/fence/test_event_kinds_complete.py` does not exist (S2-04 removed it). New events are `WorkflowInternalEvent` Pydantic subclasses added to both the `WorkflowInternalEvent` union and the `_INTERNAL_CLASSES` tuple in `plugins/events.py`. AC-13 rewritten.
3. **Dollar cap now enforced (block).** AC-5 only checked tokens; `max_dollars` was a decorative constructor param and `BudgetExceeded(reason="workflow_max_dollars_exceeded")` was unreachable. AC-5 now requires a projected-dollars check; AC-17 added for the structured-`reason` assertions.
4. **`_marker` discriminator claim corrected (harden).** A leading-underscore attribute is a Pydantic v2 *private attribute* — not validated, absent from the schema, no defense against hand-forged dicts. AC-2 reworded to the honest framing (import-linter is the sole structural guard; in-process construction is forgeable, per arch §Design-patterns row 882).
5. **Outstanding-state shape corrected (harden).** Internal state must store the full `BudgetToken` (`_outstanding: dict[BudgetTokenId, BudgetToken]`), not a `dict[BudgetTokenId, TokenCount]` — `remaining_dollars` and the dollar-cap check both need outstanding *dollars*; two parallel id-keyed dicts can desync.
6. **Event/exception name collision resolved (harden).** `BudgetExceeded` and `BudgetReconcileUnknownToken` were used as both exception and event-kind names. Events renamed `BudgetCapExceeded` / `BudgetUnknownTokenReconcile`.
7. **AC-14 reframed (harden).** `precharge` is synchronous with no `await` — `asyncio.gather` over it is a `TypeError` and single-loop "race" safety is vacuous. AC-14 now pins the deterministic sequential-exhaustion boundary instead.
8. **Coverage + test-quality hardening (harden).** Dollars invariant added to AC-7; negative-actuals validation + explicit unknown-token test added to AC-6; uuid4 hex-format assertion added to AC-8; positive-effect assertion added to AC-9; AC-10 run-count text reconciled with the snippet; property-test `EventLog` construction fixed for the Hypothesis-fixture-reuse footgun.

## Context

ADR-0010 commits Phase 4 to the **Capability pattern** for budget enforcement: `LeafLlm.invoke(...)` accepts a `BudgetToken` as a required keyword argument; calling without one is a `TypeError` caught by `mypy --strict`. The token is minted by `LlmInvocationGuard.precharge(requested_tokens)` after the guard verifies `running_total + requested ≤ max`. If the budget is exhausted, `precharge` raises `BudgetExceeded` *before* any token is minted — the leaf adapter cannot be called.

The critical anti-pattern flagged in ADR-0010 §Pattern fit is "Capability passed through ten frames." The token flows through **exactly two frames**: `FallbackTier → LeafLlm.invoke`. It does **not** flow through `PromptBuilder`, `FenceWrapper`, `EgressGuard`, or `SolvedExampleRetriever`. The `import-linter` contract this story lands is the structural guard: `BudgetToken` may be imported only by `src/codegenie/fallback/tier.py` (S6-01) and `src/codegenie/fallback/leaf/anthropic_adapter.py` (S3-02). Hypothesis property `tests/property/test_budget_token_non_reuse.py` proves token IDs are uuid4-unique and that a second `reconcile(same_token, ...)` is an **idempotent no-op** (it does not double-count and emits `BudgetReconciledDuplicate`). Note: `phase-arch-design.md §Testing strategy` line 963 phrases this as "reconcile twice *raises*" — that one-liner contradicts ADR-0010 §Tradeoffs row 3 ("duplicate reconcile calls must be safe") and arch §Component 5 ("reconcile is idempotent on `BudgetTokenId`"). The idempotent-no-op semantics are authoritative; the testing-strategy line is a stale phrasing. A *third*-party / never-precharged token still raises `BudgetReconcileUnknownToken` (AC-6) — that is the "raise" path, distinct from the duplicate path.

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
  - `src/codegenie/plugins/events.py` — the real `EventLog`. Constructor `EventLog(root: Path, workflow_id: WorkflowId, *, clock=None, sink=None)`; `emit_internal(event)` / `emit_spanning(event)` take **typed Pydantic event models**; `replay() -> Iterator[...]` reads both streams. `_INTERNAL_CLASSES` (line ~512) + the `WorkflowInternalEvent` `Annotated` union (line ~476) are the registration points. `src/codegenie/audit.py` has **no `EventLog`** — it holds `AuditWriter` / `RunRecord` only; do not import `EventLog` from it.
  - `tests/unit/plugins/test_events.py` — the established pattern for constructing `EventLog(root=tmp_path, workflow_id=_wf())`, emitting, and `list(log.replay())`.
  - `src/codegenie/types/identifiers.py` + S1-01 — `BudgetTokenId`, `TokenCount` newtypes. **Pre-check:** as of validation, `identifiers.py` does not yet contain `BudgetTokenId` / `TokenCount` — S1-01 is `Ready`/unexecuted. If S1-01 has not landed them when this story runs, define them in `budget.py` alongside the issuer (mirror S2-04's local-newtype resolution) and surface per Global Rule 7.
  - S1-04 outputs — `BudgetToken` Pydantic model, `BudgetSnapshot` model (pre-check; if the issuer/reconcile/running_total logic landed in S1-04, this story narrows scope to import-linter contract + property tests).
  - `pyproject.toml [tool.importlinter]` — Phase-4 `import-linter` contracts from S1-06 are extended here with the `BudgetToken` scope rule.

## Goal

Ship `LlmInvocationGuard(max_tokens, max_dollars, per_call_max_tokens, event_log)` with `precharge(requested_tokens) -> BudgetToken`, `reconcile(token, actual_in, actual_out, actual_dollars) -> None` (idempotent on `BudgetTokenId`), and `running_total() -> BudgetSnapshot` — plus a Hypothesis property proving `BudgetTokenId` uniqueness and `reconcile` idempotence, plus an `import-linter` contract pinning `BudgetToken` import scope to exactly `{src/codegenie/fallback/tier.py, src/codegenie/fallback/leaf/anthropic_adapter.py}`.

## Acceptance criteria

- [x] **AC-1 — Module location.** `src/codegenie/fallback/budget.py` exists. Path-scoped fence test green.
- [x] **AC-2 — `BudgetToken` Pydantic model.** Frozen-extra-forbid:
   ```python
   class BudgetToken(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       id: BudgetTokenId          # uuid4 .hex string — minted only by precharge()
       precharged_tokens: TokenCount
       precharged_dollars: Decimal
       issued_at: datetime
   ```
   If S1-04 already shipped this exact model, import it; otherwise this story is the canonical definer.
   **Note — the `id` field.** `phase-arch-design.md §Component 5` lists `BudgetToken` *without* an `id`, yet the same arch keys `outstanding_tokens` by `BudgetTokenId` and says reconcile is idempotent "on `BudgetTokenId`". The arch is internally incomplete; adding `id: BudgetTokenId` is the deliberate, necessary resolution — `reconcile(token, ...)` needs `token.id`. Keep it.
   **Note — no `_marker` discriminator.** A draft of this story added `_marker: Literal["budget_token"]` claimed to "make hand-forged dicts fail Pydantic validation." That is **false in Pydantic v2**: a leading-underscore attribute is a *private attribute* — it is not a model field, does not appear in the JSON schema, is not validated, and does not participate in `extra="forbid"`. A hand-forged `dict` carrying the four real fields validates fine regardless. The honest threat model (matching arch §Design-patterns row 882 on `SolvedExampleWriteCapability`: "Pydantic constructors are public; named as what it is") is: **the `import-linter` contract (AC-11/AC-12) is the sole structural guard; in-process direct construction of `BudgetToken` is forgeable and that residual risk is accepted.** Do not add a private-underscore "discriminator" and do not claim a data-shape guard the type system cannot deliver. If a *future* story needs deserialization-time validation (e.g. `BudgetToken` joins a discriminated union read from disk), it adds a real public `event_type`-style discriminator field then.
- [x] **AC-3 — `BudgetSnapshot` Pydantic model.** Frozen-extra-forbid; fields per arch §Component 5:
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
- [x] **AC-4 — `LlmInvocationGuard.__init__` signature.**
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
- [x] **AC-5 — `precharge(requested_tokens) -> BudgetToken` semantics.** All four failure branches must be exercised by a test; the success branch by AC-8's property.
   - Validates `requested_tokens > 0` (else `ValueError`). Zero and negative both rejected.
   - Validates `requested_tokens <= per_call_max_tokens` (else emit `BudgetCapExceeded(reason="per_call_max_exceeded", ...)` event AND raise `BudgetExceeded(reason="per_call_max_exceeded", requested=..., per_call_max=...)`).
   - Computes `projected_tokens = consumed_tokens + sum(t.precharged_tokens for t in _outstanding.values()) + requested_tokens`. If `projected_tokens > max_tokens`: emit `BudgetCapExceeded(reason="workflow_max_tokens_exceeded", ...)` event AND raise `BudgetExceeded(reason="workflow_max_tokens_exceeded", projected=projected_tokens, max=max_tokens)`.
   - Estimates `precharged_dollars` from a module-scope fixed rate (see AC below + Refactor step + Notes — `_DEFAULT_DOLLARS_PER_TOKEN: Final[Decimal]`); `precharged_dollars` is `Decimal`, never `float`.
   - **Dollar cap (was missing — now load-bearing):** computes `projected_dollars = consumed_dollars + sum(t.precharged_dollars for t in _outstanding.values()) + precharged_dollars`. If `projected_dollars > max_dollars`: emit `BudgetCapExceeded(reason="workflow_max_dollars_exceeded", ...)` event AND raise `BudgetExceeded(reason="workflow_max_dollars_exceeded", projected=projected_dollars, max=max_dollars)`. **No token is minted and `_outstanding` is not mutated when any cap is exceeded** — the precharge is a no-op on failure (test asserts `running_total()` is byte-identical before and after a rejected precharge). ADR-0010 §Decision sets `max_dollars_per_workflow=$1.50` as a *hard* cap; without this check it is decorative.
   - Else (all caps satisfied): mint a fresh `BudgetTokenId` via `uuid4().hex`; insert the full `BudgetToken` into `_outstanding` keyed by its `id`; emit `BudgetPrecharged(token_id, precharged_tokens, precharged_dollars)` event; return the `BudgetToken`.
   - **Cap-check ordering is fixed and tested:** `requested_tokens > 0` → `per_call_max` → `workflow_max_tokens` → `workflow_max_dollars`. A test pins that a call violating two caps surfaces the *first* in this order (deterministic `reason`).
- [x] **AC-6 — `reconcile(token, actual_in, actual_out, actual_dollars)` is idempotent on `token.id`.** Each of the three branches below has its own named unit test.
   - **Input validation:** `actual_in >= 0`, `actual_out >= 0`, `actual_dollars >= Decimal("0")` — any negative raises `ValueError` (symmetric with AC-5's `requested_tokens > 0`; a negative actual would silently *credit* the budget). Tested with an explicit negative-input case.
   - **First call for `token.id`** (`token.id in _outstanding`): removes the token from `_outstanding`; increments `consumed_tokens` by `actual_in + actual_out`; increments `consumed_dollars` by `actual_dollars`; adds `token.id` to `_reconciled_ids`; emits `BudgetReconciled(token_id, actual_in, actual_out, actual_dollars)`.
   - **Second call for the same `token.id`** (`token.id in _reconciled_ids`): **no-op** — does not double-count, does not re-apply the new actuals. Emits `BudgetReconciledDuplicate(token_id)` for the audit trail. (ADR-0010 §Tradeoffs row 3: "duplicate reconcile calls must be safe.")
   - **Unknown token** (`token.id` in neither `_outstanding` nor `_reconciled_ids`): emits `BudgetUnknownTokenReconcile(token_id)` event AND raises `BudgetReconcileUnknownToken(token_id)` — guard against forged tokens. A dedicated unit test constructs a `BudgetToken` directly (never precharged) and asserts the raise + event.
   - State tracking: `LlmInvocationGuard` maintains `_reconciled_ids: set[BudgetTokenId]` to enforce idempotence.
- [x] **AC-7 — `running_total() -> BudgetSnapshot`.** Pure projection over current state; no side effects; can be called arbitrarily many times. The snapshot's `outstanding_tokens` projection is derived from `_outstanding` as `{tid: tok.precharged_tokens for tid, tok in _outstanding.items()}`. Test asserts:
   - (i) **token conservation:** `consumed_tokens + sum(outstanding_tokens.values()) + remaining_tokens == max_tokens`.
   - (ii) **dollar conservation:** `consumed_dollars + sum(t.precharged_dollars for t in _outstanding.values()) + remaining_dollars == max_dollars` — the dollars analogue of (i); proves `remaining_dollars` correctly debits precharged-but-not-yet-reconciled dollars rather than `max_dollars - consumed_dollars` (which would over-report available budget).
   - (iii) Decimal field `consumed_dollars` is exact (`Decimal("0.000123")`, never `0.000122999...`).
   - (iv) calling `running_total()` does not mutate any guard field — assert two successive calls return equal snapshots and that a `precharge` between them is the *only* thing that changes the snapshot.
- [x] **AC-8 — Hypothesis: `BudgetTokenId` non-reuse + format.** `tests/property/test_budget_token_non_reuse.py` — `@given(n=st.integers(1, 50))`: construct a fresh guard with large enough budget; mint `n` tokens; assert (i) `len({t.id for t in tokens}) == n` (no collisions — catches a constant-id implementation), (ii) every `t.id` matches `^[0-9a-f]{32}$` (uuid4 `.hex` — catches `uuid1`, `str(uuid4())` with dashes, or a monotonic counter; ADR-0010 §Consequences names uuid4 explicitly because uuid1 leaks the host MAC address). 500 runs.
- [x] **AC-9 — Hypothesis: reconcile idempotence.** Same file or sibling — `@given(...)`: mint one token; reconcile with random `(actual_in, actual_out, actual_dollars)`; capture `snap_after_first`; reconcile again with the **same** token and *different* actuals; capture `snap_after_second`. Assert:
   - (i) **first reconcile actually moved state** — `snap_after_first.consumed_tokens == actual_in + actual_out` and `snap_after_first.consumed_dollars == actual_dollars`. Without this, a `reconcile` that is a total no-op would still satisfy (ii) trivially.
   - (ii) `snap_after_second == snap_after_first` — the duplicate call did not apply the new actuals.
   - (iii) exactly one `BudgetReconciledDuplicate` event fired (and the second call emitted *no* `BudgetReconciled`).
- [x] **AC-10 — Hypothesis: decimal exactness.** `tests/property/test_budget_decimal_exactness.py` — `@given(values=st.lists(st.decimals(min_value="0.00001", max_value="0.5", places=6), min_size=10, max_size=50))`: mint+reconcile each value as `actual_dollars`; assert `running_total().consumed_dollars == sum(values, Decimal("0"))` exactly (Decimal sum, not float-rounded). `max_examples=200` (a 10–50-element list per example is already broad coverage; the AC text and the TDD snippet must agree on this number). Catches `float`-creep.
- [x] **AC-11 — `import-linter` contract pinning `BudgetToken` import scope.** Stated as an **observable outcome**, not a fixed TOML block (see below for why the obvious TOML does not work):

   > Within non-test code (`codegenie.*` and `plugins.*`), the only modules permitted to import `BudgetToken` are `codegenie.fallback.budget` itself (the definer), `codegenie.fallback.tier` (S6-01), and `codegenie.fallback.leaf.anthropic_adapter` (S3-02). Any other non-test module importing `BudgetToken` is a `make lint-imports` failure.

   Extend `pyproject.toml`'s `[tool.importlinter]` (or wherever S1-06 placed Phase-4 contracts). **`import-linter` operates on module-to-module imports, not on individual symbols** — you cannot forbid `codegenie.fallback.budget.BudgetToken` while still allowing `LlmInvocationGuard`/`BudgetExceeded` to be imported from the same module. The implementer picks the mechanism that achieves the outcome above; the realistic options are:
   - a `forbidden` contract on the *module* `codegenie.fallback.budget` with `ignore_imports` whitelisting the two sanctioned importers (over-broad — also blocks the issuer/exception imports, so callers of `LlmInvocationGuard` would need entries too), **or**
   - splitting `BudgetToken` into its own submodule `codegenie.fallback.budget_token` so a clean module-level `forbidden` contract expresses exactly the scope (preferred — the contract then reads naturally and AC-12's positive control is unambiguous).

   Mirror the precedent S1-06 set for Phase-4 `import-linter` contracts; if S1-06 scope-pinned `anthropic` with a `forbidden` contract, reuse that shape. Surface the chosen mechanism per Global Rule 7. **AC-12's positive-control fixture is the load-bearing proof** — the contract is only as good as the test that proves it fires.
- [x] **AC-12 — Sole-importer test.** `tests/fence/test_budget_token_scope.py` — runs `make lint-imports` (or invokes `lintforbidden` programmatically) and asserts zero violations. Includes a **positive control**: a fixture under `tests/fixtures/violators/forged_budget_import.py` that imports `BudgetToken` outside the allowed scope; the test verifies the contract would fire on that fixture (similar mechanic to S2-04's positive-control fixture for the AST walk).
- [x] **AC-13 — Event-kind registration in `codegenie.plugins.events`.** Five new workflow-internal event classes ship in `src/codegenie/plugins/events.py`: `BudgetPrecharged`, `BudgetReconciled`, `BudgetReconciledDuplicate`, `BudgetCapExceeded`, `BudgetUnknownTokenReconcile`. (Two are renamed from a draft to avoid colliding with the exception names `BudgetExceeded` / `BudgetReconcileUnknownToken`, which live in `fallback/budget.py` — an event and an exception must not share a name.) Each is a Pydantic model exactly mirroring the existing `WorkflowInternalEvent` members (e.g. `PluginResolved`): `model_config = ConfigDict(frozen=True, extra="forbid")`, a unique `event_type: Literal[...]` discriminator, `event_id: EventId`, `workflow_id: WorkflowId`, `timestamp: datetime`, plus payload fields. **Registration = two edits in `events.py`:** add each class to the `WorkflowInternalEvent` `Annotated[... , Field(discriminator="event_type")]` union *and* to the `_INTERNAL_CLASSES` tuple — `EventLog.emit_internal` does `isinstance(event, _INTERNAL_CLASSES)` and raises `TypeError` for an unregistered class. **Stream choice:** these are **workflow-internal**, not spanning — they describe one workflow's budget accounting (mirrors S2-04's `PromptAssembled` resolution). ADR-0010 says the budget cost *vocabulary* composes into Phase 13's unified ledger; that is a forward-compat statement about the event payload shape, not a requirement that S2-05 emit on the BLAKE3-chained spanning stream. There is **no `tests/fence/test_event_kinds_complete.py`** (S2-04 confirmed it does not exist). The registration is exercised by `tests/unit/plugins/test_events.py` — extend it: emit each new event via `emit_internal`, round-trip it through `replay()`, and assert an unregistered-class instance raises `TypeError`.
- [x] **AC-14 — Deterministic exhaustion boundary.** `precharge` is **synchronous** (`def precharge`, per AC-4 and arch §Component 5 — no `await`). A synchronous method with no suspension point is atomic on a single event loop *by construction*; "50 concurrent `precharge` via `asyncio.gather`" is incoherent (`gather` takes coroutines, not sync calls) and proving race-safety for a non-suspending function is vacuous. ADR-0010 §Internal structure is explicit that Phase 4 is single-loop with a plain `int` counter; real multi-loop safety is Phase 9's concern (Temporal workers). So this AC instead pins the **exhaustion boundary deterministically:** construct a guard with `max_tokens = k * per_call_max_tokens` for a small `k`; call `precharge(requested_tokens=per_call_max_tokens)` in a loop; assert (i) exactly the first `k` calls succeed and the `(k+1)`-th raises `BudgetExceeded(reason="workflow_max_tokens_exceeded")`, (ii) at every step `consumed_tokens + sum(t.precharged_tokens for t in _outstanding.values()) <= max_tokens` holds, (iii) the rejected `(k+1)`-th call left `running_total()` byte-identical to before it (no partial mint). Do **not** introduce `asyncio.Lock` — surface the temptation per Global Rule 7.
- [x] **AC-15 — `LeafLlm.invoke` signature type-check.** A deliberately-failing `mypy` fixture at `tests/fixtures/typecheck/budget_token_missing.py`:
   ```python
   from codegenie.fallback.budget import BudgetToken
   from codegenie.fallback.leaf.protocol import LeafLlm  # S3-01

   async def caller(leaf: LeafLlm) -> None:
       # MISSING token=... — should mypy-error
       await leaf.invoke(system_prompt=..., user_message=..., schema=...)
   ```
   `tests/fence/test_budget_token_typecheck.py` runs `mypy --strict tests/fixtures/typecheck/budget_token_missing.py` via subprocess and asserts a non-zero exit with the missing-argument diagnostic. **This AC is BLOCKED until S3-01 ships `LeafLlm` Protocol** — gate this AC with `pytest.importorskip("codegenie.fallback.leaf.protocol")` so S2-05 ships standalone and S3-01's executor turns this AC green when it lands. Document the gating in the test docstring.
- [x] **AC-16 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean. `make lint-imports` green.
- [x] **AC-17 — `BudgetExceeded` is a structured typed exception, asserted per reason.** `BudgetExceeded` (exception, in `fallback/budget.py`) carries `reason: Literal["per_call_max_exceeded", "workflow_max_tokens_exceeded", "workflow_max_dollars_exceeded"]` plus the numeric context. To avoid `int | Decimal` primitive-union sloppiness, the token-cap reasons carry `int` `projected`/`max`; `workflow_max_dollars_exceeded` carries `Decimal` `projected`/`max` — pin the field names and per-reason types so the executor does not invent a loose shape. Three unit tests (one per reason) drive a guard into each branch and assert (i) the raised `BudgetExceeded.reason` is the expected literal, (ii) the structured numeric fields are present and correct, (iii) a matching `BudgetCapExceeded` event with the same `reason` was emitted to the internal stream **before** the raise (`replay()` shows it). The `workflow_max_dollars_exceeded` test is the regression guard for AC-5's previously-missing dollar cap — it must be impossible to make it pass without a real projected-dollars check.

## Implementation outline

1. **Pre-check S1-04 and S1-01**: does `BudgetToken` / `BudgetSnapshot` already live in `src/codegenie/fallback/budget.py` (model only)? Import / extend; do not duplicate. Do `BudgetTokenId` / `TokenCount` exist in `identifiers.py` yet (validation found they do not)? If not, define them locally in `budget.py` and surface per Global Rule 7.
2. **Register the five events first** in `src/codegenie/plugins/events.py` (AC-13): one Pydantic class each, mirroring `PluginResolved`'s shape; add each to the `WorkflowInternalEvent` union *and* `_INTERNAL_CLASSES`. This unblocks every test that emits or replays.
3. **Implement `LlmInvocationGuard`** as a class (not frozen — it has mutable state). Internal fields: `_consumed_tokens: int`, `_consumed_dollars: Decimal`, `_outstanding: dict[BudgetTokenId, BudgetToken]` (the **full token**, not a bare `TokenCount` — both `precharged_tokens` and `precharged_dollars` are needed for the dollar projection and dollar cap; two parallel id-keyed dicts can desync, so keep one), `_reconciled_ids: set[BudgetTokenId]`, `_event_log: EventLog`, plus the immutable config (`_max_tokens`, `_max_dollars`, `_per_call_max_tokens`). Add a private `_new_event_id() -> EventId` helper mirroring the S2-01 sibling pattern.
4. **`precharge`**: validate `requested_tokens > 0` → `per_call_max` → `workflow_max_tokens` → `workflow_max_dollars` in that fixed order; on any cap failure emit `BudgetCapExceeded` then raise `BudgetExceeded` and leave `_outstanding` untouched; on success mint and insert the full `BudgetToken` (AC-5).
5. **`reconcile`**: validate non-negative actuals; branch on `token.id ∈ _outstanding` (first call) vs `token.id ∈ _reconciled_ids` (duplicate, no-op) vs neither (unknown — emit `BudgetUnknownTokenReconcile`, raise) (AC-6).
6. **`running_total`**: build `BudgetSnapshot` purely from current state; `outstanding_tokens` and `remaining_dollars` are projections over `_outstanding` (AC-7).
7. **Add import-linter contract.** Read S1-06's contract syntax precedent; decide module-level mechanism per AC-11 (a dedicated `budget_token` submodule is the clean option).
8. **Write Hypothesis properties** before the unit tests — they are the load-bearing invariants.

## TDD plan — red / green / refactor

### Red — write the failing test first

> **`EventLog` API — do not regress this.** `EventLog` lives in `codegenie.plugins.events`, **not** `codegenie.audit`. Its constructor is `EventLog(root: Path, workflow_id: WorkflowId)` — there is no zero-arg form. Events are read via `list(log.replay())`, not a `.events` attribute. **Hypothesis footgun:** a pytest `tmp_path` fixture is resolved *once* per test function and reused across every generated example, so an `EventLog` built on it accumulates events across examples and the duplicate-count assertion below would see N dupes, not 1. Build a *fresh* `EventLog` on a fresh temp directory **inside each example** (the `_fresh_guard` helper below does this).

```python
# tests/property/test_budget_token_non_reuse.py
from __future__ import annotations

import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from hypothesis import given, settings, strategies as st

from codegenie.fallback.budget import LlmInvocationGuard
from codegenie.plugins.events import BudgetReconciledDuplicate, EventLog
from codegenie.types.identifiers import WorkflowId

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


@contextmanager
def _fresh_guard(**kwargs: object) -> Iterator[LlmInvocationGuard]:
    """A guard whose EventLog is isolated to a per-example temp dir."""
    with tempfile.TemporaryDirectory() as d:
        log = EventLog(root=Path(d), workflow_id=WorkflowId("wf-budget-test"))
        yield LlmInvocationGuard(event_log=log, **kwargs)  # type: ignore[arg-type]


@given(n=st.integers(min_value=1, max_value=50))
@settings(max_examples=500, deadline=None)
def test_each_precharge_mints_a_fresh_unique_token_id(n: int) -> None:
    with _fresh_guard(
        max_tokens=10_000_000,            # big enough for n×1000
        max_dollars=Decimal("100.00"),
        per_call_max_tokens=32_000,
    ) as guard:
        tokens = [guard.precharge(requested_tokens=1000) for _ in range(n)]
    assert len({t.id for t in tokens}) == n            # no collisions
    assert all(_HEX32.match(t.id) for t in tokens)     # uuid4 .hex, not uuid1/dashed/counter


@given(actual_pair=st.tuples(st.integers(0, 500), st.integers(0, 500)))
@settings(max_examples=500, deadline=None)
def test_reconcile_is_idempotent_on_token_id(actual_pair: tuple[int, int]) -> None:
    actual_in, actual_out = actual_pair
    with tempfile.TemporaryDirectory() as d:
        log = EventLog(root=Path(d), workflow_id=WorkflowId("wf-budget-test"))
        guard = LlmInvocationGuard(
            max_tokens=100_000, max_dollars=Decimal("10.0"),
            per_call_max_tokens=32_000, event_log=log,
        )
        token = guard.precharge(requested_tokens=1000)

        guard.reconcile(token, actual_in=actual_in, actual_out=actual_out,
                        actual_dollars=Decimal("0.001"))
        snap_after_first = guard.running_total()
        # First reconcile must actually move state — guards against a no-op reconcile.
        assert snap_after_first.consumed_tokens == actual_in + actual_out
        assert snap_after_first.consumed_dollars == Decimal("0.001")

        # Second reconcile with DIFFERENT actuals must not double-count.
        guard.reconcile(token, actual_in=actual_in + 100, actual_out=actual_out + 100,
                        actual_dollars=Decimal("0.999"))
        snap_after_second = guard.running_total()
        events = list(log.replay())

    assert snap_after_second == snap_after_first
    dupes = [e for e in events if isinstance(e, BudgetReconciledDuplicate)]
    assert len(dupes) == 1
```

```python
# tests/property/test_budget_decimal_exactness.py
from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from hypothesis import given, settings, strategies as st

from codegenie.fallback.budget import LlmInvocationGuard
from codegenie.plugins.events import EventLog
from codegenie.types.identifiers import WorkflowId


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
    with tempfile.TemporaryDirectory() as d:
        log = EventLog(root=Path(d), workflow_id=WorkflowId("wf-budget-test"))
        guard = LlmInvocationGuard(
            max_tokens=100_000_000, max_dollars=Decimal("100.0"),
            per_call_max_tokens=32_000, event_log=log,
        )
        for v in values:
            tok = guard.precharge(requested_tokens=1)
            guard.reconcile(tok, actual_in=1, actual_out=0, actual_dollars=v)
        consumed = guard.running_total().consumed_dollars
    assert consumed == sum(values, Decimal("0"))
```

Run; expect `ModuleNotFoundError` on `codegenie.fallback.budget` (and on the not-yet-registered `BudgetReconciledDuplicate` event) — the **expected** red, not a stale-import red.

### Green — make it pass

Implement `budget.py`. Smallest correct code. Keep the state mutations strictly inside `precharge` / `reconcile`; do not leak `_consumed_tokens` etc. through public methods other than `running_total()`.

### Refactor — clean up

- Extract the "validate requested_tokens" helper if it has more than one branch.
- Verify `reconcile` is at most 25 lines — three branches (first / duplicate / unknown).
- Decimal-rate-per-token constant lives at module scope as `_DEFAULT_DOLLARS_PER_TOKEN: Final[Decimal]`; module docstring documents that S7-04's `plugin.yaml` overrides it.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/budget.py` | `BudgetToken`, `BudgetSnapshot`, `LlmInvocationGuard`, `BudgetExceeded`, `BudgetReconcileUnknownToken` exceptions, `_DEFAULT_DOLLARS_PER_TOKEN`. (If AC-11's preferred mechanism is chosen, `BudgetToken` may instead live in `src/codegenie/fallback/budget_token.py`.) |
| `src/codegenie/plugins/events.py` | Add five workflow-internal event classes (`BudgetPrecharged`, `BudgetReconciled`, `BudgetReconciledDuplicate`, `BudgetCapExceeded`, `BudgetUnknownTokenReconcile`); register each in the `WorkflowInternalEvent` union + `_INTERNAL_CLASSES`. |
| `pyproject.toml` | Add `import-linter` contract for `BudgetToken` scope (AC-11). |
| `tests/unit/fallback/test_budget_guard.py` | AC-4, AC-5 (all four failure branches + no-partial-mint), AC-6 (three branches + negative-input), AC-7, AC-14, AC-17. |
| `tests/property/test_budget_token_non_reuse.py` | AC-8 + AC-9. |
| `tests/property/test_budget_decimal_exactness.py` | AC-10. |
| `tests/fence/test_budget_token_scope.py` | AC-11 + AC-12 import-linter assertion. |
| `tests/fixtures/violators/forged_budget_import.py` | Positive-control fixture for AC-12. |
| `tests/fixtures/typecheck/budget_token_missing.py` | AC-15 (gated on S3-01). |
| `tests/fence/test_budget_token_typecheck.py` | AC-15 mypy subprocess assertion. |
| `tests/unit/plugins/test_events.py` | Extend: emit + `replay()` round-trip for the five new internal events; assert `emit_internal` rejects an unregistered class (AC-13). |

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
- **`BudgetExceeded` is a typed exception with structured fields — see AC-17.** Not just a message string. `reason` is the three-member `Literal`; the `projected`/`max` numeric fields are `int` for the two token-cap reasons and `Decimal` for `workflow_max_dollars_exceeded` (do not smear them into one `int | Decimal` union — AC-17 pins per-reason types). S6-01's `FallbackTier.run` projects the exception to `RecipeApplication.Refused(reason=BUDGET_EXCEEDED, details={...})`.
- **Event log API — `codegenie.plugins.events`, not `codegenie.audit`.** This is the recurring Phase-4 trap (S2-01/02/03/04 were each hardened for it). `EventLog(root: Path, workflow_id: WorkflowId)`; emit typed Pydantic models via `emit_internal`; read via `replay()`. `audit.py` has no `EventLog`. The five budget events are workflow-internal — register them in both the `WorkflowInternalEvent` union and `_INTERNAL_CLASSES` or `emit_internal` raises `TypeError`.
- **The dollar cap is load-bearing, not decorative.** `max_dollars` ($1.50 default) must be enforced inside `precharge` (AC-5's projected-dollars branch). A draft of this story stored `max_dollars` but never checked it — AC-17's `workflow_max_dollars_exceeded` test exists specifically so that regression cannot pass silently again.
- **Store the whole `BudgetToken` in `_outstanding`.** `_outstanding: dict[BudgetTokenId, BudgetToken]` — not `dict[BudgetTokenId, TokenCount]`. The dollar projection (`remaining_dollars`) and the dollar cap both need each outstanding token's `precharged_dollars`; a parallel id→dollars dict is a second source of truth that can desync (illegal-states-representable smell). One dict, project both views from it.
- **Event vs exception names must not collide.** Exceptions `BudgetExceeded` / `BudgetReconcileUnknownToken` live in `fallback/budget.py`; the corresponding *events* are `BudgetCapExceeded` / `BudgetUnknownTokenReconcile` in `plugins/events.py`. Distinct names — a reader (and `grep`) must never have to guess which `BudgetExceeded` is meant.
- **`precharge` is synchronous; do not reach for `asyncio`.** No `async def`, no `asyncio.Lock`, no `asyncio.gather` in its tests (AC-14). A non-suspending sync method is already atomic on Phase 4's single loop; multi-loop safety is Phase 9's problem. Surface any temptation per Global Rule 7.
- **No environment-variable escape.** ADR-0010 §Consequences row 11: API key load is via `keyring`-only (S3-02's concern, not this story's). For *budget* config, the same principle: no `CODEGENIE_BUDGET_MAX_TOKENS` env var. Configuration flows via `plugin.yaml` only (S7-04). This story uses defaults; do not add env-var reads.
- **Async-safety scope.** Phase 4 is single-event-loop; a plain `int` counter is correct. Do **not** preemptively reach for `asyncio.Lock` — Phase 9 (Temporal multi-worker) is when locking becomes load-bearing. ADR-0010 §Internal structure is explicit. Surface temptation to validator per Global Rule 7.
- **The `running_total()` shape is a contract.** S7-10's `tests/integration/test_phase5_contract_snapshot.py` will snapshot the `BudgetSnapshot` model fields and field types. Adding a field is allowed (additive); removing or renaming is a Phase-amendment ADR. Document this in the model's docstring.
