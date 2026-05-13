# Story S6-08 — Task-type-mismatch safety + supervisor `xfail`

**Step:** Step 6 — Broaden coverage: adversarial Dockerfile corpus, second E2E fixture, HITL path, LLM-fallback path
**Status:** Ready
**Effort:** M
**Depends on:** S6-07
**ADRs honored:** ADR-P7-003 (`task_type` kwarg on `FallbackTier.run`), ADR-P7-009 (`DistrolessLedger`)

## Context

ADR-P7-003 added a `task_type` kwarg to `FallbackTier.run` so Phase 4 can route between vuln and distroless prompts/corpora. The kwarg is *additive* and *defaults to None* — every existing Phase 6 vuln callsite is byte-identical. But the additive widening leaves one *prompt-bleed* failure mode: an upstream caller (Phase 8's future supervisor, a bug in `replan_with_phase4`, a manual operator) could pass a **vuln advisory** with `task_type="distroless_migration"`, the LLM dutifully produces a distroless-shaped patch for a non-Dockerfile target, and the failure is *quiet* — it just doesn't help.

This is `phase-arch-design.md §Gap 6`. The remediation has two parts: (a) an integration test that exercises the mismatch and asserts **loud failure** (either Phase 3's `TrustScorer.score` rejects, or Phase 4's `OutputValidator` rejects on the structural-plan-references-registered-engine check); (b) a forward-looking `xfail` test that defines the contract Phase 8's supervisor must satisfy — *log `task_type` at every dispatch* — so Phase 8 cannot ship without making it green.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap 6` (lines 1433–1439) — the gap statement and the canonical resolution
  - `../phase-arch-design.md §Component 4 `replan_with_phase4`` — `task_type="distroless_migration"` is the dispatch key
  - `../phase-arch-design.md §Risks` — implicit prompt-bleed risk
  - `../phase-arch-design.md §Integration with Phase 8` (line 1325) — Phase 8's supervisor adopts `task_type` as the dispatch key
- **Phase ADRs:**
  - `../ADRs/0004-fallback-tier-task-type-kwarg.md` — ADR-P7-003 — the mismatch-safety test is named in Consequences (line 45); the supervisor-logging test is the forward-looking enforcement (line 46)
- **Existing code:**
  - `src/codegenie/planner/fallback_tier.py` (Phase 4 + S1-04) — `FallbackTier.run(..., task_type=...)`
  - `src/codegenie/planner/output_validator.py` (Phase 4) — `OutputValidator` rejects structurally-invalid plans
  - `src/codegenie/scoring/trust_scorer.py` (Phase 3) — `TrustScorer.score` is the vuln-validation gate
  - `tests/fixtures/repos/express-distroless/` (S5-06) — provides the vuln advisory + Express fixture combination used here
- **Phase 4 prior art:**
  - `tests/integration/test_phase4_default_task_type_behavior_unchanged.py` (S1-04) — the *positive* compatibility test; this story is the *negative* mismatch case

## Goal

`tests/integration/test_phase4_task_type_mismatch_safety.py` exercises a vuln advisory with `task_type="distroless_migration"` and asserts **loud failure** — either the LLM-produced patch fails `TrustScorer.score` validation or the patch is rejected at `OutputValidator`; the forward-looking `tests/integration/test_supervisor_logs_task_type.py` is defined and marked `xfail(strict=True)` so Phase 8 cannot ship without satisfying it.

## Acceptance criteria

- [ ] `tests/integration/test_phase4_task_type_mismatch_safety.py` exists and is green. It:
  - Loads an existing **vuln** advisory (e.g., a CVE in `lodash` from the Phase 4 fixture set or the Express fixture's `package.json`).
  - Invokes `FallbackTier.run(advisory=vuln_advisory, ..., task_type="distroless_migration")` *directly* (not through the migrate CLI — the test must isolate Phase 4's behaviour, not the full distroless pipeline).
  - Uses a recorded VCR cassette (one-time recording per the Phase 4 cassette discipline) for the LLM call.
  - Asserts **at least one** of the following loud-failure dispositions:
    - The resulting `FallbackTierResult.output_validated is False` with `validation_errors` naming the structural mismatch (e.g., `"plan_references_engine=dockerfile_recipe; advisory has no Dockerfile target"`), OR
    - The resulting plan, when handed to `TrustScorer.score(plan, advisory=vuln_advisory)`, returns `passed=False`, OR
    - `FallbackTier.run` raises a typed exception (`TaskTypeAdvisoryMismatch` or similar) before the LLM is ever invoked.
  - The test must NOT pass via the "silent success" path: any code path where the LLM-produced patch is treated as valid is a test failure.
- [ ] `tests/integration/test_supervisor_logs_task_type.py` exists and is decorated `@pytest.mark.xfail(strict=True, reason="Phase 8 supervisor not implemented; defining the contract early per Gap 6")`. It:
  - Imports the (not-yet-existing) supervisor module (the `xfail` covers the ImportError when it doesn't exist).
  - Asserts that the supervisor logs the `task_type` field at every workflow dispatch (`structlog` event `"supervisor.dispatch"` with `task_type` in the bound context).
  - Asserts the audit chain entry for the dispatch records `task_type`.
- [ ] The supervisor `xfail` test is **strict** (`strict=True`): if Phase 8 accidentally makes it pass (e.g., a stub supervisor that records the call without dispatching correctly), the test fails — preventing false negatives.
- [ ] `tests/integration/test_supervisor_logs_task_type.py` has a docstring linking back to `phase-arch-design.md §Gap 6` and ADR-P7-003 Consequences row, so Phase 8's implementer can find the contract without scavenging.
- [ ] No new fixture repos required — reuse `tests/fixtures/repos/express-distroless/` (S5-06) and an existing Phase 4 vuln-advisory fixture.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on both new test files.

## Implementation outline

1. Locate the vuln advisory fixture. The Express fixture (S5-06) carries a `package.json` with `lodash` — pair it with a synthetic `tests/fixtures/advisories/cve-2024-fake-lodash.yaml` advisory if Phase 4 doesn't already ship one suitable. Reuse Phase 4 advisory fixtures if available.
2. Write the red mismatch-safety test. Invoke `FallbackTier.run` directly with the cross-paired arguments. Record a one-time cassette for the LLM call (per S6-06's cassette discipline). Red because either the test passes silently (and we need to *add* the loud failure in a Phase 4 PR — surface this to the architect immediately) or the structural check already fires (good — confirm the disposition and pin it).
3. If the test surfaces a silent-success path, surface a follow-up to Phase 4 to wire the structural-mismatch loud failure (`OutputValidator` is the canonical place per ADR-P7-003 Consequences). Do NOT silently soften the test — that's the entire point.
4. Write the supervisor `xfail` test. Import the not-yet-existing module; assert the log shape. The `xfail(strict=True)` decorator makes the test green only when Phase 8 makes it actually pass.
5. Document both tests with clear docstrings pointing to Gap 6.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/integration/test_phase4_task_type_mismatch_safety.py
"""
Gap 6 mitigation (`phase-arch-design.md §Gap 6` + ADR-P7-003 Consequences row 4):
when a vuln advisory is paired with task_type="distroless_migration", the system
MUST fail loudly. Silent success is the bug this test guards against.
"""
from pathlib import Path
import pytest

from codegenie.planner.fallback_tier import FallbackTier
from codegenie.planner.output_validator import OutputValidator
from codegenie.scoring.trust_scorer import TrustScorer
from codegenie.schemas.advisory import Advisory

VULN_ADVISORY = Path("tests/fixtures/advisories/cve-2024-fake-lodash.yaml")

@pytest.mark.vcr(record_mode="none")
def test_vuln_advisory_with_distroless_task_type_fails_loudly(snapshot_runner) -> None:
    advisory = Advisory.from_yaml(VULN_ADVISORY.read_text())
    repo_ctx = snapshot_runner.repo_context_for("express-distroless")
    sel = snapshot_runner.recipe_selection(matched=False)

    # Could raise (loud), or return a result that fails validation (loud).
    try:
        result = FallbackTier.run(
            advisory=advisory, repo_ctx=repo_ctx, sel=sel, prior_attempts=[],
            run_id="test-run", include_pending=False, auto_promote=False,
            task_type="distroless_migration",  # mismatch — this is the bug surface
        )
    except Exception as exc:
        # Loud failure path A: raised typed exception before the LLM was ever called.
        assert "task_type" in str(exc) or "mismatch" in str(exc).lower()
        return

    # Loud failure path B: output validator rejected.
    if result.output_validated is False:
        assert any("engine" in e or "advisory" in e for e in result.validation_errors)
        return

    # Loud failure path C: TrustScorer rejected the plan.
    scoring = TrustScorer.score(plan=result.plan, advisory=advisory)
    assert scoring.passed is False, (
        "vuln advisory + distroless task_type produced a plan that TrustScorer accepted — "
        "Gap 6 silent-success failure mode"
    )
```

```python
# tests/integration/test_supervisor_logs_task_type.py
"""
Forward-looking contract (`phase-arch-design.md §Gap 6` + ADR-P7-003 Consequences row 4):
Phase 8's supervisor MUST log `task_type` at every workflow dispatch.
Defining this xfail now means Phase 8 cannot ship without making it green.
"""
import pytest

@pytest.mark.xfail(strict=True,
                   reason="Phase 8 supervisor not implemented; defining the contract early (Gap 6)")
def test_supervisor_logs_task_type_on_every_dispatch():
    from codegenie.supervisor import Supervisor  # noqa: F401 — will not exist until Phase 8
    # ... assertions on structlog events / audit chain entries
    pytest.fail("Phase 8 ships when this test passes naturally")
```

Red: cassette doesn't exist; mismatch silently succeeds (real bug surface); `xfail` test imports module that doesn't exist (expected — that's what `xfail` covers).

### Green — make it pass

- Record the cassette one-time.
- If the mismatch already fails loudly at one of paths A/B/C, the green is reading the actual error and pinning the assertion.
- If the mismatch *succeeds silently*, **stop and escalate**: surface a Phase 4 follow-up (Output Validator strengthening) before declaring this story done. The test is the design-enforcement; weakening it defeats Gap 6.

### Refactor — clean up

- Add a docstring to each path A/B/C explaining when it fires, so future maintainers understand the loud-failure disjunction.
- Confirm the `xfail` test's `strict=True` semantic — passing it accidentally must fail the suite, not silently mark it as unexpectedly-passing.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase4_task_type_mismatch_safety.py` | New — Gap 6 mitigation |
| `tests/integration/test_supervisor_logs_task_type.py` | New — forward-looking `xfail(strict=True)` for Phase 8 |
| `tests/fixtures/advisories/cve-2024-fake-lodash.yaml` | New (if Phase 4 doesn't ship one) — vuln advisory for the mismatch |
| `tests/fixtures/cassettes/<hash>.yaml.zst` | New — one-time recorded LLM call for the mismatch test |

## Out of scope

- **Strengthening `OutputValidator` to actually reject the mismatch.** If the mismatch surfaces a Phase 4 gap, the fix is a Phase 4 follow-up PR — this story names the contract, it does not own its implementation.
- **The Phase 8 supervisor implementation.** Owned by Phase 8; this story merely defines the test contract.
- **Symmetric mismatch (distroless advisory + `task_type="vuln_remediation"`).** Distroless "advisories" are not the canonical shape — Phase 7 takes CVE inputs to drive distroless choices but the advisory is still vuln-shaped. The mismatch direction in this story is the one that produces silent harm.
- **Cassette discipline + re-record workflow.** Owned by S6-06; this story consumes the convention.
- **Per-task RAG corpus retrieval correctness.** S6-07 owns it; this story is the *prompt-bleed* failure mode, not the *corpus-bleed* one.

## Notes for the implementer

- The hardest engineering question in this story is: *what does loud failure look like?* The three paths A/B/C are listed in order of preference — a typed exception (A) is loudest; an output-validator rejection (B) is second-loudest; a TrustScorer rejection (C) is the safety net. If none of these fire, **stop and escalate** rather than weakening the test.
- The `xfail(strict=True)` semantic is load-bearing. Read the pytest docs if unsure: a strict xfail that passes is reported as `XPASS(strict)` and fails the suite. This is intentional — Phase 8 making the test pass should be a *deliberate* green, not an accidental one. Without `strict`, a stub supervisor that imports cleanly would silently pass the `xfail` and Phase 8 could ship without making the assertion meaningful.
- The vuln advisory must be a *plausible* one — a fake CVE in `lodash` (which is in the Express fixture's `package.json`) makes the test realistic. Avoid synthetic-shaped advisories that the LLM would reject for unrelated reasons (e.g., advisory with no package name); those would mask the *task-type mismatch* failure mode behind a different rejection.
- The cassette captures one LLM invocation. If the LLM-fallback path retries, capture multiple cassettes — but for the mismatch case the first invocation should already be sufficient because the assertion is about the *first* produced plan failing validation.
- Per `phase-arch-design.md §Gap 6`, this test is the entire mechanical defense against prompt-bleed across task types. If a Phase 8 PR breaks it by accident, Phase 8's PR should be blocked, not this test be softened.
- `mypy --strict` on this test means: type the `result`, type the `Advisory` parsing, type the exception narrowing. The test is a contract — types make the contract auditable.
- Update story `Status:` to `Done` when complete.
