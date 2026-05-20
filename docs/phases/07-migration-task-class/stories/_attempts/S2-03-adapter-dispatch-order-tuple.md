# Attempt log: S2-03 — `_ADAPTER_DISPATCH_ORDER` `Final` tuple + `Ecosystem`-sorted intra-layer iteration

## Attempt 1 — 2026-05-19 22:30 — SUCCESS

**Approach:** Created `assembly.py` exactly per the story's implementation
outline — a `Final` tuple `_ADAPTER_DISPATCH_ORDER`, a precomputed
`_ECOSYSTEM_SORT_KEY` map, and the generator `iter_adapters_for_layer_set`
that walks the `layer_set` tuple outer-order and sorts each intra-layer subset
by `Ecosystem` declaration order. Wired the public re-export of
`iter_adapters_for_layer_set` into the package `__init__.py`; the dispatch
tuple stays module-private (reached via the module path, mirroring S2-01's
`_REGISTRY`).

**ReAct cycles:** 1 (red → green → refactor, no retry)

**Validator report:**
- AC-1..AC-2 — `test_dispatch_order_tuple_shape_and_declaration_order` green
  (exact-tuple equality + `tuple`-not-`list` shape, inner and outer).
- AC-3 — `test_iter_filters_by_layer` green (APP-only / BASE_IMAGE-only;
  catches "yields everything" + "wrong layer" mutants).
- AC-4 (load-bearing BP-1 closure) — `test_intra_layer_iteration_is_
  ecosystem_sorted_not_registration_sorted` green: DPKG registered before
  APK, helper yields `[APK, DPKG]`. Dropping `matching.sort(...)` fails this.
- AC-5 — `test_empty_runtime_layer_yields_nothing` green (RUNTIME reserved
  slot smoke).
- AC-6 — `test_multi_layer_layer_set_preserves_layer_set_tuple_order` green
  (synthetic `(APP, BASE_IMAGE)` layer-set: outer order is the layer_set
  tuple, each intra-layer Ecosystem-sorted).
- AC-7 — `mypy --strict src/` clean (194 files); param typed
  `Mapping[ProvenanceAdapterId, type[VulnProvenanceAdapter]]`.
- AC-8 — red test was first-failing (`ImportError: cannot import name
  'assembly'`), green after `assembly.py` landed.
- AC-9 — `ruff check` + `ruff format --check` clean; `lint-imports` 5/5
  contracts KEPT.
- Cross-cutting gates: `tests/unit/primitives/vuln_provenance/` +
  `tests/fence/` → 475 passed, 28 skipped (pre-existing cold-start xfail
  set, unrelated), 1 xfailed. Full suite → 5570 passed; the 3 reported
  failures are local-environment-only (see Deviations) and pass with the
  venv on `PATH`.

**Final files touched:**
- `src/codegenie/primitives/vuln_provenance/assembly.py` — created.
  `_ADAPTER_DISPATCH_ORDER`, `_ECOSYSTEM_SORT_KEY`,
  `iter_adapters_for_layer_set`.
- `src/codegenie/primitives/vuln_provenance/__init__.py` — modified.
  Re-export `iter_adapters_for_layer_set`; `__all__` + module docstring
  grown by one S2-03 entry.
- `tests/unit/primitives/vuln_provenance/test_assembly_dispatch_order.py` —
  created. 7 tests covering AC-1..AC-6 + the ADR-0007 classes-not-instances
  cross-check + a package-re-export check.
- `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` —
  modified. `_EXPECTED_PUBLIC_ALL` grown by `iter_adapters_for_layer_set`
  (necessary consequence of the prescribed `__init__.py` change — see
  Deviations).

**Tests added:**
- `test_assembly_dispatch_order.py::test_intra_layer_iteration_is_ecosystem_sorted_not_registration_sorted` — AC-4 / AC-8 (red test)
- `test_assembly_dispatch_order.py::test_dispatch_order_tuple_shape_and_declaration_order` — AC-1 + AC-2
- `test_assembly_dispatch_order.py::test_iter_filters_by_layer` — AC-3
- `test_assembly_dispatch_order.py::test_empty_runtime_layer_yields_nothing` — AC-5
- `test_assembly_dispatch_order.py::test_multi_layer_layer_set_preserves_layer_set_tuple_order` — AC-6
- `test_assembly_dispatch_order.py::test_iter_returns_classes_not_instances` — ADR-0007 cross-check
- `test_assembly_dispatch_order.py::test_iter_adapters_for_layer_set_is_reexported_from_package` — `__init__.py` re-export contract

**Documentation updated:** none beyond the module/constant/function
docstrings in `assembly.py` (the story's "Files to touch" named no external
docs; the module docstring is the canonical extension-protocol reference per
ADR-0006 §Consequences).

**Deviations from the story spec (surfaced for human review):**
1. **`test_types_dunder_all.py` was modified although it is not in the
   story's "Files to touch" table.** The story prescribes re-exporting
   `iter_adapters_for_layer_set` from `__init__.py`; that package's
   `__all__` is byte-pinned by `_EXPECTED_PUBLIC_ALL` in
   `test_types_dunder_all.py`. Re-exporting without updating the pin is a
   guaranteed `make test` failure — the dunder-all-test edit is a *required
   consequence* of the prescribed `__init__.py` change, not a discretionary
   touch. Same precedent as S2-01 and S2-02 (both modified this same fence
   for the identical reason).
2. **`_ADAPTER_DISPATCH_ORDER` is NOT re-exported from `__init__.py`.** The
   story's implementation-outline step 2 says "re-export
   `_ADAPTER_DISPATCH_ORDER` and `iter_adapters_for_layer_set`", but the
   same step then says `_ADAPTER_DISPATCH_ORDER` is module-private and S2-04
   reaches it via the module path; the "Files to touch" row only names
   `iter_adapters_for_layer_set`. Followed the narrower, internally
   consistent instruction (private dispatch tuple, module-path access) —
   mirrors S2-01's `_REGISTRY`.

**Local-environment test failures (NOT caused by this story):**
- `tests/unit/test_lint_imports_canary.py` (2 tests) and
  `tests/golden/test_goldens_match.py::test_goldens_match_live_output`
  failed in the full-suite run. The two canary tests resolve
  `lint-imports` via `shutil.which` — the console script lives in
  `.venv/bin/` which is not on this shell's `PATH`; `make lint-imports`
  and `make typecheck` fail locally for the same reason. The golden test
  passes in isolation (verified 3×) and is provably outside the
  `codegenie gather` import closure (`vuln_provenance` is referenced only
  by `types/identifiers.py` under `TYPE_CHECKING` and by
  `primitives/__init__.py`). All 3 pass when `.venv/bin` is prepended to
  `PATH`; CI runs the venv with the bin on `PATH`, so CI is the real gate.

**Follow-ups surfaced this attempt:**
- None. `assemble_provenance` (S2-04) consumes `_ADAPTER_DISPATCH_ORDER` +
  `iter_adapters_for_layer_set` and is correctly out of scope. The
  50-permutation Hypothesis property test + the `RUNTIME` reserved-slot
  property test belong to S2-05.
