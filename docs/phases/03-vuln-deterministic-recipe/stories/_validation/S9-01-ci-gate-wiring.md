# Validation report: S9-01 — Phase 3 CI gate wiring

**Validated:** 2026-05-20
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1 (autonomous run via story-validation-corrector scheduled task)
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S9-01-ci-gate-wiring.md`

## Summary

S9-01 wires the remaining Phase 3 structural invariants into CI as hard-block gates. The story's **goal is sound and traces cleanly** to High-level-impl Step 9 and the phase exit criteria — but the story had **drifted hard** from shipped reality between authoring (`phase-story-writer`) and validation. Sibling stories shipped roughly half of the originally-prescribed surface, and several ACs directly contradicted shipped code. All four critics independently reached the same conclusion: HARDEN, not RESCUE — every block is a stale-AC-vs-shipped-state reconciliation, not a broken goal. The story was rewritten in place: Contract A removed from scope (already shipped as two contracts by S1-05), `tests/fence/`/`make check` wiring removed (already shipped by S1-05), the "6-job CI" matrix work retargeted to the one real gap (the 12-job workflow already matrixes test/typecheck coverage), and Contracts B/C reframed from kernel-edit-per-plugin `import-linter` enumeration to mechanism-agnostic Open/Closed observables. 17 findings addressed (7 block, 8 harden, 2 nit).

## Findings by critic

### Coverage critic

- **F1 (block)** — AC-1 (`make check` runs Phase 3 fence) verifies nothing: `Makefile §fence` already globs `tests/fence/` and `check` already chains `fence`. Shipped by S1-05.
- **F2 (block)** — AC-2 Contract A contradicts shipped reality (two contracts vs one); the story's own meta-fence would be RED on a correct tree forever.
- **F3 (block)** — Contract C targets `codegenie.plugins.subgraph`, which does not exist (S6-03 not GREEN); `import-linter` errors on an unresolvable module.
- **F4 (block)** — Contract B enumerates plugin packages that do not exist (`plugins/` holds only `__init__.py` + `PLUGINS.lock`).
- **F5 (harden)** — AC-3 "fails with a contract-name-specific diagnostic when violated" has no planted-injection test; precedent `test_lint_imports_catches_planted_leak.py` exists.
- **F6 (block)** — CI matrix AC verifies nothing: the 12-job workflow already matrixes the canonical lanes; "six-job CI" is stale.
- **F7 (harden)** — `bubblewrap` install prescribed for "the `test` job" but `tests/integration/` runs in the `integration` lane; gate and install can land in different jobs. S4-02's own test is never audited for fail-loud.
- **F8 (harden)** — Negative space: the meta-fence does not assert `as_packages` or contract-removal detection.
- **F9 (harden)** — `make lint-imports` is not in the `make check` chain; the documented local gate has a hole vs CI.
- **F10 (harden)** — `Depends on: S8-04` does not cover the real dependency cliffs (S6-03 subgraph, S7-01..04 plugins).

### Test-Quality critic

- **F1 (block)** — The Contract-A red test pins a single-contract shape contradicting the shipped two-contract reality; RED-for-the-wrong-reason, and a "green" fix would break two existing tests.
- **F2 (block)** — The Contract-B red test asserts only a name substring; a contract named correctly with `forbidden_modules=[]` passes while enforcing nothing. Mutation-blind.
- **F3 (block)** — AC-3's "the contract catches a deliberate violation" is marked *optional* in the outline; for a load-bearing gate that is the only test proving the gate fires. `test_lint_imports_catches_planted_leak.py` is the pattern to copy.
- **F4 (harden)** — `test_bwrap_present.py`: the macOS branch is untested; import-time vs function-time contradiction between AC and snippet; the platform decision should be a pure helper.
- **F5 (harden)** — `test_ci_workflow.py` extension under-specified; the existing `any()`-across-jobs matrix test would not catch a matrix removed from one job; job names need reconciliation.
- **F6 (nit)** — The Red section describes an environment-dependent RED (bwrap test skips on macOS).

### Consistency critic

- **F1 (block)** — Context "make check ... does NOT yet run [Phase 3 fence tests]" is false; shipped by S1-05 and pinned by `test_fence_target_wiring.py`.
- **F2 (block)** — Contract A: single-contract spec contradicts the shipped two-contract decomposition pinned by `test_phase3_importlinter_contracts_shape.py`.
- **F3 (block)** — Implementation outline step 1 / Files-to-touch prescribe creating `tests/fence/__init__.py`, which already exists (would clobber).
- **F4 (block)** — Stale "six-job CI" / matrix claims contradict the 12-job workflow; `mypy`/`unit`/`integration`/`portfolio` already matrixed.
- **F5 (block)** — Contracts B/C reference modules/packages that do not exist; `import-linter` errors hard; `--` in plugin dir names raised as a possible mechanism issue (NEEDS RESEARCH — resolved below).
- **F6 (block)** — `import-linter root_packages = ["codegenie"]` omits `plugins`; B/C contracts referencing `plugins.*` would not resolve.
- **F7 (harden)** — Dependency cliff: S9-01 cannot execute while the S5-02→S8 chain is BLOCKED.
- **F8 (harden)** — No matrixed CI job actually invokes `make check` or `tests/fence/`; the new fence test would run 3.11-only.

Consistency critic explicitly recommended HARDEN, not RESCUE: "every finding is a stale-AC-vs-shipped-state reconciliation, not a broken goal."

### Design-Patterns critic

- **F1 (block)** — Contract B as enumerated `import-linter` rows is a kernel-edit-per-plugin anti-pattern (Hard-coded extension point / Open-Closed violation); contradicts CLAUDE.md "Extension by addition". Codebase precedent for the Open/Closed alternative: `test_plugins_sandbox_path_purity.py` (auto-discovering AST fence).
- **F2 (harden)** — Contract C has the same enumeration smell; can fold into the AST fence, or use `source_modules = ["plugins"]` + `as_packages = true` (auto-covers sub-packages).
- **F3 (block)** — Story is stale (Contract A shipped) and silently omits the `root_packages` extension.
- **F4 (harden)** — Duplicated `_FORBIDDEN_LLM` set in the red test; the Refactor step points at a test constant, not the production source-of-truth `codegenie._fence.FORBIDDEN_LLM_SDKS`.
- **F5 (nit)** — `fence-phase3` vs extend-`fence` ambiguity is already resolved by the Makefile (`fence` globs `tests/fence/`).
- **F6 (nit)** — `make ci-locally` convenience target is premature (Rule 2).
- **F7 (harden)** — Meta-fence hard-codes a fixed contract count/names; brittle and re-pays per plugin.

## Research briefs

No Stage-3 research was required. The one finding raised as NEEDS RESEARCH (Consistency F5 — whether `--`-containing plugin directory names are expressible as `import-linter` module paths) was resolved from codebase evidence: `plugins/loader.py` loads plugins via `importlib.import_module("plugins.{slug}.api")`, and the codebase already ships an auto-discovering AST-walk fence (`test_plugins_sandbox_path_purity.py`) that sidesteps the question entirely. The hardened ACs make the gate mechanism-agnostic and recommend the AST fence, so the import-linter-over-hyphenated-modules question does not need to be settled to execute the story.

## Conflict resolutions

- **Coverage F9 (`make lint-imports` not in `make check`) vs. the `Makefile` comment that deliberately keeps `lint-imports` separate.** Resolved per Consistency priority and Rule 11 (match the codebase): the validator did NOT mandate adding `lint-imports` to `check`. AC-12 instead requires the implementer to *decide and document* — either wire it in, or record in §Out of scope why it stays separate. Surface the choice; don't force it.
- **Design-Patterns F1 (introduce an AST fence) vs. Rule 2 (no premature abstraction).** The rule-of-three is already crossed — three plugins are a planned family (vuln-npm, universal-fallback, example-noop) — so the zero-config-edit-per-new-plugin observable is a justified AC, not pattern-fetish. The AC names the *observable behaviour*, not the pattern; the mechanism recommendation lives in Notes for the implementer.
- **All four critics vs. the ">3 blocks → likely RESCUE" heuristic.** Seven block findings would, by the editor's count heuristic, suggest RESCUE. Overridden: the dispositive RESCUE test is "do the fixes require rewriting the *goal*?" — they do not. Every block is a stale-AC reconciliation patchable in place. All four critics independently recommended HARDEN. Verdict: HARDENED.

## Edits applied

The story was substantially rewritten in place (a near-total reconciliation — the goal and story identity preserved, the scope reconciled with shipped reality). Key edits:

1. **Title + Goal** — narrowed to the genuinely-remaining work (cross-plugin isolation, subgraph isolation, bwrap substrate, 3.12 fence coverage). "Three new contracts" → the real net-new surface.
2. **`Depends on:`** — `S8-04` → `S6-03, S7-01..S7-04, S8-04` (the stories that actually land `codegenie.plugins.subgraph` and the concrete plugin directories). — Coverage F10, Consistency F7.
3. **`Validation notes` block** — added under the header per skill format.
4. **Context section** — rewritten to be factually accurate: `make check`/`fence` already wired; Contract A already shipped as two contracts; the 12-job CI topology; an explicit "import-linter vs AST fence" subsection. — Consistency F1/F2/F4, Design-Patterns F1.
5. **AC-1** — reconciled from "create `tests/fence/__init__.py`" to "the new fence test is collected by the already-wired `make fence`/`make check`". — Coverage F1, Consistency F1/F3.
6. **AC-2** — rewritten to declare Contract A explicitly out of scope (shipped by S1-05). — Coverage F2, Test-Quality F1, Consistency F2, Design-Patterns F3.
7. **AC-3 / AC-4** — Contracts B/C reframed as mechanism-agnostic observables with an explicit "adding a new plugin requires zero edits to the gate's configuration" clause. — Design-Patterns F1/F2.
8. **AC-5** — planted-violation behavior test made mandatory, one per gate, modeled on `test_lint_imports_catches_planted_leak.py`. — Coverage F5, Test-Quality F2/F3.
9. **AC-6** — bwrap install retargeted from "the `test` job" to "every Linux job that runs `tests/integration/`" (the `integration` lane). — Coverage F7, Consistency F8.
10. **AC-7** — `test_bwrap_present.py` hardened: pure `_bwrap_required(platform)` helper, table-tested on both OSes; import-time vs function-time resolved to function-time. — Test-Quality F4.
11. **AC-8** — added: S4-02's `BwrapAdapter` test audited for fail-loud-not-skip. — Coverage F7.
12. **AC-9** — retargeted matrix work to the one real gap: the new `tests/fence/` gate must run on 3.11 + 3.12 (legacy-job matrix expansion explicitly excluded). — Coverage F6, Consistency F4/F8.
13. **AC-10** — `test_ci_workflow.py` extension specified concretely: per-job (not `any()`) assertions, step-index ordering, job-name reconciliation. — Test-Quality F5.
14. **AC-11** — meta-fence: extend the existing `test_phase3_importlinter_contracts_shape.py`, assert `as_packages` + content, import `FORBIDDEN_LLM_SDKS` from the source-of-truth. — Coverage F8, Design-Patterns F4/F7.
15. **AC-12** — added: `make lint-imports` local-gate decision must be made and documented. — Coverage F9.
16. **TDD plan** — the Contract-A red test deleted; new cross-plugin/subgraph gate red test + planted-violation test + table-tested bwrap helper written; determinism of the RED stated honestly. — Test-Quality F1/F2/F3/F6.
17. **Implementation outline / Files to touch / Out of scope / Notes** — rewritten to match: `tests/fence/__init__.py` and `fence-phase3` struck; `make ci-locally` dropped; the import-linter `root_packages` requirement surfaced; the hard upstream-dependency precondition surfaced. — Consistency F3/F5/F6, Design-Patterns F5/F6.

## Verdict rationale

HARDENED. The story's goal — wire the remaining Phase 3 invariants into CI as hard-block gates — is coherent and traces to High-level-impl Step 9. Every weakness was either (a) drift from shipped reality, fixable by reconciling the AC with what S1-05/S8-03 already landed, or (b) a design-shape issue (enumerated import-linter contracts) fixable by reframing the AC as a mechanism-agnostic Open/Closed observable. None required rewriting the goal. The rewrite shrank the scope to the genuinely-remaining surface and made the upstream dependency on S6-03 + S7-01..S7-04 honest.

## Recommended next step

- The story is HARDENED and ready for `phase-story-executor` — **but it has a hard precondition**: S6-03 (ships `codegenie.plugins.subgraph`) and S7-01..S7-04 (ship the concrete plugin directories) must be GREEN first. Per CLAUDE.md the Phase 3 `S5-02 → S8` engine chain is currently BLOCKED pending a `/phase-architect` decision. Until that resolves and S6-03/S7-0x are GREEN, S9-01 is not executable; if picked up early it should be marked `BLOCKED` like its predecessors. This is a phase-sequencing gate, not a story-quality defect.
