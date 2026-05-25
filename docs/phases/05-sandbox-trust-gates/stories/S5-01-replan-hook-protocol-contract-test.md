# Story S5-01 — `ReplanHook` consumer factory + cross-phase contract test

**Step:** Step 5 — GateRunner three-retry loop + Phase 4 replan_hook integration
**Status:** Ready (Hardened 2026-05-25)
**Effort:** S
**Depends on:** S4-05, S1-04 (HARDENED — ships the `ReplanHook` Protocol), Phase 4 S6-01 (HARDENED — ships `FallbackTier.run`)
**ADRs honored:** ADR-0002, ADR-0006

## Validation notes (2026-05-25)

Hardened via `phase-story-validator` (verdict: HARDENED). The draft was
written before S1-04 (2026-05-22) and Phase 4 S6-01/S6-02/S7-01 (2026-05-24)
HARDENED — every block-tier finding traces to that lag. Source-of-truth
contradictions resolved against [`../phase-arch-design.md §Gap analysis Gap 2`](../phase-arch-design.md),
[S1-04 HARDENED](_validation/S1-04-gates-contract-abc-models.md), [Phase 4
S6-01 HARDENED](../../04-vuln-llm-fallback-rag/stories/S6-01-fallback-tier-pipeline.md),
[Phase 4 S7-01 HARDENED](../../04-vuln-llm-fallback-rag/stories/S7-01-fallback-tier-plan-recipe-engine.md),
[ADR-0002](../ADRs/0002-additive-prior-attempts-kwarg.md), [ADR-0006](../ADRs/0006-protocol-vs-abc-convention.md),
and codebase precedents ([`src/codegenie/transforms/outcomes.py:300`](../../../../src/codegenie/transforms/outcomes.py:300),
[`src/codegenie/fallback/fence/`](../../../../src/codegenie/fallback/fence/),
[`src/codegenie/types/identifiers.py`](../../../../src/codegenie/types/identifiers.py),
CLAUDE.md "Cassette workflow"). Full report:
[`_validation/S5-01-replan-hook-protocol-contract-test.md`](_validation/S5-01-replan-hook-protocol-contract-test.md).

Headline edits (every weakness the critics flagged would have crashed the
executor at first import or let a kwarg-renaming Phase 4 silently bypass
the contract):

1. **`ReplanHook` Protocol is IMPORTED from `gates/contract.py`, not
   redefined here.** S1-04 HARDENED (2026-05-22) AC-1 already adds
   `ReplanHook` to `gates/contract.py`'s `__all__`. The draft's AC-1
   ("`gates/contract.py` exports a `runtime_checkable` `Protocol` named
   `ReplanHook` with one `__call__`") duplicated S1-04 and would either
   shadow it or land a no-op. Fix: AC-1 rewritten as an *import-shape*
   assertion (the Protocol must be reachable, `runtime_checkable`, and its
   `__call__` signature is byte-identical to S1-04's frozen line).

2. **Return type is `RecipeOutcome`, NOT `RecipeApplication`.** S1-04
   HARDENED §7 locked the return type to `RecipeOutcome`
   (the `Applied | Skipped | RecipeNotApplicable | RecipeFailed`
   discriminated union at [`codegenie.transforms.outcomes:300`](../../../../src/codegenie/transforms/outcomes.py:300)).
   `RecipeApplication` does not exist anywhere in `src/codegenie/` — three
   draft assertions (`isinstance(recipe_app.diff, bytes)`,
   `len(recipe_app.diff) > 0`, both invocations) would `AttributeError` on
   first dereference; `Applied` carries `transform_id`/`plugin_id`/`recipe_id`,
   not `.diff`. Fix: AC-RO-1..AC-RO-3 pin `RecipeOutcome` discrimination
   on the variant tag; assertions branch on `Applied` vs `RecipeFailed`.

3. **`codegenie.llm.fence` and `canary_matcher.match` do not exist.** The
   actual fence module tree is at [`codegenie.fallback.fence`](../../../../src/codegenie/fallback/fence/)
   (`wrapper.py`, `canary.py`, `prompt_builder.py`); the canary surface
   is `CanaryGuard.scan` + `scan_pure`, not `canary_matcher.match`. The
   draft's mock-patch target would `ModuleNotFoundError` before the test
   ever ran. Fix: the canary mock is **removed entirely from S5-01** — the
   canary is invoked by `FenceWrapper.compose_prior_attempts` which S5-03
   ships; asserting it here asserts *future* behavior. The fence-wrapped
   prompt round-trip belongs in S5-05.

4. **`FallbackTier.run` is `async`.** Phase 4 S6-01 HARDENED pins
   `async def run(advisory, repo_ctx, recipe_selection, *, prior_attempts: Sequence[AttemptSummary] = ()) -> RecipeApplication`.
   The draft's synchronous Protocol + `lambda ctx: fallback_tier.run(...)`
   returns an unawaited coroutine; `recipe_app = hook(ctx)` binds a
   coroutine object whose attribute access raises
   `AttributeError: 'coroutine' object has no attribute ...`. Fix:
   AC-ASYNC-1..AC-ASYNC-3 pin the Protocol as `async def __call__`, the
   factory closure as `async def _call`, and the test as
   `await hook(ctx)` (the project's `asyncio_mode = "auto"` config makes
   the marker redundant — surfaced in Notes).

5. **`prior_attempts: Sequence[AttemptSummary] = ()`**, not
   `list[AttemptSummary] = []`. Phase 4 S6-01 HARDENED is explicit:
   read-covariant `Sequence`, immutable empty tuple default (no
   mutable-default footgun). Fix: AC-SIG-1 + AC-SIG-2 pin both.

6. **VCR cassette over a live Phase 4 call is wrong.** Phase 4 ships an
   audited cassette pipeline at [`tests/cassettes/anthropic/`](../../../../tests/cassettes/anthropic/)
   with a BLAKE3 `cassettes.lock` manifest, CODEOWNERS gate, four-layer
   sanitizer, and the `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1`
   ergonomic (CLAUDE.md "Cassette workflow"). A new orphan cassette
   under `tests/integration/contracts/cassettes/` would bypass every
   existing defense. Fix: drop live-Phase-4 VCR from S5-01. Replace with
   `AsyncMock(spec=FallbackTier)` — the contract under test is *the
   kwarg-name + identity-of-prior-attempts signature*, not LLM output.
   S5-05 owns the end-to-end test and must reuse the Phase 4 cassette
   infrastructure when it lands there.

7. **Mutation-resistance via identity-equal assertion.** The draft test
   would pass even if the closure silently dropped `prior_attempts`
   on the floor before reaching Phase 4. Mutation: swap
   `prior_attempts=ctx.prior_attempts` for `prior_attempts=[]` — draft
   test passes. Fix: AC-THR-2 asserts `spy.call_args.kwargs["prior_attempts"]`
   is **identity-equal** (`is`) to `ctx.prior_attempts`, not just `==`.
   An identity check catches the `list(ctx.prior_attempts)` defensive
   copy mutation; a list-equality check would miss it.

8. **mypy must-fail harness, not `# type: ignore` smoke.** The draft's
   typing test annotates `# type: ignore[arg-type]` to "confirm the type
   checker rejects it" — but `# type: ignore` *silences* the rejection,
   so there is no observable failure. Fix: the test invokes
   `mypy --strict tests/typing/test_replan_hook_typing.py` as a subprocess,
   captures stdout/stderr, asserts (a) exit code nonzero, (b) stderr
   contains the expected error code. Mirrors Phase 7.5 S1-06's
   must-fail harness pattern.

9. **Composition root, not adapter, owns substrate assembly.** Per
   Phase 4 S7-01 HARDENED Notes ("composition root, not the adapter, owns
   substrate assembly"), the 10-substrate `FallbackTier(...)` build lives
   in the plugin's `transforms()` factory. `make_orchestrator_replan_hook`
   accepts a pre-built `FallbackTier` — Dependency Inversion (Port, not
   substrate). Fix: AC-DI-1 pins the factory signature accepts
   `fallback_tier: FallbackTier`, not the 10-substrate dep set; AC-DI-2
   forbids imports under `codegenie.rag/`, `codegenie.fallback.leaf/`,
   or `codegenie.fallback.cassette/` from this module.

10. **No `sandbox/` imports.** Promoted from Notes to AC-NOSAND-1 with
    a stdlib `ast.parse`-based fence test (mirrors S5-04's AST-scan
    pattern). Stronger than the draft's Notes-only mention.

11. **Property-based threading test.** Hypothesis strategy over
    `lists(builds(AttemptSummary, ...), min_size=0, max_size=8)`; for
    each shrunk input the spy sees the same list identity-equal. Catches
    mutations like `prior_attempts=ctx.prior_attempts[1:]` (silently
    drops the first attempt under non-empty input).

12. **Signature-snapshot test.** A test that uses `inspect.signature` to
    pin `FallbackTier.run`'s parameter names (`advisory`, `repo_ctx`,
    `recipe_selection`, `prior_attempts`), keyword-only-ness of
    `prior_attempts`, and its `()` default. If Phase 4 renames the
    kwarg, this fails loudly *here* at the seam, not in some downstream
    pipeline. This is Gap 2's whole point.

13. **`GateContext.advisory`/`recipe`/`transform_output` are `str`
    placeholders today** (S1-04 HARDENED Note "Open ambiguity"). The
    factory must forward them unchanged (no type coercion); the spy
    assertion is byte-identical. Surfaced in Notes; AC-FWD-1 makes the
    contract explicit.

14. **`make_orchestrator_replan_hook` is the only public name.** Draft
    flips between `_OrchestratorReplanHook` class and the factory
    closure. Picked the factory + named inner `async def _call(ctx)`
    pattern (traceback ergonomics).

15. **Coverage floor + import-linter row.** Phase 5's `orchestrator/`
    package is a new top-level under `src/codegenie/`; landing it
    requires a fence row per CLAUDE.md "Structural defenses live under
    `tests/fence/`." AC-PKG-1 makes this explicit (create the row if
    S5-01 is first to land the package).

16. **Out-of-scope expanded** to name S5-03 (`compose_prior_attempts`),
    S5-05 (end-to-end fence-wrapped prompt), Phase 3 typed
    `Advisory`/`Recipe` widening, and any cross-phase cassette work.

No `RESCUE`-tier findings — every gap was patchable by rewriting ACs +
the TDD plan and routing through S1-04 + Phase 4 HARDENED surfaces. No
Stage-3 research needed; every gap was answerable from in-repo
precedents and the seven prior validation reports.

## Context

`GateRunner` (S5-02) invokes Phase 4's `FallbackTier.run` on every
retryable failure to obtain a new `RecipeOutcome`. The architecture
(§Component design) called this a "closure over `FallbackTier.run`"
without a typed contract — Gap 2 in the gap analysis. S1-04 HARDENED
plants the typed Protocol seam (`ReplanHook` in `gates/contract.py`);
this story plants the **concrete consumer** (`make_orchestrator_replan_hook`
under `src/codegenie/orchestrator/`) and the **cross-phase contract
test** that asserts the closure threads `prior_attempts` faithfully into
Phase 4's `FallbackTier.run` with the correct kwarg name and identity.

Without this contract test, Phase 4 can rename `prior_attempts` to
`attempts` (or drop the kwarg) and Phase 5 silently breaks. With it,
the seam is signature-snapshotted — any cross-phase rename fails at
this seam, loudly, at unit-test speed.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §Gap analysis Gap 2`](../phase-arch-design.md) — formalize `ReplanHook` Protocol + contract test rationale.
  - [`../phase-arch-design.md §Component design — GateRunner`](../phase-arch-design.md) — `replan_hook: ReplanHook | None` signature; closure over `FallbackTier.run`.
  - [`../phase-arch-design.md §Process view §Scenario 2`](../phase-arch-design.md) — sequence diagram showing the retry call into Phase 4 with `prior_attempts=[AttemptSummary(...)]`.
  - [`../phase-arch-design.md §Code contracts and APIs`](../phase-arch-design.md) — `AttemptSummary` / `GateContext` shapes (S1-04 is authoritative on the field set).
- **Phase ADRs:**
  - [`../ADRs/0002-additive-prior-attempts-kwarg.md`](../ADRs/0002-additive-prior-attempts-kwarg.md) — `prior_attempts: Sequence[AttemptSummary] = ()` kwarg shape and prompt-injection rationale.
  - [`../ADRs/0006-protocol-vs-abc-convention.md`](../ADRs/0006-protocol-vs-abc-convention.md) — Protocol (not ABC) for cross-phase callables; structural typing matches "closure" framing.
- **Production ADRs:**
  - [`../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md`](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — `FallbackTier.run` is the load-bearing target the hook wraps.
- **Source design:**
  - [`../final-design.md §Synthesis ledger — Retry feedback transport row`](../final-design.md) — winner score 12.
- **Prior HARDENED stories (the surface this one rides on):**
  - [`./S1-04-gates-contract-abc-models.md`](./S1-04-gates-contract-abc-models.md) HARDENED — ships `ReplanHook`, `AttemptSummary`, `GateContext`, `RecipeOutcome` return type.
  - [`../../04-vuln-llm-fallback-rag/stories/S6-01-fallback-tier-pipeline.md`](../../04-vuln-llm-fallback-rag/stories/S6-01-fallback-tier-pipeline.md) HARDENED — ships `async def FallbackTier.run(..., *, prior_attempts: Sequence[AttemptSummary] = ())`.
  - [`../../04-vuln-llm-fallback-rag/stories/S7-01-fallback-tier-plan-recipe-engine.md`](../../04-vuln-llm-fallback-rag/stories/S7-01-fallback-tier-plan-recipe-engine.md) HARDENED — composition-root discipline ("the adapter takes a pre-built `FallbackTier`; substrate assembly lives in the plugin's `transforms()` factory").
- **Existing code:**
  - [`src/codegenie/gates/contract.py`](../../../../src/codegenie/gates/contract.py) (from S1-04) — `ReplanHook`, `AttemptSummary`, `GateContext` already live here.
  - [`src/codegenie/transforms/outcomes.py:300`](../../../../src/codegenie/transforms/outcomes.py:300) — `RecipeOutcome = Annotated[Applied | Skipped | RecipeNotApplicable | RecipeFailed, Field(discriminator="kind")]`.
  - [`src/codegenie/fallback/fence/`](../../../../src/codegenie/fallback/fence/) — `FenceWrapper`, `CanaryGuard` (do not re-implement; not exercised by S5-01).
- **Style reference:**
  - [`../../00-bullet-tracer-foundations/stories/S4-01-language-detection-probe.md`](../../00-bullet-tracer-foundations/stories/S4-01-language-detection-probe.md) (story shape + TDD plan structure).
  - Phase 7.5 S1-06 (must-fail mypy harness pattern).
  - S5-04 (AST-scan-for-imports fence pattern; mirrored).

## Goal

Land the concrete `make_orchestrator_replan_hook` factory under
`src/codegenie/orchestrator/replan_hook.py` — a closure that conforms to
the `ReplanHook` Protocol *already shipped by S1-04* — and a contract
test asserting the closure (a) is async, (b) threads `prior_attempts`
identity-faithfully into `FallbackTier.run`'s `prior_attempts=` kwarg,
(c) returns the `RecipeOutcome` unchanged, (d) does not import anything
under `src/codegenie/sandbox/`, (e) is rejected by `mypy --strict` when
its body is type-incorrect.

The fence-wrapped prior-attempt block in Phase 4's prompt is out of
scope — that's S5-03's `FenceWrapper.compose_prior_attempts` + S5-05's
end-to-end cross-phase round-trip.

## Acceptance criteria

### A. Protocol import & shape (S1-04 already declares it)

- [ ] **AC-1 — Import shape:** `from codegenie.gates.contract import ReplanHook, GateContext, AttemptSummary` succeeds (no side effects; idempotent on second import: `id(mod_first) == id(mod_second)`).
- [ ] **AC-1a — `runtime_checkable`:** `getattr(ReplanHook, "_is_runtime_protocol", False) is True`.
- [ ] **AC-1b — Signature snapshot of `ReplanHook.__call__`:** `inspect.signature(ReplanHook.__call__)` parameter names are exactly `("self", "ctx")`; return annotation resolves to `codegenie.transforms.outcomes.RecipeOutcome` (verified via `typing.get_type_hints(ReplanHook.__call__)["return"]`). **This story owns the snapshot test; if S1-04's signature changes, this fails loudly here.**
- [ ] **AC-1c — Story does NOT edit `gates/contract.py`.** A `git diff --name-only HEAD~1..HEAD` (or equivalent) in the test does not include `src/codegenie/gates/contract.py` (the Protocol was shipped by S1-04; re-editing risks shadowing). Surface as a Notes-for-implementer rule; not a runtime test.

### B. Concrete factory (`make_orchestrator_replan_hook`)

- [ ] **AC-FAC-1 — Module location:** `src/codegenie/orchestrator/replan_hook.py` exists and exposes exactly one public name `make_orchestrator_replan_hook`; the module's `__all__ == ("make_orchestrator_replan_hook",)`.
- [ ] **AC-FAC-2 — Factory signature:** `make_orchestrator_replan_hook(*, fallback_tier: FallbackTier, repo_ctx, recipe_selection) -> ReplanHook` — three keyword-only parameters; no `advisory` parameter (advisory is captured from `ctx` at call time, which is the closure's whole point — see AC-FWD-1).
- [ ] **AC-FAC-3 — Inner function is named, not lambda:** the returned hook's `__name__` is non-empty (`_replan_hook` or similar) and `__qualname__` includes `make_orchestrator_replan_hook` so tracebacks are readable.
- [ ] **AC-DI-1 — Dependency Inversion:** the factory accepts a *pre-built* `FallbackTier` (Port, not substrate) — the test passes `AsyncMock(spec=FallbackTier)`. The factory must NOT instantiate `FallbackTier` itself (no `FallbackTier(...)` construction in `replan_hook.py`).
- [ ] **AC-DI-2 — Substrate isolation:** `src/codegenie/orchestrator/replan_hook.py` may not import anything under `codegenie.rag`, `codegenie.fallback.leaf`, or `codegenie.fallback.cassette`. Only the public `FallbackTier` class from `codegenie.fallback` may be imported (Phase 4 S7-01 "composition root, not the adapter, owns substrate assembly"). Enforced by AC-NOSAND-1's AST scan extended with the rag/leaf/cassette prefix list.

### C. Threading contract (the load-bearing test)

- [ ] **AC-THR-1 — Kwarg name pinned:** when the closure invokes `fallback_tier.run`, the call passes `prior_attempts` as a *keyword* argument (not positional). Spy assertion: `"prior_attempts" in spy.await_args.kwargs`.
- [ ] **AC-THR-2 — Identity-faithful threading:** the spy sees `spy.await_args.kwargs["prior_attempts"] is ctx.prior_attempts` — **identity-equal** (not list-equality). Catches the defensive-copy mutation (`list(ctx.prior_attempts)`) and the slice mutation (`ctx.prior_attempts[1:]`) that a list-`==` assertion would miss.
- [ ] **AC-THR-3 — Three additional kwargs pinned:** the spy sees `spy.await_args.kwargs["advisory"] is ctx.advisory`, `["repo_ctx"] is repo_ctx_captured`, `["recipe_selection"] is recipe_selection_captured`. Identity for `repo_ctx`/`recipe_selection` (captured at factory build), identity for `advisory` (captured from `ctx` at call time).
- [ ] **AC-THR-4 — No extra kwargs:** `set(spy.await_args.kwargs.keys()) == {"advisory", "repo_ctx", "recipe_selection", "prior_attempts"}` — no leaked state (e.g., a stray `workflow_id` or `run_id` from `ctx` accidentally forwarded).
- [ ] **AC-THR-5 — Positional args are empty:** `spy.await_args.args == ()` — the closure passes everything keyword-only.
- [ ] **AC-RO-1 — `RecipeOutcome` returned unchanged:** the closure returns whatever `fallback_tier.run` returns, with the same object identity (`returned_outcome is fixture_outcome`). No wrapping, no copying.
- [ ] **AC-RO-2 — Variant discrimination test:** the test parametrizes over all four `RecipeOutcome` variants (`Applied`, `Skipped`, `RecipeNotApplicable`, `RecipeFailed`); for each, the closure returns it unchanged.
- [ ] **AC-FWD-1 — No coercion on placeholder types:** `ctx.advisory`/`ctx.recipe`/`ctx.transform_output` are `str` placeholders today (S1-04 Note "Open ambiguity"); the factory must forward them byte-identical to `FallbackTier.run`. The test passes a deliberately unusual `str` value (e.g., `"CVE-2024-XYZ\nMULTI-LINE"`) and asserts the spy sees the exact same string object.

### D. Async correctness

- [ ] **AC-ASYNC-1 — Protocol is async:** `inspect.iscoroutinefunction(ReplanHook.__call__)` is `True` (verified at runtime; if S1-04 didn't ship it async, this fails here).
- [ ] **AC-ASYNC-2 — Factory closure is async:** `inspect.iscoroutinefunction(make_orchestrator_replan_hook(fallback_tier=..., repo_ctx=..., recipe_selection=...))` is `True`.
- [ ] **AC-ASYNC-3 — Test awaits the closure:** the contract test uses `await hook(ctx)` (the project's `asyncio_mode = "auto"` config means no `@pytest.mark.asyncio` marker is required; a sync test that forgets to `await` would bind a coroutine and fail at the first attribute access — explicitly mutation-test this by leaving an unawaited variant in the suite that's expected to fail).

### E. Static safety (mypy must-fail harness)

- [ ] **AC-MYPY-1 — Positive: factory passes `mypy --strict`.** Running `mypy --strict src/codegenie/orchestrator/replan_hook.py` exits 0 with no errors.
- [ ] **AC-MYPY-2 — Negative: non-conforming callable is rejected.** A companion file `tests/typing/test_replan_hook_typing_mustfail.py` defines a deliberately-wrong callable (e.g., one returning `int`) and passes it to a `def expect_replan_hook(h: ReplanHook) -> None: ...` helper. The story's TDD plan invokes `mypy --strict tests/typing/test_replan_hook_typing_mustfail.py` as a subprocess; the assertion: (a) exit code is nonzero, (b) stderr contains the substring `Argument 1 to "expect_replan_hook"` AND mentions an incompatible-type error (e.g., `error: ... [arg-type]`). No `# type: ignore` is used (a `# type: ignore` silences the rejection and removes the signal). Mirrors Phase 7.5 S1-06's must-fail pattern.
- [ ] **AC-MYPY-3 — Runtime `isinstance` caveat documented:** the test contains a Python comment block (or paired Note) stating that `isinstance(closure, ReplanHook)` is *necessary-but-not-sufficient* (`runtime_checkable` Protocols only check `__call__` presence, not signature). The mypy must-fail harness is the sufficient check; don't tighten the runtime check (which would silently over-reject duck-typed test stubs).

### F. AST fences (cold-start + cross-package)

- [ ] **AC-NOSAND-1 — No `sandbox/` imports in `orchestrator/replan_hook.py`.** New file `tests/fence/test_orchestrator_replan_hook_imports.py`: `ast.parse(open("src/codegenie/orchestrator/replan_hook.py").read())`; iterate every `ast.Import` and `ast.ImportFrom`; assert no `module` (or alias name) starts with `codegenie.sandbox` or `codegenie.rag` or `codegenie.fallback.leaf` or `codegenie.fallback.cassette`. The test names the four banned prefixes in a `_BANNED_PREFIXES` Final tuple at module top so adding a fifth is a one-line edit.
- [ ] **AC-PKG-1 — `src/codegenie/orchestrator/` is a new top-level package.** If S5-01 is the first story to land it, this story creates `src/codegenie/orchestrator/__init__.py` (empty save for `from codegenie.orchestrator.replan_hook import make_orchestrator_replan_hook`) AND adds the cold-start fence row per CLAUDE.md "Structural defenses live under `tests/fence/`". If the package already exists at land time, the test merely confirms the fence row references `orchestrator/`.
- [ ] **AC-SIG-1 — `FallbackTier.run` signature snapshot:** a separate `tests/integration/contracts/test_fallback_tier_signature_snapshot.py` uses `inspect.signature(FallbackTier.run)` to pin: parameter names exactly `("self", "advisory", "repo_ctx", "recipe_selection", "prior_attempts")`; `prior_attempts` is `KEYWORD_ONLY`; `prior_attempts.default` is `()` (empty tuple — verified via `is ()` or `== () and type(...) is tuple`); `prior_attempts.annotation` resolves to `Sequence[AttemptSummary]`. If Phase 4 renames or drops the kwarg, this fails *here*, loudly.
- [ ] **AC-SIG-2 — Default is immutable empty tuple, not list:** `FallbackTier.run.__defaults__[-1] is ()` or equivalent identity check (catches a future Phase 4 mutation `prior_attempts: list[AttemptSummary] = []` regression).

### G. TDD plan + tooling

- [ ] **AC-TDD-1 — Red test exists, is committed, and is green.** The Step "Red — write the failing test first" below ships as the canonical red.
- [ ] **AC-TOOL-1 — Property-based threading test:** Hypothesis strategy `lists(builds(AttemptSummary, attempt_id=integers(1, 1024), sandbox_run_id=text(min_size=1, max_size=64), failing_signals=lists(sampled_from(["build", "install", "tests"]), max_size=3), prior_failure_summary=text(max_size=4096), evidence_paths=just({})), min_size=0, max_size=8)`. For each shrunk input the spy sees the same list identity-equal to the input. Mutation-test: `prior_attempts=ctx.prior_attempts[1:]` is caught by the shrinker.
- [ ] **AC-TOOL-2 — Lint + typecheck + test gates pass:** `ruff check src/codegenie/orchestrator tests/integration/contracts tests/typing tests/fence`, `mypy --strict src/codegenie/orchestrator`, `pytest tests/integration/contracts/test_replan_hook_contract.py tests/integration/contracts/test_fallback_tier_signature_snapshot.py tests/fence/test_orchestrator_replan_hook_imports.py tests/typing/` all pass.
- [ ] **AC-TOOL-3 — Coverage floor:** line ≥ 95% / branch ≥ 90% on `src/codegenie/orchestrator/replan_hook.py` (matches the README convention surfaced in S1-04 Note #15).

## Implementation outline

1. **Confirm S1-04 + Phase 4 S6-01 are GREEN.** Read `gates/contract.py` for the `ReplanHook` Protocol; read `codegenie.fallback`'s `FallbackTier` class for the `run(...)` async signature and the four kwarg names. If either is not yet GREEN, BLOCK the story and surface the precondition.
2. **Create `src/codegenie/orchestrator/__init__.py`** (if absent) with the re-export of `make_orchestrator_replan_hook`. Add the cold-start fence row per AC-PKG-1.
3. **Write the red contract test first** (`tests/integration/contracts/test_replan_hook_contract.py` — five tests: import shape, identity-faithful threading, variant discrimination, async correctness, no-extra-kwargs). Use `AsyncMock(spec=FallbackTier)` as the spy; **no VCR cassette**.
4. **Write the signature-snapshot test** (`tests/integration/contracts/test_fallback_tier_signature_snapshot.py`) — pure `inspect.signature` introspection; no calls into Phase 4.
5. **Write the AST fence test** (`tests/fence/test_orchestrator_replan_hook_imports.py`) — `ast.parse` + `_BANNED_PREFIXES` walk.
6. **Write the mypy must-fail typing test** (`tests/typing/test_replan_hook_typing_mustfail.py` — the file mypy is supposed to *fail* on — and `tests/typing/test_replan_hook_typing_runner.py` — the subprocess invoker that asserts the failure).
7. **Implement** `make_orchestrator_replan_hook`:
   ```python
   # src/codegenie/orchestrator/replan_hook.py
   from __future__ import annotations

   from collections.abc import Sequence
   from typing import TYPE_CHECKING

   from codegenie.gates.contract import GateContext, ReplanHook

   if TYPE_CHECKING:
       from codegenie.fallback import FallbackTier
       from codegenie.transforms.outcomes import RecipeOutcome

   __all__ = ("make_orchestrator_replan_hook",)


   def make_orchestrator_replan_hook(
       *,
       fallback_tier: FallbackTier,
       repo_ctx: object,         # placeholder until Phase 3 ships the typed model
       recipe_selection: object, # placeholder until Phase 3 ships the typed model
   ) -> ReplanHook:
       """Closure factory wiring GateRunner → FallbackTier.run.

       Per Phase 5 ADR-0002 the seam is keyword-only and additive; per
       Phase 4 S7-01 the substrate stays in the plugin's transforms()
       factory and this adapter accepts a *pre-built* FallbackTier.
       """
       async def _replan_hook(ctx: GateContext) -> RecipeOutcome:
           return await fallback_tier.run(
               advisory=ctx.advisory,
               repo_ctx=repo_ctx,
               recipe_selection=recipe_selection,
               prior_attempts=ctx.prior_attempts,
           )
       return _replan_hook
   ```
8. **Refactor:** ensure the docstring cites ADR-0002, ADR-0006, Phase 5 Gap 2, and Phase 4 S7-01's composition-root note; verify no `sandbox/` / `rag/` / `fallback.leaf/` / `fallback.cassette/` imports leaked.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Five test files. The load-bearing one is below; see Implementation outline §3–§6 for the others.

```python
# tests/integration/contracts/test_replan_hook_contract.py
from __future__ import annotations

import inspect
from collections.abc import Sequence
from unittest.mock import AsyncMock

import pytest
from hypothesis import given
from hypothesis import strategies as st

from codegenie.fallback import FallbackTier  # the public Port
from codegenie.gates.contract import (
    AttemptSummary,
    GateContext,
    ReplanHook,
)
from codegenie.orchestrator.replan_hook import make_orchestrator_replan_hook
from codegenie.transforms.outcomes import (
    Applied,
    RecipeFailed,
    RecipeNotApplicable,
    RecipeOutcome,
    Skipped,
)


def _make_ctx(prior_attempts: Sequence[AttemptSummary] = ()) -> GateContext:
    return GateContext(
        worktree="/tmp/wt",
        advisory="CVE-2024-XYZ\nMULTI-LINE",        # str placeholder per S1-04
        recipe="r1",
        transform_output="t1",
        prior_attempts=list(prior_attempts),
        workflow_id="wf-1",
        run_id="run-1",
    )


def _applied() -> Applied:
    return Applied(transform_id="bk3-deadbeef" * 4, plugin_id="p1", recipe_id="r1")


# --- (i) Protocol import + runtime conformance ----------------------------

def test_protocol_is_runtime_checkable_and_async() -> None:
    assert getattr(ReplanHook, "_is_runtime_protocol", False) is True
    assert inspect.iscoroutinefunction(ReplanHook.__call__)
    sig = inspect.signature(ReplanHook.__call__)
    assert tuple(sig.parameters) == ("self", "ctx")


# --- (ii) Identity-faithful threading (the load-bearing assertion) --------

async def test_closure_threads_prior_attempts_identity_faithfully() -> None:
    spy = AsyncMock(spec=FallbackTier)
    spy.run.return_value = _applied()
    repo_ctx, recipe_selection = object(), object()
    hook = make_orchestrator_replan_hook(
        fallback_tier=spy,
        repo_ctx=repo_ctx,
        recipe_selection=recipe_selection,
    )

    # runtime conformance — necessary but not sufficient (AC-MYPY-3)
    assert isinstance(hook, ReplanHook)
    # the closure must itself be a coroutine function (AC-ASYNC-2)
    assert inspect.iscoroutinefunction(hook)

    ctx = _make_ctx([AttemptSummary(
        attempt_id=1, sandbox_run_id="sb-1", failing_signals=["build"],
        prior_failure_summary="boom", evidence_paths={},
    )])
    out = await hook(ctx)

    # (AC-RO-1) returned unchanged with identity
    assert out is spy.run.return_value

    # (AC-THR-5) no positional args
    assert spy.run.await_args.args == ()

    # (AC-THR-4) exact kwarg set — no extra leaked state
    assert set(spy.run.await_args.kwargs) == {
        "advisory", "repo_ctx", "recipe_selection", "prior_attempts",
    }

    # (AC-THR-1, AC-THR-2) prior_attempts is identity-equal, not list-equal
    assert spy.run.await_args.kwargs["prior_attempts"] is ctx.prior_attempts

    # (AC-THR-3, AC-FWD-1) other kwargs forwarded byte-identical
    assert spy.run.await_args.kwargs["advisory"] is ctx.advisory
    assert spy.run.await_args.kwargs["repo_ctx"] is repo_ctx
    assert spy.run.await_args.kwargs["recipe_selection"] is recipe_selection


# --- (iii) Variant discrimination across the RecipeOutcome union ---------

@pytest.mark.parametrize("outcome_factory", [
    lambda: _applied(),
    lambda: Skipped(reason="recipe_disabled", plugin_id="p1"),  # field names per outcomes.py
    lambda: RecipeNotApplicable(reason="no_match", considered=[]),
    # RecipeFailed parametrization uses a fixture-built RecipeError
])
async def test_returns_recipe_outcome_unchanged_for_each_variant(outcome_factory) -> None:
    spy = AsyncMock(spec=FallbackTier)
    spy.run.return_value = outcome_factory()
    hook = make_orchestrator_replan_hook(
        fallback_tier=spy, repo_ctx=object(), recipe_selection=object(),
    )
    out = await hook(_make_ctx())
    assert out is spy.run.return_value
    assert isinstance(out, (Applied, Skipped, RecipeNotApplicable, RecipeFailed))


# --- (iv) Property-based threading (Hypothesis) ---------------------------

attempt_summary_st = st.builds(
    AttemptSummary,
    attempt_id=st.integers(min_value=1, max_value=1024),
    sandbox_run_id=st.text(min_size=1, max_size=64),
    failing_signals=st.lists(st.sampled_from(["build", "install", "tests"]), max_size=3),
    prior_failure_summary=st.text(max_size=4096),
    evidence_paths=st.just({}),
)

@given(attempts=st.lists(attempt_summary_st, min_size=0, max_size=8))
async def test_prior_attempts_threaded_identity_under_arbitrary_shapes(attempts) -> None:
    spy = AsyncMock(spec=FallbackTier)
    spy.run.return_value = _applied()
    hook = make_orchestrator_replan_hook(
        fallback_tier=spy, repo_ctx=object(), recipe_selection=object(),
    )
    ctx = _make_ctx(attempts)
    await hook(ctx)
    # the shrinker would catch `prior_attempts[1:]` (drops first) and
    # `list(prior_attempts)` (defensive copy) — both fail identity-equal.
    assert spy.run.await_args.kwargs["prior_attempts"] is ctx.prior_attempts
```

```python
# tests/integration/contracts/test_fallback_tier_signature_snapshot.py
import inspect
from collections.abc import Sequence

from codegenie.fallback import FallbackTier
from codegenie.gates.contract import AttemptSummary


def test_fallback_tier_run_signature_is_snapshot_pinned() -> None:
    sig = inspect.signature(FallbackTier.run)
    params = list(sig.parameters.values())
    names = [p.name for p in params]
    assert names == ["self", "advisory", "repo_ctx", "recipe_selection", "prior_attempts"]

    pa = sig.parameters["prior_attempts"]
    assert pa.kind == inspect.Parameter.KEYWORD_ONLY
    # AC-SIG-2 — default is the *empty tuple* literal, not a list
    assert pa.default == () and type(pa.default) is tuple
    # annotation resolves to Sequence[AttemptSummary] (or stringified during typing)
    assert "Sequence" in str(pa.annotation) and "AttemptSummary" in str(pa.annotation)

    assert inspect.iscoroutinefunction(FallbackTier.run)
```

```python
# tests/fence/test_orchestrator_replan_hook_imports.py
import ast
from pathlib import Path
from typing import Final

_BANNED_PREFIXES: Final[tuple[str, ...]] = (
    "codegenie.sandbox",
    "codegenie.rag",
    "codegenie.fallback.leaf",
    "codegenie.fallback.cassette",
)


def test_replan_hook_imports_are_clean() -> None:
    src = Path("src/codegenie/orchestrator/replan_hook.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not any(mod.startswith(p) for p in _BANNED_PREFIXES), (
                f"forbidden import: from {mod} ..."
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name.startswith(p) for p in _BANNED_PREFIXES), (
                    f"forbidden import: {alias.name}"
                )
```

```python
# tests/typing/test_replan_hook_typing_mustfail.py
# This file is INTENDED to fail mypy --strict. It is run as a subprocess by
# tests/typing/test_replan_hook_typing_runner.py; the runner asserts the
# failure. No `# type: ignore` is used — that would silence the signal.
from __future__ import annotations
from codegenie.gates.contract import GateContext, ReplanHook


def expect_replan_hook(h: ReplanHook) -> None:  # noqa: D401
    pass


async def wrong_hook(ctx: GateContext) -> int:   # wrong return type
    return 7


expect_replan_hook(wrong_hook)  # mypy must reject this line
```

```python
# tests/typing/test_replan_hook_typing_runner.py
import subprocess
import sys


def test_mypy_rejects_non_conforming_replan_hook() -> None:
    proc = subprocess.run(
        [
            sys.executable, "-m", "mypy", "--strict",
            "tests/typing/test_replan_hook_typing_mustfail.py",
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode != 0, "mypy --strict was expected to fail"
    combined = proc.stdout + proc.stderr
    assert 'Argument 1 to "expect_replan_hook"' in combined
    assert "[arg-type]" in combined
```

### Green — make it pass

Smallest implementation: ship `make_orchestrator_replan_hook` per
Implementation outline §7. No edits to `gates/contract.py` (S1-04 owns
it). No cassette work. The five test files run under `pytest -q` against
the `AsyncMock`-spy'd `FallbackTier`.

### Refactor — clean up

- Replace any anonymous `lambda` survivor with the named inner
  `async def _replan_hook(ctx)` for traceback ergonomics.
- Add a one-line docstring citing ADR-0002, ADR-0006, Gap 2, and Phase 4
  S7-01's composition-root note.
- Confirm `from __future__ import annotations` is line 1; the
  `RecipeOutcome` import is under `if TYPE_CHECKING:` to avoid runtime
  cycles.
- Confirm `__all__` is exactly `("make_orchestrator_replan_hook",)`.
- Re-export from `src/codegenie/orchestrator/__init__.py` (one line:
  `from codegenie.orchestrator.replan_hook import make_orchestrator_replan_hook`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/orchestrator/__init__.py` | New package — re-export `make_orchestrator_replan_hook`. |
| `src/codegenie/orchestrator/replan_hook.py` | The concrete factory. |
| `tests/integration/contracts/__init__.py` | New test package dir. |
| `tests/integration/contracts/test_replan_hook_contract.py` | Five-test contract suite (import, threading, variants, async, property-based). |
| `tests/integration/contracts/test_fallback_tier_signature_snapshot.py` | Gap-2 signature snapshot — the loud-rename detector. |
| `tests/fence/test_orchestrator_replan_hook_imports.py` | AST scan — no `sandbox/`, `rag/`, `fallback.leaf/`, `fallback.cassette/` imports. |
| `tests/fence/test_orchestrator_cold_start.py` (or extend an existing fence file) | Cold-start fence row per AC-PKG-1. |
| `tests/typing/test_replan_hook_typing_mustfail.py` | The intentionally-failing typing file. |
| `tests/typing/test_replan_hook_typing_runner.py` | Subprocess invoker asserting the failure. |
| `pyproject.toml` | Confirm `hypothesis` is already in `[project.optional-dependencies].dev` (no new dep expected; surface if absent). |

## Out of scope

- `GateRunner.run` loop implementation — **S5-02**.
- `FenceWrapper.compose_prior_attempts` helper + Phase 4's prompt builder consuming `prior_attempts` — **S5-03**.
- Stage 6 chokepoint AST test — **S5-04**.
- End-to-end retry-recovers integration with a *real* cassette under Phase 4's audited cassette infrastructure (CLAUDE.md "Cassette workflow") — **S5-05**.
- Widening `GateContext.advisory`/`recipe`/`transform_output` from `str` placeholder to Phase 3 typed Pydantic models — **future Phase 3 widening story** (surface as ADR amendment when Phase 3 ships the types).
- Adding `ReplanHook` to `gates/contract.py` — **already shipped by S1-04 HARDENED**; AC-1c forbids editing.

## Notes for the implementer

- **`ReplanHook` lives in `gates/contract.py` per S1-04 HARDENED.** Do
  not edit that file. Import the Protocol; don't redeclare it.
- **The return type is `RecipeOutcome` (a discriminated union), not
  `RecipeApplication`** (which does not exist). Match on `kind` if you
  branch; tests assert via `isinstance(out, (Applied, Skipped, ...))`.
- **The factory accepts a pre-built `FallbackTier`.** Per Phase 4 S7-01
  HARDENED, the 10-substrate `FallbackTier(...)` assembly lives in the
  plugin's `transforms()` factory (composition root); the orchestrator
  hook depends only on the *Port*. Tests pass `AsyncMock(spec=FallbackTier)`.
- **`FallbackTier.run` is `async`.** The closure body is
  `await fallback_tier.run(...)`. The Protocol's `__call__` is also
  `async def`. The project's `asyncio_mode = "auto"` pytest config (per
  `pyproject.toml § [tool.pytest.ini_options]`) makes
  `@pytest.mark.asyncio` redundant — coroutine tests run without it.
- **`isinstance(closure, ReplanHook)` is necessary but not sufficient.**
  `runtime_checkable` Protocols only check `__call__` *presence*, not its
  signature. The mypy must-fail harness is the sufficient check. Don't
  tighten the runtime check (over-rejects duck-typed test stubs).
- **No VCR cassette in S5-01.** The contract this story protects is
  *the cross-phase call signature*, not the LLM output. Cassettes test
  end-to-end behavior; spies test cross-phase contracts. The end-to-end
  test belongs in S5-05 and must reuse the Phase 4 cassette infrastructure
  at [`tests/cassettes/anthropic/`](../../../../tests/cassettes/anthropic/)
  (CLAUDE.md "Cassette workflow") — not a parallel orphan tree.
- **`ctx.advisory`/`recipe`/`transform_output` are `str` placeholders.**
  S1-04 HARDENED Note "Open ambiguity (resolved)" documents this. The
  factory must forward them byte-identical. When Phase 3 ships the typed
  models, an additive widening story tightens both ends.
- **`prior_attempts` is `Sequence[AttemptSummary]` with `()` default.**
  Per Phase 4 S6-01 HARDENED — read-covariant `Sequence` (callers
  passing `list` typecheck), immutable empty tuple default (no
  mutable-default footgun). If the signature-snapshot test fails because
  Phase 4 shipped `list[...]` or `[...]` instead, BLOCK the executor and
  surface as a Global-Rule-7 conflict per CLAUDE.md.
- **The `make_orchestrator_replan_hook` factory's parameter list is
  closed under what the orchestrator owns** — `fallback_tier`, `repo_ctx`,
  `recipe_selection`. Pulling `advisory` from `ctx` (not the factory) is
  what makes the closure usable across attempts.
- **No retry semantics in the hook itself.** Retry is `GateRunner`'s job
  (S5-02). The hook is a one-shot async dispatch.
- **Pattern lifts (Notes-only, not promoted to AC):**
  - **Dependency Inversion** at the cross-phase seam — the orchestrator
    depends on the `FallbackTier` Port, not the substrate (Phase 4 S7-01
    "composition root, not the adapter, owns substrate assembly").
  - **Hexagonal / Ports-and-adapters** — `ReplanHook` is the Port; the
    factory is the adapter; new replan strategies (e.g., Phase 6's
    LangGraph hook) are new adapters, not edits to `gates/contract.py`
    (Open/Closed at the cross-phase seam).
  - **Functional core / imperative shell** — `replan_hook.py` has zero
    state of its own; the inner `_replan_hook` is referentially
    transparent given its captured collaborators.
  - **Tagged-union discipline in tests** — when expanding variant
    coverage past `Applied`, use `match outcome: case Applied(): ...`
    over `if outcome.kind == "applied"`. Surface only; match the
    existing Phase 5 test style at executor time (Rule 11).
