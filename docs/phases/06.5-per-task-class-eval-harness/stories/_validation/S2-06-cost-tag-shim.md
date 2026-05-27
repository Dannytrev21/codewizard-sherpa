# Validation report — S2-06 (cost-tag env shim + Phase 5 ADR-0010 amendment)

**Validated:** 2026-05-26
**Verdict:** **HARDENED**
**Story status updated to:** `Ready (HARDENED 2026-05-26)`

## TL;DR

The story is structurally sound and traces cleanly to ADR-0007. Four
critic lenses surfaced **one block-level concurrency hazard** the story
silently inherits from the runner architecture (`asyncio.Semaphore(N=4)`
fan-out vs. process-global env var), plus a cluster of test-quality and
coverage gaps where ACs and tests were thin enough that an obviously
wrong implementation could pass.

The block-level finding is **not** a design redo — it lives at the
*contract* between this story (the context manager) and S3-02 (the
runner that calls it). The story now (a) declares the
single-threaded / non-concurrent re-entrancy contract explicitly in
the public docstring, (b) carries an AC asserting that contract,
(c) flags the runner-side serialization obligation in Notes-for-
implementer with explicit handoff to S3-02. Together that resolves
the cross-phase concurrency hazard without redesigning the env-var
mechanism.

Everything else (nested-stack robustness, metamorphic determinism,
pure-impure split, `Final` env-var name constant, fixture concreteness)
is in-place hardening of ACs + TDD plan.

## Context brief

- **Goal:** `tag_invocation(task_class, case_id, run_started_iso)` is a
  context manager that sets `CODEGENIE_BENCH_INVOCATION_TAG` on enter
  and restores prior value on exit; Phase 5's `CostEmitter` reads the
  env var to mark `SandboxCostEntry.bench_invocation=True`.
- **ADR-0007** is the source of truth (env-var contract; additive
  `bench_invocation: bool = False`; medium reversibility; tag-prefix
  invariant). The story tracks ADR-0007 faithfully.
- **Phase 5's `SandboxCostEntry` / `CostEmitter`** are documented in
  Phase 5 ADR-0010 + ADR-0014 but **have not yet shipped**
  (`src/codegenie/sandbox/cost.py` does not exist; Phase 5 S7-03 is
  `Ready (HARDENED 2026-05-25)`, not GREEN). The story's "graceful
  degradation" clause + the cross-phase amendment train ride along
  with this fact, mirroring the canary-seed pattern.
- **Concurrency:** `phase-arch-design.md` lines 259, 594, 826 are
  explicit: the runner uses
  `asyncio.Semaphore(N=min(os.cpu_count(), 4))` and the per-task code
  path is literally `tag_invocation(...)` → `await SUT.ainvoke(case)` →
  exit. Two concurrent tasks would race on the process-global env var.
  The story does not surface this.

## Critics' raw findings

### Coverage critic — 8 findings (1 block, 5 harden, 2 nit)

- **F-COV-1 (block):** No AC for the concurrency contract. The env var
  is process-global; two concurrent `tag_invocation(...)` calls (which
  `asyncio.Semaphore(N=4)` in `runner.py` explicitly invites) corrupt
  each other's tags. The story has zero text on this. → ADDED AC + docstring contract.
- **F-COV-2 (harden):** No AC for nested `tag_invocation` calls (call
  B *inside* call A's `with` block). Save/restore via the snapshot
  pattern handles this correctly only if `prior` is captured per-call;
  a careless impl using a module-level `_prior` slot would silently
  fail. → ADDED nested-stack AC + TDD test.
- **F-COV-3 (harden):** No AC for metamorphic determinism — same
  inputs produce the same tag; different inputs produce different
  tags. Today a constant impl (`os.environ[var] = "bench:fixed"`) would
  satisfy the current AC-2 verbatim and the `startswith("bench:")`
  shape AC. → ADDED metamorphic AC + TDD pair.
- **F-COV-4 (harden):** No AC for empty-string prior value. The
  save-restore semantics need to distinguish `prior is None` from
  `prior == ""`; both are truthy-false but only one means "unset."
  → ADDED edge-case AC + parametrized fixture.
- **F-COV-5 (harden):** No AC that the `_ENV_VAR` constant is
  module-exported. The refactor section mentions it as a stretch goal,
  but Phase 5's amendment to `CostEmitter` will *import* the name —
  exporting it as `Final[str]` is the load-bearing path that avoids
  string duplication across two modules. → PROMOTED from refactor to AC.
- **F-COV-6 (harden):** No AC enforces the functional-core / imperative-
  shell split. Tag construction is pure (`(tc, case, iso) -> str`);
  env-var set/clear is impure. Coupling them in one helper denies
  the pure half a unit test and forces every test to monkey with the
  environment. → ADDED AC: pure `_build_tag` helper extracted.
- **F-COV-7 (nit):** No AC for explicit input validation (empty
  strings, non-`str` types). Surfaces only if callers pass bad data;
  `s2-01-bench-import-path-resolution.md` already validates task-class
  names at the loader boundary, so this is acceptably defended at the
  caller. → DEFERRED to caller; noted in implementer notes.
- **F-COV-8 (nit):** No AC for structlog `cost_tag.env_set` /
  `cost_tag.env_cleared` events (refactor section). Observability is a
  nice-to-have, not load-bearing. → KEPT in refactor section.

### Test-Quality critic — 9 findings (2 block, 5 harden, 2 nit)

- **F-TQ-1 (block):** `test_tag_format_begins_with_bench_colon` is
  trivially-passable. `def f(): os.environ[var] = "bench:"` survives.
  The test must assert the tag also *contains* all three input values
  in a structurally meaningful way (not just `in`, since substring
  containment also survives `"bench:abc"`). → REWRITTEN: assert the
  tag equals the canonical format AND that mutating any one input
  produces a different tag.
- **F-TQ-2 (block):** No concurrency test. `asyncio.gather(
  task_a_with_tag_invocation, task_b_with_tag_invocation)` is the
  exact load pattern S3-02 will create. The story's claim of
  "deterministic teardown" (ADR-0007 §Tradeoffs row 3) is false under
  concurrent entry. The test must either (a) prove serialization via
  an `asyncio.Lock` inside the shim, OR (b) prove the documented
  non-concurrent contract by raising on re-entry from a different
  task. → ADDED a `pytest.raises(...)` test asserting the chosen
  enforcement mode; default is "documented contract only" with the
  runner side (S3-02) owning serialization.
- **F-TQ-3 (harden):** Cross-phase contract test uses `stub_cost_emitter.emit(...)`
  with `...` placeholder args — no fixture defined. The previous
  S2-05 validation (F-COV-8 / F-TQ-9) flagged the identical pattern
  for `case_with_pin`. → ADDED concrete fixture sketch in TDD plan.
- **F-TQ-4 (harden):** No property-based test for the tag round-trip.
  Hypothesis over `(task_class, case_id, run_started_iso)` strings
  drawn from `regex("^[a-z][a-z0-9-]*[a-z0-9]$")` (task-class) +
  `regex("^[a-z0-9-]+$")` (case-id) + `from_regex(ISO-8601)` would
  catch a delimiter-collision bug if one input ever contains `:`.
  → ADDED a Hypothesis test.
- **F-TQ-5 (harden):** `test_tag_invocation_save_restores_prior_value`
  monkeypatches `"prior-value"` — bypasses the empty-string-prior
  ambiguity. Parametrize over `["prior-value", "", "bench:older"]`.
  → ADDED parametrize.
- **F-TQ-6 (harden):** No nested-context-manager test. A wrong impl
  using `os.environ.pop(_ENV_VAR, None)` instead of the save/restore
  chain survives single-level. → ADDED nested test (mirror S2-05's
  F-TQ-5 lesson; the rescue path's failure mode applies here too).
- **F-TQ-7 (harden):** No test that the pure `_build_tag` helper is
  independently importable. → ADDED a direct-import test in the
  red phase.
- **F-TQ-8 (nit):** Adversarial test's `simulate by filtering the
  list` is structurally identical to the cross-phase contract test
  and adds little. Keep it but rename to clarify it tests the
  *filter-discipline contract* (Phase 13 will compose), not the shim
  itself. → KEPT with renamed assertion.
- **F-TQ-9 (nit):** `assert v == "bench:2026-05-12T00:00:00+00:00:vuln-remediation:001-x"`
  is correct but couples the test to the exact format. Replace with
  the rebuilt format via the pure helper to keep one source-of-truth.
  → REWRITTEN.

### Consistency critic — 7 findings (1 block, 4 harden, 2 nit)

- **F-CON-1 (block):** Phase 5 `src/codegenie/sandbox/cost.py` does
  not exist on disk. Phase 5 S7-03 is HARDENED, not GREEN. The story
  promises to "amend" a file that hasn't been written. This is the
  same structural hazard the S2-05 validation flagged (`Canary.mint`),
  but with one critical difference: the *design* surface exists
  (Phase 5 ADR-0010 + ADR-0014 + S7-03 hardened story), and the
  amendment shape is fully specified. The fix is sequencing: this
  story now declares an explicit blocker on Phase 5 S7-03 being GREEN
  before the cross-phase Pydantic edit lands. The shim itself
  (`src/codegenie/eval/cost_tag.py`) can ship first; the amendment
  rides behind. → ADDED explicit "Depends on" gating + sequencing note.
- **F-CON-2 (harden):** `phase-arch-design.md §Edge cases #15`
  reference resolves to line 958, which says "Phase 13 owns the
  consumer filter (`WHERE bench_invocation IS NOT TRUE`)." Story's
  AC matches. OK.
- **F-CON-3 (harden):** ADR-0007 §Tradeoffs row 4 says "the
  redundancy is by design" — the `bench:` prefix AND the
  `bench_invocation=True` flag carry the same meaning. Story's AC
  surfaces this. OK.
- **F-CON-4 (harden):** ADR-0007 §Tradeoffs row 3 says "forgetting
  `__exit__` (or an unhandled exception inside the with-block) would
  leak the tag." The story tests exception cleanup but does not test
  the leak case (an interpreter death inside the with block — out of
  scope for unit tests; documented as residual risk). → NOTED in
  implementer notes.
- **F-CON-5 (harden):** `phase-arch-design.md` line 826 explicitly
  documents the call pattern (`tag_invocation(...) → await
  SUT.ainvoke(case)`). The "Notes for implementer" doesn't
  cross-reference S3-02's runner ownership of serialization. → ADDED
  cross-reference + runner-side guidance.
- **F-CON-6 (nit):** `TaskClassName` / `CaseId` newtypes are deferred
  phase-wide (S1-03's identifier-consolidation pattern; S2-01 line
  369; S2-02 line 506). Story uses raw `str`. Consistent with the
  rest of the phase. → NOTED, no action.
- **F-CON-7 (nit):** ADR-0007 §Reversibility = Medium. Story states
  this verbatim. OK.

### Design-Patterns critic — 6 findings (0 block, 5 harden, 1 nit)

- **F-DP-1 (harden):** **Functional core / imperative shell.** Tag
  construction is pure; env-var set/clear is impure. A pure
  `_build_tag(task_class, case_id, run_started_iso) -> str` helper
  is the natural split. → ADDED to implementation outline + AC.
- **F-DP-2 (harden):** **Capability constant.** The env-var name
  must be exported as `Final[str]` so Phase 5's `CostEmitter` can
  `from codegenie.eval.cost_tag import BENCH_INVOCATION_ENV_VAR`
  instead of duplicating the string literal. → PROMOTED from
  refactor to AC; also surfaces the dependency-inversion seam
  (the producer of the env-var name is `codegenie.eval`; the
  consumer is `codegenie.sandbox` — one-way data flow).
- **F-DP-3 (harden):** **Re-entrancy / hidden singleton.** The env
  var is a process-global hidden singleton — exactly the
  action-at-a-distance hazard the S2-05 validation called out. Two
  paths exist: (a) document the non-concurrent contract and gate
  serialization at the runner (S3-02); (b) wrap the set/clear pair
  in an `asyncio.Lock`. Option (a) is leaner (Rule 2 — Phase 6.5's
  runner concurrency=4 is the only known caller; a lock here imposes
  cost on hypothetical future callers). Option (b) is more defensive
  but introduces a singleton. → CHOSE (a); explicit AC + docstring +
  cross-reference to S3-02 + ADR-0007 §Tradeoffs row 3.
- **F-DP-4 (harden):** **Rule-of-three for "scoped env-var primitive."**
  ADR-0007 §Consequences row 8 explicitly anticipates future tags
  (`CODEGENIE_DEV_INVOCATION_TAG`, etc.) following the same shape.
  Today there is only one consumer (this shim). Per CLAUDE.md +
  Rule 2 ("three similar lines is better than premature abstraction"),
  do NOT extract a `scoped_env_var(name, value)` primitive now. → NOTED
  as trigger-deferred in implementer notes; the third consumer is
  the extraction trigger.
- **F-DP-5 (harden):** **Primitive obsession on str identifiers.**
  `TaskClassName` / `CaseId` newtypes are *phase-wide deferred*
  (S1-03 / S2-01 / S2-02 precedent). Story conforms. No action.
- **F-DP-6 (nit):** **Smart constructor for the tag string.** A
  `BenchInvocationTag` newtype that wraps `str` and enforces the
  `bench:` prefix at construction would close primitive-obsession
  on the tag. Surface area = one variable; payoff = low; defer.
  → NOTED in implementer notes as deferred extract.

## Conflict resolution

No critic conflicts. All four converged. Coverage's "test
concurrency" finding maps to Test-Quality's F-TQ-2 maps to
Design-Patterns' F-DP-3 maps to Consistency's F-CON-5 — same
problem, four lenses. The resolution (documented non-concurrent
contract + runner-side serialization at S3-02) satisfies all four.

## Researcher (Stage 3)

**Not invoked.** No `NEEDS RESEARCH` findings — every critic finding
maps to a known-pattern (functional core / imperative shell, capability
constant, save-restore chain, metamorphic determinism). The
concurrency hazard maps to the canonical "process-global mutable state
under cooperative concurrency" pattern; the resolution is documented
in CPython's `os.environ` semantics (not thread/task local).

## Edits applied

| Section | Before | After |
|---|---|---|
| Header | `Depends on: S1-02` | `Depends on: S1-02` + sequencing block stating Phase 5 S7-03 GREEN is the precondition for the amendment landing (the shim ships independently) |
| Acceptance criteria | 10 items | 16 items — added concurrency contract, nested-call save/restore, empty-string prior, metamorphic determinism, `_ENV_VAR`/`BENCH_INVOCATION_ENV_VAR` `Final[str]` export, pure `_build_tag` helper, strengthened tag-shape assertion, explicit non-Phase-5-sequencing guard |
| Implementation outline | 5 steps | 6 steps — extracted pure `_build_tag(...)`, plus explicit "Step 4 = Phase 5 amendment lands only after S7-03 GREEN" gating |
| TDD plan | 7 tests | 11 tests — strengthened tag-shape, added nested-call, added metamorphic pair, added Hypothesis property, added concurrent-entry contract assertion, added pure-helper direct-import, parametrized prior-value over `["", "prior-value", "bench:older"]` |
| Notes for implementer | 4 bullets | 8 bullets — added S3-02 serialization ownership cross-reference, documented residual `os._exit` leak risk, recorded the rule-of-three trigger for a generic scoped-env-var primitive, surfaced the deferred `BenchInvocationTag` newtype + `TaskClassName` / `CaseId` consolidation precedents |

## Verdict rationale

The story prescribes a small, focused shim with a clean contract.
The four critics surfaced real defects but no contradictions with the
goal or ADR-0007. Every finding has a concrete fix; the editor
applied them in-place. **HARDENED.**
