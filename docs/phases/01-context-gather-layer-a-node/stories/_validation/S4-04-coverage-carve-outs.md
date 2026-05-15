# Validation report — S4-04 Coverage carve-outs declared in `pyproject.toml`

**Story:** [S4-04-coverage-carve-outs.md](../S4-04-coverage-carve-outs.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S4-04 is the smallest story in Step 4 — pure infrastructure config + a tiny enforcement script (Effort: S). The story was directionally correct (ADR-0005 cleanly pinned, the carve-out floors right, the order-with-S6-02 right) but had three load-bearing weaknesses that would have let a wrong implementation land silently:

1. **Mechanism fabrication risk (CV-1 / CN-2).** The original Implementation outline mentioned `pytest-cov`'s `--cov-fail-under-file=...` (a flag that does **not exist**), and the High-level-impl.md text mentioned `[tool.coverage.report] exclude_also` (which *removes lines from coverage measurement* — the **opposite** of declaring a per-module floor). `[tool.coverage.paths]` is path-aliasing, not thresholds. `coverage.py`'s `fail_under` is **global only**. There is no native per-module-floor mechanism in either tool, so the "implementer's call" in AC-1 was vacuous: the answer is almost always a custom script, and the original story did not say so. An implementer trusting the outline could easily have written a config that does nothing at all, or worse, that excludes both modules from coverage entirely.
2. **Stale ratchet-plan comment in `pyproject.toml` (CN-1).** Lines 175–177 currently say *"Phase 1 bumps to 87/77, Phase 2 to 90/80"* — a plan that contradicts ADR-0005, which makes Phase 1 the 90/80 ratchet with 85/75 carve-outs (no 87/77 intermediate). The story did not mention this comment at all, even though it lives in the file the PR touches. Rule 7 (surface conflicts, don't average them) + Rule 12 (Fail loud) — leaving the stale prose in place tells the next reviewer to keep things at 85/75 when they read the carve-out config.
3. **Manual red-phase only (TQ-1 / CN-3).** ADR-0005 §Decision says *"CI fails if any module drops below its declared floor."* The original red-phase was a manual toggle that was reverted before commit — zero permanent CI signal. If the script (or the chosen mechanism) regresses, or someone deletes the carve-out table, no test fires. Rule 12 violation in spirit.

Plus three smaller findings: AC bundling (AC-5 conflated runtime checks with config claims), the rationale comment requirement was too thin (a path-only pointer, no substantive reason), and a registry-pattern lift opportunity at the config-file boundary (the same two entries would otherwise live in three places — `pyproject.toml`, the script's constants, the test's expectations).

The synthesizer rewrote the original **8 bundled ACs** into **14 individually-verifiable ACs** organised into four groups (Mechanism / Comments / Enforcement test / Land-time conditions / Hygiene). The TDD plan went from **3 manual phases with no permanent tests** to **11 named permanent tests** under `tests/unit/build/test_coverage_carve_outs.py`. The design-pattern lifts (data-driven TOML registry + functional-core/imperative-shell split for the script) were surfaced in *Notes for the implementer* — not elevated to ACs — because with only two consumers today the Rule of Three is **not** met and Rule 2 (Simplicity First) governs.

**No `NEEDS RESEARCH` findings.** Every weakness was resolvable from authority docs (ADR-0005 + phase-arch-design + High-level-impl + `pyproject.toml` itself + general knowledge of `coverage.py` / `pytest-cov` capabilities). Stage 3 skipped per skill's token-economy guidance.

For a one-file-edit story the four critic subagents would have burned tokens disproportionate to the work; the four lenses (Coverage / Test-Quality / Consistency / Design-Patterns) were applied inline by the validator. The findings are tagged with the lens that produced them so the report is auditable in the standard shape.

## Critic findings

### Coverage (CV-)

- **CV-1 [block] — Mechanism fabrication.** Original AC-1: *"`pytest-cov`'s per-file thresholds via `--cov-fail-under-file=...` if the plugin version supports it (preferred)"*. **This flag does not exist** in any released version of `pytest-cov`. `coverage.py`'s `fail_under` is global only. There is no native per-module-floor mechanism. The "implementer's call" framing made this an under-specified AC: a trusting executor could write a useless config. **Resolution:** new AC-1 explicitly names the three fabricated mechanisms as **not acceptable**, and pins the actual options (custom script vs. a verified native flag with cited version-specific docs). New AC-10 wires the chosen mechanism to the CI `test` job.
- **CV-2 [harden] — AC-5 conflated runtime + config.** Original AC-5 bundled "CI runs the test job" + "local coverage shows the actual percentages" + "if below floor, add tests to the parent probe's PR" into one bullet. **Resolution:** split into AC-13 (PR body lists percentages — config-time claim) and AC-14 (do-not-merge if below floor — reviewer check).
- **CV-3 [harden] — Negative behaviour not pinned.** No AC asserted *"the gate fails when a module dips below floor"*. AC-6 (original) made this manual. **Resolution:** lifted to AC-7 (automated, synthetic-data test).
- **CV-4 [block] — Stale `87/77` ratchet-plan comment unaddressed.** `pyproject.toml` line 175–177 plan contradicts ADR-0005. Story did not mention. **Resolution:** new AC-9 requires rewriting the comment in this PR. (Promoted to CN-1 because the dominant lens is Consistency.)
- **CV-5 [harden] — Rationale comment was a thin pointer.** Original AC-3 required the inline comment reference ADR-0005 by path; that's it. A future contributor reads the comment, sees `# see ADR-0005`, and has to chase the ADR cold to understand why the floor exists. **Resolution:** new AC-8 requires three substrings (the literal `ADR-0005`, the gameability rationale, the ADR-amendment-required clause).

### Test-Quality (TQ-)

- **TQ-1 [block] — Manual red-phase only.** No permanent test. Mechanism not guarded in CI. Rule 9 / Rule 12 violation. **Resolution:** new `tests/unit/build/test_coverage_carve_outs.py` with 11 named tests. AC-6, AC-7, AC-10 codify what each covers.
- **TQ-2 [harden] — Verification via simulated 90/80 (future state).** The original red-phase toggled the global from 85 to 90 locally to confirm the carve-out caught `ci.py` — but this verifies a state that isn't current. **Resolution:** new TDD tests 6–10 feed `check()` synthetic `coverage.json`-shaped dicts directly; no state-toggling required. The CLI-shape smoke test (test 10) runs `python scripts/check_coverage_carve_outs.py` as a subprocess once for the end-to-end exit-code shape.
- **TQ-3 [harden] — CI wiring not asserted.** Even if a script exists and works, nothing asserts CI actually invokes it. **Resolution:** new AC-10 + TDD test 11 grep the workflow file for the script name (or skip with reason if native mechanism chosen).

### Consistency (CN-)

- **CN-1 [block] — `pyproject.toml` 87/77 comment contradicts ADR-0005.** Already covered above (CV-4). The conflict is between two co-located authorities: the comment in the file the PR touches vs. ADR-0005 (the source of truth for coverage policy in Phase 1). ADR wins. **Resolution:** AC-9 rewrites the comment to match ADR-0005 while explicitly preserving the S4-04 / S6-02 sequencing (this PR does NOT raise the global to 90/80; S6-02 does).
- **CN-2 [block] — High-level-impl.md §Step 6 mentions `exclude_also` as the carve-out home.** `exclude_also` is a `coverage.py` setting that removes matching lines from coverage measurement entirely — it would silently raise the apparent coverage of both modules to 100% by not measuring them, which is the **opposite** of declaring an 85/75 floor. The story acknowledged this in implementation outline prose but did not lift it to an AC. **Resolution:** AC-1 explicitly names `exclude_also` as not acceptable.
- **CN-3 [block] — "CI fails if any module drops below floor" was prose-only.** ADR-0005 §Decision pins the negative behaviour as a contract. **Resolution:** AC-7 makes it a permanent automated test with concrete synthetic data.
- **CN-4 [nit] — Mechanism choice left to runtime.** The "if mechanism requires" hedge in Files-to-touch effectively allowed the script to be omitted. Given coverage.py / pytest-cov realities, the script is effectively required. **Resolution:** Files-to-touch now says *"Almost certainly required — omit only if a native mechanism is found and verified"* and AC-10 requires the PR body to cite the docs URL when a native mechanism is claimed.

### Design-Patterns (DP-)

- **DP-1 [Notes-only — registry-at-config-boundary].** The carve-out list lives in `pyproject.toml` *and* the script's logic *and* the test's expectations. Inlining the same data in three places sets up a drift class (a future Phase 2 PR updates one, forgets the others). Reading the data from `pyproject.toml` in both the script and the test centralises the source of truth at the config-file boundary — Open/Closed at the TOML layer, no Python registry class needed. **Resolution:** surfaced in *Notes for the implementer*. **Not** elevated to an AC because (a) Rule 2 (Simplicity First) governs at two consumers; (b) ADR-0005 requires every new carve-out be ADR-gated anyway, so the "easy to add" property is already friction-bounded.
- **DP-2 [Notes-only — functional-core / imperative-shell for the script].** `check()` pure, `main()` does I/O. Same discipline the probes use. Surfaced in *Notes for the implementer*; AC-6 / AC-7 test `check()` directly which forces the shape.
- **DP-3 [Notes-only — rename-survivability via dotted module names].** Original story flagged this concern but only as a prose note. **Resolution:** AC-2 now requires both file path **and** dotted module name be recorded, so a half-applied rename in Phase 2 breaks AC-7's synthetic-coverage test. *Notes for the implementer* adds a CODEOWNERS suggestion.

## Most load-bearing fixes (block-tier)

1. **CN-1 / CV-4 — Stale `87/77` ratchet-plan comment.** New AC-9 rewrites it in this PR. Test 4 enforces no `87/77` substring anywhere in `pyproject.toml`.
2. **CV-1 / CN-2 — Mechanism fabrication.** New AC-1 names the three fabricated mechanisms (`--cov-fail-under-file`, `[tool.coverage.paths]`, `exclude_also`) as **not acceptable** and pins the actual options.
3. **TQ-1 / CN-3 — Permanent automated test.** New `tests/unit/build/test_coverage_carve_outs.py` with 11 named tests (AC-6, AC-7, AC-10).
4. **CV-5 — Rationale comment with three substrings.** New AC-8: `ADR-0005` + gameability phrase + `Further carve-outs require a new ADR amending 0005.`
5. **DP-3 — Rename guard via dotted module name.** New AC-2 records both `path` and `module` per row.

## Design-pattern lifts elevated to ACs

None. All DP findings remained as *Notes for the implementer*. The story is small enough (two carve-outs, ~50 LOC script, one new test file) that Rule 2 governs and the Rule of Three is not met for any kernel extraction.

## Lifts surfaced in Notes only

- **DP-1 — TOML-table-as-registry.** Centralises the carve-out data at the config-file boundary so the script and the test read the same source.
- **DP-2 — Pure `check()` + imperative `main()`.** Same functional-core/imperative-shell discipline as the probes; the script is small enough that the seam costs nothing.
- **DP-3 — Rename-survivability.** Beyond AC-2's dotted-module-name field, a CODEOWNERS entry or a doc-string note in the script anchors the rename obligation.

## Conflicts resolved

- **CN-1 (pyproject.toml comment) vs. story scope (S4-04 doesn't raise the global).** Resolution: rewrite the comment **in this PR** but only to fix what is *currently wrong* — the comment must still say "global not raised in S4-04; S6-02 raises it"; it must not preemptively bake in 90/80. Consistency wins (Rule 7), bounded by Surgical Changes (Rule 3).
- **DP-1 (registry pattern) vs. Rule 2 (Simplicity First) and Rule 11 (Match conventions).** Resolution: surface as Notes, do not elevate. Two carve-outs do not justify a Python registry class; reading the data from TOML in two places is a zero-cost discipline.
- **High-level-impl.md §Step 6 "`exclude_also` or equivalent"** vs. **`coverage.py` reality.** Resolution: the doc text is loose; ADR-0005 is authoritative on intent (floor, not exclusion); AC-1 names `exclude_also` as not acceptable.

## Before / after AC count

- **Before:** 8 ACs, several bundled, one fabricated mechanism, manual-only red phase, no rationale-substance requirement, no rename-guard.
- **After:** 14 ACs in four named groups (Mechanism / Comments / Enforcement test / Land-time conditions / Hygiene), all individually-verifiable, every one with a corresponding TDD test or a PR-body / reviewer check.

## TDD plan size

- **Before:** 3 phases (Red manual / Green declare / Refactor), no permanent tests, mechanism guarded only by a one-shot manual toggle.
- **After:** 11 named permanent tests under `tests/unit/build/test_coverage_carve_outs.py`. `check()` is exercised directly with synthetic dicts (tests 6–9); the CLI shape is smoked once (test 10); the TOML table, comment substrings, stale-comment removal, and CI wiring are individually pinned (tests 2, 3, 4, 11).

## Verdict rationale

**HARDENED**, not RESCUE: the story's goal, scope, ADR alignment, and out-of-scope rules were all correct. The weaknesses were specification-level — vague ACs, fabricated mechanism options, manual-only verification, missed stale-comment cleanup. All resolvable by editing in place without changing the story's intent.

**HARDENED**, not STRONG: three block-tier findings (CN-1, CV-1/CN-2, TQ-1/CN-3) each required mandatory edits before the executor could safely execute.
