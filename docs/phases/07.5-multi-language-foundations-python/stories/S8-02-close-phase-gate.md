# Story S8-02 — Close the phase gate (`import-linter`, `make fence`, ADR reconciliation)

**Step:** Step 8 — Wire the e2e proof and close the phase gate
**Status:** Ready
**Effort:** S
**Depends on:** S7-05, S8-01
**ADRs honored:** ADR-0001, ADR-0002, ADR-0003, ADR-0004, ADR-0005, ADR-0006, ADR-0007, ADR-0008, ADR-0009, ADR-0010, ADR-0011, ADR-0012

## Context
Phase 7.5 added three new sub-packages (`codegenie.languages`, `codegenie.probes.python`, `codegenie.depgraph.python`) and one new PyPI wheel (`tree-sitter-python`). This story is the phase gate: it finalizes the `import-linter` contracts so the new sub-packages are structurally policed, extends `make fence` so the `tree-sitter-python` pin is asserted and no `FORBIDDEN_LLM_SDK` rode in alongside it, and reconciles `phase-arch-design.md`'s ADR references against the 12 ADRs already in `ADRs/`. It writes **no new ADRs** — the phase's 12 ADRs were authored at architecture time. The story closes with `make check` + CI fully green including the new conformance and e2e slices.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Goals → G1` — "`import-linter` contract listing the new sub-packages" — and `G5`, `G12` — the `make fence` extension obligations.
- **Architecture:** `../phase-arch-design.md §Harness engineering → Configuration` — "the `tree-sitter-python` wheel pin lives in `pyproject.toml` + `uv.lock`; `make fence` asserts the pin is present and no `FORBIDDEN_LLM_SDK` rode in."
- **Architecture:** `../phase-arch-design.md §Testing strategy → CI gates` — "`make fence` extended … `import-linter` contracts updated for the new Python sub-packages."
- **Phase ADRs:** `../ADRs/` — all 12 ADRs (0001–0012) — this story confirms each is referenced by `phase-arch-design.md` and none is orphaned (`High-level-impl.md §Step 8` done-criterion).
- **Phase ADRs:** `../ADRs/0012-languagepack-contract-snapshot-fence-not-byte-edit-allowlist.md` — ADR-0012 — no new per-phase byte-edit allowlist fence may be added; the `import-linter` contracts here are structural, not allowlists.
- **Production ADRs:** `../../../production/adrs/0002-deterministic-pipeline-no-llm.md` (and `0005`) — the runtime closure the `fence` job locks; the `tree-sitter-python` wheel must not drag an LLM SDK in.
- **Production ADRs:** `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — commitment 2: Phase 7's byte-edit allowlist is the *last*; this story adds none.
- **Existing code:** `pyproject.toml §[tool.importlinter]` (lines ~338–432) — the existing contracts; the Phase 3 / Phase 7 LLM-SDK contracts (`as_packages = true`, `forbidden_modules` mirroring `FORBIDDEN_LLM_SDKS`) are the precedent to mirror for `codegenie.languages` / `codegenie.probes.python` / `codegenie.depgraph.python`.
- **Existing code:** `tests/unit/test_pyproject_fence.py` — the `make fence` test (`FORBIDDEN_LLM_SDKS`, `EXPECTED_FORBIDDEN_SET`); extend it with the `tree-sitter-python` pin assertion.
- **Existing code:** `tests/fence/test_phase3_importlinter_contracts_shape.py`, `tests/fence/test_phase7_importlinter_contracts_shape.py` — the precedent for a fence test asserting the *shape* of new `import-linter` contracts; mirror it for Phase 7.5.
- **Existing code:** `Makefile` (`fence`, `lint-imports`, `check` targets) — the imperative surface.
- **Source design:** `../final-design.md §Synthesis ledger` — the phase-gate-close row.

## Goal
Finalize the `import-linter` contracts for the three new Python sub-packages, extend `make fence` to assert the `tree-sitter-python` wheel pin, reconcile the ADR references, and confirm `make check` + CI are fully green.

## Acceptance criteria
- [ ] `pyproject.toml §[tool.importlinter]` carries an LLM-SDK `forbidden` contract for each of `codegenie.languages`, `codegenie.probes.python`, `codegenie.depgraph.python` (`as_packages = true`, `forbidden_modules` mirroring `FORBIDDEN_LLM_SDKS`); `make lint-imports` is green.
- [ ] `tests/unit/test_pyproject_fence.py` asserts the `tree-sitter-python` wheel is pinned in `pyproject.toml` (and present in `uv.lock`) and that no `FORBIDDEN_LLM_SDK` is a dependency — the TDD red test below.
- [ ] A Phase-7.5 `import-linter` contract-shape fence (`tests/fence/test_phase7_5_importlinter_contracts_shape.py` or repo-conventional name) asserts the three new contracts exist and their `forbidden_modules` set matches `FORBIDDEN_LLM_SDKS` — mirroring the Phase 3 / Phase 7 shape tests.
- [ ] The TDD red test (the `tree-sitter-python` pin assertion) exists, is committed red, and is green.
- [ ] `phase-arch-design.md`'s ADR references are reconciled — every one of the 12 ADRs (0001–0012) is referenced/honored by the arch design and no ADR is orphaned; a short reconciliation note is added if the arch design lacks a consolidated ADR table.
- [ ] No new per-phase byte-edit allowlist fence is added (ADR-0012 / production-ADR-0043 commitment 2) — the new contracts are structural `import-linter` contracts, not allowlists.
- [ ] `make check` (lint → typecheck → test → fence) is fully green including the new conformance and e2e slices; `ruff check`, `ruff format --check`, `mypy --strict` pass on every touched file; Status set to `Done` on completion.

## Implementation outline
1. Read `pyproject.toml §[tool.importlinter]` and the Phase 3/7 LLM-SDK contracts; add three new `forbidden` contracts (one per new sub-package), `as_packages = true`, `include_external_packages = true`, `forbidden_modules` = the five `FORBIDDEN_LLM_SDKS`.
2. Add a Phase-7.5 `import-linter` contract-shape fence test mirroring `test_phase7_importlinter_contracts_shape.py` — asserts the three contracts are present and their forbidden set has not drifted from `FORBIDDEN_LLM_SDKS`.
3. Extend `tests/unit/test_pyproject_fence.py` with an assertion that `tree-sitter-python` is pinned in `pyproject.toml` `[project.dependencies]` (and `uv.lock`) and that the pin did not bring an LLM SDK in.
4. Run `make lint-imports`, `make fence`, `make check` — fix any drift surfaced.
5. Reconcile `phase-arch-design.md`'s ADR references — confirm each ADR 0001–0012 is named; add a one-line reconciliation note (a short ADR-coverage table) if the arch design has no consolidated ADR index.
6. Confirm the CI matrix (Python 3.11 / 3.12 × `ubuntu-24.04`) reproduces `make check` green.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/test_pyproject_fence.py` (extend).

Test name: `test_tree_sitter_python_wheel_is_pinned`.

```python
# arrange: read pyproject.toml [project.dependencies] (or [project.optional-
#   dependencies]) and uv.lock.
# act: extract the dependency names + the resolved lock entries.
# assert: "tree-sitter-python" appears with a version specifier in pyproject.toml
#   AND a corresponding entry exists in uv.lock; AND no FORBIDDEN_LLM_SDK name
#   appears in either.
#   (intent: the Python grammar is part of the runtime closure and must be
#    pinned, reproducible, and LLM-SDK-free — a missing pin would let a
#    Python gather fail at language_for("python") only at runtime; an SDK
#    riding in alongside it would breach production-ADR-0002.)
```

This must fail first because the `tree-sitter-python` pin does not yet exist at the time the test is written, or because the assertion is new. Commit it red. (If S4-01 already landed the pin, write the assertion so it would still fail against a pre-S4-01 `pyproject.toml` — the test is the durable guard regardless of land order.)

A second red test — the contract-shape fence — in `tests/fence/test_phase7_5_importlinter_contracts_shape.py`:

```python
# assert: the three new [[tool.importlinter.contracts]] entries for
#   codegenie.languages / codegenie.probes.python / codegenie.depgraph.python
#   exist, are type="forbidden", as_packages=true, and their forbidden_modules
#   set equals FORBIDDEN_LLM_SDKS — drift between the two is a hard failure.
```

Fails first because the contracts do not yet exist.

### Green — make it pass
Add the three `[[tool.importlinter.contracts]]` blocks to `pyproject.toml` mirroring the Phase 7 LLM-SDK contract block (comment header explaining the cold-start / closure intent, `as_packages = true`, `include_external_packages = true`, the five forbidden names). Add the contract-shape fence test. The `tree-sitter-python` pin itself is landed by S4-01 — this story only adds the *assertion*; if S4-01's pin is missing, surface it loudly (do not silently add the pin here unless S4-01 is incomplete, in which case note it in the attempt log).

### Refactor — clean up
Add explanatory comment headers to each new contract block (the Phase 3/7 contracts carry multi-line rationale comments — match that style). Ensure the contract-shape fence references `FORBIDDEN_LLM_SDKS` as the single source of truth, never a re-typed literal. Confirm `make check` is fully green; if `phase-arch-design.md` lacks an ADR table, add a compact one (ADR-NNNN → governing component) so the "no ADR orphaned" criterion is auditable.

## Files to touch
| Path | Why |
|---|---|
| `pyproject.toml` | Add three `[[tool.importlinter.contracts]]` blocks for the new Python sub-packages. |
| `tests/unit/test_pyproject_fence.py` | Add the `tree-sitter-python` wheel-pin assertion. |
| `tests/fence/test_phase7_5_importlinter_contracts_shape.py` | New — assert the three new contracts' shape + non-drift from `FORBIDDEN_LLM_SDKS`. |
| `docs/phases/07.5-multi-language-foundations-python/phase-arch-design.md` | Reconcile ADR references / add a consolidated ADR-coverage table if absent. |

## Out of scope
- Writing new ADRs — the 12 ADRs already exist in `ADRs/`; this step is reconciliation only (`High-level-impl.md §Step 8`).
- The `LanguagePack` contract-snapshot fence — that is S7-05 (a dependency of this story).
- The e2e slice row — that is S8-01 (a dependency of this story).
- Per-phase byte-edit allowlist fences — explicitly forbidden by ADR-0012 / production-ADR-0043 commitment 2.
- The `depgraph` purity AST fence — that is S5-06; this story only adds the LLM-SDK `import-linter` contracts, not the network/exec-purity fence.

## Notes for the implementer
- Mirror the *exact* Phase 7 LLM-SDK contract block (`pyproject.toml` ~lines 425–432) — `as_packages = true` is load-bearing: without it only the package `__init__.py` is scanned and a submodule SDK import leaks (the Phase 7 comment spells this out).
- The `tree-sitter-python` pin may already be landed by S4-01 — this story owns the *assertion*, not necessarily the pin; if the pin is missing, fail loud and record it in the attempt log rather than silently fixing S4-01's gap.
- `make fence` today runs `tests/unit/test_pyproject_fence.py`; extending that file is the lowest-friction way to add the wheel-pin gate — verify the `make fence` target's pytest path still picks the new assertion up.
- The contract-shape fence must reference `codegenie._fence.FORBIDDEN_LLM_SDKS` (or the `_fence` constant the Phase 3/7 shape tests use) as the single source of truth — a re-typed literal would silently drift, defeating the test (Rule 9).
- "No ADR orphaned" is a real done-criterion: walk all 12 ADR files and confirm each is named in `phase-arch-design.md`; ADR-0003 (grammars one-to-many) and ADR-0005 (`ProjectDetector` Protocol) are easy to miss in a consolidated table.
- This story closes the phase gate — do not expand scope: it is wiring + assertions + reconciliation. If `make check` surfaces a genuine bug in an earlier step's deliverable, file it as a separate finding rather than fixing it under this story.
