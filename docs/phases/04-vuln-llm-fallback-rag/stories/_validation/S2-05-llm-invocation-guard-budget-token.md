# Validation report: S2-05 — LlmInvocationGuard + BudgetToken capability issuer

**Validated:** 2026-05-21
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S2-05's goal is sound and traces cleanly to ADR-0010: ship `LlmInvocationGuard` with `precharge`/`reconcile`/`running_total`, the load-bearing Hypothesis properties, and the `import-linter` contract that pins `BudgetToken`'s import scope. The capability + circuit-breaker shape is right, and the functional-core/imperative-shell split (mutable guard, pure `running_total()`) is well chosen.

But the draft was not executor-ready. It carried the **recurring Phase-4 stale-`EventLog` mistake** that S2-01/02/03/04 were each hardened against (`codegenie.audit.EventLog`, zero-arg construction, `.events` — all wrong; the real surface is `codegenie.plugins.events.EventLog`). It left the **$1.50 dollar cap unenforced** — `max_dollars` was a stored-but-never-checked constructor param and the `BudgetExceeded(reason="workflow_max_dollars_exceeded")` branch was unreachable. It prescribed an **internal state shape** (`dict[BudgetTokenId, TokenCount]`) that structurally cannot compute `remaining_dollars`. It made a **false Pydantic claim** (a `_marker` private attribute "makes hand-forged dicts fail validation"). It used `BudgetExceeded` as both an exception and an event name, and framed a synchronous `precharge` as needing an `asyncio.gather` race test. All fixable in place — verdict **HARDENED**.

## Context brief

- **Story snapshot:** `LlmInvocationGuard(max_tokens, max_dollars, per_call_max_tokens, event_log)` with `precharge(requested_tokens) -> BudgetToken`, idempotent `reconcile(...)`, `running_total() -> BudgetSnapshot`; three Hypothesis properties; one `import-linter` contract.
- **Phase constraints:** ADR-0010 — capability-as-function-signature-argument, two-frame discipline, defaults 250K/$1.50/32K, decimal exactness, idempotent reconcile, no env-var escape. ADR-0003 — module under `src/codegenie/fallback/`.
- **Existing-code reality:** `src/codegenie/fallback/` is not implemented yet (all Phase-4 stories are docs-only). `EventLog` lives in `src/codegenie/plugins/events.py` — `EventLog(root: Path, workflow_id: WorkflowId, *, clock=None, sink=None)`, typed-Pydantic `emit_internal`/`emit_spanning`, `replay()` iterator; `_INTERNAL_CLASSES` tuple + `WorkflowInternalEvent` `Annotated` union are the registration points. `src/codegenie/audit.py` holds `AuditWriter`/`RunRecord` only — no `EventLog`. `tests/fence/test_event_kinds_complete.py` does not exist. `BudgetTokenId`/`TokenCount` are not yet in `identifiers.py`.
- **Sibling lineage:** This is the last of Step 2's five trust-boundary primitives. S2-01/02/03/04 were all HARDENED for the same stale `codegenie.audit.EventLog` assumption; S2-04 established the local-newtype resolution, the positive-control-fixture pattern, and the `WorkflowInternalEvent` registration framing carried forward here.
- **Open ambiguities:** none requiring user input. The one ambiguous design point (internal vs spanning event stream) was resolved autonomously — see Conflict resolutions.

## Findings by critic

### Consistency critic

- **C1 (block)** — Stale `codegenie.audit.EventLog` API throughout (References, TDD plan imports/construction/`.events`, AC-13, Files-to-touch). Identical to S2-04 C2. The real surface is `codegenie.plugins.events.EventLog`. Fixed everywhere.
- **C2 (block)** — Event registration wrong. `tests/fence/test_event_kinds_complete.py` does not exist (S2-04 removed it). Real registration = a `WorkflowInternalEvent` Pydantic subclass added to the `Annotated` union **and** the `_INTERNAL_CLASSES` tuple; `emit_internal` does `isinstance(event, _INTERNAL_CLASSES)` and `TypeError`s otherwise. AC-13 and Files-to-touch rewritten; test moves to `tests/unit/plugins/test_events.py`.
- **C3 (harden)** — The story's own Context paragraph parroted arch §Testing-strategy line 963 ("reconcile twice *raises*"), which contradicts the story's AC-6/AC-9 (idempotent no-op) **and** ADR-0010 §Tradeoffs row 3 ("duplicate reconcile calls must be safe") **and** arch §Component 5 ("idempotent on `BudgetTokenId`"). The idempotent-no-op semantics are authoritative; the arch one-liner is stale. Context corrected; the genuine raise-path (`BudgetReconcileUnknownToken` for never-precharged tokens) called out as the distinct case.
- **C4 (note, not a defect)** — Arch §Component 5 lists `BudgetToken` without an `id` field, yet keys `outstanding_tokens` by `BudgetTokenId` and makes reconcile idempotent "on `BudgetTokenId`". The arch is internally incomplete; the story's `id: BudgetTokenId` addition is the necessary, correct resolution. Documented as deliberate in AC-2; not undone.

### Coverage critic

- **Cov1 (block)** — The $1.50 dollar cap was unenforced. `max_dollars` was an AC-4 constructor param and `BudgetSnapshot` exposed `max_dollars`/`remaining_dollars`, but AC-5's `precharge` only checked tokens, so `BudgetExceeded(reason="workflow_max_dollars_exceeded")` (named in Notes) was unreachable. ADR-0010 §Decision sets it as a *hard* cap. AC-5 now requires a projected-dollars check + no-partial-mint guarantee; AC-17 added as the per-reason regression test.
- **Cov2 (harden)** — `remaining_dollars` was a computed `BudgetSnapshot` field with no test constraining it. AC-7 now asserts the dollar-conservation invariant alongside the token one.
- **Cov3 (harden)** — `reconcile` had no input validation; a negative `actual_*` would silently *credit* the budget. AC-6 now rejects negatives with `ValueError`, symmetric with AC-5's `requested_tokens > 0`.
- **Cov4 (harden)** — AC-6's unknown-token raise had no explicit test in the TDD plan (lumped vaguely into "AC-4..AC-7"). AC-6 now mandates a dedicated test that constructs a never-precharged `BudgetToken` and asserts the raise + event.

### Test-Quality critic

- **TQ1 (block)** — Both property-test snippets imported `EventLog` from the wrong module, constructed it zero-arg, and read `.events`. The "expect `ModuleNotFoundError`" red phase would have failed at `codegenie.audit` import for the *wrong* reason. Additionally, an `EventLog` built on a pytest `tmp_path` fixture is reused across all Hypothesis examples — events accumulate and the `len(dupes) == 1` assertion would see N. Both snippets rewritten with a per-example `tempfile.TemporaryDirectory()` + `EventLog(root=..., workflow_id=...)` and `list(log.replay())`.
- **TQ2 (harden)** — AC-8's `len({t.id ...}) == n` catches a constant-id impl but not `uuid1` (MAC-leaking — ADR-0010 explicitly forbids) or a dashed `str(uuid4())` or a counter. Added a `^[0-9a-f]{32}$` format assertion.
- **TQ3 (harden)** — AC-9's idempotence property (`snap1 == snap2`) is satisfied trivially by a `reconcile` that is a *total* no-op. Added a positive assertion that the first reconcile actually moved `consumed_tokens`/`consumed_dollars`, and that the second emitted no `BudgetReconciled`.
- **TQ4 (harden)** — AC-14 framed a *synchronous* `precharge` as needing a 50-way `asyncio.gather` race test. `gather` takes coroutines, not sync calls (`TypeError`), and a non-suspending sync method is atomic on a single loop by construction — the test was theater. Reframed to a deterministic exhaustion-boundary test (mint until the `(k+1)`-th call trips `BudgetExceeded`; invariant holds at every step; rejected call leaves state byte-identical).
- **TQ5 (harden)** — AC-10 text said "500+ runs"; the snippet set `max_examples=200`. Reconciled to 200 in both.
- **TQ6 (harden)** — No test asserted `BudgetExceeded`'s structured `reason`/`projected`/`max` per branch. Added AC-17 — one test per reason literal, asserting the raise fields and the matching pre-raise `BudgetCapExceeded` event.

### Design-Patterns critic

- **DP1 (harden)** — Implementation outline prescribed `_outstanding_tokens: dict[BudgetTokenId, TokenCount]` — token counts only. `remaining_dollars` and the dollar cap (Cov1) both need each outstanding token's `precharged_dollars`; a second parallel id-keyed dict is a second source of truth that can desync (illegal-states-representable). Fixed: store the full `BudgetToken` (`_outstanding: dict[BudgetTokenId, BudgetToken]`) and project both views. One source of truth.
- **DP2 (harden)** — `BudgetToken._marker` was claimed to be a discriminator that "makes hand-forged dicts fail Pydantic validation." False in Pydantic v2 — a leading-underscore attribute is a *private attribute*: not a field, not in the schema, not validated, irrelevant to `extra="forbid"`. AC-2 reworded to the honest model (matching arch row 882 on `SolvedExampleWriteCapability`): the `import-linter` contract is the sole structural guard; in-process construction is forgeable and that residual risk is accepted. `_marker` removed.
- **DP3 (harden)** — `BudgetExceeded` was used as both an exception (`fallback/budget.py`) and an event kind (AC-13); same for `BudgetReconcileUnknownToken`. Events renamed `BudgetCapExceeded` / `BudgetUnknownTokenReconcile`; exceptions keep their names.
- **DP4 (harden)** — AC-11 shipped a fixed TOML block that `import-linter` cannot honor — it operates on module-to-module imports, not individual symbols, so `forbidden_modules = ["...budget.BudgetToken"]` cannot forbid `BudgetToken` while allowing `LlmInvocationGuard` from the same module. Rewritten as an observable-outcome AC with the realistic mechanism options (preferred: split `BudgetToken` into its own submodule for a clean module-level `forbidden` contract); AC-12's positive control named as the load-bearing proof.
- **DP5 (note — STRONG aspect)** — The guard-is-a-mutable-class / `running_total()`-is-a-pure-projection split is a correct functional-core/imperative-shell application; left unchanged. The capability pattern (`BudgetToken` as a function-signature argument) and circuit breaker are correctly applied per ADR-0010. No new abstraction introduced — Rule 2 respected; no registry/strategy was warranted here.

## Research briefs

None. Every finding was resolved from in-repo docs, current `src/codegenie/plugins/events.py` source, and the S2-04 sibling validation report. No finding was tagged `NEEDS RESEARCH`; Stage 3 skipped.

## Conflict resolutions

- **Event stream: internal vs spanning.** ADR-0010 says budget `cost.llm.call` entries "compose with Phase 5's `cost.sandbox.run`" for Phase 13's unified ledger, and `CostSandboxRun` is a *spanning* event — which could argue the budget events belong on the BLAKE3-chained spanning stream. Resolved to **workflow-internal**, mirroring S2-04's C3 resolution for `PromptAssembled`: the five budget events describe one workflow's budget accounting. ADR-0010's "composes" is a forward-compat statement about event-payload *vocabulary*, not a requirement to emit on the spanning chain. The `LlmInvocationGuard` is a per-workflow object. Pinned internal in AC-13; rationale recorded there.
- **Consistency vs Coverage on `_marker`.** Coverage might want a real deserialization-time discriminator; Consistency (arch writes `_marker` with the underscore) and the type-system reality (private attrs are not validated) win — the honest framing is that the import-linter contract is the only structural guard. `_marker` removed rather than promoted to a public field, because no story yet needs disk-deserialized `BudgetToken`s.
- **Arch testing-strategy line vs ADR-0010.** Arch §Testing-strategy line 963 ("reconcile twice raises") contradicts ADR-0010 §Tradeoffs row 3 + arch §Component 5. Consistency priority: the ADR + the component spec win; the testing-strategy one-liner is stale. Story's AC-6 (idempotent no-op) was already correct and kept.

## Edits applied

1. Header `Status: Ready -> HARDENED`; `Validation notes` block added under the header.
2. Context paragraph corrected: reconcile-twice is an idempotent no-op, not a raise; stale arch line 963 flagged.
3. References: `audit.py` entry replaced with the real `plugins/events.py` API + `tests/unit/plugins/test_events.py` precedent + an `identifiers.py` pre-check note.
4. AC-2: `_marker` removed; honest threat-model note added; `id`-field arch-gap resolution documented.
5. AC-5: projected-dollars cap branch added; no-partial-mint-on-failure guarantee; fixed cap-check ordering.
6. AC-6: negative-actuals `ValueError`; three branches each with a named test; `BudgetUnknownTokenReconcile` event on the unknown path.
7. AC-7: dollar-conservation invariant (ii) and a no-mutation assertion (iv) added.
8. AC-8: uuid4 `^[0-9a-f]{32}$` format assertion added.
9. AC-9: first-reconcile-moved-state positive assertion; no-second-`BudgetReconciled` assertion.
10. AC-10: run count reconciled to `max_examples=200` in AC text.
11. AC-11: rewritten as an observable-outcome AC; unworkable fixed TOML replaced with mechanism options.
12. AC-13: rewritten for `plugins/events.py` registration (`WorkflowInternalEvent` union + `_INTERNAL_CLASSES`); five event names pinned; internal-stream choice justified.
13. AC-14: reframed from incoherent `asyncio.gather` race test to a deterministic exhaustion-boundary test.
14. AC-17 added: per-reason `BudgetExceeded` structured-field tests; the dollar-cap regression guard.
15. Implementation outline: events-first step; `_outstanding: dict[BudgetTokenId, BudgetToken]`; `_new_event_id` helper; fixed cap-check order.
16. TDD plan Red section: both property snippets rewritten — correct `EventLog` import/construction, per-example temp dir (`_fresh_guard` helper / inline `TemporaryDirectory`), `list(log.replay())`, `isinstance` event filtering, hex-format + first-reconcile-effect assertions.
17. Files-to-touch: `audit.py` → `plugins/events.py`; `tests/fence/test_event_kinds_complete.py` → `tests/unit/plugins/test_events.py`; AC coverage column updated.
18. Notes for the implementer: six notes added/updated (EventLog API, dollar cap is load-bearing, `_outstanding` whole-token shape, event/exception name collision, sync `precharge` / no `asyncio`, `BudgetExceeded` per-reason field types).

## Verdict rationale

HARDENED. The story's goal is correct and traces to ADR-0010 with no structural contradiction — the capability + circuit-breaker design, two-frame discipline, decimal exactness, and idempotent reconcile are all right. The blockers were stale codebase assumptions (the recurring `codegenie.audit.EventLog` trap), one genuine missing requirement (the dollar cap was specified by the ADR but never wired into `precharge`), an internal-state shape that could not satisfy the dollar projection, and a handful of mutation-weak tests. After the edits, every AC is individually verifiable, the dollar cap has a regression test that cannot pass without real enforcement, the TDD plan will collect against the real event API, and the prescribed implementation has one source of truth for outstanding budget. Ready for `phase-story-executor`.

## Recommended next step

`phase-story-executor` can implement S2-05 standalone — it has no hard dependency on S2-01/02/03/04 landing first (Notes confirm independence). Sequence: (1) register the five events in `plugins/events.py` and extend `tests/unit/plugins/test_events.py`; (2) write the three Hypothesis properties (AC-8/9/10) — the load-bearing invariants; (3) implement `budget.py` with `_outstanding: dict[BudgetTokenId, BudgetToken]`; (4) AC-17's dollar-cap test last, as the proof the previously-missing cap is real. AC-15 stays gated on S3-01 via `pytest.importorskip`.
