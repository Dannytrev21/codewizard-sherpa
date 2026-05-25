# Validation report: S5-01 — `ReplanHook` Protocol + integration contract test

**Validated:** 2026-05-25
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S5-01 is the load-bearing typed seam between Phase 5's `GateRunner` retry loop
and Phase 4's `FallbackTier.run` — Gap 2 in `phase-arch-design.md`. The goal
(plant the typed `ReplanHook` seam + a contract test) is intact and correctly
framed; the draft correctly identifies that without this seam Phase 4 can
rename a kwarg and Phase 5 silently breaks.

But the draft was written **before** S1-04 was hardened (2026-05-22) and
**before** Phase 4 S6-01/S6-02/S7-01 reached HARDENED (2026-05-24). As a
consequence every block-tier finding traces to that gap: the draft asserts a
synchronous Protocol with a return type that no longer exists, mocks symbols
that were never written, and asserts end-to-end fence-wrapped-prompt behavior
that S5-03 / S5-05 own.

| Draft assumption | Reality on `master` (or HARDENED upstream story) |
|---|---|
| `ReplanHook` Protocol is *defined* by this story | S1-04 HARDENED (2026-05-22) already adds `ReplanHook` to `gates/contract.py`'s `__all__` (AC-1). This story extends the seam (concrete adapter + integration test); the Protocol declaration is **already shipped**. |
| `ReplanHook.__call__` returns `RecipeApplication` | S1-04 HARDENED §7 locked the return type to `RecipeOutcome` (the `Applied \| Skipped \| RecipeNotApplicable \| RecipeFailed` discriminated union at [`codegenie.transforms.outcomes`](../../../../src/codegenie/transforms/outcomes.py:300)). `RecipeApplication` does not exist anywhere in `src/codegenie/`. |
| `recipe_app.diff` is `bytes` and non-empty | `Applied` carries `transform_id: TransformId, plugin_id, recipe_id` — no `.diff` field. Attribute access would raise on first dereference. |
| Mock target is `codegenie.llm.fence.canary_matcher.match` | `codegenie.llm.fence` does not exist. Phase 4 ships the fence module tree at `codegenie.fallback.fence` ([`wrapper.py`](../../../../src/codegenie/fallback/fence/wrapper.py), [`canary.py`](../../../../src/codegenie/fallback/fence/canary.py), [`prompt_builder.py`](../../../../src/codegenie/fallback/fence/prompt_builder.py)). There is no `canary_matcher` module; the canary surface is `CanaryGuard.scan` + `scan_pure`. The `patch` call would `ModuleNotFoundError` before the test ever ran. |
| `FallbackTier.run` is synchronous; the closure can call it inline | Phase 4 S6-01 HARDENED locked `async def run(advisory, repo_ctx, recipe_selection, *, prior_attempts: Sequence[AttemptSummary] = ()) -> RecipeApplication`. A synchronous `ReplanHook.__call__` cannot await it without leaking an unawaited-coroutine `RuntimeWarning` at runtime and a `# type: ignore` everywhere. |
| `prior_attempts: list[AttemptSummary] = []` | Phase 4 S6-01 HARDENED pins `prior_attempts: Sequence[AttemptSummary] = ()` (read-covariant; immutable empty tuple — no mutable-default footgun). |
| Phase 4's prompt contains `<BEGIN_PRIOR_ATTEMPT_...>` blocks at S5-01 land time | The fence-wrap composition (`FenceWrapper.compose_prior_attempts`) **ships in S5-03**, which depends on S5-02 which depends on S5-01. At S5-01 land time Phase 4's prompt builder does not consume `prior_attempts`. Asserting the wrapped block is present is a *future-bug-as-AC*. |
| VCR cassette under `tests/integration/contracts/cassettes/` over a live Phase 4 call | Phase 4 ships an audited cassette pipeline at `tests/cassettes/anthropic/` with a BLAKE3 `cassettes.lock` manifest, CODEOWNERS gate, four-layer sanitizer, and the `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1` ergonomic (per [CLAUDE.md](../../../../CLAUDE.md) "Cassette workflow"). A new orphan cassette tree bypasses every existing defense. |
| `GateContext.advisory: Advisory` | S1-04 HARDENED Note "Open ambiguity (resolved)": `advisory`/`recipe`/`transform_output` are typed as `str` placeholders today — Phase 3 has not shipped typed `Advisory`/`Recipe`/`TransformOutput` Pydantic models. The factory must accept this and surface it as a Notes ambiguity (not silently invent typed kwargs). |
| `fallback_tier_stub.last_prompt_text()` | Invented helper — no precedent in `tests/cassettes/anthropic/` or `tests/conftest.py`. The Phase-4-canonical pattern is `tests/fixtures/fallback_tier_callable.py` (called out as "the contract Phase 6 reads" in Phase 4 §"No `langgraph` in Phase 4"). |

The validator's response: **narrow the story's scope to its non-deferred
core, replace every invented symbol with the shipped reality, and defer the
fence-wrapped-prompt assertion to S5-05** (which already depends on both S5-03
and S5-04 and is the right home for the cross-phase round-trip test).

The remaining slice — what S5-01 actually owns:

1. The *concrete* `make_orchestrator_replan_hook` factory under
   `src/codegenie/orchestrator/replan_hook.py` that builds a closure
   conforming to the `ReplanHook` Protocol shipped by S1-04.
2. A unit-level contract test that verifies the closure is async,
   conforms to the Protocol at runtime, and faithfully threads
   `prior_attempts` into a spy/mock `FallbackTier.run` call with the
   correct kwarg name (`prior_attempts=`) and the correct identity
   (the *same* sequence object the closure was given via `ctx`).
3. A static AST fence: `src/codegenie/orchestrator/replan_hook.py` may
   not import anything under `src/codegenie/sandbox/`.
4. A mypy `must-fail` harness verifying `_OrchestratorReplanHook`
   *does* conform structurally (the failing twin under `tests/typing/`
   demonstrates the type checker rejects a non-conforming callable).

That's enough for Gap 2's contract-snapshot purpose — Phase 4 cannot
silently rename `prior_attempts` to `attempts` or drop the kwarg without
the spy assertion failing loudly.

No `RESCUE`-tier escalation: the goal text needed only minor edits (drop
`RecipeApplication.diff`-shaped wording); the acceptance criteria, the
implementation outline, and the TDD plan were rewritten in place to bind
to the actual upstream surfaces. Every gap was patchable from the four
honored ADRs plus S1-04, S6-01, S6-02, S7-01 HARDENED reports and the
existing kernels (`fallback/fence/`, `transforms/outcomes.py`,
`types/identifiers.py`). Stage 3 (research) was skipped — every gap was
answerable from in-repo precedents and the prior validation reports.

## Findings by critic

### Coverage critic

#### Block-tier (would silently pass / would crash on first real input)

1. **(coverage — block) `ReplanHook` is already shipped by S1-04.** The
   draft AC-1 attempts to add the Protocol again. Two outcomes — both bad:
   (a) the executor edits `gates/contract.py` to "add" `ReplanHook`,
   producing a duplicate definition that triggers Python's NameError or
   silently shadows S1-04's; (b) the executor sees S1-04 already shipped
   it and writes a no-op story. **Fix:** rewrite AC-1 as an *import-shape*
   assertion (`from codegenie.gates.contract import ReplanHook` succeeds;
   `ReplanHook` is `runtime_checkable`; the `__call__` annotation matches
   S1-04's exact frozen signature). The Protocol's *declaration* is now
   S1-04's surface; S5-01 owns only the *consumer* and the *contract test*.

2. **(coverage — block) Return type is `RecipeOutcome`, not
   `RecipeApplication`.** Three test assertions (`isinstance(recipe_app.diff, bytes)`,
   `len(recipe_app.diff) > 0`, both calls) would `AttributeError` on
   first dereference. **Fix:** new AC-RO-1 pinning that the closure returns
   `RecipeOutcome`; the contract assertion is on the variant tag
   (`outcome.kind == "applied"`), not on a non-existent `.diff` field;
   `Applied.transform_id`, `Applied.plugin_id`, `Applied.recipe_id` are the
   three observable fields ([`outcomes.py:249-258`](../../../../src/codegenie/transforms/outcomes.py:249)).

3. **(coverage — block) Mock target `codegenie.llm.fence.canary_matcher.match`
   is invented.** Three flavors of failure: (a) `ModuleNotFoundError` at
   `patch(...)` resolve; (b) even with the correct path
   (`codegenie.fallback.fence.canary.scan_pure`) the test couples S5-01 to
   Phase 4's *internal* canary scanning, not to the seam this story is
   meant to protect; (c) the canary is invoked by `compose_prior_attempts`
   which S5-03 ships — at S5-01 land time it is not invoked by Phase 4's
   prompt builder at all. **Fix:** drop the canary-mock AC entirely from
   S5-01 (deferred to S5-05 with the cross-phase round-trip test); replace
   with a spy on `FallbackTier.run` asserting `prior_attempts=` is the
   kwarg name and the value is identity-equal to `ctx.prior_attempts`.

4. **(coverage — block) `async def` not awaited.** Phase 4 S6-01 HARDENED
   pins `async def FallbackTier.run(...)`. The story's Protocol declares
   sync `def __call__`. The closure body `lambda ctx: fallback_tier.run(...)`
   returns a coroutine, never awaits it, and the test's `recipe_app = hook(ctx)`
   binds a coroutine object whose attribute access produces:
   `AttributeError: 'coroutine' object has no attribute 'kind'`. **Fix:**
   new AC-ASYNC-1 pinning the Protocol's `async def __call__`; AC-ASYNC-2
   pinning the factory closure as `async def _call(ctx)`; AC-ASYNC-3
   pinning the test as `pytest.mark.asyncio` + `await hook(ctx)` (the
   project's `asyncio_mode = "auto"` config makes the marker redundant —
   surface this).

5. **(coverage — block) `prior_attempts` typed as `list[AttemptSummary]`
   contradicts Phase 4's `Sequence[AttemptSummary]`.** Mypy `--strict` on
   the closure passing `list[...]` into `Sequence[...]` is fine
   (`list` IS a `Sequence`), but the *Protocol signature* must match Phase 4's
   exactly so the contract snapshot remains stable. **Fix:** AC-SIG-1 pins
   the Protocol's `prior_attempts` argument as `Sequence[AttemptSummary]`
   (read-covariant); AC-SIG-2 pins the default as `()` (immutable empty tuple);
   negative test: a Protocol declaration of `list[AttemptSummary] = []` is
   *added* and `mypy --strict` is asserted to reject calling Phase 4's
   `run` with that type (mutation-test the regression).

6. **(coverage — block) Cassette infrastructure conflict.** The draft
   spawns a new `tests/integration/contracts/cassettes/` tree. Phase 4
   ships `tests/cassettes/anthropic/` with a BLAKE3 `cassettes.lock`
   manifest, CODEOWNERS gate, four-layer sanitizer (CLAUDE.md "Cassette
   workflow"), and `make refresh-cassettes`. The orphan tree bypasses
   every existing defense and would land an `unowned cassette` finding at
   the next `make refresh-cassettes` invocation. **Fix:** drop the
   live-Phase-4 VCR cassette from S5-01 entirely. Replace with a
   `FallbackTier` spy/stub that records `(args, kwargs)` and lets the
   closure return a deterministic `Applied(...)` instance. The cross-phase
   round-trip (which legitimately needs a cassette) belongs in S5-05 and
   must reuse the Phase 4 cassette infrastructure when it lands.

7. **(coverage — block) Asserts behavior S5-03 ships.** The fence-wrapped
   `<BEGIN_PRIOR_ATTEMPT_{canary}>...<END_PRIOR_ATTEMPT_{canary}>` block
   in the captured prompt is produced by `FenceWrapper.compose_prior_attempts`
   (S5-03 AC-3). At S5-01 land time that helper does not exist and Phase 4's
   prompt builder does not consume `prior_attempts`. Asserting the
   wrapped block exists is asserting *future* behavior. **Fix:** delete
   sub-assertion (b) and (c) of the draft test; route the wrapped-prompt
   contract to S5-05 (which depends on S5-03 and S5-04).

#### Harden-tier (right answer with edits)

8. **(coverage — harden) `_OrchestratorReplanHook` class vs factory
   closure.** Draft hedges ("`_OrchestratorReplanHook` (or equivalent
   closure factory)"). Pick one. The factory pattern is what
   `make_orchestrator_replan_hook` already names; the closure body becomes
   a named inner `async def _call(ctx)` so tracebacks are readable. **Fix:**
   AC-FAC-1 pins `make_orchestrator_replan_hook(*, fallback_tier, repo_ctx, recipe_selection) -> ReplanHook`;
   AC-FAC-2 pins the inner function as named (not lambda) for traceback
   ergonomics; AC-FAC-3 pins `advisory` is *captured from `ctx` at call
   time*, not from the factory args (the closure's whole point).

9. **(coverage — harden) Placeholder-typed `ctx.advisory`.** S1-04
   HARDENED Note pins `GateContext.advisory: str` as a placeholder until
   Phase 3 ships an `Advisory` typed model. The factory must forward
   `ctx.advisory` unchanged (whatever its runtime type) into
   `FallbackTier.run`. **Fix:** AC-FWD-1 — the factory does no type
   coercion on `ctx.advisory`/`ctx.recipe`/`ctx.transform_output`; the
   `kwargs` dict passed to `fallback_tier.run` carries them byte-identical
   (spy assertion). Notes-for-implementer cite S1-04's open ambiguity.

10. **(coverage — harden) `runtime_checkable` Protocol false-positive
    risk.** A `runtime_checkable` Protocol with a single method only
    checks for the *presence* of `__call__`, not its signature. Any
    callable passes `isinstance(x, ReplanHook)`. **Fix:** AC-RT-1 pins
    the runtime check as *necessary-but-not-sufficient* (passes for any
    callable); AC-MYPY-1 pins the mypy `must-fail` harness as the
    sufficient check; tests cite this asymmetry in a comment so future
    readers don't tighten the runtime check (which would silently
    over-reject duck-typed test stubs).

### Test Quality critic

#### Block-tier

11. **(tq — block) Test is not mutation-resistant.** The draft test
    passes if the closure returns *any* truthy `RecipeOutcome` and the
    canary mock is called *anywhere* — even if `prior_attempts` is
    silently dropped on the floor before reaching Phase 4. Mutation:
    swap `prior_attempts=ctx.prior_attempts` for `prior_attempts=[]` —
    the test passes. **Fix:** replace canary assertion with a
    `unittest.mock.Mock(spec=FallbackTier)` spy; the spy's
    `call_args.kwargs["prior_attempts"]` is asserted **identity-equal**
    (`is`) to `ctx.prior_attempts`, not just `==`. An identity check
    catches the `list(ctx.prior_attempts)` copy mutation; a list-equality
    check would miss it.

12. **(tq — block) `fallback_tier_stub.last_prompt_text()` is invented.**
    Drop the helper. Replace with `AsyncMock(spec=FallbackTier)` and
    assert on `await_args.kwargs`.

13. **(tq — block) mypy smoke test doesn't actually run mypy.** The draft
    drops a `# type: ignore[arg-type]` annotation and expects "the type
    checker rejects it" — but a `# type: ignore` *silences* the rejection,
    so there is no observable failure. **Fix:** the test invokes
    `mypy --strict tests/typing/test_replan_hook_typing.py` as a
    subprocess, captures stdout/stderr, and asserts (a) exit code is
    nonzero, (b) stderr contains `Argument 1 to "expect_replan_hook"`
    error. This is the "must-fail" pattern Phase 7.5 S1-06 introduced.

#### Harden-tier

14. **(tq — harden) Add a property-based test for `ctx.prior_attempts`
    threading.** Hypothesis strategy: `lists(builds(AttemptSummary, ...),
    min_size=0, max_size=8)`. For each generated list, the spy must see
    the same list (identity-equal) as `kwargs["prior_attempts"]`. Mutation:
    `prior_attempts=list(ctx.prior_attempts)` passes the equality check
    but fails the identity check; `prior_attempts=ctx.prior_attempts[1:]`
    silently drops the first attempt under non-empty input — caught by
    Hypothesis's shrinker.

15. **(tq — harden) Add a contract-snapshot test that pins Phase 4's
    `FallbackTier.run` signature** by introspection (`inspect.signature`),
    asserting the parameter names `("advisory", "repo_ctx",
    "recipe_selection", "prior_attempts")` are present and `prior_attempts`
    is keyword-only with default `()`. If Phase 4 renames the kwarg, this
    test fails loudly *here*, at the seam, not in some downstream pipeline.
    This is Gap 2's whole point.

### Consistency critic

#### Block-tier

16. **(consistency — block) Story redefines a Protocol S1-04 ships.**
    Already covered in #1. Add a Notes-for-implementer note pointing to
    S1-04 HARDENED §7 with the exact line.

17. **(consistency — block) Goal text overspecifies non-existent types.**
    "returns a usable `RecipeApplication` with the fence-wrapped summary
    visible in the Phase 4 prompt." Two errors: (a) `RecipeApplication`
    doesn't exist; (b) the fence-wrapped-summary assertion belongs in
    S5-05. **Fix:** rewrite the goal: "Wire the concrete
    `make_orchestrator_replan_hook` factory that conforms to the
    `ReplanHook` Protocol shipped by S1-04, and a contract test
    asserting the closure (a) is async, (b) threads `prior_attempts`
    into `FallbackTier.run` identity-faithfully, (c) does not import
    `sandbox/`, (d) is rejected by `mypy --strict` when its body is
    type-incorrect."

18. **(consistency — block) "Closure over `FallbackTier.run`" implies
    composition root ownership.** Per Phase 4 S7-01 HARDENED "composition
    root, not the adapter, owns substrate assembly" — the 10-substrate
    `FallbackTier(...)` build lives in the plugin's `transforms()`
    factory. The `make_orchestrator_replan_hook` factory accepts a
    *pre-built* `FallbackTier` (Dependency Inversion — Port, not the
    substrate). **Fix:** AC-DI-1 — the factory's signature accepts
    `fallback_tier: FallbackTier`, not the 10-substrate dep set; AC-DI-2 —
    the factory module must not import anything under `src/codegenie/rag/`,
    `src/codegenie/fallback/leaf/`, or `src/codegenie/fallback/cassette/`
    (only the public `FallbackTier` class via `codegenie.fallback`).

#### Harden-tier

19. **(consistency — harden) No `sandbox/` imports** — already in
    Notes. Promote to AC-NOSAND-1 with an AST scan: `ast.parse(...)`
    of `src/codegenie/orchestrator/replan_hook.py`; iterate all `Import`
    and `ImportFrom` nodes; assert no `module` starts with
    `codegenie.sandbox`. Mirror S5-04's AST-scan pattern.

20. **(consistency — harden) `orchestrator/` package may not yet exist.**
    The story creates `src/codegenie/orchestrator/replan_hook.py` and
    re-exports via `src/codegenie/orchestrator/__init__.py`. New
    package = new fence row in `tests/fence/` (per CLAUDE.md "Structural
    defenses live under `tests/fence/`"). **Fix:** AC-PKG-1 — landing
    `src/codegenie/orchestrator/` requires a corresponding cold-start
    fence row; if S5-01 is the first story to land it, this story
    creates that row; if not, this story confirms the row exists.

### Design Patterns critic

21. **(dp — surface as Note) Closure factory is the right pattern.**
    The factory pattern + `async def` inner function + `partial`-like
    capture of `repo_ctx`/`recipe_selection` is idiomatic Python (and
    aligns with Phase 4 S7-01's composition-root discipline). No
    structural change needed.

22. **(dp — surface as Note) Open/Closed at the cross-phase seam.**
    `ReplanHook` is the Phase 4/Phase 5 Port (hexagonal pattern). Adding
    a new replan strategy (e.g., a chain-of-fallbacks hook for Phase 6's
    LangGraph) is a new adapter, not an edit to `gates/contract.py`. The
    HARDENED S1-04 already has this right; no story-level edit needed.

23. **(dp — surface as Note) Spy vs cassette for cross-phase contracts.**
    The validator chose spy (`AsyncMock(spec=FallbackTier)`) over
    cassette for S5-01 because the contract under test is *the signature
    of the cross-phase call*, not the LLM output. Cassettes test
    end-to-end behavior; spies test cross-phase contracts. S5-05 owns
    the end-to-end test; this story owns the contract.

24. **(dp — surface as Note) Sum-type discrimination in tests.** Tests
    that branch on `RecipeOutcome` variants should use
    `match outcome: case Applied(): ...; case Failed(): ...` (tagged-union
    discipline per CLAUDE.md "tagged union > anaemic dict"), not
    `if outcome.kind == "applied"`. Surface in Notes; the test as written
    only checks the `Applied` happy path so no immediate edit needed.

## Conflict resolution

- **Coverage wants a fence-wrapped-prompt AC; Consistency says S5-03/S5-05
  own it.** Consistency wins (source of truth is the dependency graph).
  AC deferred to S5-05; note added to Out-of-scope.
- **Test-Quality wants a Hypothesis property test; Coverage wants a
  parametrized list-of-known-sizes test.** Both kept. The Hypothesis
  test catches shrink-shaped mutations; the parametrized test pins the
  edge cases (`[]`, `[one]`, `[three]`) explicitly.
- **Design-Patterns wants `match` over `if`.** Rule 2 / Rule 11 — match
  the existing convention. The existing Phase 5 test files (`tests/gates/test_*.py`)
  use `assert outcome.kind == "applied"`. Surface in Notes only.

## Stage 3 — research

**Skipped.** Every gap was answerable from in-repo precedents:

- S1-04 HARDENED report (`ReplanHook` declaration + `RecipeOutcome` return type)
- Phase 4 S6-01 HARDENED (FallbackTier `async def run` + `Sequence[...] = ()`)
- Phase 4 S7-01 HARDENED (composition-root discipline)
- Phase 7.5 S1-06 (`mypy --strict` must-fail harness pattern)
- S5-04 (AST-scan-for-imports pattern, mirrored)
- CLAUDE.md "Cassette workflow" (existing cassette infrastructure)

No external canonical pattern was needed.

## Edits applied to `S5-01-replan-hook-protocol-contract-test.md`

### 1. Status line
- Before: `**Status:** Ready`
- After: `**Status:** Ready (Hardened 2026-05-25)`

### 2. Goal text rewrite
- Before: "Add the typed `ReplanHook` Protocol to `gates/contract.py` and
  a VCR-cassette integration contract test asserting the orchestrator's
  concrete hook implementation accepts a `GateContext` carrying
  `prior_attempts` and returns a usable `RecipeApplication` with the
  fence-wrapped summary visible in the Phase 4 prompt."
- After: "Land the concrete `make_orchestrator_replan_hook` factory under
  `src/codegenie/orchestrator/replan_hook.py` — a closure that conforms to
  the `ReplanHook` Protocol *already shipped by S1-04* — and a contract
  test asserting the closure (a) is async, (b) threads `prior_attempts`
  identity-faithfully into `FallbackTier.run`'s `prior_attempts=` kwarg,
  (c) returns the `RecipeOutcome` unchanged, (d) does not import
  anything under `src/codegenie/sandbox/`, (e) is rejected by
  `mypy --strict` when its body is type-incorrect. The fence-wrapped
  prior-attempt block in Phase 4's prompt is out of scope — that's
  S5-03's helper + S5-05's end-to-end round-trip."

### 3. Acceptance criteria — replaced the 7-AC draft with a 19-AC hardened set
Headers: A. Protocol import & shape | B. Concrete factory | C. Threading
contract | D. Async correctness | E. Static safety | F. AST fences | G.
TDD plan + tooling. Every AC is observable; every observable assertion has
a paired test in the rewritten TDD plan.

### 4. Implementation outline rewrite
- Drop step 1 (the Protocol is already in S1-04)
- Replace VCR/cassette steps with `AsyncMock(spec=FallbackTier)` setup
- Add the mypy-must-fail subprocess invocation pattern from Phase 7.5 S1-06

### 5. TDD plan rewrite
Five tests instead of two: (i) Protocol import + runtime conformance,
(ii) async threading with identity-equal spy assertion + sum-type
discrimination, (iii) Hypothesis property test over `prior_attempts`
shapes, (iv) signature-snapshot test pinning `FallbackTier.run`'s kwarg
names, (v) mypy must-fail subprocess test.

### 6. Files to touch
Drop the two cassette YAML rows. Add `tests/fence/test_orchestrator_replan_hook_imports.py`
for the AST scan.

### 7. Out-of-scope expanded
Explicitly list S5-03 (`compose_prior_attempts`), S5-05 (end-to-end
fence-wrapped prompt), and Phase 3 typed `Advisory`/`Recipe` widening.

### 8. Notes for the implementer
Cite S1-04 HARDENED §7 (Protocol home), Phase 4 S6-01 HARDENED (`async def`
signature), Phase 4 S7-01 HARDENED (composition root), CLAUDE.md
Cassette workflow (why no cassette in this story), and Phase 7.5 S1-06
(must-fail harness pattern).

## Verdict

**HARDENED.** Story is now ready for `phase-story-executor`.

The Gap 2 contract surface is preserved (Phase 4 cannot silently rename
`prior_attempts` to `attempts` without S5-01's signature-snapshot test
failing loudly). The story no longer contradicts S1-04 or Phase 4
HARDENED stories. The fence-wrapped-prompt assertion is correctly
deferred to S5-05. The mypy must-fail harness gives the type checker
real teeth on the cross-phase contract.

Executor preconditions:
- S1-04 GREEN (ships `ReplanHook` Protocol + `AttemptSummary` + `GateContext`)
- Phase 4 S6-01 GREEN (ships `FallbackTier.run`)
- `src/codegenie/orchestrator/` package may need to be created; if so,
  add the fence row per AC-PKG-1.
