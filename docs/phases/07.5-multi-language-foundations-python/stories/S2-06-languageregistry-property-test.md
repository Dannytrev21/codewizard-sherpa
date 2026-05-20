# Story S2-06 — `LanguageRegistry` Hypothesis property test

**Step:** Step 2 — Land the `register_language` / `validate_pack` kernel and `LanguageRegistry`
**Status:** Ready
**Effort:** S
**Depends on:** S2-01
**ADRs honored:** ADR-0002

## Context
`LanguageRegistry.all()` must be deterministically sorted (golden files in S7-04 depend on the ordering) and `get` must round-trip every registered pack. Example tests cover the two-pack case; this story adds the one targeted Hypothesis property — for *any* sequence of distinct packs, `all()` is sorted and `get(p.language) == p` for every registered `p` — so the invariant holds beyond the hand-picked cases.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Testing strategy — Property tests` — "One property over `LanguageRegistry` (Hypothesis): for any sequence of distinct packs, `all()` returns them sorted *and* `get(p.language) == p` for every registered `p`. Modest and targeted."
- **Architecture:** `../phase-arch-design.md §Component design — LanguageRegistry + default_language_registry` — `all()` is sorted by `Language` for determinism; `get` raises on absence.
- **Architecture:** `../phase-arch-design.md §Harness engineering — Idempotence` — "`LanguageRegistry.all()` is sorted — deterministic across processes."
- **Phase ADRs:** `../ADRs/0002-register-language-validate-all-then-commit-no-unregister.md` — ADR-0002 — the registry semantics the property pins.
- **Existing code:** `src/codegenie/languages/registry.py` — `LanguageRegistry` (S2-01) — the subject under test.
- **Existing code:** existing Hypothesis tests under `tests/` (search `import hypothesis`) — match the project's `@given` / strategy-construction conventions.

## Goal
Add a Hypothesis property test asserting that for any sequence of distinct-`Language` packs registered into a fresh `LanguageRegistry`, `all()` is sorted by `Language` and `get(p.language) == p` holds for every registered pack.

## Acceptance criteria
- [ ] The property test in `tests/unit/languages/test_language_registry_property.py` exists, is committed, and was observed failing (or correctly green only after S2-01) — confirm it exercises real generated input, not a degenerate single case.
- [ ] A Hypothesis strategy generates sequences of `LanguagePack` values with **distinct** `Language` keys (de-duplicated by `Language` so no duplicate-registration raise occurs).
- [ ] The property asserts `registry.all()` equals the input packs sorted by `Language`.
- [ ] The property asserts `registry.get(p.language) == p` for every registered `p`.
- [ ] Each generated case uses a **fresh** `LanguageRegistry()` instance — the global `default_language_registry` is never touched.
- [ ] The test runs inside `make check`'s wall-clock envelope (a modest `max_examples` — no over-investment).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/languages/test_language_registry_property.py` pass on touched files.
- [ ] Story `**Status:**` set to `Done`.

## Implementation outline
1. Create `tests/unit/languages/test_language_registry_property.py`.
2. Build a Hypothesis strategy for `LanguagePack` values — either a small `@composite` strategy or a fixed pool of stub packs sampled without replacement; the key requirement is **distinct `Language` keys** per generated sequence.
3. `@given(packs=<that strategy>)` — construct a fresh `LanguageRegistry()`, register each pack, then assert: (a) `all()` == `sorted(packs, key=...)`; (b) `get(p.language) == p` for every `p`.
4. Cap `max_examples` modestly (the arch calls the property "modest and targeted" — do not over-invest).
5. Keep the stub-pack construction minimal — these packs need only valid `LanguagePack` fields, not real probes/strategies (this test exercises the registry, not `validate_pack`).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_language_registry_property.py`.

```python
from hypothesis import given

# test_all_sorted_and_get_round_trips_for_any_distinct_pack_sequence
#   @given(packs = a strategy of LanguagePack lists with distinct Language keys)
#   arrange: reg = LanguageRegistry()
#   act:     for p in packs: reg.register(p)
#   assert:  reg.all() == tuple(sorted(packs, key=lambda p: p.language))
#   assert:  all(reg.get(p.language) == p for p in packs)
```

If written before S2-01 it fails with `ImportError`. With S2-01 present, confirm the property genuinely exercises generated sequences (temporarily break the `all()` sort to watch it fail, then revert) so it is not a vacuous green.

### Green — make it pass
With `LanguageRegistry` from S2-01 already correct, the property passes once the strategy and assertions are written. If it fails, the bug is in S2-01's `all()` sort or `get` — fix there, not by weakening the property.

### Refactor — clean up
Tidy the strategy into a named helper; add a docstring stating the invariant and why it matters (golden-file determinism — Rule 9: encode *why*); confirm `max_examples` is modest; `mypy --strict` clean on the test file.

## Files to touch
| Path | Why |
|---|---|
| `tests/unit/languages/test_language_registry_property.py` | New — the Hypothesis property test. |
| `tests/unit/languages/conftest.py` (optional) | A shared stub-`LanguagePack` factory if one is not already available. |

## Out of scope
- Properties over `validate_pack` / `register_language` — example tests (S2-02..S2-05) cover those; the arch deliberately scopes property testing to this one `LanguageRegistry` invariant.
- Duplicate-`Language` behavior — covered by S2-01's example tests; the strategy here de-duplicates so it never triggers.

## Notes for the implementer
- The strategy **must** generate distinct `Language` keys — a duplicate would make `register` raise and the property would be testing the wrong thing. De-duplicate by `Language` inside the strategy or sample a fixed pool without replacement.
- Use a *fresh* `LanguageRegistry()` per generated case — never register into `default_language_registry`, or Hypothesis's many runs pollute the global singleton and poison sibling tests.
- The property encodes *why* `all()` is sorted: golden-file determinism (S7-04). State that in the test docstring per Rule 9 — a test that just checks "sorted" without the reason is weaker.
- Keep `max_examples` modest — the arch explicitly says "modest and targeted; no over-investment." This is one property, not a property-test suite.
- The stub packs need only be *constructible* `LanguagePack` values — they do not need real probes or strategies, because this test never calls `validate_pack` or the fan-out. Reuse a stub-pack factory if S2-01's tests already built one.
- Verify the property has teeth before declaring done: transiently break `all()`'s sort key and confirm Hypothesis finds a counterexample.
