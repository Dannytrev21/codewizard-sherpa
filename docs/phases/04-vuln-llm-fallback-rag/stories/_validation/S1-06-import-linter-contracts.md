# Validation report — S1-06 import-linter contracts mirroring the fence

**Validated:** 2026-05-21
**Validator:** phase-story-validator (scheduled `story-validation-corrector` run)
**Verdict:** HARDENED
**Findings:** 12 — 4 block, 7 harden, 1 nit
**Stage 3 (research):** skipped — every finding was verified directly against the installed `import-linter 2.11`; no `NEEDS RESEARCH` items.

---

## Context brief

- **Goal:** add four `forbidden` import-linter contracts to `pyproject.toml` so `make lint-imports` enforces the same path-scoped admissions as the S1-05 pytest fence, at lint time.
- **Depends on:** S1-05 (HARDENED) — lands the path-scoped pytest fence, narrows `FORBIDDEN_LLM_SDKS`, and defines `GATHER_PIPELINE_PATHS` / `PHASE4_ADMITTED_PACKAGES` / `PHASE4_STILL_FORBIDDEN`.
- **ADR honored:** ADR-0003 — import-linter is the lint-time belt-and-suspenders alongside the test-time pytest fence.
- **Sibling-family lineage:** this is the **3rd** "ship an import-linter LLM-SDK contract" story in the repo. Phase-3 S1-05 shipped `codegenie.plugins` / `codegenie.transforms` contracts + `test_phase3_importlinter_contracts_shape.py`; Phase-7 S1-06 shipped the `codegenie.primitives.vuln_provenance` contract + `test_phase7_importlinter_contracts_shape.py`. The pattern (static `tomllib`-read shape-drift test) is **established** — matching it is mandatory, not optional (Rule 11).

## Verification performed

Run against the live repo + installed toolchain:

| Check | Result |
|---|---|
| `import-linter` version | 2.11 |
| `python -m importlinter` | **fails** — "No module named importlinter.__main__" |
| `lint-imports` CLI | console script; `[OPTIONS]` only, **no `lint` subcommand** |
| `forbidden` contract `unmatched_ignore_imports_alerting` default | **`AlertLevel.ERROR`** (`importlinter/contracts/forbidden.py`) |
| `pyproject.toml` `[tool.importlinter]` contract count | **six** `forbidden` contracts (story claimed two) |
| `tomli_w` | importable, but only as a **transitive** dep of `pip-audit` — not declared |
| `tests/fence/__init__.py` | exists |
| `tests/fence/test_phase3_importlinter_contracts_shape.py` | exists — the precedent |

---

## Findings

### Consistency

- **C1 — block — `as_packages = true` missing on contract #1.** AC-1.1 omitted `as_packages`. import-linter scans only a package's `__init__.py` unless `as_packages = true`; a violating probe submodule slips through. The Phase-3 contracts set it explicitly and `test_phase3_importlinter_contracts_shape.py` pins it. **Fixed:** AC-1 now requires `as_packages = true` on all four; TDD-plan TOML corrected.
- **C2 — block — `as_packages = true` missing/inconsistent on contracts #2–#4.** AC-1.2 prose mentioned it; AC-1.3/1.4 and *all* the TDD-plan green-section TOML blocks omitted it. With `source_modules = ["codegenie"]` and no `as_packages`, only `codegenie/__init__.py` is scanned — the contract is near-useless. **Fixed:** same as C1.
- **C3 — harden — stale Context claim.** Story Context said `pyproject.toml` has "two `forbidden` contracts (Phase-0 cold-start defense)." It has **six** (2 cold-start, 1 ADR-0013 `types.identifiers`, 2 Phase-3 LLM-SDK, 1 Phase-7 LLM-SDK). The relevant precedent is the Phase-3/Phase-7 LLM-SDK contracts. **Fixed:** References block updated.
- **C4 — block — cross-story hazard (Rule 7).** S1-05's narrowing of `FORBIDDEN_LLM_SDKS` breaks `test_phase3_importlinter_contracts_shape.py::test_contract_forbids_exactly_the_llm_sdk_closure` and the Phase-7 twin (they assert `set(forbidden_modules) == FORBIDDEN_LLM_SDKS`; the Phase-3/7 contracts still list `anthropic`, and the new hyphenated `sentence-transformers` distribution name can never set-equal the underscore import name). `make check` cannot be green until reconciled. **Fixed:** folded into AC-8 + a prominent Notes-for-implementer entry; flagged as in-scope for S1-06 (it owns import-linter contracts) with an escalation path.

### Coverage

- **V1 — block — AC-4's "forward-clean whitelist" premise is mechanically false.** import-linter's `forbidden` contract defaults `unmatched_ignore_imports_alerting = ERROR`. Pre-populated `ignore_imports` naming not-yet-existent modules makes `lint-imports` **error**, so `make lint-imports` would not exit 0. **Fixed:** AC-1 now ships contracts #2–#4 with `ignore_imports` omitted; AC-4 premise corrected; downstream stories (S3-02/S4-01/S4-03) append their own edge — recorded in Out-of-scope.
- **V2 — harden — `include_external_packages` asserted, not eyeballed.** AC-3 said "verified to remain present" with no check. **Fixed:** AC-6's shape test now asserts `include_external_packages is True`.
- **V3 — harden — no AC covered the Phase-3/Phase-7 reconciliation.** **Fixed:** see C4 → AC-8.

### Test Quality

- **T1 — block — TDD-plan negative test invoked a non-existent entrypoint.** `subprocess.run([sys.executable, "-m", "importlinter", "lint", …])` — `python -m importlinter` fails outright and there is no `lint` subcommand. `assert returncode != 0` would pass for the wrong reason; `assert name_substr in result.stdout` would fail. The contract would never actually be exercised. **Fixed:** the broken synthetic-subprocess test is replaced as the primary guard (T2); the optional live-fire test (AC-7) is specified to use the `lint-imports` console script.
- **T2 — harden — primary mutation guard was brittle with a coverage-cliff fallback.** AC-6 was a synthetic-tmp-pyproject `lint-imports` run; AC-7 was a manual-runbook fallback that erodes coverage. The codebase precedent (`test_phase3/7_importlinter_contracts_shape.py`) is a robust static `tomllib`-read shape test — Phase 3/7 shipped *only* that. **Fixed:** AC-6 rewritten as `test_phase4_importlinter_contracts_shape.py` mirroring the precedent; AC-7 demoted to optional, so dropping the live-fire test is no longer a coverage regression.
- **T3 — harden — undeclared `tomli_w` dependency.** The TDD plan did `import tomli_w`; `tomli_w` is only a transitive dep of `pip-audit`. **Fixed:** the shape test uses stdlib `tomllib` (read-only); `tomli_w` eliminated.
- **T4 — harden — `env=` replacement / `sys.path` collision in the synthetic test.** `env={"PYTHONPATH": …}` drops `PATH`/`HOME`; the editable-installed `codegenie` can shadow the synthetic tree. **Fixed:** AC-7 + Notes now require merging `os.environ` and warn about the collision (further reason the static shape test is the right primary guard).

### Design Patterns

- **D1 — harden — reinvented mechanism instead of consuming the convention.** **Fixed:** AC-6 mirrors `test_phase3_importlinter_contracts_shape.py` structurally (`_load()` helper, parametrized assertions).
- **D2 — harden — contracts not coupled to a source of truth.** Phase-3/7 shape tests pin `forbidden_modules` to `FORBIDDEN_LLM_SDKS`. The Phase-4 contracts have a different shape, but should pin to the Phase-4 fence constants. **Fixed:** AC-6 derives expected `source_modules`/`forbidden_modules` by **importing** `GATHER_PIPELINE_PATHS` / `PHASE4_ADMITTED_PACKAGES` / `PHASE4_STILL_FORBIDDEN` from the S1-05 fence module — the import IS the drift coupling.
- **D3 — nit — path-vs-module-name namespace mismatch.** `GATHER_PIPELINE_PATHS` is path strings; `source_modules` is dotted module names. **Fixed:** AC-6 + the TDD plan's `_path_to_module` helper translate explicitly; called out in Notes.

## Conflict resolution

No critic conflicts. Consistency C1/C2 (require `as_packages`) and Coverage V1 (empty `ignore_imports`) both push the same direction as Design-Patterns D1/D2 (mirror the precedent). The story's original synthetic-subprocess test was both a Test-Quality failure (T1, broken invocation) and a Design-Patterns failure (D1, ignores the convention) — replacing it with the shape test resolves both at once.

## Edits applied to the story

- Header `Status: Ready → HARDENED`; `Validation notes` block inserted.
- References — `[tool.importlinter]` entry corrected (six contracts; Phase-3/7 precedent named); Phase-3/7 shape-test files added as references.
- Acceptance criteria — fully restructured: AC-1 requires `as_packages = true` ×4 and empty `ignore_imports`; AC-3 asserts `include_external_packages`; AC-4 premise corrected; AC-6 rewritten as the shape-drift test; AC-7 demoted to optional live-fire; AC-8 absorbs the C4 cross-story reconciliation; AC-9/AC-10 hygiene.
- Implementation outline — rewritten (red shape test first; empty `ignore_imports`; cross-story reconciliation step).
- TDD plan — synthetic-subprocess test replaced with the `test_phase4_importlinter_contracts_shape.py` shape test; green-section TOML corrected (`as_packages = true`, no `ignore_imports`, ADR-0003 comment header).
- Files to touch — shape test added; Phase-3/7 shape tests + contracts added as likely-touched.
- Out of scope — clarified `FORBIDDEN_LLM_SDKS` narrowing is S1-05; `ignore_imports` population is downstream stories.
- Notes for the implementer — rewritten around the verified import-linter behavior.

## Verdict

**HARDENED.** The goal and scope were sound and trace cleanly to ADR-0003; the weaknesses were real but all patchable. The four block-severity findings (C1/C2 missing `as_packages`, V1 false `ignore_imports` premise, T1 broken test invocation, C4 cross-story hazard) would each have cost the executor an attempt — C1/C2 and V1 would have shipped a silently-broken or build-breaking contract, T1 a test that never exercised the contract, C4 a red `make check`. The story is now ready for `phase-story-executor`.
