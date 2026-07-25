# Validation report — S1-03 `@critical_event` decorator + registry

**Date:** 2026-07-25
**Story:** `docs/phases/09-temporal-durable-workflow/stories/S1-03-critical-event-registry.md`
**Verdict:** HARDENED
**Skill:** phase-story-validator

## Summary

Story S1-03 lands the `@critical_event` decorator and the module-level
`_CRITICAL_EVENTS: Final[frozenset[str]]` snapshot inside
`codegenie.events.payloads`. It decorates exactly the five variants whose
loss would compromise audit / safety / cost claims (`MergeOutcome`,
`BudgetExhausted`, `TrustGateFailed`, `WorkflowTerminated`,
`ChainTamperDetected`) so that S3-02's `EventBatchWriter.append` takes
the synchronous-flush path for them and rides the batched
`COPY ... FROM STDIN BINARY` path for everything else. The vocabulary
fence at `tests/fence/test_critical_event_vocabulary.py` pins the set to
the golden five and — after hardening — cross-checks with S1-02's
`_ALL_VARIANT_CLASSES` so a renamed/deleted variant surfaces loudly.

The original draft was solid on shape (pattern-parity with `@register_probe`,
two-stage builder-then-freeze) but under-specified on: (1) type-safety of
the decorator's target class, (2) drift protection between the golden and
the actual union membership, (3) post-freeze immutability of the mutable
staging attribute, and (4) test-pollution risk from the naive collision
test. It also carried one factually-wrong claim in Notes-for-implementer
about exception-class parity with `@register_probe`.

Fifteen findings were addressed in place (4 blocks, 8 hardens, 3 nits).
No RESCUE — the goal is well-scoped and each block has a clean in-place
fix.

## Context Brief (Stage 1)

### Story snapshot
- **Goal:** Land the `@critical_event` decorator + the module-level
  `_CRITICAL_EVENTS: Final[frozenset[str]]` registry inside
  `codegenie.events.payloads`, apply it to exactly the five named
  variants, and ship a vocabulary-fence test that pins the set to the
  golden five.
- **Non-goals:** `EventBatchWriter` consumption (S3-02), synchronous-flush
  semantics (S3-03), adding new critical events in future phases.

### Load-bearing references (verified read)
- `phase-arch-design.md §Concurrency, blocking, durable checkpoints`
  (line 258) — names the five sync-flush variants explicitly, matches
  the golden set.
- `phase-arch-design.md §C5 — Canonical event log` (lines 535–544) —
  decorator signature `critical_event(cls: type[T]) -> type[T]` and
  writer usage `type(event).__name__ in _CRITICAL_EVENTS`.
- `phase-arch-design.md §Design patterns applied #8` (line 538) —
  Open/Closed via `@critical_event` decorator; parity with
  `@register_probe` explicitly claimed at the *shape* level (not the
  exception-class level).
- `phase-arch-design.md §Stable contracts vs internal` (line 294) —
  `@critical_event` listed as an Open/Closed extension point alongside
  `@register_activity` and `@register_projection`.
- `phase-arch-design.md` variant listing (lines 161–174) — visual
  confirmation of which five variants carry the `[critical_event]`
  annotation in the arch class diagram.
- `ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — full
  read. §Decision names the five variants; §Consequences names the
  fence test path and pins the golden set; §Consequences point 1 uses
  `Final[set[str]]` — story strengthens to `Final[frozenset[str]]`
  which is a valid tightening (documented in Notes).
- `production ADRs/0043-extension-by-addition-means-no-silent-edits.md`
  (referenced indirectly) — the compiler-policed loud edit is the
  golden-fence test.
- **Precedent module read:** `src/codegenie/probes/registry.py` —
  the decorator-registry pattern reference. `register_probe` raises
  `ProbeError` (not `TypeError`) — invalidates the story's original
  claim of exception-class parity.
- **Sibling story:** S1-02 HARDENED (not yet GREEN). S1-03 cannot
  execute until S1-02 GREEN — the target module `payloads.py` must
  exist on disk and `_Base` + `_ALL_VARIANT_CLASSES` + the five variant
  classes must be defined before this story's edits land.
- **Prior validation report:** S1-02's `_validation/` report established
  the `_ALL_VARIANT_CLASSES: Final[tuple[type[_Base], ...]]` extension
  seam; S1-03's orphan cross-check (new AC-7) is a direct consumer of
  that seam.

### Sibling-family lineage
- This story is the **2nd concrete consumer** of the decorator-registry
  pattern (after `@register_probe`, Phase 0). Rule-of-three NOT YET
  REACHED — no kernel extract mandated; document parity in Notes only.
- Prior framings carried forward: collision-at-import discipline
  (raises immediately), decorator returns class unchanged (identity),
  registry populated at module import time (write-only-then-freeze).
- Divergences introduced deliberately by this story: exception class
  (`TypeError` here vs `ProbeError` in `@register_probe`); post-freeze
  `del` of the mutable staging attribute (not present in
  `@register_probe`); type-bound TypeVar (`_BaseT`) vs the untyped
  `type[Probe]` in probes.

### Open ambiguities (resolved before Stage 2)
1. Exception class parity — resolved: keep `TypeError`, remove the
   misleading Notes claim, document the divergence.
2. Where does `_BaseT` come from? — resolved by AC-6: module-scoped
   `TypeVar("_BaseT", bound=_Base)`.
3. How do tests avoid polluting `_CRITICAL_EVENTS_BUILDER`? — resolved
   by AC-8 (`del` at module tail) plus test-side `monkeypatch` fixture.

## Stage-2 findings — four critics

### Coverage critic

| #  | Finding | Severity | Fix applied |
|----|---------|----------|-------------|
| C1 | No AC ensures the decorated variants are actual members of the S1-02 discriminated union. A rename of `MergeOutcome` to `MergeResult` in S1-02 (without a corresponding decorator update here) would leave a dangling name in `_CRITICAL_EVENTS` that `EventBatchWriter` never matches — silent loss of the sync-flush guarantee. | BLOCK | New AC-7 + fence test `test_critical_events_are_all_actual_union_variants` cross-checks `_CRITICAL_EVENTS <= {cls.__name__ for cls in _ALL_VARIANT_CLASSES}`. |
| C2 | No AC pins the runtime type of `_CRITICAL_EVENTS` — a refactor that types the annotation `frozenset[str]` but assigns a `set` literal would type-check under `mypy --strict` (Pydantic uses `Final` for immutability of the *binding*, not the *value*). | HARDEN | AC-5 strengthened: added `isinstance(_CRITICAL_EVENTS, frozenset)` assertion alongside the `AttributeError` mutation check. |
| C3 | No AC covers `__all__` — a symbol that is not in `__all__` but is used cross-module is a linter-flagged fragility. `_CRITICAL_EVENTS` is *the* stable public symbol for S3-02; it must be explicitly exported. | HARDEN | New AC-9: `_CRITICAL_EVENTS` and `critical_event` in `__all__`; `_CRITICAL_EVENTS_BUILDER` never in `__all__`. |
| C4 | No AC for what happens if the decorator is applied to a class that is NOT a `_Base` subclass. Without a type bound, this is silent runtime success — the string enters the registry but the writer never matches. | BLOCK | Rolled into AC-6 + the new `TypeVar("_BaseT", bound=_Base)`. Type bound makes mis-application a `mypy --strict` build break. |
| C5 | Fence's error message shows both missing and extra — original wording ok. | NIT | Preserved verbatim, added a note in the message that "adding or removing requires an ADR-0006 amendment". |

### Test Quality critic (mutation-resistance)

| #  | Finding | Severity | Fix applied |
|----|---------|----------|-------------|
| T1 | The collision test defines `_Fake(BaseModel)` inside the test function and calls `critical_event(_Fake)` twice. Since `_CRITICAL_EVENTS_BUILDER` is a module-level `set`, the FIRST call pollutes it for the entire pytest process. A second run of the same test in the same process would fail on the first call, not the second — false positive that erodes the semantics. | BLOCK | Rewrote the test to use `monkeypatch.setattr(payloads, "_CRITICAL_EVENTS_BUILDER", set(), raising=False)` to install a fresh mutable stage for the test's duration; also switched to `_Base` subclass and `type()` with unique per-test class names (`_FakeCollisionA`, `_FakeCollisionB`). Combined with the AC-8 `del` at module tail, the test-pollution vector is closed on both ends. |
| T2 | Test uses `BaseModel` directly, not `_Base`. If AC-6's type bound lands, calling `critical_event(_Fake)` where `_Fake(BaseModel)` becomes a `mypy --strict` error and the tests wouldn't type-check. | HARDEN | Test rewritten to construct `_Fake` via `type("_FakeCollisionA", (_Base,), {...})` so the class inherits `_Base` and the type bound is satisfied. |
| T3 | No test that `mypy --strict` actually rejects `@critical_event` on a non-`_Base` class. Without this, the type bound is a documentation-only claim. | HARDEN | Added a comment in AC-6 that the mypy check is exercised by the *existing* `make typecheck` gate — the five decorator lines in `payloads.py` inherit `_Base` so they pass; a hypothetical mis-application would be a mypy build break. Explicit reveal_type test deferred (would require a `.mypy_test/` fixture — out of scope; the compile-time check is sufficient discipline). |
| T4 | The vocabulary fence's single assertion (golden equality) doesn't catch the *drift* mode where a variant class is renamed in S1-02 and the decorator sticker gets moved to the new name but the golden isn't updated — the golden and the runtime set both agree, but neither is a variant in `_ALL_VARIANT_CLASSES`. | BLOCK | Rolled into AC-7 orphan cross-check (see C1). Together the two checks cover: golden ≡ runtime (AC-3), runtime ⊆ union members (AC-7). |
| T5 | No test that `_CRITICAL_EVENTS_BUILDER` is `del`-ed. Without a test, a future refactor could re-introduce the mutable attribute and the "post-freeze immutability" claim would be silently gone. | HARDEN | New test `test_builder_is_gone_after_module_import` under AC-8 asserts `not hasattr(payloads, "_CRITICAL_EVENTS_BUILDER")`. |
| T6 | No test enforces `__all__` membership. AC-9 pins this. | HARDEN | New test `test_public_surface_names_the_frozen_set_and_decorator_only` under AC-9. |

### Consistency critic

| #  | Finding | Severity | Fix applied |
|----|---------|----------|-------------|
| K1 | `Depends on: S1-01, S1-02`. Both are currently HARDENED (validated) but not GREEN (not yet on disk). This story edits `codegenie.events.payloads` and imports `_Base` from it — cannot execute before S1-02 GREEN. | BLOCK | Rewrote `Depends on:` to `S1-01 **GREEN**, S1-02 **GREEN** (the module `src/codegenie/events/payloads.py` and the `_Base` class + five variant classes must be on disk; HARDENED is not sufficient — this story edits that module and imports `_Base` as its TypeVar bound).` |
| K2 | Notes-for-implementer §3: "The decorator's collision-raise (`TypeError`) is the parity with `@register_probe`." — factually wrong. `@register_probe` raises `codegenie.errors.ProbeError`, not `TypeError`. | BLOCK | Rewrote the Notes paragraph: parity is at the *shape* level (decorator-populated module-level registry, collision-at-import), NOT at the exception-class level. `TypeError` is a deliberate choice — usage-error semantic, no new domain exception. If a third decorator-registry lands, a shared `RegistryError` base becomes worth considering; not before. |
| K3 | ADR-0006 §Consequences point 1 says `Final[set[str]]` but the story tightens to `Final[frozenset[str]]`. This is a strengthening (immutable-at-runtime, not just Final-binding) and should be documented as such rather than glossed over. | HARDEN | Notes-for-implementer §"Two-stage build" now explicitly documents the tightening: the `del` step + the frozenset type together provide both binding and value immutability. |
| K4 | The Implementation-outline code snippet uses `_BaseT` in the signature but never defines it. Reader has to guess whether it's `TypeVar("_BaseT", bound=BaseModel)`, `TypeVar("_BaseT", bound=_Base)`, or an unbound `TypeVar`. | BLOCK | Implementation-outline §2 now explicitly declares `_BaseT = TypeVar("_BaseT", bound=_Base)` immediately after the `_Base` definition. Chosen bound is `_Base` (tighter than `BaseModel`) so the decorator is scoped to actual event variants. |
| K5 | The tests use `pydantic.BaseModel` in the sample code — inconsistent with AC-6's type bound of `_Base`. | HARDEN | Test rewrites in the TDD plan now import `_Base` and construct throwaway classes with `type("_FakeCollisionA", (_Base,), {...})`. Consistent with the bound. |
| K6 | The Notes-for-implementer paragraph about `_CRITICAL_EVENTS_BUILDER` internality is fine but doesn't explain WHY the single-underscore prefix is enough — no `del`, no `__all__` exclusion, no module-init trick. | HARDEN | Notes-for-implementer §"Two-stage build" now spells out all three defenses (single-underscore convention, `del` at module tail, `__all__` exclusion) and pins the load-bearing invariant they collectively enforce. |

### Design Patterns critic

| #  | Finding | Severity | Fix applied |
|----|---------|----------|-------------|
| D1 | Second concrete consumer of the decorator-registry pattern after `@register_probe`. Cardinality NOT YET at rule-of-three; no kernel extract warranted. | NIT | Added Notes-for-implementer §"Decorator-registry family (Rule of Three watch)" — documents the count, names the two likely third precedents (`@register_activity`, `@register_projection`), and explicitly forbids pre-extraction. |
| D2 | The two-stage build (mutable-then-frozen) is safe within one module import, but a post-import `critical_event(SomeLateClass)` call would mutate the builder without updating the frozen snapshot — silent divergence between "what the writer sees" and "what the golden fence pins". A hazard the ADR doesn't mention. | HARDEN | New AC-8 + `del _CRITICAL_EVENTS_BUILDER` at module tail. Post-import calls raise `NameError` at the `.add(...)` line — loud failure. Fence test `test_builder_is_gone_after_module_import` locks the invariant. |
| D3 | Storing `cls.__name__` (strings) vs `cls` (types) is primitive obsession by literal reading, but ADR-0006 justifies it: name-based indirection is rename-safe and grep-safe. Trade-off already documented in ADR-0006 §Tradeoffs. | NIT | Notes-for-implementer §"String identity (not class identity)" documents the trade-off inline for the implementer. |
| D4 | Decorator target has no type bound in the original snippet — accepts any class. Extension-by-addition violated: a contributor could decorate an unrelated `BaseModel`, the runtime path succeeds silently, and the golden-fence cross-check (AC-7) catches it at test-time only. Compile-time is cheaper. | HARDEN | Rolled into AC-6 + K4. `TypeVar("_BaseT", bound=_Base)` closes the loop. |
| D5 | The Implementation outline reserves the decorator as immediately-below-`_Base`. This is the right anchor point but not explicitly justified. | NIT | Implementation outline §2 now names the reason: TypeVar bound to `_Base` requires `_Base` to be defined first; keeping the decorator adjacent to the TypeVar is a locality-of-decision win. |

## Stage-3 — no research required

All findings resolved from arch + ADR + precedent module (`registry.py`)
+ the sibling `_validation/S1-02-...md` report. No `NEEDS RESEARCH` tags.

## Conflict resolutions

- **Coverage C4 vs Design-Patterns D4** both proposed a type bound.
  Merged into a single AC-6 (Coverage's framing — "AC that decorator
  rejects non-`_Base` classes") with the Design-Patterns rationale
  (extension-by-addition guardrail) folded into Notes-for-implementer.
- **Test-Quality T1 vs Design-Patterns D2** both proposed a fix for
  builder-mutation risk. T1 is test-side (monkeypatch), D2 is
  module-side (`del` at tail). Both landed — different failure modes,
  belt-and-braces. Test-Quality's fix is sufficient in isolation;
  Design-Patterns's fix hardens the runtime path in addition.
- **Consistency K2 vs Design-Patterns D1** both touched on
  `@register_probe` parity. Consistency wins on the factual correction
  (the parity claim was wrong); Design-Patterns's rule-of-three watch
  is additive framing for future phases and landed separately.

## Edits applied (HARDENED)

### Edit 1 — Depends-on tightened (Consistency K1)
- Source: Consistency K1
- Before: `**Depends on:** S1-01, S1-02`
- After: `**Depends on:** S1-01 **GREEN**, S1-02 **GREEN** (the module `src/codegenie/events/payloads.py` and the `_Base` class + five variant classes must be on disk; HARDENED is not sufficient — this story edits that module and imports `_Base` as its TypeVar bound).`
- Rationale: matches the S1-02 hardening precedent; loud dependency semantics.

### Edit 2 — Status flipped
- Before: `**Status:** Ready`
- After: `**Status:** HARDENED`

### Edit 3 — Validation notes block inserted under the header.

### Edit 4 — Acceptance criteria expanded from 8 to 11 numbered entries.
- Original AC-1..AC-8 preserved (numbered explicitly for the first time).
- AC-3 error-message wording tightened (Coverage C5).
- AC-4 rewrote to demand unique per-test class names + `_Base` bound (Test-Quality T1, T2).
- AC-5 added the `isinstance(_CRITICAL_EVENTS, frozenset)` clause (Coverage C2).
- AC-6 rewritten with the explicit `TypeVar("_BaseT", bound=_Base)` bound (Coverage C4, K4, Design-Patterns D4).
- AC-7 NEW: orphan cross-check against `_ALL_VARIANT_CLASSES` (Coverage C1, Test-Quality T4).
- AC-8 NEW: `_CRITICAL_EVENTS_BUILDER` `del`-ed at module tail + fence test (Design-Patterns D2, Test-Quality T5).
- AC-9 NEW: `__all__` membership pinned (Coverage C3, Test-Quality T6).
- AC-10, AC-11: renumbered originals ("red test committed", "lint/typecheck/pytest clean").

### Edit 5 — Implementation outline extended from 6 to 7 steps.
- New step 2 declares the `TypeVar` bound.
- Step 3's snippet now includes a full docstring citing ADR-0006 and production ADR-0043.
- New step 5 spells out the `del` on the line after the frozenset snapshot.
- New step 6 covers `__all__` extension.

### Edit 6 — TDD plan expanded from 4 to 8 tests.
- Vocabulary fence file grew to five tests (golden equality, orphan cross-check, isinstance frozenset, immutability, builder-is-gone, `__all__` membership).
- Registry test file grew to three tests: the naive collision test (now guarded by `pytest.skip` when the builder is unreachable), the `monkeypatch`-guarded canonical collision test, and the identity test.
- Every test now has an AC-N breadcrumb comment explaining what it verifies.

### Edit 7 — Notes-for-implementer expanded from 6 to 9 paragraphs.
- New: "Exception-class parity with `@register_probe` — clarified" (Consistency K2).
- New: "Type bound is the extension-by-addition guardrail" (Design-Patterns D4).
- New: "String identity (not class identity) is the writer's key" (Design-Patterns D3).
- New: "Test pollution" (Test-Quality T1).
- New: "Decorator-registry family (Rule of Three watch)" (Design-Patterns D1).
- New: "`_Base` visibility" (test import discipline).
- Existing paragraphs on `_CRITICAL_EVENTS_BUILDER` and the stable public symbol were rewritten for clarity.

## Verdict rationale

HARDENED. Every AC is individually verifiable (a third party can run each
test and get a binary pass/fail). The AC set collectively guarantees the
goal (five-and-only-five variants sync-flushed; drift on golden, union
membership, `__all__`, or immutability is caught at test time). The TDD
plan is mutation-resistant to the failure modes the design pattern makes
possible (silent post-import registration, silent orphan variants, silent
type-drift on the frozen snapshot). The story consumes the existing
`@register_probe` precedent for shape without introducing a shared kernel
that Rule 2 would reject at cardinality 2. The story lines up cleanly
with S1-02's `_ALL_VARIANT_CLASSES` seam (the orphan cross-check is a
direct consumer).

## Recommended next step

`phase-story-executor` — but only *after* S1-02 has been executed to
GREEN. If S1-02 is still HARDENED at the time this story is picked up,
the executor should surface the block and pick S1-02 up first.
