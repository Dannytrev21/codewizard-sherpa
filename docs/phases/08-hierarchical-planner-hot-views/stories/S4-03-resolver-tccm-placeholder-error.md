# Story S4-03 — Fail loud on the resolver placeholder with ResolverTccmPlaceholder

**Step:** Step 4 — Build the `ConcreteResolution → BundleResolution` adapter (C2)
**Status:** Ready
**Effort:** S
**Depends on:** S4-02
**ADRs honored:** ADR-0009

## Context
The C2 adapter (`to_bundle_resolution`, S4-02) translates a `ConcreteResolution` into a `BundleResolution`-shaped value — but if the resolver still hands the `ComposedTccm` placeholder (empty `provides`/`requires`, no `must_read` band), a naive translation would silently produce an empty Bundle. The architect's Edge case 2 and ADR-0009 require the opposite: fail loud. This story adds the typed `ResolverTccmPlaceholder` error so `to_bundle_resolution` raises — naming S3-01 as the prerequisite — the instant it sees a placeholder TCCM, never silently building a contentless Bundle. This is the fail-loud guard that closes Step 4.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C2 — ConcreteResolution → BundleResolution adapter` — §Failure behavior: "raise a typed `ResolverTccmPlaceholder` error naming S3-01 as the prerequisite — fail loud, never silently build an empty Bundle"
  - `../phase-arch-design.md §Edge cases` — edge case 2 (resolver still returns the `ComposedTccm` placeholder)
  - `../phase-arch-design.md §Control flow` — decision point D5 (placeholder → raise `ResolverTccmPlaceholder`)
  - `../phase-arch-design.md §Harness engineering` — error IDs match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; never silent (Rule 12)
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0009-concrete-resolution-to-bundle-resolution-adapter.md` — ADR-0009 — §Decision (c) "raises a typed `ResolverTccmPlaceholder` error — naming S3-01 as the prerequisite"; §Consequences "fail loud, naming S3-01"
- **Attempt log:**
  - `../_attempts/S4-01.md` — read first; tells you whether the placeholder is the current resolver reality (it determines whether this guard is live or defensive)
- **Existing code:**
  - `src/codegenie/plugins/resolver.py` — `ComposedTccm` (line ~120 — `provides`, `requires`; no `must_read`) — the placeholder shape this story detects
  - `src/codegenie/plugins/errors.py` — existing plugin-error idioms; mirror the codebase's typed-error convention
  - `src/codegenie/supervisor/bundle_resolution.py` — S4-02's `to_bundle_resolution`, where the guard is inserted

## Goal
`to_bundle_resolution` raises a typed `ResolverTccmPlaceholder` error — never builds an empty Bundle — when its input's `composed_tccm` is still the `ComposedTccm` placeholder.

## Acceptance criteria
- [ ] `codegenie/supervisor/bundle_resolution.py` defines a typed `ResolverTccmPlaceholder` error whose message names S3-01 as the prerequisite and carries an error ID matching `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
- [ ] `to_bundle_resolution` raises `ResolverTccmPlaceholder` when `composed_tccm` is a placeholder — detected by the placeholder's structural signature (empty `provides` and `requires`, no `must_read` band), never by a `try/except` swallow.
- [ ] A `ConcreteResolution` with a *non-placeholder* (real `TCCM`-shaped) `composed_tccm` does **not** raise — `to_bundle_resolution` returns a `ResolvedBundleInput` as in S4-02.
- [ ] The error is logged via `structlog` with its error ID before being raised (per §Harness engineering — never silent).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files; `make check` green.

## Implementation outline
1. Read `../_attempts/S4-01.md` — confirm whether the placeholder is the live resolver reality (guard is load-bearing) or whether the real `TCCM` already ships (guard is defensive, per ADR-0009 §Consequences last bullet).
2. Define `ResolverTccmPlaceholder` as a typed error in `bundle_resolution.py`, following the codebase's typed-error convention (see `plugins/errors.py`); give it a module-level error ID and add it to the package's `_WARNING_IDS`/error-ID set if one exists.
3. Write a pure predicate that recognises the placeholder structurally — empty `provides`, empty `requires`, no `must_read` band — rather than checking the concrete class name (so it survives a class rename).
4. Insert the guard at the head of `to_bundle_resolution`: if the predicate fires, log via `structlog` and raise; otherwise proceed to S4-02's translation.
5. Confirm `make check` green and the functional-core purity AST test (S4-02) still passes — the guard adds no I/O.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/supervisor/test_resolver_tccm_placeholder.py`

One red test per behavior:

```python
def test_to_bundle_resolution_raises_on_placeholder_composed_tccm() -> None:
    # arrange: a ConcreteResolution whose composed_tccm is the ComposedTccm
    # placeholder — empty provides/requires, no must_read band.
    resolution = make_concrete_resolution_with_placeholder_tccm()
    # act / assert: the adapter fails loud — never silently builds an empty
    # Bundle (edge case 2, ADR-0009). The error names S3-01 as the prerequisite.
    with pytest.raises(ResolverTccmPlaceholder) as exc:
        to_bundle_resolution(resolution)
    assert "S3-01" in str(exc.value)

def test_to_bundle_resolution_does_not_raise_on_real_tccm() -> None:
    # arrange: a ConcreteResolution whose composed_tccm is a real-TCCM-shaped
    # value (non-empty bands).
    resolution = make_concrete_resolution_with_real_tccm()
    # act: the guard must NOT fire — the adapter translates normally.
    result = to_bundle_resolution(resolution)
    # assert: a valid ResolvedBundleInput came back.
    assert result.plugin_id == resolution.plugin.manifest.plugin_id
```

### Green — make it pass
Add `ResolverTccmPlaceholder`, the structural placeholder predicate, and the guard at the head of `to_bundle_resolution` — log then raise on a placeholder, fall through to S4-02's translation otherwise. The smallest code that makes both tests pass.

### Refactor — clean up
Docstring on `ResolverTccmPlaceholder` citing ADR-0009 and edge case 2; docstring on the placeholder predicate explaining the structural (not class-name) check; confirm the error ID matches the regex and is validated at import via `raise AssertionError(...)` (bare `assert` is forbidden). Confirm the structlog call carries the error ID.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/supervisor/bundle_resolution.py` | Add `ResolverTccmPlaceholder`, the placeholder predicate, and the guard in `to_bundle_resolution` |
| `tests/unit/supervisor/test_resolver_tccm_placeholder.py` | New — placeholder-raises and real-TCCM-does-not-raise tests |

## Out of scope
- The adapter's translation logic (`ResolvedBundleInput`, the object→callable mapping) — S4-02.
- Shipping the resolver-internal S3-01 real-`TCCM` substitution that would retire this guard — resolver-package work outside Phase 8 (routed by S4-01).
- The `build_bundle_node` that calls `to_bundle_resolution` — Step 6 (S6-02).

## Notes for the implementer
- Fail loud (Rule 12) — never `try/except` the placeholder into an empty Bundle. The whole point of this story is that a placeholder TCCM is a *loud* failure, not a degraded success.
- Detect the placeholder *structurally* (empty `provides`/`requires`, no `must_read`), not by `isinstance(..., ComposedTccm)` — a class rename or a real `TCCM` that happens to be empty should both be caught by the same guard, and the real-`TCCM` path must not depend on the placeholder class still existing.
- The error message must name S3-01 explicitly (ADR-0009 §Decision) — a future implementer hitting this error needs to know the resolver-internal substitution is the fix, not a Phase-8 workaround.
- Error IDs must match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` and be validated at import via `raise AssertionError(...)` — bare `assert` is forbidden by the `forbidden-patterns` hook.
- Per ADR-0009 §Consequences, if S4-01 found the real `TCCM` already ships, this guard becomes defensive — still write it; a defensive guard against a future regression is correct, and the test stays meaningful.
- Keep the guard pure — the structlog call is the only side effect, and logging is permitted in the otherwise-pure adapter per §Harness engineering; do not let the S4-02 purity AST fence flag it (logging imports are conventionally allowlisted — mirror `tests/unit/plugins/test_resolver_purity.py`).
