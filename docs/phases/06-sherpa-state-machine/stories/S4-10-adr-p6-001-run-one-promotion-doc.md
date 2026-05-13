# Story S4-10 — Land ADR-P6-001 (`run_one` public promotion) doc + verify Phase 5 contract snapshot

**Step:** Step 4 — Implement the ten nodes as thin wrappers over Phase 3/4/5 engines
**Status:** Ready
**Effort:** S
**Depends on:** S4-06
**ADRs honored:** ADR-0010 (the existing Phase 6 ADR that *names* ADR-P6-001 as the surgical Phase 5 touch — this story finalizes the documentation of what shipped)

## Context

Documentation-only story. ADR-0010 in this phase's ADR set is the **forward-looking** Architecture Decision Record committing to the principle — "promote `_run_one_attempt` to public `run_one`, this is the only Phase 0–5 source touch in Phase 6." S4-06 actually *executed* the change (either as branch 1 rename-only or branch 2 small-refactor; branch 3 would have blocked the story).

This story closes the documentation loop in two ways:

1. **Commit `ADR-P6-001` in Nygard format** as a stand-alone file under `docs/phases/06-sherpa-state-machine/ADRs/`. This is the *post-mortem* record — it describes exactly the code shape that shipped, including the lockstep update to Phase 5's contract-snapshot test (if a refactor was needed). It is the **canonical reference Phase 7's `validate_in_sandbox` equivalent will cite** when it calls `run_one` for distroless gates. ADR-0010 describes the decision; ADR-P6-001 describes the diff.
2. **Update Phase 5's contract snapshot** if one exists. Phase 5 ships under `tests/gates/test_runner_contract.py` (or analog) — a frozen snapshot of `GateRunner`'s public API. If S4-06 added `run_one` (or refactored to expose it), the snapshot must reflect the new public symbol. Without this update, a future Phase 5 refactor could silently revert the promotion and Phase 6 wouldn't notice until the integration tests run (slow).

If Phase 5 ships *no* contract-snapshot test, this story surfaces that gap, and the implementer adds a minimal one (≤ 20 LOC) — without it, the public-promotion is undefended.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Gap analysis Gap 2`; `../phase-arch-design.md §Component 5 "validate_in_sandbox" row`
- **Phase ADRs:** `../ADRs/0010-phase5-runner-run-one-public-promotion.md` — the forward-looking ADR that S4-10 documents the realization of; ADR-0010's "Consequences" section explicitly names `tests/graph/test_runner_run_one_public.py` (created in S4-06) + amendment of this ADR
- **Prior phases:** `../../05-sandbox-trust-gates/final-design.md §6 GateRunner` — the contract `run_one` extends; `../../05-sandbox-trust-gates/` (look for any `contract` test files)
- **Source design:** `../final-design.md §"Any new ADRs implied by this design that should be drafted"` lists ADR-P6-001 as the first item

## Goal

Land `docs/phases/06-sherpa-state-machine/ADRs/P6-001-run-one-public-promotion-shipped.md` in Nygard format describing exactly what S4-06 shipped, and update (or create) Phase 5's contract-snapshot test to assert `GateRunner.run_one` is public.

## Acceptance criteria

- [ ] `docs/phases/06-sherpa-state-machine/ADRs/P6-001-run-one-public-promotion-shipped.md` exists in Nygard format with sections: **Status**, **Context**, **Decision** (describing *what shipped*: rename-only OR small refactor with line counts), **Consequences**, **Reversibility**, **Evidence / sources**.
- [ ] The ADR's **Decision** section quotes the actual `git diff` summary against Phase 5 (e.g., "5 lines changed in `src/codegenie/gates/runner.py`: rename of private method `_run_one_attempt` to public `run_one`; one callsite in `GateRunner.run` updated").
- [ ] Phase 5 contract snapshot updated: if `tests/gates/test_runner_contract.py` exists, add an assertion that `GateRunner.run_one` is public and takes `(transition, ctx) -> GateOutcome`. If no such file exists, create a minimal one.
- [ ] `tests/graph/test_runner_run_one_public.py` (created in S4-06) still green — it's the CI canary for the same invariant, from Phase 6's side.
- [ ] Full Phase 5 regression suite still green after the contract-snapshot update.
- [ ] `../ADRs/README.md` (if it indexes ADRs) updated to list `P6-001`.

## Implementation outline

1. Read `git diff origin/master -- src/codegenie/gates/runner.py` to see exactly what S4-06 shipped. Note line count, classify as "rename-only" or "small refactor."
2. Write ADR-P6-001 in Nygard format. Cross-reference ADR-0010 (the forward-looking ADR) at the top so a reader knows the relationship.
3. Locate Phase 5's contract-snapshot tests (`grep -r "test_runner_contract" tests/` or `find tests -name '*runner*contract*'`). If found, add a one-liner assertion for `run_one`. If not found, create the minimal snapshot file.
4. Run full Phase 5 regression suite to confirm no drift; run `tests/graph/test_runner_run_one_public.py` to confirm Phase 6's canary still green.
5. Update `../ADRs/README.md` index entry.
6. Commit as a doc-only PR; no production code touched.

## TDD plan — red / green / refactor

This is a documentation story; the "test" is the existence of the ADR file plus the Phase 5 contract-snapshot test. The red/green/refactor maps onto:

```python
# tests/gates/test_runner_contract.py (CREATE IF MISSING; EXTEND IF PRESENT)
"""Phase 5 contract snapshot — Phase 6 added run_one (ADR-P6-001).

Reverting these signatures requires a deliberate ADR amendment in lockstep."""
import inspect
from codegenie.gates.runner import GateRunner


def test_run_one_is_public_with_documented_signature():
    """ADR-P6-001 invariant — see docs/phases/06-sherpa-state-machine/ADRs/P6-001-*.md"""
    assert hasattr(GateRunner, "run_one")
    sig = inspect.signature(GateRunner.run_one)
    params = list(sig.parameters)
    # self, transition, ctx
    assert params[1] == "transition", f"expected 'transition' as 2nd param, got {params}"
    assert params[2] == "ctx", f"expected 'ctx' as 3rd param, got {params}"


def test_run_remains_callable_for_sync_callers():
    """Phase 5's looped GateRunner.run MUST still work — Phase 5 sync regression depends on it."""
    assert hasattr(GateRunner, "run")
    assert callable(GateRunner.run)
```

**Red:** Phase 5 contract snapshot missing the new assertion (or file missing entirely).
**Green:** Add the assertion (and the file if needed); ADR-P6-001 doc committed.
**Refactor:** Confirm the ADR file's "Evidence / sources" section cross-references ADR-0010 (forward-looking), the actual diff URL, and the canary tests on both sides (Phase 5 contract snapshot + Phase 6's `test_runner_run_one_public.py`).

## Files to touch

| Path | Action |
|---|---|
| `docs/phases/06-sherpa-state-machine/ADRs/P6-001-run-one-public-promotion-shipped.md` | New (Nygard format) |
| `docs/phases/06-sherpa-state-machine/ADRs/README.md` | Update index (add row for P6-001) |
| `tests/gates/test_runner_contract.py` | Extend (or create) with the two assertions above |

## Out of scope

- Any production code changes — S4-06 already landed those.
- Editing ADR-0010 — keep the forward-looking ADR intact; ADR-P6-001 is the post-mortem companion.
- Phase 5 internal refactors beyond what S4-06 shipped — additive only.
- Migrating other private Phase 5 helpers to public — out of Phase 6 scope.
- The Phase 5 sync regression suite full re-architecting — Phase 5 owns its own tests; this story only adds the contract-snapshot assertions Phase 6 relies on.

## Notes for the implementer

- **Be specific in the ADR.** Vague "we changed Phase 5" prose isn't an ADR; reference the actual line-count and the actual filenames. Future maintainers reading this ADR (Phase 7's distroless `validate_in_sandbox`-equivalent author, in particular) need to know exactly what API surface they can rely on.
- The Nygard sections are: Title; Status (Accepted); Context; Decision; Consequences; Reversibility; Evidence / sources. Keep the file under 80 lines — ADRs are not essays.
- Phase 5's contract-snapshot test, if missing, is a *Phase 5* test by ownership but a *Phase 6* dependency by need. The minimal version above (~ 20 LOC) suffices; surface it in your PR description so Phase 5's owners are aware.
- If `tests/graph/test_runner_run_one_public.py` (S4-06's canary) and `tests/gates/test_runner_contract.py` (this story) seem redundant — they are, deliberately. They guard the same invariant from two angles (Phase 6 import side + Phase 5 export side). Both must turn green. The day one of them goes red and the other doesn't, you've found a subtle Phase 5 internal break.
- If you discover during this story that S4-06 *didn't* actually update the ADR's Decision section as required by S4-06's AC, that's a bug in S4-06's completion — surface it as a follow-up rather than papering over it here.
- This story is short on code (zero production code, ~ 20 LOC of test) but heavy on **judgment**: how loudly does the Phase 5 side guard the contract? The conservative answer is "as loudly as Phase 6 does," and that's what the contract-snapshot test bakes in.
