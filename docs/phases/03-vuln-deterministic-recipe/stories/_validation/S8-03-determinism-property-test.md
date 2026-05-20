# Validation report: S8-03 — Determinism property test (Hypothesis, 100 runs)

**Validated:** 2026-05-20
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1 (automated scheduled task `story-validation-corrector`)

## Summary

S8-03 lands `tests/property/test_transform_determinism.py` — the executable form of Goal G4 ("same inputs → same Transform bytes"), the cardinal Phase-3 commitment. The *goal* is sound and traces 1:1 to `phase-arch-design.md §Goals G4` and §Testing strategy §Property tests. But the story as written was built on a comparison surface that does not exist and a Hypothesis strategy that cannot deliver its headline number.

The two block-class defects: (1) the story asserts on `RemediationOrchestrator.run(...).transform.diff_bytes` / `.transform_id`, but the **shipped** `RemediationOutcome` union (`src/codegenie/transforms/outcomes.py`) is `Validated(branch, report_path, passed, failing) | RemediationNotApplicable(reason) | RemediationFailed(error, partial_report_path)` — no variant carries `.transform`; (2) `@given(st.sampled_from(_REPO_FIXTURES))` over a 5-element set exhausts at 5 examples (Hypothesis dedupes draws), so `max_examples=100` is dead and "100 runs" was false. Both have clean in-place fixes — derive a `_determinism_key` from the shipped union, and mirror the established sibling `tests/property/test_bundle_determinism.py`'s `st.integers` seed strategy. Seven further `harden` findings and two `nit`s were applied. No goal contradiction → HARDENED, not RESCUE.

Stage 2 ran as a single-validator synthesis pass — the four critic lenses were applied without fanning out to subagents, a deliberate token-economy choice under the scheduled-task budget. Every source the four critics would read was read in Stage 1: the story, `CLAUDE.md`, `phase-arch-design.md` (Goals/Testing strategy/Edge cases), ADR-0001/0008/0010, `High-level-impl.md`, the shipped `src/codegenie/transforms/outcomes.py` reality (via S6-04's hardened story + validation), the sibling `tests/property/test_bundle_determinism.py`, and the hardened S8-01 / S8-02 / S6-04 stories.

## Findings by critic

### Coverage critic

**C-F1 — `major-bump-required` produces no Transform; `assert a.transform.diff_bytes` would `AttributeError`.**
- Severity: harden (cross-linked to Consistency K-F1, the authoritative source)
- Per S8-01 AC-1, `major-bump-required` → `RemediationNotApplicable(MAJOR_BUMP_REFUSE)`. The story's own Refactor section *acknowledges* non-Transform outcomes exist ("those don't produce a `Transform` at all") yet the AC grid includes the fixture and the property body unconditionally dereferences `.transform`.
- Fix: the property compares a `_determinism_key` that `match`es the shipped union — `git diff` for `Validated`, `(kind, reason)` for `RemediationNotApplicable`. Determinism of the refuse path is itself G4 ("replay produces identical outputs").

**C-F2 — the paired cache-key test is wrong by construction.**
- Severity: harden
- `test_vuln_index_digest_is_part_of_cache_key` seeds the sqlite with "one extra (irrelevant) row" and expects a *different* `transform.diff_bytes`. A different `vuln_index.digest` causes a Bundle cache *miss* — but recompute with identical inputs yields byte-*identical* output. The test would fail (expects different, gets same).
- Fix: the seeded delta must *re-classify a CVE relevant to the fixture* (ADR-0008's actual motivation: "a CVE-feed refresh that re-classifies a CVE … must not return a stale cache hit"). Renamed `test_vuln_index_refresh_changes_transform`; AC-6 rewritten.

**C-F3 — no mutation guard; the property can pass vacuously.**
- Severity: harden (cross-linked to Test-Quality T-F4)
- If `_run_workflow` silently produced a constant (a no-op, an early return), the property `a.key == b.key` passes trivially. Rule 9 — a test that passes against a wrong implementation is worthless.
- Fix: AC-12 — assert the `git diff` is non-empty for `Validated` outcomes (the workflow actually patched something), plus an `xfail(strict=True)` meta-test against a deliberately non-deterministic shim, mirroring the sibling.

**C-F4 — the runtime budget is dishonest.**
- Severity: nit
- 100 examples × 2 perturbed runs = up to 200 jailed `npm install` + `npm test` executions. The story claims "~3 s warm" / "≤ 5 minutes on CI". The sibling's 100 examples are pure in-memory ms-scale builds; a real express workflow with subprocess jail is not 3 s.
- Fix: Out-of-scope bullet rewritten — the executor measures actual wall-time and may reduce `max_examples` with a documented rationale; the concurrency perturbation preserves the test's power at lower N.

### Test-Quality critic

**T-F1 — `@given(st.sampled_from(_REPO_FIXTURES))` cannot deliver `max_examples=100`.**
- Severity: harden (block-class defect, clean in-place fix)
- Hypothesis dedupes draws and detects an exhausted search space; a 5-element `sampled_from` yields 5 examples, not 100. The headline "100 runs" — the number from `phase-arch-design.md §Testing strategy` — is silently false. The story's Notes even claim "Hypothesis is here for the bookkeeping (100 examples…)" — but it would not produce 100.
- Fix: mirror `tests/property/test_bundle_determinism.py` exactly — `@given(seed=st.integers(min_value=0, max_value=10**9))`; the seed selects the fixture (`_CVE_FIXTURES[seed % len]`) and derives the perturbation. AC-2 forbids `sampled_from` for this dimension.

**T-F2 — 100 plain repeats of identical inputs is a weak determinism test.**
- Severity: harden
- The story runs `RemediationOrchestrator.run(...)` "twice with identical inputs". The sibling `test_bundle_determinism.py` does *not* just repeat — it injects seeded scheduler jitter so each example genuinely stresses the non-deterministic seam (`asyncio.Semaphore` interleaving). Plain repeats in one process share `PYTHONHASHSEED` and exercise few interleavings.
- Fix: AC-4 — perturb `CODEGENIE_BUNDLE_CONCURRENCY` (the ADR-0008 env knob) across the run-pair (run A at 1, run B at `min(4,cpu)`). A deterministic serial-fallback `BundleBuilder` is invariant to concurrency; a hedged-race one is not — so the perturbation is the workflow-level analogue of the sibling's jitter.

**T-F3 — cold-cache isolation is unstated.**
- Severity: harden
- AC-55 covers example-to-example isolation but not run-A-vs-run-B cache independence. If both runs of a pair shared a `BundleBuilder` `cache_dir`, run B would be a cache hit — the property would then test cache-read determinism, not compute determinism. The sibling explicitly uses `mktemp(f"a-{seed}")` / `mktemp(f"b-{seed}")`.
- Fix: AC-10 — each run gets its own `cache_dir` / npm-cache extraction / `.codegenie/` root.

**T-F4 — no negative control.**
- Severity: harden (merged into C-F3 / AC-12)
- The sibling ships an `xfail(strict=True)` meta-test against `_HedgedRaceBundleBuilder` — proof the property has teeth. S8-03 had none.
- Fix: AC-12 adds the teeth meta-test + the non-empty-diff guard.

### Consistency critic

**K-F1 — the comparison surface contradicts shipped `outcomes.py`.** (BLOCK-class)
- Severity: harden (clean in-place fix → HARDENED not RESCUE)
- The story's header, Goal, AC, TDD plan, and Notes all assert on `RemediationOrchestrator.run(...).transform.diff_bytes` and `.transform_id`. The shipped `RemediationOutcome` (`src/codegenie/transforms/outcomes.py`, S1-03 GREEN 2026-05-18, confirmed by S6-04 validation note 1) is the tagged union `Validated(branch, report_path, passed, failing) | RemediationNotApplicable(reason) | RemediationFailed(error, partial_report_path)`. **No variant exposes `.transform` or `.transform_id`.** Variant class names are `RemediationNotApplicable` / `RemediationFailed`, not `RemediationOutcome.NotApplicable`. S6-04's own validation corrected this exact misconception in its integration-test AC; S8-03 repeated the pre-correction mistake.
- Fix: AC-5 introduces `_determinism_key(repo, outcome)` deriving the byte surface from the shipped variants — `git diff` of `Validated.branch`, `(kind, reason)` for `RemediationNotApplicable`. Header ADR-0001 line, Goal, Context (new reconciliation paragraph), References, TDD plan, and Notes all corrected.

**K-F2 — `Files to touch` names a non-existent `tests/conftest.py`.**
- Severity: harden
- There is no root `tests/conftest.py`; conftest files are per-directory. S8-01's validation *explicitly dropped* a `tests/conftest.py` row. The `prewarmed_npm_cache` / `seeded_vuln_index` fixtures are consumed only by this property test; a root conftest would force session-scoped tarball extraction onto the entire ~2,300-test suite.
- Fix: fixtures move to a new `tests/property/conftest.py` (AC-13; Files-to-touch updated).

**K-F3 — missing dependency on S6-05 / the orchestrator surface.**
- Severity: harden
- `Depends on:` listed only S8-01, S8-02. The story imports/drives `RemediationOrchestrator` — that surface is shipped by S6-04 and wired into the CLI by S6-05. Dependency-cliff smell.
- Fix: `Depends on:` now includes S6-05 (transitively S6-04); the story drives the workflow via the `codegenie remediate` CLI.

**K-F4 — AC-1 ("runs in CI on every PR") contradicts the Refactor's `@pytest.mark.slow`.**
- Severity: harden
- If `slow` is excluded from default `pytest -q` (which `make test`/`make check` run), the property never runs in `make check`; "runs in CI on every PR" then needs an explicit mechanism.
- Fix: AC-1 rewritten — the file carries `@pytest.mark.slow`; default `pytest -q` excludes it; CI runs it via an explicit `pytest -m slow` step; the `slow` marker is registered in `pyproject.toml`; CI-YAML wiring is flagged as S9-01's boundary.

**K-F5 — ACs were unnumbered.**
- Severity: nit
- Siblings S8-01 / S8-02 were renumbered AC-1..AC-N for traceability during their own validation.
- Fix: numbered AC-1..AC-15.

### Design-Patterns critic

**D-F1 — re-declares the fixture list instead of consuming the S8-01 manifest.**
- Severity: harden
- Smell: missed kernel consumption / single-source-of-truth violation. The story declares `_REPO_FIXTURES` (a literal tuple) and `_CVE_BY_FIXTURE` (a dict). S8-01 shipped `tests/fixtures/repos/_portfolio.py` — a `Final` tuple `PORTFOLIO` of `FixtureSpec(name, path, is_adversarial, cve_ids: tuple[CveId, ...], …)` — and S8-01 AC-7 **explicitly names S8-03's `_REPO_FIXTURES`/`_CVE_IDS`** as the re-declaration the manifest exists to eliminate. Rule-of-three conclusively past.
- Fix: AC-9 — `_CVE_FIXTURES = tuple(s for s in PORTFOLIO if s.cve_ids)`; fixture dirs from `FixtureSpec.path`, CVE ids from `FixtureSpec.cve_ids`. The test declares no literal fixture-name tuple and no `_CVE_BY_FIXTURE`.

**D-F2 — `_determinism_key` / masking-helper extraction.**
- Severity: nit
- If the story needs report masking, S8-02's `_mask_nondeterministic_fields` (a test-module-internal helper) is the precedent — rule-of-three would say extract to a shared `tests/_e2e_support.py` rather than importing test-from-test.
- Fix: surfaced in Notes for the implementer; not mandated — the `git diff` surface (AC-5) needs no masking, which is the preferred path (Rule 2 — the executor judges at implementation time).

## Research briefs

None. No finding was tagged `NEEDS RESEARCH` — the canonical determinism-property pattern is already in-repo (`tests/property/test_bundle_determinism.py`), and the shipped `RemediationOutcome` shape is authoritative in `src/codegenie/transforms/outcomes.py`. Stage 3 skipped.

## Conflict resolutions

- **Coverage C-F1 vs the arch's "byte-identical `Transform.diff_bytes`" framing (G4).** Coverage wanted a comparison surface that handles non-Transform outcomes; the arch headline says "Transform bytes". Resolution (Consistency senior): the shipped `RemediationOutcome` is the source of truth — no `.transform` exists. `_determinism_key` honors the arch *intent* (G4 clause 2, "replay produces identical outputs") for all outcomes while reconstructing the byte-level Transform effect via `git diff` of the patch branch for `Validated`. No contradiction with the arch — the arch describes the property, not the API.
- **Test-Quality T-F2 (perturbation) vs Rule 2 (Simplicity).** Injecting concurrency perturbation adds machinery. Resolution: kept — the perturbation is one env-var set per run (`CODEGENIE_BUNDLE_CONCURRENCY` already exists per ADR-0008), not new abstraction, and without it the "100 runs" are near-worthless repeats. The sibling sets the precedent.

## Edits applied

### Edit 1 — header block (Status / Depends on / ADRs honored)
- Status `Ready` → `HARDENED (validated 2026-05-20 …)`.
- `Depends on:` → added S6-05; annotated each dependency.
- ADRs-honored ADR-0001 clause corrected: removed the false "`Transform.diff_bytes` exposed via `RemediationOrchestrator.run(...).transform_id`"; now describes the `git diff`-of-`Validated.branch` surface. ADR-0008 clause notes the AC-4 concurrency perturbation; ADR-0010 clause notes the shipped union.

### Edit 2 — `## Validation notes` block inserted under the header.

### Edit 3 — Context
- Rewrote the "The property is:" paragraph — corrected to `_determinism_key`, `st.integers` seed, explicit note that `sampled_from` over 5 values cannot yield 100 runs.
- Added a "Reconciliation with shipped reality" paragraph documenting the `RemediationOutcome` union and the non-Transform `major-bump-required` case.

### Edit 4 — References
- Promoted `tests/property/test_bundle_determinism.py` to "THE canonical pattern to mirror".
- Added `src/codegenie/transforms/outcomes.py` (the shipped union) and `tests/fixtures/repos/_portfolio.py` (the manifest).
- Corrected the orchestrator reference (driven via the S6-05 CLET, not hand-constructed).

### Edit 5 — Goal — rewritten to the seed-based strategy + `_determinism_key` + teeth-check + relevant-re-classification paired test.

### Edit 6 — Acceptance criteria — replaced the 13 unnumbered bullets with AC-1..AC-15 (per the findings above).

### Edit 7 — Implementation outline — rewrote the strategy/property/paired-test steps; `tests/property/conftest.py`; `_determinism_key`; CLI-driven `_run_workflow`.

### Edit 8 — TDD plan — replaced the Red code block (imports `PORTFOLIO`, `outcomes.py` variants; `st.integers` seed; `_determinism_key` `match`; perturbed concurrency; mutation guard; corrected paired test). Green/Refactor updated.

### Edit 9 — Files to touch — `tests/conftest.py` → `tests/property/conftest.py`; `pyproject.toml` edit (register `slow` marker).

### Edit 10 — Out of scope — performance-budget bullet rewritten to be honest about the 200-jailed-run cost.

### Edit 11 — Notes for the implementer — rewritten: mirror the sibling, the shipped-union comparison surface, CLI-driven workflow, concurrency perturbation, cold caches, relevant re-classification, masking-helper extraction opportunity.

## Verdict rationale

HARDENED. The story's goal — an offline-only Hypothesis determinism property over the 5 CVE fixtures, verifying Goal G4 — is correct, well-motivated, and traces cleanly to the arch and ADR-0008. Every defect is mechanism-layer (a comparison surface that does not exist, a strategy that cannot deliver its count, a paired test wrong by construction, a re-declared list, a misplaced conftest) — all fixable in place without touching the goal or scope. Two of the findings are block-class in severity but each had a clean, unambiguous in-place fix (the shipped `RemediationOutcome` shape and the sibling `st.integers` pattern are both authoritative and in-repo), so the story is repaired, not rescued.

## Recommended next step

`phase-story-executor` to implement. The executor must, before writing code, read `src/codegenie/transforms/outcomes.py` (the shipped `RemediationOutcome` variants), `tests/property/test_bundle_determinism.py` (the pattern to mirror), and the S6-04 / S6-05 / S8-02 attempt logs (to confirm the `codegenie remediate` CLI surface, the `Validated.branch` shape, and the on-disk report path).
