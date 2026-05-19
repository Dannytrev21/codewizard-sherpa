# Validation report — S6-02 (`TrustScorer` with constructor-injected `EventLog` + `SignalKind` open registry)

**Date:** 2026-05-19
**Validator:** phase-story-validator (inline four-lens analysis — subagent prompts hit input length cap, so the four critics' questions were applied directly against the loaded context)
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/03-vuln-deterministic-recipe/stories/S6-02-trust-scorer-injected-log.md`](../S6-02-trust-scorer-injected-log.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's core architecture choices are correct (Gap 5 constructor injection, two-stream EventLog read, strict-AND scoring, open `SignalKind` registry) and trace cleanly to ADR-0001 / ADR-0005 / ADR-0010 / 05-ADR-0003. Goal and scope are unchanged.

But the acceptance criteria and TDD plan had a handful of real gaps an executor could slip a wrong-but-passing implementation through:

1. A self-contradictory AC ("idempotent for the same `(name)` call, but raises on duplicate from different modules") that didn't match the named `PluginAlreadyRegistered` precedent (which **always** raises).
2. `pytest.raises(Exception)` swallowing the difference between `pydantic.ValidationError` and any unrelated error.
3. `set(out.failing) == {...}` losing the "ordered as input" invariant Notes-for-implementer said was load-bearing.
4. No AC for stateless `score()` across calls — Notes mandated it but the lazy-impl thought experiment (cache `_degraded` in `__init__`) would pass every test.
5. No empty-signals contract — Stage 6 always collects 5 signals per architecture, but `score([])` had no defined behavior.
6. No cross-event-type test — the existing tests only ruled out cross-workflow leakage, not cross-event-type leakage.
7. `details` rejection tested with a single nested-dict case; lists / None / bytes / datetime were not pinned.
8. No functional-core / imperative-shell separation in the prescribed impl outline, despite CLAUDE.md mandating it.
9. No import-time-registration AC strong enough to survive a wrong impl moving the registrations into a function nothing calls.
10. The "decorator-like helper" wording in AC contradicted the function-call shape shown in the Implementation outline (matching `register_plugin` per the explicit precedent at `plugins/registry.py:10-16`).

All ten are in-place-fixable; none threaten the goal or scope. → HARDENED.

## Context Brief (Stage 1 output)

### Story snapshot
- **Goal:** ship `TrustScorer(event_log)` (Gap 5 fix; constructor-injection mandatory) with strict-AND scoring + confidence folded from `AdapterDegraded` events filtered on `workflow_id`. Ship the `SignalKind` open registry with 5 Phase-3 module-level registrations.
- **Non-goals:** Phase 5/7 widening of `SignalKind`; per-signal confidence; per-kind `details` schemas; retry decision; spanning-stream reads.

### Goal-to-AC trace (before validation)
All 16 original ACs traced to the goal; none were orthogonal. The gap was in **mutation-resistance**, not coverage of intent.

### Constraints in play
- ADR-0001 §Consequences row 5 — `TrustScorer.__init__(event_log: EventLog)` mandatory; ambient-state rejected.
- ADR-0005 §Consequences — `TrustScorer` reads its own workflow's **internal** stream for `AdapterDegraded`.
- ADR-0010 Decision (3) — `TrustOutcome.confidence: Literal["high", "degraded"]` is a closed Literal (no payload), distinct from `AdapterConfidence` tagged-union.
- 05-ADR-0003 — Phase 5 widens via `register_signal_kind("trace") / ("policy")` in new files; **zero edits** here.
- CLAUDE.md §Conventions — functional core / imperative shell; "every probe declares a module-level `_WARNING_IDS`" framing translated here to: pure helpers do not touch `EventLog`.
- `plugins/registry.py:10-16` — `register_plugin` is explicitly a **function call, NOT a class decorator**. The story had "decorator-like helper" language that contradicted this precedent.
- `plugins/registry.py:18-49` audit anchor — N=5 OR "common-surface only" is the kernel-extract trigger; this story is the 5th registry, so the audit anchor needs an entry. Dispatch shapes still diverge → deferral still holds.
- `plugins/errors.py:74-78` — `PluginAlreadyRegistered(name, existing, duplicate)` is the named precedent for `SignalKindAlreadyRegistered`.

### Open ambiguities surfaced before critics
- AC contradiction on idempotent-vs-raise → flagged as the single `block`-tier finding.
- "Decorator-like helper" language mismatch with function-call outline → harden.

Neither ambiguity required user clarification; both have a clear answer from the named precedent.

## Findings (synthesized from the four-lens inline analysis)

Severity legend: **block** (story should not go to executor without fix) · **harden** (in-place fix applied) · **nit** (small clarification).

### Consistency lens (highest priority — source-of-truth contradictions)

#### C-F1 (block → fixed) — Self-contradictory duplicate-registration AC
- **What was wrong:** "`register_signal_kind(name)` is **idempotent for the same `(name)` call**, but raises `SignalKindAlreadyRegistered(name)` if called twice from different modules — mirrors `PluginRegistry`'s `PluginAlreadyRegistered` shape." This combines two mutually exclusive behaviors.
- **Source of truth:** `src/codegenie/plugins/registry.py:119-122` — `PluginRegistry.register` **always raises** on duplicate; never idempotent. `PluginAlreadyRegistered` carries `name`, `existing`, `duplicate` per `plugins/errors.py:74-78`.
- **Fix applied:** Rewrote as AC-13 ("always raises on duplicate; carries `.name`, `.existing`, `.duplicate`"); added test `test_register_signal_kind_rejects_duplicate_with_origin_payload` that asserts the payload fields are populated, not just that an exception is raised. Documented the rationale in Notes-for-implementer (no idempotent path; tests use `SignalKindRegistry.fresh()` for re-registration).

#### C-F2 (harden → fixed) — "Decorator-like helper" terminology
- **What was wrong:** AC referred to `register_signal_kind` as a "decorator-like helper" but the Implementation outline showed the function-call shape `BUILD = register_signal_kind("build")`.
- **Source of truth:** `plugins/registry.py:10-16` — "**`register_plugin` is a function call, NOT a class decorator.** Plugins are *instances* that carry composed state ... the class-decorator shape used by the three sibling registries would force module-import-time zero-arg construction, breaking the manifest-carrying contract."
- **Fix applied:** AC-11 now says "registration helper (function call, NOT a class decorator — mirrors `register_plugin`'s shape per `plugins/registry.py:10-16` module docstring)." Notes-for-implementer paragraph cross-references ADR-0002 §Decision.

#### C-F3 (harden → fixed) — Import-time registration not pinned explicitly
- **What was wrong:** The story's Notes said "the import is the registration" but no AC structurally enforced that `transforms/__init__.py` imports `signal_kinds`. A consumer doing `from codegenie.transforms import TrustScorer` could observe an empty registry.
- **Fix applied:** AC-12 + a subprocess-import test (`test_fresh_subprocess_import_populates_default_registry`) that spawns a clean Python process, imports `codegenie.transforms`, and asserts the 5 kinds are present. Notes-for-implementer pins the `import codegenie.transforms.signal_kinds  # noqa: F401` obligation in `transforms/__init__.py`.

### Coverage lens

#### Cov-F1 (harden → fixed) — Stateless-`score()` not enforced by any AC
- **What was wrong:** Notes said "the scorer must remain stateless across `score` calls"; no AC pinned it. Lazy impl that caches `_degraded_flag` in `__init__` would pass every original test (which only call `score()` once per scorer instance).
- **Fix applied:** AC-16 + `test_score_is_stateless_across_calls` — emits `AdapterDegraded` *between* two `score()` calls and asserts the second outcome's confidence flipped.

#### Cov-F2 (harden → fixed) — `failing` list order not pinned
- **What was wrong:** Notes-for-implementer §6 said "ordered as input"; no AC. The parametrize test used `assert set(out.failing) == {...}`, which would accept a sorted-`failing` implementation.
- **Fix applied:** AC-4 + AC-19 + new `test_failing_preserves_caller_order_not_sorted` test using a deliberately reversed kind sequence; parametrize test now asserts list equality.

#### Cov-F3 (harden → fixed) — Empty-signals contract undefined
- **What was wrong:** `score([])` had no documented behavior. Architecture says Stage 6 collects 5 signals; an empty list is a caller bug. Silent `passed=True, confidence="high"` would mis-report a broken collection as a successful workflow.
- **Fix applied:** AC-10 + `EmptySignals` exception + `test_empty_signals_rejected`.

#### Cov-F4 (harden → fixed) — Cross-event-type safety not tested
- **What was wrong:** Only cross-workflow leakage was tested. A wrong impl filtering on `workflow_id` only (ignoring `event_type`) would pass `test_confidence_high_when_adapter_degraded_is_other_workflow` but fail when any other internal event happens to share the workflow.
- **Fix applied:** AC-17 + `test_confidence_high_when_internal_event_is_not_adapter_degraded` (emits `PluginResolved` with matching `workflow_id`, asserts confidence stays high).

#### Cov-F5 (harden → fixed) — `outcome.signals` preservation not tested
- **What was wrong:** AC said "preserved verbatim"; no test asserted list order or membership.
- **Fix applied:** AC-5 + `test_outcome_signals_preserved_verbatim` (asserts `out.signals == signals` and `[id(s) for s in out.signals] == [id(s) for s in signals]` — no rebuilding).

#### Cov-F6 (harden → fixed) — `details` rejection too thin
- **What was wrong:** Single `with pytest.raises(Exception): TrustSignal(... details={"nested": {"oops": "object"}})` test. A permissive impl that only rejected dict-nesting would pass.
- **Fix applied:** Parametrized test `test_trust_signal_details_primitives_only` covers list, tuple, None, bytes, datetime, nested-dict, and arbitrary object.

### Test-Quality lens

#### TQ-F1 (harden → fixed) — `pytest.raises(Exception)` too broad
- **What was wrong:** Would pass on any exception including `TypeError`, `KeyError`, `RuntimeError`. The intent (Pydantic `ValidationError`) was a comment, not an assertion.
- **Fix applied:** Replaced with `pytest.raises(ValidationError)` (imported from `pydantic`).

#### TQ-F2 (harden → fixed) — `set(out.failing) == {...}` loses order
- See Cov-F2 above. Tightened to list equality.

#### TQ-F3 (harden → fixed) — `test_phase3_five_kinds_registered_at_import` satisfiable by side effect
- **What was wrong:** The test would pass if *any* prior test (or test-collection step) had populated the registry; it didn't actually test the module-level statements.
- **Fix applied:**
  1. Direct module-attribute assertion: `assert BUILD == SignalKind("build")` plus `assert BUILD in signal_kind_registry`.
  2. AST-walk test `test_signal_kinds_module_has_5_top_level_register_calls` — survives the mutation "moved the registrations into a function nothing calls."
  3. Subprocess-import test (also referenced in C-F3) for the strongest assertion.

#### TQ-F4 (harden → fixed) — Duplicate-error payload not pinned
- **What was wrong:** Only `with pytest.raises(SignalKindAlreadyRegistered)`; the test would pass against `raise SignalKindAlreadyRegistered(name="...")` with no origin fields.
- **Fix applied:** Test now asserts `.name`, `.existing`, `.duplicate` are populated and that the message names the colliding kind.

#### TQ-F5 (nit → added) — Property test for confidence fold
- **What was wrong:** The confidence rule ("`degraded` iff at least one `AdapterDegraded` with matching `workflow_id`") is a clean property; a Hypothesis test future-proofs against subtle filter bugs (e.g., a wrong impl using `event.workflow_id != self._event_log.workflow_id` somewhere).
- **Fix applied:** `test_confidence_property_iff_matching_adapter_degraded` generates random sequences of `(event_type, workflow_id)` pairs and asserts the outcome's confidence exactly matches the reference fold.

### Design-Patterns lens

#### DP-F1 (harden → fixed) — Pure-impure tangle in `score()`
- **Smell:** Functional-core / imperative-shell violation (CLAUDE.md §Conventions).
- **What was wrong:** `score()` mixed pure logic (strict-AND fold over signals) with impure I/O (`self._event_log.replay()`).
- **Fix applied:** Implementation outline now prescribes two pure helpers — `_compute_strict_and(signals)` and `_has_adapter_degraded_for_workflow(events, workflow_id)` — and `TrustScorer.score()` as the imperative shell that calls them. AC-15 + an AST-walk purity test (`test_pure_helpers_have_no_io_dependencies`) + a unit test on `_compute_strict_and` independently.

#### DP-F2 (nit → noted) — 5th-registry audit anchor
- **Smell:** Implicit registry pattern; rule-of-three threshold tracking.
- **What was wrong:** This is the 5th decorator/function-call registry. `plugins/registry.py:18-49` documents the kernel-extract trigger as "N=5 OR common-surface-only." N=5 fires.
- **Fix applied (deferral preserved):** Notes-for-implementer paragraph documents that the trigger fires but the deferral still holds (dispatch shapes diverge; `SignalKindRegistry`'s minimal surface would couple to the four heavyweight registries' bespoke dispatch). Action item: the implementer reword `plugins/registry.py`'s audit-anchor paragraph to bump the count to 5.

#### DP-F3 (nit → noted) — `InMemorySink` test fixture
- **Smell:** Hexagonal / ports-and-adapters opportunity (test seam).
- **What was wrong:** Original test code used `tmp_path` + zstd round-trips. S6-01 introduced `InMemorySink` for exactly this case.
- **Fix applied:** New TDD plan uses `InMemorySink()`. Notes-for-implementer documents the convention (in-memory for tests; disk for production).

#### DP-F4 (nit → not flagged) — `TrustScorer` depends on concrete `EventLog`, not Protocol
- **Considered:** Should `TrustScorer.__init__` take an `EventLogReader` Protocol (`replay()` + `workflow_id`)? 
- **Resolution:** Not flagged. S6-04 (orchestrator) will use the same concrete `EventLog` in tests; the in-memory-sink test seam already gives clean fakes. Introducing a Protocol is YAGNI per Rule 2 unless a third consumer arrives. No action.

### Lessons reusable across the family

- The "Notes-for-implementer mandates X, but no AC enforces X" pattern is a recurring story smell. When a Note says something is mandatory, it deserves an AC + test.
- Cross-checking against the named precedent (`PluginAlreadyRegistered`, `PluginRegistry.register`) catches almost every "registry-like" inconsistency without needing fresh research.
- The lazy-impl thought experiment caught both stateless-score and order-preservation gaps. Worth doing for every score-/fold-/walk-shaped story.

## Edits applied — locations in the story

| Section | Edit |
|---|---|
| Header | Status `Ready` → `HARDENED`; appended Validation-notes block summarizing changes. |
| Acceptance criteria | Renumbered AC-1 … AC-22; rewrote duplicate-registration AC (AC-13); added AC-10 (empty signals), AC-15 (pure helpers), AC-16 (stateless), AC-17 (cross-event-type), AC-12 (import-time registration), AC-19 (list-equality strict-AND), AC-20 (no module-level mutable state), AC-4 (failing order), AC-5 (signals preservation); tightened AC-7 (details primitives parametrize), AC-11 ("registration helper, not decorator"). |
| Implementation outline | Split `score()` into pure helpers + imperative shell; pinned `SignalKindRegistry` shape with `_kinds: dict[SignalKind, str]` and `origin` parameter; added `transforms/__init__.py` import obligation. |
| TDD plan | Wholesale rewrite of `tests/unit/transforms/test_trust_scorer.py`: typed imports, `InMemorySink` fixtures, list-equality parametrize, parametrized `details` rejection, cross-event-type test, stateless test, empty-signals test, AST-walk purity test, subprocess-import test, Hypothesis property test, origin-payload assertion. |
| Refactor section | Updated O(N) note to reference AC-16; added AST-purity verification step. |
| Notes for the implementer | Extended with: structural ambient-state defense (forbidden classmethod names); 5th-registry kernel-extract audit-anchor obligation; `InMemorySink` convention; `transforms/__init__.py` import obligation; reworded the registration-mechanism paragraph to reference `register_plugin` (function-call, not decorator). |

## Verdict

**HARDENED.** Ready for executor. The story now constrains a correct implementation tightly enough that a wrong implementation cannot pass the TDD plan, and the prescribed shape (pure helpers + imperative shell + explicit `__init__` import obligation + tracked-origin duplicate errors) follows the existing codebase conventions without inventing new scaffolding.

Open items deferred to the implementer (none block execution):
- Reword the audit-anchor paragraph in `src/codegenie/plugins/registry.py` (lines 18-49) to bump the registry count to 5 and document this story as the new precedent for the deferral.
- Confirm with S6-01's hardened tests that `InMemorySink` is the export name (the story assumes so; if S6-01 used a different name, update imports accordingly).
