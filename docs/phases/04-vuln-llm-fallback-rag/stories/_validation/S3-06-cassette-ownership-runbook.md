# Validation report: S3-06 — CODEOWNERS + cassette runbook + `make refresh-cassettes`

**Validated:** 2026-05-21 — phase-story-validator v1
**Verdict:** HARDENED
**Story:** `docs/phases/04-vuln-llm-fallback-rag/stories/S3-06-cassette-ownership-runbook.md`

## Summary

S3-06 ships the fourth (human) layer of ADR-0014's cassette discipline: a `.github/CODEOWNERS`
gate, a `docs/operations/cassettes.md` runbook, and a `make refresh-cassettes` operator
ergonomic. The goal is sound and every AC traces to it — this is a HARDENED, not a RESCUE.

The draft had four classes of real, fixable weakness:

1. **A factual error.** The story asserted `.github/CODEOWNERS` does not exist and must be
   *created*. It already exists (Phase 0 + Phase 3 rules, single owner `@Dannytrev21`). The
   story must *amend* it. This error cascaded into AC-1's `@<placeholder>` and an
   implementation step ("pause to ask the user for the steward handle") that an autonomous
   executor cannot perform — and need not, because the handle (`@Dannytrev21`) is already
   in the repo.
2. **An untestable branch.** The draft's `make refresh-cassettes` bundled the cheap policy
   gate with the expensive `pytest --record-mode=all` + live-API recording, so no test could
   prove the gate *passes* with the acknowledgement set without spending real tokens. Only
   the block branch was tested; an `exit 2`-always mutant would have shipped green.
3. **Thin / unverifiable ACs.** "or a manual test" (AC-9) and "or skip if no good linter
   exists" (AC-16) escape hatches; a CODEOWNERS test that passed on an invalid `@<…>`
   placeholder; a runbook test covering 7 of 9 sections by prose substring.
4. **Consistency drift.** Context vs AC-7 disagreed on the acknowledgement spelling; the
   `cassette-review` vs single-human `cassette-steward` tension with ADR-0014 was unflagged;
   the nightly drift job was mis-scoped to Phase 6.5 (ADR-0005 §Consequences puts it in
   Phase 4); `make docs --strict` is a make-flag error.

All were patched in place. The story is now ready for the executor.

## Context brief

- **Goal:** Make cassette regeneration explicit, traceable, reviewable — one canonical runbook.
- **Family:** 4th and final layer of ADR-0014 cassette discipline (after S3-04 sanitizer,
  S3-05 lock + scanner). Sibling validations S3-04 and S3-05 both HARDENED; S3-05's report
  established the ordering S3-04 → S3-05 → S3-06 → S3-02 AC-19 (live cassette bytes are
  deferred until the discipline stack + refresh workflow exist). S3-06's Notes already
  reflect this — consistent.
- **Source-of-truth docs read:** ADR-0014 (full), ADR-0005 §Decision + §Consequences,
  `phase-arch-design.md` §Component 12 + §Gap analysis Gap 2, `Makefile`, `.github/CODEOWNERS`,
  `tests/unit/test_project_artifacts.py`, `pyproject.toml` markers block.

## Findings by critic

### Coverage critic

- **F1 `block`** — no test for the with-flag (refresh-works) path; an unconditional `exit 2`
  ships green. (Coverage proposed a `make -n` dry-run test — **rejected** during synthesis:
  `make -n` does not execute the recipe's shell `if`, so it cannot distinguish flag-set from
  flag-unset. Test-Quality's gate-extraction is the correct mechanism.)
- **F2 `block`** — AC-1's "no placeholder" rule was prose-only; the CODEOWNERS test checked
  paths, not owner tokens, so a literal `@<…>` could ship.
- **F3 `harden`** — runbook section test covers 7 of 9 AC-5 sections.
- **F4 `harden`** — AC-9 / AC-16 "or manual / or skip" escape hatches.
- **F5 `harden`** — AC-15 `make docs --strict` wording is a make-flag error.
- **F6/F7 `nit`** — AC-8 marker attachment untested; `docs/contributing.md` conditional
  ("if it exists") — it does exist.

### Test-Quality critic

- **TQ-1 `block`** — gate's pass branch untestable without spending tokens; extract a
  `_refresh-cassettes-gate` phony prerequisite that does *only* the `@if` check, so both
  branches are tokenlessly testable. Provided drop-in tests.
- **TQ-2 `harden`** — `test_codeowners_…` passes on the invalid `@<placeholder>` syntax.
- **TQ-3 `harden`** — runbook test: 7/9, prose substring not heading-shaped.
- **TQ-4 `harden`** — the story's Notes overstate the gate: `make` imports env vars and
  command-line vars into `$(VAR)` identically, so the gate is intentional friction, not an
  isolation boundary. Prose must not claim an env-var bypass is blocked.
- **TQ-5 `harden`** — AC-8/10/11/16 had no tests; mutant recipes ship green. Provided
  static recipe-body assertions in the `test_makefile_targets.py` style.

### Consistency critic

- **F-CODEOWNERS `harden`** — factual error: `.github/CODEOWNERS` already exists; the story
  must amend, not create.
- **F1 `harden`** — internal contradiction (Context says `--i-understand-this-spends-tokens`;
  AC-7 uses the make variable `I_UNDERSTAND_THIS_SPENDS_TOKENS=1`) + an unflagged deviation
  from ADR-0014 §Decision item 6. The make-variable choice is correct (`make` cannot accept
  `--flags`) but must be *stated* as a deviation.
- **F2 `harden`** — ADR-0014 §Decision writes the owner as the team-shaped `cassette-review`;
  Gap 2 supersedes it with a single-human `cassette-steward`. The story implements Gap 2 but
  did not name the override.
- **F4 `nit`** — `refresh-cassettes` must be declared `.PHONY` (`test_makefile_targets.py`
  asserts every target is `.PHONY`). Recipe is POSIX-`/bin/sh`-clean (no bash-isms) — verified.
- **F5 `harden`** — nightly drift job mis-scoped to Phase 6.5; ADR-0005 §Consequences:
  "the nightly drift job is in scope for Phase 4's CI surface." Phase 6.5 owns only the
  bench harness *reading* `cassettes.lock`.
- **F7 `clean`** — no LLM-fence or CLAUDE.md-commitment violation; `refresh-cassettes` is an
  operator-only dev path, not in the gather-pipeline runtime closure.

### Design-Patterns critic

- **DP-1 `nit`** — recommended keeping the gate inline (no second token-spending consumer;
  `refresh-goldens` is CODEOWNERS-gated only, no token spend → rule-of-three count is one).
  **Overridden** — see Conflict resolution.
- **DP-2 `harden`** — `Files to touch` omits S3-02's cassette-recording test file (AC-8
  requires decorating it); without the marker, `make refresh-cassettes`'s `-m` selector
  matches zero tests — a silent no-op.
- **DP-3 `nit` (affirm)** — per-vendor marker is the right extension-by-addition seam; a
  `--vendor` parameter would be premature. Kept.
- **DP-4 `harden`** — AC-5 §5 re-pinned the `cassettes.lock` byte format that S3-05 owns and
  `phase-arch-design.md` pins as a stable contract; two normative copies drift. Reference,
  don't restate.
- **DP-5 `nit` (affirm)** — the only Python (the test file) is clean; no type issues.

## Conflict resolution

**TQ-1 (`block`, extract the gate) vs DP-1 (`nit`, keep it inline).** Resolved in favour of
**TQ-1 — extract `_refresh-cassettes-gate`.** Two reasons:

1. *Skill priority.* Test-Quality outranks Design-Patterns when they conflict.
2. *Substance.* DP-1's claim that extraction "buys nothing testable" analysed only the
   block branch — for which DP-1 is right that the two targets are equivalent. But the
   **pass branch** is genuinely unreachable without extraction: running the whole
   `refresh-cassettes` recipe with the acknowledgement set fires `pytest --record-mode=all`
   against the live API. Extraction is therefore not speculative abstraction (no Rule 2
   violation) — it is load-bearing for coverage of a real branch. It is functional-core /
   imperative-shell at the Makefile level: pure policy split from the side effect.

DP-1's underlying YAGNI instinct is preserved as a Notes-for-implementer line: if a *second*
token-spending target ever appears, generalise the `@if` into a shared `_token-spend-gate:`
prerequisite *then* (rule of three), not now.

Coverage's F1 `make -n` fix was also rejected (mechanically wrong — `make -n` prints the
recipe without executing the shell `if`, so it cannot distinguish the branches).

No `NEEDS RESEARCH` findings — every fix uses techniques already in `test_makefile_targets.py`
and `test_project_artifacts.py`. Stage 3 (researcher) skipped.

## Edits applied

| # | Location | Before → After |
|---|---|---|
| 1 | Header | `Status: Ready` → `HARDENED`; added a `Validation notes` block. |
| 2 | Context (item 3) | Acknowledgement described as `--i-understand-this-spends-tokens` flag → make variable `I_UNDERSTAND_THIS_SPENDS_TOKENS=1`, with the ADR-0014 deviation stated inline. |
| 3 | References | "no existing CODEOWNERS — create it" → "`.github/CODEOWNERS` already exists — amend it"; added the `test_project_artifacts.py` `GITHUB_USER_RE` / `_parse_codeowners` reuse pointer, the POSIX-sh / `.PHONY` Makefile contract, and the `docs/contributing.md`-exists fact. |
| 4 | AC-1 | "create … `@<placeholder>` … pause to ask the user" → "amend … `@Dannytrev21` … MUST NOT contain a literal `@<…>` placeholder". |
| 5 | AC-2 / AC-3 | AC-3 gained the `cassette-review` → `cassette-steward` deviation note (flags ADR-0014 §Decision for a doc cleanup). |
| 6 | AC-5 §5 | Re-pinned `cassettes.lock` byte format → one-line illustration + pointer to S3-05 as source-of-truth. |
| 7 | AC-7 | Single `refresh-cassettes` target → two targets: `_refresh-cassettes-gate` (pure policy) + `refresh-cassettes` (action, depends on the gate); `.PHONY` requirement; ADR-0014 deviation comment in the recipe. |
| 8 | AC-8 | Marker registration sharpened; S3-02 test decoration made explicit with a `BLOCKED` path if the file is absent. |
| 9 | AC-9 | "test via subprocess shim or a manual test" → both branches verified automatically via `_refresh-cassettes-gate`. |
| 10 | AC-11 → +AC-20, +AC-21 | New AC-20 (static recipe-body assertions: records + rebuilds + gate prerequisite) and AC-21 (`-m uses_anthropic_cassette --collect-only` collects ≥ 1 — guards the silent no-op). |
| 11 | AC-13 | "if `docs/contributing.md` exists, otherwise inline" → it exists; note lands there. |
| 12 | AC-14 | Single without-flag test → full enumerated safety + shape suite (block / pass / prerequisite / recipe body / CODEOWNERS / runbook / marker). |
| 13 | AC-15 | `make docs --strict` (make-flag error) → `make docs`; added internal-cross-link coverage note. |
| 14 | AC-16 | "use a linter if available, or skip" → a concrete in-repo CODEOWNERS well-formedness test (owner-token shape; no `<`/`>` placeholder). |
| 15 | TDD plan — Red | 3 thin tests → 9 mutation-aware tests with per-test mutation-intent comments; reuses `OWNER_RE` / `_recipe_body` / `tomllib`. |
| 16 | Implementation outline | Step 1 rewritten (amend, real handle, no pause); gate-extraction + S3-02 marker + contributing.md steps added. |
| 17 | Files to touch | Added a Create/Modify column; CODEOWNERS marked Modify; added S3-02 test file + `docs/contributing.md` rows. |
| 18 | Out of scope | Nightly drift workflow corrected from "Phase 6.5" → Phase-4 CI scope (ADR-0005 §Consequences); out of scope for S3-06 specifically. |
| 19 | Notes for implementer | Handle note rewritten (`@Dannytrev21`); env-var-vs-make-variable claim corrected (gate is friction, not isolation); `make docs --strict` fixed; gate-extraction rationale added. |

## Verdict

**HARDENED.** The goal was always sound and every AC traced to it; the weaknesses were a
factual error, one untestable branch, several thin/escape-hatch ACs, and unflagged
ADR deviations — all patched in place. The story is ready for `phase-story-executor`.

Two carry-forwards for the executor's attention:

- **AC-8 / AC-21 depend on S3-02's recording tests existing.** If that test file cannot be
  located, the correct outcome is `BLOCKED` — do not weaken the marker-attachment test.
- **AC-3 asks for a doc cleanup of ADR-0014 §Decision** (`cassette-review` → `cassette-steward`).
  That ADR edit is small and in-scope as a consistency fix, but if the executor prefers to
  keep S3-06 surgical it may instead flag it for a follow-up — either way the divergence
  must not be left silent.
