# Attempt log — S2-05 Property tests: dispatch-order invariance + idempotence

Append-only. Each entry records one executor pass.

---

## Attempt 1 — 2026-05-20 — GREEN

**Executor:** Claude Opus 4.7 via `codewizard-executer` scheduled task.

**Context:** The six S2-05 files were already present in the working tree as
untracked files when this pass began (a prior interrupted run had written
them but not committed). This pass verified them against all 11 acceptance
criteria, fixed two lint/type issues, confirmed green, and committed.

### Files (all under `tests/property/vuln_provenance/`)

| File | Role |
|---|---|
| `__init__.py` | Test package marker (new directory). |
| `conftest.py` | Autouse `provenance_registry_reset` fixture (localized duplicate of S2-01's). |
| `_strategies.py` | `adapter_returning` factory + `app_kind_strategy` / `base_kind_strategy` + fixed call-arg helpers. |
| `test_dispatch_order_invariant.py` | AC-1 (50-permutation invariance) + AC-4 (RUNTIME reserved slot). |
| `test_idempotence.py` | AC-2 (idempotence). |
| `test_both_invariant.py` | AC-3 (`Both` no-recursion). Cross-referenced by S12-03. |

### Verification + fixes applied this pass

1. **Ruff E741** — `test_idempotence.py` used ambiguous loop variable `l` in a
   `note(...)` comprehension. Renamed to `layer` / `eco`. `ruff check` now clean.
2. **mypy `unreachable`** — `test_both_invariant.py` originally asserted
   `not isinstance(result.app_record, Both)` directly. S1-03 types
   `Both.app_record` as `AppKind` (a union with no `Both` member), so under
   `warn_unreachable = true` mypy flagged the `isinstance(..., Both)` branch as
   statically dead. Fix: widen the nested records to the full `Provenance`
   union (`app_record: Provenance = result.app_record`) before the
   `not isinstance(..., Both)` guard — `Both` IS a `Provenance` member, so the
   check is a LIVE runtime assertion again. The widening is documented inline:
   the test proves S1-03's type-level recursion guard survives assembly at
   runtime; if a future change weakens the union, the assert fails loud.

### Conftest placement decision (story §Notes offered two options)

The story offered move-to-top-level vs. localized duplicate. The shipped files
chose the **localized duplicate** at `tests/property/vuln_provenance/conftest.py`
(documented in that file's docstring): `tests/unit/...` and `tests/property/...`
have no common ancestor `conftest.py` (the repo ships no top-level
`tests/conftest.py`), and introducing one would make the autouse fixture run
for the entire ~5500-test suite — a non-surgical change for a 10-line fixture
(global Rule 3). The localized conftest mirrors S2-01's own package-scoped
placement. The S2-01 attempt log placed its fixture package-scoped too, so the
two choices are consistent.

### Verification

| Check | Result |
|---|---|
| `pytest tests/property/vuln_provenance/` | 4/4 PASSED |
| `pytest tests/property/vuln_provenance/ tests/unit/primitives/vuln_provenance/` | 210/210 PASSED |
| `ruff check tests/property/vuln_provenance/` | All checks passed |
| `ruff format --check tests/property/vuln_provenance/` | 6 files already formatted |
| `mypy --strict --explicit-package-bases tests/property/vuln_provenance/` | Success: no issues found in 6 source files |
| `lint-imports` (5 contracts) | Contracts: 5 kept, 0 broken |

**Pre-existing failures unrelated to S2-05** (confirmed identical on clean
`master` @ b819d74 via `git stash`):

- `tests/fence/test_phase7_no_llm.py::test_scanner_catches_each_planted_sdk_under_primitive`
  (5 params) + `tests/fence/test_no_llm_in_transforms.py` (2 params) fail when
  `tests/fence/` is run as a narrow subset — a test-isolation artifact of the
  `pkgutil.walk_packages` + `sys.modules` snapshot/restore dance. They pass in
  the full-suite run (CI for S2-04 was green with these identical files). S2-05
  ships only additive `tests/property/` files and does not touch `src/` or
  `tests/fence/`, so it cannot affect this behavior.
- `tests/unit/test_lint_imports_canary.py` + `test_precommit_and_docs_config.py`
  fail locally only (`lint-imports` console script not on `PATH` outside the
  venv; pre-commit hooks not installed). CI runs with the venv active and green.

### AC checklist — all ✓

- [x] AC-1 — 50-permutation registration-order invariance; `@settings(max_examples=50)`; reference result computed once, order-independent via explicit `registry=` kwarg.
- [x] AC-2 — Idempotence; `@settings(max_examples=30)`; two calls, byte-identical inputs, `==` equal results; empty-plan case exercises the `Unknown("no_adapter_resolved")` arm.
- [x] AC-3 — `Both` no-recursion; `@settings(max_examples=30)`; asserts `app_record`/`base_record` are AppKind/BaseKind variants and neither is a `Both`.
- [x] AC-4 — `Layer.RUNTIME` reserved slot stays empty across permutations; asserts no `RuntimeBundled` top-level nor nested in `Both.base_record`.
- [x] AC-5 — `adapter_returning(expected)` factory in `_strategies.py` builds a fresh dependency-free `VulnProvenanceAdapter`-shaped class per call.
- [x] AC-6 — All property tests use the autouse `provenance_registry_reset` fixture; each `@given` body asserts `_REGISTRY == {}` on entry + clears in `finally:`.
- [x] AC-7 — `note(...)` calls print the permutation/plan + result + reference on shrinkage.
- [x] AC-8 — `tests/property/vuln_provenance/__init__.py` exists.
- [x] AC-9 — Property tests run under default pytest collection; no `-m` marker.
- [x] AC-10 — `test_assemble_invariant_under_50_registration_order_permutations` is the headline regression lock (retrospective red — S2-03/S2-04 already GREEN).
- [x] AC-11 — `ruff check`, `ruff format --check`, `mypy --strict`, `lint-imports` all clean.

### Out of scope (unchanged from story)

- SBOM-tampering property test → S4-04.
- `Both` always emits coordination event → S12-03.
- Adversarial tests → S12-04.
- Performance property tests → S12-05.
- Real Phase 3/7 plugin adapters → S3 + S4.
