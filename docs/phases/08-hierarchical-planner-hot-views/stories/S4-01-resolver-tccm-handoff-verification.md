# Story S4-01 — Verify the resolver TCCM handoff and route S3-01 if unmet

**Step:** Step 4 — Build the `ConcreteResolution → BundleResolution` adapter (C2)
**Status:** Ready
**Effort:** S
**Depends on:** S2-04
**ADRs honored:** ADR-0009

## Context
Step 4 builds the `ConcreteResolution → BundleResolution` adapter (Component C2) that bridges the resolver's output to `BundleBuilder.build`'s input Protocol — but the adapter is structurally blocked if the resolver still hands a placeholder TCCM. The architect's Gap 2 / Open Question 1 makes this a **gating prerequisite**: before any adapter code is written, an implementer must verify against the shipped `src/codegenie/plugins/resolver.py` whether `resolve` returns the real `codegenie.plugins.tccm.TCCM` or the documented `ComposedTccm` placeholder. This story is the verification gate — it produces a recorded finding, not new runtime code, and routes the resolver-internal S3-01 substitution loudly as a Phase-8 prerequisite if the placeholder is still in place.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Gap 2 — ConcreteResolution does not structurally satisfy BundleBuilder.build's input Protocol` — the three concrete type mismatches; the placeholder problem
  - `../phase-arch-design.md §C2 — ConcreteResolution → BundleResolution adapter` — names this verification as Open Question 1
  - `../phase-arch-design.md §Open questions deferred to implementation` — item 1, the gating-prerequisite statement
  - `../phase-arch-design.md §Edge cases` — edge case 2 (resolver still returns the `ComposedTccm` placeholder)
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0009-concrete-resolution-to-bundle-resolution-adapter.md` — ADR-0009 — §Consequences "A Phase-8 gating prerequisite is surfaced (Open Question 1)"; the implementer must verify `resolver.resolve` hands the real `TCCM`
- **Implementation plan:**
  - `../High-level-impl.md §Step 4` — done-criteria bullet 1 (the verification result is recorded in the step's attempt log) and Implementation-level risk 1
- **Existing code (verify against these):**
  - `src/codegenie/plugins/resolver.py` — `ComposedTccm` (line ~120, the placeholder with only `provides`/`requires`, no `must_read` band), `ConcreteResolution.composed_tccm: ComposedTccm` (line ~162), `resolve()` (line ~485)
  - `src/codegenie/plugins/tccm.py` — the real `TCCM` (line ~226, has `must_read: list[ContextQuery]`)
  - `src/codegenie/plugins/bundle.py` — `BundleResolution` Protocol (line ~276, expects `composed_tccm: TCCM`)

## Goal
The placeholder-vs-real status of `resolver.resolve`'s `composed_tccm` is verified against the shipped codebase, recorded in the Step 4 attempt log, and a guard test pins the current reality so S4-02/S4-03 build against a known truth.

## Acceptance criteria
- [ ] An append-only entry in `docs/phases/08-hierarchical-planner-hot-views/_attempts/S4-01.md` records: which type `ConcreteResolution.composed_tccm` is (`ComposedTccm` or `TCCM`), whether it carries a `must_read` band, the file:line evidence, and the routing conclusion.
- [ ] If `composed_tccm` is still `ComposedTccm`: the attempt log explicitly names S3-01 (the resolver-internal real-`TCCM` substitution) as a Phase-8 prerequisite for S4-02/S4-03, and the README manifest's "Open implementation questions" status for Open Question 1 is updated to reflect the finding.
- [ ] A guard test asserts the verified current reality (the field's annotation and whether it has `must_read`) — so a future resolver change that ships the real `TCCM` makes the guard test fail loudly, signalling S4-03's placeholder branch can be retired.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Read `src/codegenie/plugins/resolver.py` — confirm the type of `ConcreteResolution.composed_tccm` and inspect `ComposedTccm`'s field set (`provides`, `requires`; absence of `must_read`).
2. Read `src/codegenie/plugins/tccm.py` `TCCM` — confirm it carries `must_read: list[ContextQuery]` (the band a "thin call" would need).
3. Write the guard test that introspects `ConcreteResolution.model_fields["composed_tccm"]` and asserts the annotation and the absence of `must_read` on the placeholder type — pinning the current reality.
4. Record the finding in `_attempts/S4-01.md` with file:line evidence and the explicit routing conclusion.
5. If the placeholder is confirmed: update the README manifest's Open Question 1 status note so downstream stories see the prerequisite without re-deriving it.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/supervisor/test_resolver_tccm_handoff.py`

One red test per behavior — a guard that pins the verified resolver reality:

```python
def test_concrete_resolution_composed_tccm_is_still_the_placeholder() -> None:
    # arrange: import the shipped resolver model.
    from codegenie.plugins.resolver import ComposedTccm, ConcreteResolution
    # act: introspect the declared field type of composed_tccm.
    field = ConcreteResolution.model_fields["composed_tccm"]
    # assert: it is the placeholder ComposedTccm (no must_read band) — NOT the
    # real codegenie.plugins.tccm.TCCM. When the resolver's S3-01 substitution
    # ships the real TCCM, this test fails loudly — that is the signal to retire
    # S4-03's ResolverTccmPlaceholder branch.
    assert field.annotation is ComposedTccm
    assert "must_read" not in ComposedTccm.model_fields
```

(If the verification finds the resolver *already* hands the real `TCCM`, invert this test — assert `field.annotation` is `codegenie.plugins.tccm.TCCM` — and record that in the attempt log instead. Write whichever test matches the verified codebase reality.)

### Green — make it pass
No production code — the test reflects the shipped resolver as-is. "Green" is the test passing against the current codebase plus the recorded attempt-log finding.

### Refactor — clean up
Add a module docstring on the test file explaining it is the Open-Question-1 gating guard and that its failure is the S3-01-shipped signal. Ensure the attempt-log entry is dated 2026-05-21 and append-only.

## Files to touch
| Path | Why |
|---|---|
| `tests/unit/supervisor/test_resolver_tccm_handoff.py` | New — the guard test pinning the verified resolver-TCCM reality |
| `docs/phases/08-hierarchical-planner-hot-views/_attempts/S4-01.md` | New — append-only record of the verification finding and routing conclusion |
| `docs/phases/08-hierarchical-planner-hot-views/stories/README.md` | Update Open Question 1's status note if the placeholder is confirmed |

## Out of scope
- The adapter itself (`ResolvedBundleInput`, `to_bundle_resolution`) — S4-02.
- The `ResolverTccmPlaceholder` typed error and the fail-loud branch — S4-03.
- Actually shipping the resolver-internal S3-01 real-`TCCM` substitution — that is resolver-package work outside Phase 8; this story only *routes* it as a prerequisite.

## Notes for the implementer
- This is a verification gate, not a coding story — its deliverable is a *recorded finding* plus a guard test. Do not start S4-02 until this finding is recorded (ADR-0009 §Consequences).
- The architect already verified (`phase-arch-design.md §Gap 2`) that the codebase ships the `ComposedTccm` placeholder — your job is to re-confirm against the live `resolver.py` at execution time, since it may have changed.
- The guard test must *fail* when the resolver later ships the real `TCCM` — that loud failure is the intended signal, not a regression. Document this in the test docstring so a future agent does not "fix" it by deleting the test.
- Fail loud (Rule 12): if the placeholder is still in place, the attempt log must say so unambiguously and name S3-01 — S4-02/S4-03 depend on this being surfaced, not buried.
- Do not work around a placeholder finding by stubbing a fake `TCCM` — that is exactly the "silently build an empty Bundle" failure ADR-0009 forbids.
