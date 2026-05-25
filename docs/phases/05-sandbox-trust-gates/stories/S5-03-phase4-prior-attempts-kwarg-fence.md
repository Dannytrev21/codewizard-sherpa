# Story S5-03 — Phase-5-side cross-phase `prior_attempts` contract conformance (ADR-0002)

**Step:** Step 5 — GateRunner three-retry loop + Phase 4 replan_hook integration
**Status:** Ready (HARDENED 2026-05-25)
**Effort:** S
**Depends on:** S5-02 (`GateRunner`); transitively S5-01 (`ReplanHook` Protocol + concrete adapter)
**ADRs honored:** ADR-0002

## Validation notes (2026-05-25 — phase-story-validator)

Story HARDENED. Substantial rewrite — the original draft predated every upstream surface this story exists to coordinate. Summary of changes:

- **Scope narrowed.** The draft asserted Phase 5 must add `prior_attempts` to `ApplyContext` and to `FallbackTier.run`, and build a `FenceWrapper.compose_prior_attempts` helper. Every one of those is upstream-owned:
  - Phase 3 S1-04 (**GREEN**) already shipped `ApplyContext.prior_attempts: tuple[AttemptSummary, ...] = ()` at [`src/codegenie/transforms/apply_context.py:140`](../../../../src/codegenie/transforms/apply_context.py) — immutable container per V-D-F2 closure (Pydantic `frozen=True` does not freeze in-place mutation).
  - Phase 4 S6-01 (**HARDENED**) already pinned `async def run(advisory, repo_ctx, recipe_selection, *, prior_attempts: Sequence[AttemptSummary] = ()) -> RecipeApplication` — keyword-only, read-covariant, immutable empty-tuple default ([`stories/S6-01-fallback-tier-pipeline.md:51`](../../../04-vuln-llm-fallback-rag/stories/S6-01-fallback-tier-pipeline.md)).
  - Phase 4 S6-02 (**HARDENED**) already pinned the prompt-assembly reduction: when `bool(prior_attempts) is True`, `FallbackTier.run` passes `prior_attempts[-1].prior_failure_summary` (raw `str`) into `PromptBuilder.build(prior_attempt_summary=...)` ([`stories/S6-02-retry-bypass-rag.md:47`](../../../04-vuln-llm-fallback-rag/stories/S6-02-retry-bypass-rag.md)). `PromptBuilder` owns the fence call — S2-04 AC-13 enforces "PromptBuilder is the sole fence-call site" via an AST-walking guard.
  - The `"prior_attempt_summary"` fence `SourceKind` is **already** in [`src/codegenie/fallback/fence/wrapper.py:53-76`](../../../../src/codegenie/fallback/fence/wrapper.py) with cap `4 * 1024` UTF-8 bytes, dispatched polymorphically via `_TRUNCATION_CAPS[source_kind]`.
- **Rejected the `FenceWrapper.compose_prior_attempts` helper.** It violates four shipped patterns: (a) the polymorphism-by-data Strategy (`_TRUNCATION_CAPS[source_kind]`); (b) the functional-core / imperative-shell separation (`fence_pure` pure + `FenceWrapper` shell-emits-events); (c) the sole-mint-site discipline (S2-04 AC-13 AST-walking guard); (d) the `HexNonce` newtype + `^[0-9a-f]{32}$` pattern. The draft's `<BEGIN_PRIOR_ATTEMPT_{16hex_upper}>` delimiter directly contradicts the shipped `<UNTRUSTED_INPUT id={32hex_lower}>` delimiter — Rule 7 ("surface conflicts, don't average them") applies.
- **Module paths corrected.** `codegenie.llm.fence` → `codegenie.fallback.fence`. `src/codegenie/plan/fallback.py` → `src/codegenie/fallback/tier.py` (HARDENED upstream; not yet GREEN). `codegenie.gates.contract.AttemptSummary` → `codegenie.transforms.apply_context.AttemptSummary`.
- **`AttemptSummary` field shape corrected.** Shipped fields: `attempt: AttemptNumber`, `failing_signals: tuple[SignalKind, ...]`, `prior_failure_summary: str`, `evidence_paths: tuple[SandboxedPath, ...]`, `transform_id: TransformId | None`. The draft used `attempt_id`, `sandbox_run_id`, `list[str]`, `dict[...]` — none correct.
- **4 KB vs 8 KB conflation closed.** `AttemptSummary._SUMMARY_UTF8_BYTES_CAP = 8192` is the **storage** validation cap (raises on over-cap). `_TRUNCATION_CAPS["prior_attempt_summary"] = 4 * 1024` is the **render** truncation cap (codepoint-safe; no `…[truncated]` text marker — the `FencedSegment.truncated: bool` field is the signal).
- **`Sequence[AttemptSummary] = ()` adopted everywhere.** No mutable-default footgun. `Sequence` is read-covariant so `list` and `tuple` callers both typecheck. Matches both Phase 3 shipped (`tuple[..., ...] = ()`) and Phase 4 HARDENED (`Sequence[...] = ()`).
- **ACs rewritten as introspection-driven conformance assertions.** No new production code in `src/codegenie/`; one new test file at `tests/schema/test_phase5_cross_phase_prior_attempts_contract.py` plus one new test in `tests/unit/orchestrator/test_replan_hook_seam_identity.py` (or extension of an S5-01 test if that one lands first).
- **Cross-story follow-up surfaced (Rule 7).** S5-05 asserts `re.search(r"<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>", text)` — bound to the rejected helper. The correct assertion is `re.search(r"<UNTRUSTED_INPUT id=[0-9a-f]{32}>", text)` plus `PromptAssembled.source_kinds_used` contains `"prior_attempt_summary"`. **Recommend S5-05 be re-validated before execution.**
- **Status:** `Ready` → `Ready (HARDENED 2026-05-25)`.

See [`_validation/S5-03-phase4-prior-attempts-kwarg-fence.md`](_validation/S5-03-phase4-prior-attempts-kwarg-fence.md) for the full critic reports, conflict-resolution log, and design-pattern findings.

## Context

ADR-0002 is the cross-phase additive amendment that carries failed-attempt evidence from Phase 5's `GateRunner` retry loop into Phase 4's recipe→RAG→LLM ladder — without breaking either side's existing callsites and without leaking raw sandbox stderr into the LLM prompt. The amendment touches three packages: `codegenie.transforms` (Phase 3 — `ApplyContext` field; `AttemptSummary` model), `codegenie.fallback` (Phase 4 — `FallbackTier.run` kwarg; `PromptBuilder.build(prior_attempt_summary=...)` reduction; `FenceWrapper` fence-by-source-kind dispatch), and the future `codegenie.gates` package (Phase 5 — `GateRunner` retry envelope; `ReplanHook` adapter).

When this story was originally drafted, **none** of the upstream surfaces had landed. Since then:

- **Phase 3 S1-04 shipped GREEN** with `ApplyContext.prior_attempts: tuple[AttemptSummary, ...] = ()` and `AttemptSummary` (Pydantic v2, `frozen=True`, `extra="forbid"`, 8 KB UTF-8-bytes summary cap, NUL/C0/bidi rejection per ADR-0010 / E20).
- **Phase 4 S6-01 reached HARDENED** with `async def FallbackTier.run(..., *, prior_attempts: Sequence[AttemptSummary] = ()) -> RecipeApplication`.
- **Phase 4 S6-02 reached HARDENED** with the retry-bypass branch: when `bool(prior_attempts)`, skip RAG, pass `prior_attempts[-1].prior_failure_summary` into `PromptBuilder.build(prior_attempt_summary=...)`, emit `RagSkippedOnRetry`.
- **Phase 4 S2-02 / S2-04 shipped GREEN** with the `"prior_attempt_summary"` `SourceKind` + cap + `PromptBuilder` sole-fence-site discipline.

So this story owes **no production code in `src/codegenie/`**. What it owes is a Phase-5-side **conformance fence** — a CI test that pins the byte-stable upstream surfaces from the consumer's side, so a future renaming on either side fails Phase 5's tests *first* (loud, before the integration test at S5-05 silently breaks). The shape mirrors how `tests/schema/test_no_llm_imports_in_sandbox.py` and `test_stage6_chokepoint.py` (S1-07 / S5-04) defend Phase 5's structural invariants from inside Phase 5.

The second residual scope is a Phase-5-side **seam test**: the orchestrator's `make_orchestrator_replan_hook` closure (S5-01 territory, but Phase 5's responsibility) must forward `ctx.prior_attempts` to `FallbackTier.run(prior_attempts=...)` **by identity** — i.e., the *same* sequence object, not a rebuilt copy. This guards against a "looks-correct, breaks-audit-identity" regression at the seam.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Component design — `GateContext`, `AttemptSummary`" §"Logical view"](../phase-arch-design.md) — `ApplyContext +prior_attempts` and `FallbackTier.run +prior_attempts` are the two amendment points (Phase 3 and Phase 4).
  - [`../phase-arch-design.md` §"Best-practices for safe leaf LLM calls — Prompt template structure"](../phase-arch-design.md) — Phase 5 owns the sanitized `prior_failure_summary` via `AttemptSummary`; Phase 4 owns the fence/canary/truncation pattern (do not duplicate).
  - [`../phase-arch-design.md` §Edge cases #16](../phase-arch-design.md) — prompt-injection-in-stderr handled by Phase 4's `CanaryGuard` (reused via `PromptBuilder` → `FenceWrapper.fence`).
- **Phase ADRs:**
  - [`../ADRs/0002-additive-prior-attempts-kwarg.md`](../ADRs/0002-additive-prior-attempts-kwarg.md) — additive-only; cross-phase contract; reuses Phase 4's `FenceWrapper`. Unamended; still authoritative.
- **Production ADRs:**
  - [`../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md`](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — `FallbackTier.run` is the recipe→RAG→LLM ladder; the kwarg lives at the public surface (Phase 4 owns the prompt-internal threading per S6-02).
- **Source design:**
  - [`../final-design.md` §"Synthesis ledger — Retry feedback transport row"](../final-design.md) and §"Departures from all three inputs §3".
- **Upstream HARDENED / GREEN stories:**
  - Phase 3 S1-04 GREEN — [`../../../03-vuln-deterministic-recipe/stories/S1-04-transform-abc-apply-context.md`](../../../03-vuln-deterministic-recipe/stories/S1-04-transform-abc-apply-context.md) (shipped `ApplyContext`, `AttemptSummary`).
  - Phase 4 S6-01 HARDENED — [`../../../04-vuln-llm-fallback-rag/stories/S6-01-fallback-tier-pipeline.md`](../../../04-vuln-llm-fallback-rag/stories/S6-01-fallback-tier-pipeline.md) (`FallbackTier.run` signature).
  - Phase 4 S6-02 HARDENED — [`../../../04-vuln-llm-fallback-rag/stories/S6-02-retry-bypass-rag.md`](../../../04-vuln-llm-fallback-rag/stories/S6-02-retry-bypass-rag.md) (retry-bypass branch + `prior_attempt_summary` reduction).
  - Phase 4 S2-02 / S2-04 GREEN — [`src/codegenie/fallback/fence/wrapper.py`](../../../../src/codegenie/fallback/fence/wrapper.py), [`src/codegenie/fallback/fence/prompt_builder.py`](../../../../src/codegenie/fallback/fence/prompt_builder.py).
- **Existing code to consume (not modify):**
  - [`src/codegenie/transforms/apply_context.py`](../../../../src/codegenie/transforms/apply_context.py) — `ApplyContext`, `AttemptSummary`.
  - [`src/codegenie/fallback/fence/wrapper.py`](../../../../src/codegenie/fallback/fence/wrapper.py) — `FenceWrapper`, `SourceKind`, `_TRUNCATION_CAPS`, `HexNonce`.
  - [`src/codegenie/fallback/fence/prompt_builder.py`](../../../../src/codegenie/fallback/fence/prompt_builder.py) — `PromptBuilder.build(prior_attempt_summary=...)`.
  - `src/codegenie/fallback/tier.py` — `FallbackTier` (HARDENED, not yet GREEN; conformance test skips with reason until then).

## Goal

Land a Phase-5-side cross-phase conformance fence that pins the four byte-stable upstream surfaces of ADR-0002 (`ApplyContext.prior_attempts`, `AttemptSummary` shape, `FallbackTier.run` signature when GREEN, fence `SourceKind` + cap), plus an identity-preserving seam test that proves the orchestrator's `ReplanHook` closure forwards `ctx.prior_attempts` to `FallbackTier.run` by identity (kwarg name + object identity).

## Acceptance criteria

### Conformance fence — shipped Phase 3 surface

- [ ] **AC-CONF-1 (`ApplyContext.prior_attempts` field-shape lock).** `tests/schema/test_phase5_cross_phase_prior_attempts_contract.py::test_apply_context_prior_attempts_shape` introspects `ApplyContext.model_fields["prior_attempts"]` and asserts: (a) the field exists; (b) its annotation is `tuple[AttemptSummary, ...]` (use `typing.get_args` + `typing.get_origin`); (c) its default-factory or default value equals `()`. The test imports `ApplyContext` from `codegenie.transforms.apply_context` (asserts importability at that exact path).
- [ ] **AC-IMP-1 (`AttemptSummary` import path lock).** Same test file `test_attempt_summary_import_path` asserts `from codegenie.transforms.apply_context import AttemptSummary` succeeds; any `from codegenie.gates.contract import AttemptSummary` raises `ImportError` (parametrized negative).
- [ ] **AC-IMP-2 (`AttemptSummary` field shape lock).** `test_attempt_summary_model_fields` asserts `set(AttemptSummary.model_fields) == {"attempt", "failing_signals", "prior_failure_summary", "evidence_paths", "transform_id"}`. Each field's annotation is introspected: `attempt → AttemptNumber`, `failing_signals → tuple[SignalKind, ...]`, `prior_failure_summary → str`, `evidence_paths → tuple[SandboxedPath, ...]`, `transform_id → TransformId | None`. (Use `typing.get_args` over the field annotation to detect Union / `| None`.)
- [ ] **AC-IMP-3 (validation-cap vs render-cap distinction).** `test_summary_cap_distinction` asserts (a) `AttemptSummary._SUMMARY_UTF8_BYTES_CAP == 8192` (storage cap; over-cap *raises*, not truncates); (b) `from codegenie.fallback.fence.wrapper import _TRUNCATION_CAPS; assert _TRUNCATION_CAPS["prior_attempt_summary"] == 4 * 1024` (render cap; over-cap *truncates codepoint-safe* with `FencedSegment.truncated=True`). Adversarial subcase: a 8193-byte summary `pytest.raises(ValueError)` at `AttemptSummary(...)` construction; a 4097-byte payload passed through `FenceWrapper.fence(...)` returns `truncated=True`, never raises.

### Conformance fence — shipped Phase 4 surface

- [ ] **AC-CONF-3 (`SourceKind` Literal contains `"prior_attempt_summary"`).** `test_source_kind_membership` imports `SourceKind` from `codegenie.fallback.fence.wrapper` and asserts `"prior_attempt_summary" in typing.get_args(SourceKind)`. Parametrized adversarial: `"prior_attempts"` (typo), `"PRIOR_ATTEMPT_SUMMARY"` (case mismatch), `"attempt_summary"` (truncated) all NOT in the union.
- [ ] **AC-CONF-3b (`HexNonce` shape lock).** `test_hex_nonce_pattern` asserts the production nonce factory produces `re.fullmatch(r"^[0-9a-f]{32}$", _default_nonce_source())` for 100 samples (the `secrets.token_hex(16)` guarantee). The draft's `secrets.token_hex(8).upper()` pattern is **explicitly negative-asserted** (asserts `re.fullmatch(r"^[A-F0-9]{16}$", _default_nonce_source())` always fails) to fence against regression.
- [ ] **AC-CONF-4 (`PromptBuilder.build` signature lock).** `test_prompt_builder_accepts_prior_attempt_summary` introspects `inspect.signature(PromptBuilder.build)` (imported from `codegenie.fallback.fence.prompt_builder`) and asserts: parameter `prior_attempt_summary` exists; kind is `KEYWORD_ONLY`; default is `None`; annotation `str | None` (use `inspect.signature(...).parameters[...].annotation` + `typing.get_args` to handle the union).

### Conformance fence — Phase 4 surface awaiting GREEN

- [ ] **AC-CONF-2 (`FallbackTier.run` signature lock — skipped-until-GREEN).** `test_fallback_tier_run_signature` attempts `from codegenie.fallback.tier import FallbackTier` — if `ImportError`, calls `pytest.skip("Phase 4 S6-01 not GREEN yet; FallbackTier class not landed")` with a structured reason. Once the import succeeds, asserts via `inspect.signature(FallbackTier.run)`: (a) `run` is `async def` (via `asyncio.iscoroutinefunction`); (b) parameter `prior_attempts` exists, `kind is KEYWORD_ONLY`, default is `()` (truly the empty tuple — `param.default is ()` AND `type(param.default) is tuple`); (c) annotation type is `Sequence[AttemptSummary]` (use `typing.get_origin` + `typing.get_args` to confirm it's `collections.abc.Sequence` parameterized over `AttemptSummary`). The skip→fail-loud transition is the structural breadcrumb that S6-01 has landed.

### Replan-hook seam — identity preservation

- [ ] **AC-SEAM-1 (`ReplanHook` closure forwards `prior_attempts` by identity).** `tests/unit/orchestrator/test_replan_hook_seam_identity.py::test_closure_forwards_prior_attempts_kwarg_by_identity` builds the orchestrator's `make_orchestrator_replan_hook(fallback_tier=AsyncMock(spec=FallbackTier), ...)` closure (from S5-01), constructs a `ctx: GateContext` with `prior_attempts=(AttemptSummary(...), AttemptSummary(...))` (two-element tuple), `await`s `closure(ctx)`, then asserts (a) `fallback_tier.run.assert_awaited_once()`; (b) the call's `kwargs["prior_attempts"]` **is the same object** (`is`-identity) as `ctx.prior_attempts` (not a copy, not a rebuild); (c) the call's kwargs have the literal key `prior_attempts` (catches a `prior_attempt`/`priorAttempts`/`prior` typo). Skip-with-reason if `FallbackTier` cannot be imported (S6-01 not GREEN). Use `AsyncMock(spec=FallbackTier)` — the `spec=` is load-bearing: a renamed-method mutation on `FallbackTier` would `AttributeError` at construction rather than silently absorbing.
- [ ] **AC-SEAM-2 (`ReplanHook` closure honors empty-tuple equivalence).** Same test file `test_closure_empty_tuple_forwards_empty_tuple` builds `ctx` with `prior_attempts=()`, awaits the closure, asserts `kwargs["prior_attempts"] == ()` AND `type(kwargs["prior_attempts"]) is tuple`. Adversarial mutation: a closure that "normalizes" `()` to `[]` or omits the kwarg entirely fails this AC.

### Cross-cutting

- [ ] **AC-META-1 (kwarg-absent ≡ kwarg-empty-tuple).** `test_kwarg_absent_equivalent_to_empty_tuple` — when `FallbackTier` is importable, calls `inspect.signature(FallbackTier.run).bind(<positional args>)` and `inspect.signature(FallbackTier.run).bind(<positional args>, prior_attempts=())`; asserts `.arguments` differ only by the presence of the `prior_attempts` key, and that `Sequence[AttemptSummary]`'s default `()` is the value bound in the absent-kwarg case. Skip-with-reason if `FallbackTier` cannot be imported.
- [ ] **AC-PLAIN-PY-1 (no JSON-escape leakage in TDD source).** A meta-test `test_test_file_parses_cleanly` runs `ast.parse((TEST_ROOT / "schema" / "test_phase5_cross_phase_prior_attempts_contract.py").read_text())` (and the same on the seam-identity test) — asserts no `SyntaxError`. (The validator's recurring closure on JSON-escape leakage from prior stories.)
- [ ] **AC-NO-NEW-SRC (no production-code edits owed by this story).** `git diff --name-only HEAD~1 HEAD | grep '^src/codegenie/'` is empty for the commit that lands S5-03 (verified by the PR author in the description; not a CI test, but called out so the reviewer rejects a PR that smuggles `src/` edits into a conformance-fence story).
- [ ] **AC-NO-NEW-FENCE (no new `FenceWrapper.fence(...)` callsite).** A meta-check: `grep -rn "FenceWrapper().fence\|fence_wrapper.fence\|fence\.fence(" src/codegenie/` outside `src/codegenie/fallback/fence/prompt_builder.py` returns empty. Enforced as a docstring assertion in the PR description; Phase 4 S2-04's AC-13 AST-walking guard already enforces this in CI, so this AC is a verbal restatement to prevent the wrong instinct.
- [ ] **TDD plan's red test exists, is committed, and is green.**
- [ ] `ruff`, `mypy --strict src/codegenie/transforms src/codegenie/fallback`, `pytest tests/schema/test_phase5_cross_phase_prior_attempts_contract.py tests/unit/orchestrator/test_replan_hook_seam_identity.py` pass.

## Implementation outline

1. Create `tests/schema/test_phase5_cross_phase_prior_attempts_contract.py`. Each test is an introspection function — no production code in `src/codegenie/` is modified.
   - Group 1: Phase 3 shipped surface (AC-CONF-1, AC-IMP-1, AC-IMP-2, AC-IMP-3).
   - Group 2: Phase 4 shipped surface (AC-CONF-3, AC-CONF-3b, AC-CONF-4).
   - Group 3: Phase 4 awaiting-GREEN surface (AC-CONF-2) — `try-except ImportError → pytest.skip(...)` pattern with a structured skip reason that names S6-01.
   - Group 4: cross-cutting (AC-META-1, AC-PLAIN-PY-1).
2. Create `tests/unit/orchestrator/test_replan_hook_seam_identity.py` (or extend S5-01's existing test file if it lands first — coordinate with the executor reading both stories).
   - One test for identity-preserving forward (AC-SEAM-1).
   - One test for empty-tuple equivalence (AC-SEAM-2).
   - Both `try-except ImportError → pytest.skip(...)` on `FallbackTier`.
3. Run the test suite. Every AC must be GREEN-or-skipped-with-reason after the conformance tests land. No `xfail` — either the upstream surface is present (test passes) or the upstream surface is absent (test skips with reason naming the story that will ship it).
4. Update [`stories/S5-05-retry-recovers-integration.md`](S5-05-retry-recovers-integration.md) ONLY by appending one line in its Notes section: `Cross-story breadcrumb (from S5-03 validation): the regex assertion in this story is bound to the rejected helper and needs re-validation before execution.` Do NOT edit S5-05's ACs in this PR — that is the S5-05 validator pass's job.

**Explicitly NOT done by this story:**
- No edits to `src/codegenie/transforms/apply_context.py`.
- No edits to `src/codegenie/fallback/**`.
- No new `FenceWrapper.compose_prior_attempts` or any sibling helper.
- No new `tests/golden/prompts/*.txt` baseline file.
- No contract-snapshot regeneration on Phase 3 or Phase 4 (those regenerations happened — or will happen — at the *shipping* story for each side, per ADR-0002 § Consequences).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/schema/test_phase5_cross_phase_prior_attempts_contract.py`

```python
"""Phase-5-side cross-phase conformance fence for ADR-0002.

Pins the byte-stable surfaces of `ApplyContext.prior_attempts`,
`AttemptSummary`, the fence `SourceKind` Literal + `_TRUNCATION_CAPS`,
`PromptBuilder.build(prior_attempt_summary=...)`, and (when GREEN)
`FallbackTier.run`. A future rename anywhere in the upstream stack fails
THIS test first — loud, structured, and pre-integration.

See `docs/phases/05-sandbox-trust-gates/ADRs/0002-additive-prior-attempts-kwarg.md`.
"""
from __future__ import annotations

import ast
import inspect
import re
import secrets
import typing
from collections.abc import Sequence
from pathlib import Path

import pytest

# --- Group 1: Phase 3 shipped surface ---------------------------------------


def test_apply_context_prior_attempts_shape() -> None:
    from codegenie.transforms.apply_context import ApplyContext, AttemptSummary

    fields = ApplyContext.model_fields
    assert "prior_attempts" in fields, "ApplyContext must carry prior_attempts (ADR-0002)"

    ann = fields["prior_attempts"].annotation
    assert typing.get_origin(ann) is tuple
    args = typing.get_args(ann)
    assert args == (AttemptSummary, Ellipsis), f"expected tuple[AttemptSummary, ...], got {args!r}"

    default = fields["prior_attempts"].default
    assert default == ()
    assert type(default) is tuple


def test_attempt_summary_import_path_canonical() -> None:
    # Canonical path — must succeed.
    from codegenie.transforms.apply_context import AttemptSummary  # noqa: F401

    # Wrong path the draft of S5-03 used — must NOT exist.
    with pytest.raises(ModuleNotFoundError):
        __import__("codegenie.gates.contract", fromlist=["AttemptSummary"])


def test_attempt_summary_model_fields() -> None:
    from codegenie.transforms.apply_context import AttemptSummary

    expected = {"attempt", "failing_signals", "prior_failure_summary", "evidence_paths", "transform_id"}
    assert set(AttemptSummary.model_fields) == expected


def test_attempt_summary_storage_cap_raises() -> None:
    from codegenie.transforms.apply_context import AttemptSummary

    too_big = "x" * 8193  # one byte over 8 KiB
    with pytest.raises(ValueError, match="prior_failure_summary exceeds"):
        AttemptSummary(
            attempt=1,
            failing_signals=(),
            prior_failure_summary=too_big,
            evidence_paths=(),
            transform_id=None,
        )


# --- Group 2: Phase 4 shipped surface ---------------------------------------


def test_source_kind_contains_prior_attempt_summary() -> None:
    from codegenie.fallback.fence.wrapper import SourceKind

    members = typing.get_args(SourceKind)
    assert "prior_attempt_summary" in members
    # Adversarial near-misses.
    for typo in ("prior_attempts", "PRIOR_ATTEMPT_SUMMARY", "attempt_summary"):
        assert typo not in members


def test_render_cap_is_4kib() -> None:
    from codegenie.fallback.fence.wrapper import _TRUNCATION_CAPS

    assert _TRUNCATION_CAPS["prior_attempt_summary"] == 4 * 1024


def test_hex_nonce_pattern_is_32_lowercase() -> None:
    from codegenie.fallback.fence.wrapper import _default_nonce_source

    for _ in range(100):
        nonce = _default_nonce_source()
        assert re.fullmatch(r"^[0-9a-f]{32}$", nonce), nonce
        # Negative: the draft pattern (16 uppercase hex) must NEVER match.
        assert not re.fullmatch(r"^[A-F0-9]{16}$", nonce)


def test_prompt_builder_build_accepts_prior_attempt_summary() -> None:
    from codegenie.fallback.fence.prompt_builder import PromptBuilder

    sig = inspect.signature(PromptBuilder.build)
    assert "prior_attempt_summary" in sig.parameters
    param = sig.parameters["prior_attempt_summary"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is None
    # Annotation is `str | None` — get_args returns the two arms.
    arms = typing.get_args(param.annotation)
    assert str in arms and type(None) in arms


# --- Group 3: Phase 4 surface awaiting GREEN --------------------------------


def _import_fallback_tier_or_skip() -> type:
    try:
        from codegenie.fallback.tier import FallbackTier
    except ImportError:
        pytest.skip("Phase 4 S6-01 not GREEN yet; FallbackTier class not landed")
    return FallbackTier


def test_fallback_tier_run_signature_when_green() -> None:
    import asyncio

    FallbackTier = _import_fallback_tier_or_skip()
    assert asyncio.iscoroutinefunction(FallbackTier.run)

    from codegenie.transforms.apply_context import AttemptSummary

    sig = inspect.signature(FallbackTier.run)
    assert "prior_attempts" in sig.parameters
    param = sig.parameters["prior_attempts"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default == ()
    assert type(param.default) is tuple

    origin = typing.get_origin(param.annotation)
    args = typing.get_args(param.annotation)
    # Sequence[AttemptSummary] — Python normalizes the origin to
    # collections.abc.Sequence under PEP 585.
    from collections.abc import Sequence as AbcSequence
    assert origin is AbcSequence
    assert args == (AttemptSummary,)


def test_kwarg_absent_equivalent_to_empty_tuple_when_green() -> None:
    FallbackTier = _import_fallback_tier_or_skip()
    sig = inspect.signature(FallbackTier.run)
    # Binding works either way — that's the equivalence we are pinning.
    absent = sig.bind_partial()
    explicit = sig.bind_partial(prior_attempts=())
    # The default arrives via apply_defaults().
    absent.apply_defaults()
    explicit.apply_defaults()
    assert absent.arguments.get("prior_attempts") == ()
    assert explicit.arguments["prior_attempts"] == ()


# --- Group 4: cross-cutting -------------------------------------------------


def test_this_file_parses_cleanly() -> None:
    # Catches the recurring JSON-escape leakage regression (\"...\" instead of "...").
    here = Path(__file__).read_text()
    ast.parse(here)


def test_seam_identity_test_file_parses_cleanly() -> None:
    here = Path(__file__).parent.parent / "unit" / "orchestrator" / "test_replan_hook_seam_identity.py"
    if not here.exists():
        pytest.skip(f"{here} not yet created")
    ast.parse(here.read_text())
```

Test file path: `tests/unit/orchestrator/test_replan_hook_seam_identity.py`

```python
"""Phase-5-side seam test — ReplanHook closure forwards prior_attempts by identity.

Pins: kwarg name + object identity at the orchestrator → FallbackTier seam.
A regression that rebuilds the tuple (`prior_attempts=tuple(ctx.prior_attempts)`)
or renames the kwarg (`prior_attempt`/`priorAttempts`) fails LOUD.

See `docs/phases/05-sandbox-trust-gates/ADRs/0002-additive-prior-attempts-kwarg.md`.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


def _import_fallback_tier_or_skip() -> type:
    try:
        from codegenie.fallback.tier import FallbackTier
    except ImportError:
        pytest.skip("Phase 4 S6-01 not GREEN yet; FallbackTier class not landed")
    return FallbackTier


def _make_attempt_summary(n: int) -> object:
    from codegenie.transforms.apply_context import AttemptSummary

    return AttemptSummary(
        attempt=n,
        failing_signals=(),
        prior_failure_summary=f"attempt {n} failure",
        evidence_paths=(),
        transform_id=None,
    )


async def test_closure_forwards_prior_attempts_kwarg_by_identity() -> None:
    FallbackTier = _import_fallback_tier_or_skip()
    from codegenie.orchestrator.replan_hook import make_orchestrator_replan_hook
    from codegenie.gates.contract import GateContext  # S1-04 surface

    fallback = AsyncMock(spec=FallbackTier)
    fallback.run.return_value = object()  # opaque RecipeApplication stand-in

    closure = make_orchestrator_replan_hook(fallback_tier=fallback)

    summaries = (_make_attempt_summary(1), _make_attempt_summary(2))
    ctx = GateContext(prior_attempts=summaries)  # remainder of fields default

    await closure(ctx)

    fallback.run.assert_awaited_once()
    _, kwargs = fallback.run.await_args
    assert "prior_attempts" in kwargs, "kwarg must be named exactly prior_attempts"
    assert kwargs["prior_attempts"] is summaries, "closure must forward by identity, not rebuild"


async def test_closure_empty_tuple_forwards_empty_tuple() -> None:
    FallbackTier = _import_fallback_tier_or_skip()
    from codegenie.orchestrator.replan_hook import make_orchestrator_replan_hook
    from codegenie.gates.contract import GateContext

    fallback = AsyncMock(spec=FallbackTier)
    fallback.run.return_value = object()
    closure = make_orchestrator_replan_hook(fallback_tier=fallback)

    ctx = GateContext(prior_attempts=())
    await closure(ctx)

    _, kwargs = fallback.run.await_args
    assert kwargs["prior_attempts"] == ()
    assert type(kwargs["prior_attempts"]) is tuple
```

### Green — make it pass

- The Phase-3 group (AC-CONF-1, AC-IMP-1, AC-IMP-2, AC-IMP-3) **passes immediately** — the upstream surface is shipped.
- The Phase-4 GREEN group (AC-CONF-3, AC-CONF-3b, AC-CONF-4) **passes immediately** — Phase 4 S2-02/S2-04 shipped GREEN.
- The Phase-4 HARDENED-pending-GREEN group (AC-CONF-2, AC-META-1) **skips with structured reasons** until S6-01 lands GREEN.
- The seam-identity group (AC-SEAM-1, AC-SEAM-2) **skips with structured reasons** until S5-01 + S6-01 land their concrete surfaces (`make_orchestrator_replan_hook`, `FallbackTier`).
- The cross-cutting meta-tests (AC-PLAIN-PY-1) pass immediately.

No production-code change in `src/codegenie/` is required to reach green.

### Refactor — clean up

- Extract `_import_fallback_tier_or_skip()` into a `tests/_helpers/upstream_skip.py` module if a future story needs the same skip-with-reason pattern (rule of three: not yet — keep it local).
- Verify the `try-except ImportError → pytest.skip(...)` skip reasons name the upstream story precisely (S6-01 for `FallbackTier`, S5-01 for `make_orchestrator_replan_hook`) so a future maintainer can find the un-skip dependency in one grep.
- Add a one-line docstring on each test linking to ADR-0002 (already in the file-level docstring; per-test linking is overkill).

## Files to touch

| Path | Why |
|---|---|
| `tests/schema/test_phase5_cross_phase_prior_attempts_contract.py` | **New file.** All conformance ACs. Introspection-only — no production-code imports beyond the inspected symbols. |
| `tests/unit/orchestrator/test_replan_hook_seam_identity.py` | **New file** (or extension of S5-01's test file if it lands first). Seam-identity ACs. |
| `docs/phases/05-sandbox-trust-gates/stories/S5-05-retry-recovers-integration.md` | One-line Notes append: cross-story breadcrumb that the `<BEGIN_PRIOR_ATTEMPT_...>` regex needs re-validation. **Do NOT touch S5-05's ACs in this PR.** |

**Not touched** (explicitly): `src/codegenie/transforms/apply_context.py`, `src/codegenie/fallback/**`, `src/codegenie/orchestrator/**`, any `tests/golden/prompts/*.txt`, any contract-snapshot file.

## Out of scope

- `GateRunner` loop body — S5-02.
- Concrete orchestrator `make_orchestrator_replan_hook` factory — S5-01.
- End-to-end retry-recovers integration with cassette — S5-05.
- Phase 4 model-call retry/timeout policy — Phase 4's own concern.
- Phase 6 reducer for `prior_attempts` (LangGraph `operator.add`) — Phase 6.
- **Building a `FenceWrapper.compose_prior_attempts` helper** — explicitly *rejected* by this validation: it would (a) violate the polymorphism-by-data Strategy via `_TRUNCATION_CAPS`; (b) violate the functional-core / imperative-shell separation; (c) be rejected at CI by S2-04 AC-13's AST-walking sole-fence-call-site guard; (d) fork the delimiter format (`<BEGIN_PRIOR_ATTEMPT_>` ≠ shipped `<UNTRUSTED_INPUT id=>`); (e) use the wrong canary width (16 upper hex ≠ shipped 32 lower hex `HexNonce`).
- Adding `prior_attempts` to `ApplyContext` — already shipped Phase 3 S1-04 GREEN.
- Adding `prior_attempts` kwarg to `FallbackTier.run` — already pinned Phase 4 S6-01 HARDENED.
- Wiring the prompt-builder reduction (`prior_attempts[-1].prior_failure_summary` → `PromptBuilder.build`) — already pinned Phase 4 S6-02 HARDENED.
- Contract-snapshot regenerations on Phase 3 or Phase 4 sides — owned by the shipping story for each side, not by S5-03.
- Regenerating any baseline golden file — the "byte-identical with empty kwarg" property is trivially true for an additive default-empty kwarg; the existing Phase 4 S6-07 byte-identical replay property test covers the meaningful property.

## Notes for the implementer

### The canonical reduction path (do NOT re-implement)

Phase 4 S6-02 HARDENED locked the cross-phase reduction. When `bool(prior_attempts) is True` inside `FallbackTier.run`:

1. Skip RAG retrieval entirely (the deterministic-RAG-on-same-inputs failure mode).
2. Emit `RagSkippedOnRetry(last_attempt_number=prior_attempts[-1].attempt, attempt_count=len(prior_attempts), last_failing_signals=prior_attempts[-1].failing_signals)`.
3. Pass `prior_attempts[-1].prior_failure_summary` (raw `str`, already capped at 8 KiB at `AttemptSummary` model-validate time) into `PromptBuilder.build(prior_attempt_summary=...)`.
4. `PromptBuilder.build` calls `FenceWrapper.fence(payload, source_kind="prior_attempt_summary")` — `fence_pure` truncates codepoint-safely at 4 KiB, the scanner detects injection patterns + per-nonce delimiter collisions, the imperative shell emits `FenceApplied` and (on collision) `CanaryCollisionEvent` audit events.
5. The fenced block lands inside the larger `FencedPromptBody` newtype the LLM consumes.

Phase 5's only "writing" responsibility at this seam is producing `AttemptSummary` values via the `RetryLedger` (S2-01) and feeding them through `ApplyContext.prior_attempts` into the orchestrator's `ReplanHook` closure. The closure forwards them by identity into `FallbackTier.run(prior_attempts=...)`. That's the whole flow.

### Why a helper would be rejected

A `FenceWrapper.compose_prior_attempts` static method or sibling helper would:

1. **Fork the polymorphism-by-data Strategy.** The kernel dispatches on `source_kind: Literal[...]` via `_TRUNCATION_CAPS[source_kind]`. Adding a new "fence purpose" must be one `Literal` member + one `_TRUNCATION_CAPS` row — never a new method. The Open/Closed Principle is the load-bearing invariant; a sibling helper violates it.
2. **Violate the functional-core / imperative-shell separation.** `fence_pure` is the pure core (stdlib + Pydantic, no I/O, no events); `FenceWrapper.fence` is the imperative shell that mints `HexNonce` and emits `FenceApplied` / `CanaryCollisionEvent`. A helper that mints canaries internally would either bypass audit emission (no `FenceApplied` event — auditability broken) or duplicate the shell (two minting sites — drift inevitable).
3. **Be rejected by CI.** Phase 4 S2-04 AC-13 enforces "`PromptBuilder` is the sole fence-call site" via an AST-walking guard at `tests/unit/fallback/test_prompt_builder_no_fence_bypass.py`. A new helper outside `prompt_builder.py` would fail that test on PR.
4. **Violate the `HexNonce` newtype.** The shipped nonce is `secrets.token_hex(16)` → 32 lowercase hex chars matching `^[0-9a-f]{32}$`. The original draft prescribed `secrets.token_hex(8).upper()` → 16 uppercase hex chars. Two patterns. Rule 7 ("surface conflicts, don't average them") — pick the shipped one.

### Skip-with-reason discipline

Every conformance assertion that depends on Phase 4 S6-01 GREEN uses `try-except ImportError → pytest.skip(<structured reason>)`. The skip reason MUST name the upstream story (e.g., `"Phase 4 S6-01 not GREEN yet; FallbackTier class not landed"`). When S6-01 lands GREEN, the import succeeds and the skip flips to a hard assertion automatically — no manual edit needed. This is the structural breadcrumb pattern the rest of Phase 5's conformance tests should mirror.

### The S5-05 follow-up

S5-05 asserts `re.search(r"<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>", text)` in the Phase 4 prompt. That regex is bound to the rejected helper this story refused to build. The correct assertion (once S5-05 is re-validated) is:

```python
# Structural check — preferred:
assert "prior_attempt_summary" in events_by_kind["PromptAssembled"].source_kinds_used

# Regex backup, if a textual assertion is unavoidable:
assert re.search(r"<UNTRUSTED_INPUT id=[0-9a-f]{32}>", text)
```

This story does NOT edit S5-05's ACs — it only appends the one-line breadcrumb pointing the next validator pass at the dependency. The S5-05 validation pass (when it runs) should fold this in.

### `Sequence` vs `tuple` annotation choice

ADR-0002 § Decision originally read `list[AttemptSummary] = []`. Phase 3 S1-04 (GREEN) chose `tuple[AttemptSummary, ...] = ()` for true immutability. Phase 4 S6-01 (HARDENED) chose `Sequence[AttemptSummary] = ()` for read-covariance (so `list` and `tuple` callers both typecheck). Both choices are sound; both are immutable-default-safe. Neither contradicts ADR-0002 — the ADR text predates the implementation discussions that drove the type refinement; the **decision** (additive kwarg, default-empty, Phase 5 owns `AttemptSummary` data, Phase 4 owns prompt-thread) is intact. Surface this nuance in any future ADR amendment if a Phase 8+ consumer reads the ADR text in isolation.

### Coordinate with the executor on file co-location

If S5-01's executor pass lands `tests/unit/orchestrator/test_replan_hook_seam_identity.py` first (containing different tests for the closure), this story's AC-SEAM-1 + AC-SEAM-2 should be added as new test functions in that file rather than a new file — read the file before creating it. Conversely, if this story lands first, S5-01 picks up the existing file and adds its own tests there.
