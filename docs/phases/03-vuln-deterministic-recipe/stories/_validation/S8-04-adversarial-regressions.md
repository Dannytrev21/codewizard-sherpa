# Validation report: S8-04 — Adversarial regression tests E1–E20

**Validated:** 2026-05-20
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S8-04 lands a regression test for every §Edge cases row (E1–E20) plus a breaking-test-suite no-retry contract test and an `extends`-chain composition test, marked `phase03_adv` for a discrete CI gate. The story's *intent* and *coverage shape* are sound — all 20 edge cases have a target, and the goal traces. But the story shipped four real blockers and ten hardenable weaknesses: it prescribed a non-existent directory convention, a pytest-broken marker mechanism, and outcome-type symbol names that do not exist in the shipped code; and several ACs were thin enough that a wrong implementation could pass them. All findings have in-place fixes, so the verdict is HARDENED, not RESCUE. One structural caveat is now explicit in the story: S8-04's real prerequisites (S4-*, S5-*, S6-04, S7-*) are mostly HARDENED-not-executed and S5-02 is BLOCKED, so the story itself is **BLOCKED for execution** until that upstream lands — the executor must precondition-check before writing tests against absent code.

## Findings by critic

### Coverage critic

- **block** — `Depends on: S8-03` is wrong; the suite cannot execute. Every E# test invokes `codegenie remediate` / the orchestrator / `SubprocessJail` / recipes / loader / resolver — none of which exist (`orchestrator.py` unbuilt, S6-04 only HARDENED; S5-02 BLOCKED). As written the executor writes 23 tests that error at import. Fix: widen `Depends on` to the real prerequisite set + add a precondition AC.
- **harden** — AC "runs all the above" command `pytest tests/adversarial/ -m phase03_adv` path-scopes the run and misses E2 + extends-chain (both under `tests/integration/`). Also flagged the conftest-`pytestmark` non-propagation.
- **harden (NEEDS RESEARCH→resolved)** — E11 outcome discriminator unspecified ("`Failed` or `Validated(passed=False)`"); a test omitting the top-level assertion passes regardless. Resolve against §C6.
- **harden** — E15 AC "CLI exits 0 if otherwise OK" is unverifiable.
- **harden** — arch §Adversarial-tests item "malformed recipe YAML rejected at load" is silently dropped (not an E# row, not in Out-of-scope).
- **harden** — E8/E14 "canary file does not exist" passes spuriously if the install/commit stage never ran.
- **nit** — Goal sentence enumerates only ~7 of the 20 E# cases; trace-completeness reader can't confirm.
- **nit** — E16 "2-MiB record" should state the 1-MiB cap inline.

### Test-Quality critic

- **block** — `conftest.py` `pytestmark` does not work; `pytestmark` is module-scoped and conftest has no tests → every E# file unmarked → `-m phase03_adv` collects zero, exits 5, green-looking suite runs nothing. Phase-2 precedent does per-file `pytestmark`. Notes line's "Phase 2's conftest.py is `pytestmark`" is factually false.
- **block** — the red test is not red-first; the story admits S6-04 already honors the no-retry contract, so the test is green-first. By the story's own line 213 definition that makes it "invalid". A *regression* suite over shipped impl is green-first by construction; demanding red-first is a category error. Replace with mutation verification.
- **harden** — `report.get("attempts") in (None, [], 0)` is tautological — an omitted field passes regardless of retry. Make event-count the primary signal.
- **harden** — E8/E14 "canary absent" weak; promote the spec-inspection / mechanism assertion to primary.
- **harden** — E15 "exits 0 if otherwise OK" weak unless the fixture is minimal + a control run.
- **harden** — E5/E13/E18 assert "event present" with no payload intent.
- **nit** — `tests/adversarial/` path discrepancy vs `tests/adv/phase02/`.
- **nit** — E12 "loop until swap lands" is CI-flaky; make the deterministic path required.

### Consistency critic

- **block (F1)** — `tests/adversarial/` does not exist; shipped convention is `tests/adv/` + `tests/adv/phase02/`. Doc-vs-code conflict (arch §Testing strategy itself says `tests/adversarial/`). Resolution per Rule 7/11: shipped code wins → `tests/adv/phase03/`; flag arch lines 986/989/1062 as cleanup.
- **block (F4)** — `RecipeOutcome.Failed` / `RemediationOutcome.Failed` are not real symbols; shipped variants are `RecipeFailed` / `RemediationFailed` etc. `RecipeFailed` has no `reason` field (`error: RecipeError`); `Applied` has `transform_id`, not `transform`.
- **block (F5)** — reason-token casing: E1/E19/E20 use snake_case `reason=...`; `RecipeFailed` carries `error.error_id` (dotted snake-case), not `reason`. E4/E6 UPPER reasons are correct against `NotApplicableReason`.
- **harden (F2)** — References line 39 mislabels `tests/adversarial/` as "Phase 2 precedent"; the precedent is `tests/adv/phase02/`. Notes mis-cite the Phase-2 conftest pattern.
- **harden (F3)** — E19 rollback contradiction: arch row says "rollback branch", but disk-full happens mid-write of `Transform.diff_bytes` before any branch exists. The story (no rollback) is correct; arch row is wrong.
- **nit (F6)** — E18 `TrustOutcome.confidence == "degraded"` unverifiable until S6-02 ships; `Validated` carries no `confidence` field.

### Design-Patterns critic

- **block** — marker mechanism broken in pytest; use per-file `pytestmark` (the real Phase-2 convention) — that already delivers "add a file, zero edits to conftest". (Validator note: the critic proposed a `pytest_collection_modifyitems` hook; rejected in favour of per-file `pytestmark` because Rule 11 — match the shipped Phase-2 convention — and Consistency outranks Design-Patterns. Per-file `pytestmark` + the meta-test is equally extension-by-addition.)
- **block** — `tests/adversarial/` forks the `tests/adv/` convention → use `tests/adv/phase03/`.
- **block** — `tests/fixtures/repos/yarn-berry/` is scope bleed; the fixture portfolio is S8-01's. Move ownership to S8-01.
- **harden** — shared helpers belong in `_helpers.py` (Phase 0/2 precedent), not `conftest.py`.
- **harden** — `_assert_no_branch_created` shared across E11/E12/E19 may mask distinct intent (TOCTOU abort vs disk-full); verify the assertion is byte-identical before lifting, else keep inline.
- **harden (NEEDS RESEARCH→resolved)** — E12 debug seam: do not add a production seam for a test; default to the loop approach; option-1 seam only if one already exists.
- **nit** — marker description string should match the `phase02_adv` shape `(CI-gating; see tests/adv/phase03/)`.

## Research briefs

None. Three findings were tagged `NEEDS RESEARCH` (E11 discriminator, E18 `TrustOutcome.confidence`, E12 seam) but all three are codebase-state verifications, not canonical-pattern lookups — resolved directly by reading `src/codegenie/transforms/outcomes.py`, `sandbox_jail.py`, and the arch §C6/§C8/§C10. Stage 3 (arXiv / library-docs research) was correctly skipped.

## Conflict resolutions

- **Marker mechanism: `pytest_collection_modifyitems` hook (Design-Patterns) vs per-file `pytestmark` (Consistency/Test-Quality).** Resolved in favour of per-file `pytestmark` — the shipped Phase-2 convention (`tests/adv/phase02/test_*.py`). Priority chain `Consistency > Design-Patterns` plus Rule 11 (match the codebase). Per-file `pytestmark` is still pure extension-by-addition; the `test_marker_applied.py` meta-test closes the forgotten-marker gap the hook was meant to address.
- **Directory: arch doc (`tests/adversarial/`) vs shipped code (`tests/adv/phaseNN/`).** The arch doc is a source of truth, but it predates and contradicts the realized Phase-0/1/2 convention. CLAUDE.md "match the existing convention; pick the more recent and surface the older as cleanup" + Rule 7 → story follows `tests/adv/phase03/`; arch lines 986/989/1062 flagged for cleanup (validator does not edit the arch doc — out of scope).

## Edits applied

### Edit 1 — Status → HARDENED; `Depends on` widened
- Source: Coverage block, Consistency F4.
- `Status: Ready` → `HARDENED (validated 2026-05-20 …)`. `Depends on: S8-03` → S8-01 + S8-03 + an explicit "real execution prerequisites" clause (S4-*, S5-*, S6-04, S7-* must be GREEN) and a BLOCKED-until-upstream-lands note.

### Edit 2 — Validation notes block inserted under the header.

### Edit 3 — directory `tests/adversarial/` → `tests/adv/phase03/` everywhere
- Source: Consistency F1, all critics. `replace_all`.

### Edit 4 — References block corrected
- Source: Consistency F2. Line 39 now cites `tests/adv/phase02/` as the real precedent and describes its actual conftest (no `pytestmark`); added a reference row for `src/codegenie/transforms/outcomes.py` (the shipped variant classes).

### Edit 5 — Acceptance criteria section rewritten
- Source: all four critics. Added a "Typed-assertion vocabulary" preamble box listing the real shipped variant classes + field shapes. Corrected every E# AC to the real symbols (`RecipeFailed.error.error_id`, `RecipeNotApplicable.reason`, `Applied.transform_id`, `RequiresHumanReview.reason ∈ {…}`, `Validated`). Resolved E11 → `Validated(passed=False, failing=[SignalKind("cve_delta")])`. Hardened E3/E5/E8/E13/E14/E15/E18 to assert the containment mechanism + that the relevant stage ran. Added a marker meta-test AC, fixed the run-command AC (marker-scoped, picks up E2 + extends-chain), and replaced the "red test fails first" AC with a Mutation-verification AC.

### Edit 6 — Implementation outline rewritten
- Source: Test-Quality #1, Consistency, Design-Patterns. Added a step-0 precondition check; fixed the marker mechanism (per-file `pytestmark`, conftest holds no marker); moved `yarn-berry/` fixture ownership to S8-01; made the no-retry proof event-count-primary; made the E12 swap deterministic with no production seam.

### Edit 7 — TDD plan Red section rewritten
- Source: Test-Quality #2/#3. Fixed the `FIXTURE` relative path (`parents[2]`); replaced `report.get("attempts") in (None, [], 0)` with a present-and-empty check + a spelled-out event-count assertion; replaced the false "red-first" framing with mutation-verification discipline.

### Edit 8 — Green/Refactor updated
- Canonical marker-scoped run command; helpers in `_helpers.py`; caveat against a shared `_assert_no_branch_created` masking distinct intent.

### Edit 9 — Files to touch updated
- conftest row (no `pytestmark`); added `_helpers.py` + `test_marker_applied.py` rows; `yarn-berry/` row marked NOT created here (S8-01-owned).

### Edit 10 — Out of scope extended
- Added `malformed-recipe-YAML-rejected-at-load` (with rationale — Phase-15 recipe loader), and a `capability-construction fence` row (S4-05-owned).

### Edit 11 — Notes for implementer rewritten
- Corrected symbol names; fixed the no-retry snippet; fixed the marker-discipline bullet; made E12 default to the no-seam loop; removed the false "every test fails before impl" bullet; added an extension-by-addition note.

### Edit 12 — Context §2 cve_delta hedge resolved
- The "`RemediationFailed` or `Validated`, depending on C6" hedge replaced with the resolved answer (`Validated`).

## Verdict rationale

HARDENED. The story's goal, scope, and coverage shape are correct — every §Edge cases row has a verifiable target and the AC set traces to the goal — so this is not a RESCUE. But it carried four blockers (non-existent directory, pytest-broken marker mechanism, non-existent outcome symbols, understated dependencies) and ten hardenable weaknesses, every one of which has a clean in-place fix. After the 12 edits, each AC names a real shipped symbol, asserts on a discriminated-union variant + payload (ADR-0010), and would fail under mutation. The one residual is sequencing, not story quality: S8-04 cannot be *executed* until S4-*/S5-*/S6-04/S7-* are GREEN — now explicit in the `Depends on` line and a step-0 precondition.

## Recommended next step

- The story is HARDENED and ready for `phase-story-executor` **once its upstream prerequisites (S6-04 orchestrator, S5-* recipe engines, S4-* jail, S7-* plugins) are GREEN**. Until then the executor's step-0 precondition check will (correctly) mark it BLOCKED.
- Separately: `phase-arch-design.md §Testing strategy` should be cleaned up — change `tests/adversarial/` → `tests/adv/phase03/` (lines ~986, ~989, ~1062) and drop "rollback branch" from the E19 row (~line 997). This is an arch-doc edit, out of scope for the validator.
