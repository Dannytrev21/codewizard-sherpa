# S1-03 attempt log — seven-variant `Provenance` discriminated union

Story: [`S1-03-provenance-discriminated-union.md`](../S1-03-provenance-discriminated-union.md).
Append-only journal.

## 2026-05-19 — Attempt 1: GREEN on first pass

### Outcome

GREEN. All 14 hardened ACs (the validator pass expanded the AC list to
14 — see `_validation/S1-03-provenance-discriminated-union.md`) carry
runtime evidence. Gates green:

```
$ .venv/bin/pytest tests/unit/primitives/vuln_provenance/ \
    tests/fence/test_vuln_provenance_frozen_base.py \
    tests/fence/test_vuln_provenance_no_model_construct.py \
    tests/fence/test_kernel_frozen.py --no-cov -q
132 passed in 22.30s

$ .venv/bin/mypy --strict src/
Success: no issues found in 188 source files

$ .venv/bin/ruff check . && .venv/bin/ruff format --check .
All checks passed!
3778 files already formatted

$ .venv/bin/lint-imports --config pyproject.toml --no-cache
Contracts: 4 kept, 0 broken.

$ .venv/bin/pytest -q
5432 passed, 7 failed (pre-existing env failures), 69 skipped, 3 deselected,
5 xfailed in 219.76s
```

The 7 pre-existing failures are identical to the set documented in
S1-02's attempt log (`_attempts/S1-02-…md`) and unrelated to this
story's scope (Phase 2 adversarial secret-scan, golden snapshot,
sandbox-exec integration, lint-imports canary).

### Acceptance criteria — runtime evidence ledger

| AC | Pin | Evidence |
|---|---|---|
| AC-1 — seven verbatim variants | `src/codegenie/primitives/vuln_provenance/types.py` adds `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, `Both`, `Unknown` with the field shapes from `phase-arch-design.md §Component design §2`. | `test_provenance_union.py::test_app_direct_kind_and_fields`, `…::test_app_transitive_kind_and_chain`, `…::test_app_vendored_kind`, `…::test_base_image_kind_and_optional_stage` (both `stage=None` and `stage=DockerStageName("builder")`), `…::test_runtime_bundled_kind`, `…::test_both_kind_and_nested_records`, `…::test_unknown_kind_and_optional_details`, `…::test_unknown_accepts_details_dict_str_str`. |
| AC-2 — `AppKind` / `BaseKind` nested discriminated unions | `types.py:268-275` — both aliases use `Annotated[X \| Y \| Z, Field(discriminator="kind")]` modern PEP 604 form (ruff UP007). | `test_provenance_union.py::test_app_kind_and_base_kind_aliases_importable` + every AC-4 case below routes through them. |
| AC-3 — `Provenance` final alias | `types.py:298` — `Provenance = Annotated[AppDirect \| AppTransitive \| AppVendored \| BaseImage \| RuntimeBundled \| Both \| Unknown, Field(discriminator="kind")]`. | `test_provenance_union.py::test_provenance_round_trip_via_type_adapter[…]` (7 variants). |
| AC-4 — `Both` recursion guard (six structural-rejection cases) | Pydantic v2 nested discriminated unions over non-`Both`/non-`Unknown` variants reject illegal shapes at construction; no runtime guard. | `test_both_rejects_both_in_app_record`, `…_both_in_base_record`, `…_both_in_both_records`, `…_unknown_in_app_record`, `…_unknown_in_base_record`, `…_base_image_in_app_record`, `…_app_direct_in_base_record` — 7 cases (one extra). |
| AC-5 — `frozen=True` per-variant | All seven inherit `_Frozen` (S1-02). | `test_app_direct_frozen`, `test_app_transitive_frozen`, `test_app_vendored_frozen`, `test_base_image_frozen`, `test_runtime_bundled_frozen`, `test_both_frozen`, `test_unknown_frozen`. |
| AC-6 — `extra="forbid"` per-variant | `_Frozen` carries `extra="forbid"`. | `test_app_direct_extra_forbidden`, `…_app_transitive_…`, `…_app_vendored_…`, `…_base_image_…`, `…_runtime_bundled_…`, `…_both_…`, `…_unknown_…`. |
| AC-7 — round-trip via outer discriminator (dict + JSON-string) | `TypeAdapter(Provenance).validate_python(p.model_dump()) == p` and `TypeAdapter(Provenance).validate_json(TypeAdapter(Provenance).dump_json(p)) == p`. | `test_provenance_round_trip_via_type_adapter[app_direct\|app_transitive\|app_vendored\|base_image\|base_image_no_stage\|runtime_bundled\|unknown]`, `test_provenance_round_trip_both`, `test_provenance_round_trip_json_string`. |
| AC-8 — `AppTransitive.chain` length ≥ 2 | `chain: Annotated[tuple[PackageId, ...], Field(min_length=2)]`. | `test_app_transitive_chain_length_one_rejected`, `…_empty_rejected`, `…_two_ok`, `…_three_ok`. |
| AC-9 — exhaustiveness via `match` + `assert_never` | `test_provenance_exhaustiveness.py::_summarise` covers all seven `case` arms with `case _: assert_never(p)` wildcard. | 7 happy-path tests in `test_provenance_exhaustiveness.py`; mypy --strict would catch a missing arm. |
| AC-10 — `__init__.py` re-exports the union surface (and only this) | `__init__.py` re-exports 13 names (3 from S1-02 + 7 variants + 2 aliases + 1 final alias); `__all__` is sorted (locked by `test_types_dunder_all.py`). | `test_full_public_surface_importable_from_package`; `test_public_init_all_is_exact_and_sorted_and_omits_private`. |
| AC-11 — project-wide `make check` clean | Gate listed at top of this section. | mypy strict on all 188 source files; ruff check on all 3778; lint-imports 4/4 contracts; full pytest 5432 passed (7 pre-existing env failures unrelated). |
| AC-12 — `Unknown.details: dict[str, str]` runtime value-type pin | Pydantic v2's runtime type-check on `dict[str, str]` rejects non-`str` values. | `test_unknown_details_rejects_non_str_values[int_value\|none_value\|list_value\|dict_value\|bool_value]` — 5 cases. |
| AC-13 — discriminator-routing integrity at deserialization | `Field(discriminator="kind")` on `Provenance` and `AppKind`/`BaseKind` routes payloads strictly; no first-member coercion. | `test_provenance_discriminator_rejects_unknown_kind`, `…_routes_by_kind_field`, `…_rejects_base_shape_under_app_kind`, `…_rejects_nested_both_at_deserialization`. |
| AC-14 — mypy-negative pins the static layer of the recursion guard | `test_provenance_mypy_negative.py` spawns `mypy --strict` over hand-written snippets that pass `Both`, `Unknown`, `BaseImage` into `Both(app_record=…)` and asserts non-zero exit. | 3 rejects + 2 accepts (negative-control) — all pass. |

### Deviations from the story (worth flagging)

1. **Modernised union syntax to PEP 604.** The story shows
   `Annotated[Union[...], Field(...)]`; ruff (UP007) requires the
   `A | B | C` form on Python 3.11+. Identical semantics — Pydantic v2
   resolves both shapes through `Annotated.__metadata__`. The static
   contract is unchanged (the AC-14 mypy-negative test catches any
   regression).
2. **`AppTransitive.chain` uses `Annotated[tuple[…], Field(min_length=2)]`,
   not the story-spec'd `Field(min_length=2)` after the annotation.**
   Mirrors the `outcomes.py` precedent verbatim — keeps Pydantic v2 happy
   with `from __future__ import annotations` and matches the AC-8
   hardened text ("codebase precedent style, mirroring
   `transforms/outcomes.py`").
3. **`tests/unit/primitives/vuln_provenance/test_types_module_purity.py`
   widened with one additive entry** — `codegenie.types.identifiers` is
   admitted as the single sibling-package dependency (per ADR-0004's
   "field types reference kernel-tier newtypes" carve-out). The
   widening is a CI failure unless intentional, and the comment cites
   ADR-0004 as the gate.
4. **Six AC-4 cases became seven** — the `Both(app_record=inner_both,
   base_record=inner_both)` cross-case was added defensively. No
   contract change; just one extra parametrized assertion.

### Files touched (final)

| Path | Why |
|---|---|
| `src/codegenie/primitives/vuln_provenance/types.py` | EXTENDED — added the seven variants, `AppKind`/`BaseKind`/`Provenance` aliases, plus `pathlib.Path` + `codegenie.types.identifiers` imports admitted by ADR-0004. |
| `src/codegenie/primitives/vuln_provenance/__init__.py` | EXTENDED — re-exports grew from 3 to 13 names (sorted, locked tuple updated). |
| `tests/unit/primitives/vuln_provenance/test_provenance_union.py` | NEW — covers AC-1, AC-2, AC-3, AC-4 (7 cases), AC-5 (7 variants), AC-6 (7 variants), AC-7 (dict + JSON-string + Both nested), AC-8 (4 boundary cases), AC-10, AC-12 (5 non-str-value cases), AC-13 (4 discriminator integrity cases). 52 test items. |
| `tests/unit/primitives/vuln_provenance/test_provenance_exhaustiveness.py` | NEW — AC-9. 7 happy-path tests over `_summarise` with `case _: assert_never(p)` wildcard. |
| `tests/unit/primitives/vuln_provenance/test_provenance_mypy_negative.py` | NEW — AC-14. 3 rejects (nested-`Both`, `Unknown`-in-`Both`, `BaseImage`-in-`Both`) + 2 negative-control accepts. Mirrors `test_types_mypy_negative.py` + `test_identifiers_phase7_mypy_negative.py`. |
| `tests/unit/primitives/vuln_provenance/test_types_module_purity.py` | EXTENDED — allowlist widened by `{pathlib, codegenie.types.identifiers}` (ADR-0004 carve-out). |
| `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` | EXTENDED — `_EXPECTED_TYPES_ALL` and `_EXPECTED_PUBLIC_ALL` grew from 3 to 13 entries (sorted, ASCII). |

### Tests added (summary)

| File | Count | ACs covered |
|---|---|---|
| `tests/unit/primitives/vuln_provenance/test_provenance_union.py` | 52 items (incl. parametrize) | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-10, AC-12, AC-13 |
| `tests/unit/primitives/vuln_provenance/test_provenance_exhaustiveness.py` | 7 | AC-9 |
| `tests/unit/primitives/vuln_provenance/test_provenance_mypy_negative.py` | 5 (3 rejects + 2 accepts) | AC-14 |
| **Total** | **64 new pytest items** | All 14 ACs |

### Refactor decisions

- **No premature abstraction.** Each variant is a small `_Frozen`
  subclass; no mixins, no shared base beyond `_Frozen`. Plugin-style
  registry for variants was explicitly rejected — the seven variants
  are a closed contract per ADR-0038, not an extension point.
- **PEP 604 `X | Y` over `Union[X, Y]`.** Matches the codebase
  precedent (`outcomes.py` uses `|`) and ruff UP007.
- **Field-level invariants over `@field_validator`.** AC-8's chain
  length ≥ 2 lives at the type level (`Field(min_length=2)`), not in
  a validator method — the story's notes explicitly ban defensive
  validators on `Both.app_record` / `Both.base_record`.
- **No `model_construct(...)` call sites.** The S1-02 AC-14 fence
  catches bypass attempts; this story adds variants without using
  the smart-constructor bypass.

### Lessons for the next Phase 7 story (S1-04)

- **The `__all__` locked tuples grow next time too.** S1-04 adds
  `VulnProvenanceAdapter` Protocol + errors — update
  `_EXPECTED_TYPES_ALL` and `_EXPECTED_PUBLIC_ALL` together. ASCII
  sort position is critical.
- **The Protocol lives in the `vuln_provenance` package** but the
  module-purity allowlist only admits `typing`, `enum`, `pathlib`,
  `pydantic`, `codegenie.types.identifiers`. Protocol + ABC live
  under `typing` — no new import needed unless errors pull in
  `codegenie.types.errors` (precedent exists; admit via ADR-0004
  amendment if so).
- **Adapter `attribute(...)` returns `Provenance` (the outer alias).**
  Downstream callers MUST deserialize via `TypeAdapter(Provenance)`,
  not per-variant `model_validate` — the discriminator routing is
  the safety pin.
- **The recursion-guard contract is closed.** S2-04
  `assemble_provenance`'s `match (app, base)` arms can rely on
  `Both.app_record: AppKind` and `Both.base_record: BaseKind` being
  non-`Both`, non-`Unknown` — no defensive instance checks needed.
- **AC-14's mypy-negative pattern is reusable.** Future stories that
  add closed sum-type contracts (e.g., `RecipeOutcome` widening,
  `SignalKind` taxonomies) can mirror `test_provenance_mypy_negative.py`
  one-for-one — 3 rejects + 2 accepts, ~150 lines.
