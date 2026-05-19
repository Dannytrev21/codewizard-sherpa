# S1-05 — SyftSbom Pydantic reader models — attempt log

Append-only journal of executor attempts. Most recent attempt last.

## 2026-05-19 — Attempt 1 — GREEN (one shot)

**Executor:** phase-story-executor (Claude Opus 4.7 via codewizard-executer
scheduled task)

**Result:** GREEN on the first attempt — no retry needed.

### What shipped

| Path | Change | Why |
|---|---|---|
| `src/codegenie/primitives/vuln_provenance/syft_reader.py` | NEW (≈90 lines) | Three Pydantic models (`SyftSbom`, `SyftArtifact`, `SyftLocation`) carrying the deliberate `extra="allow"` posture, plus the two `_KNOWN_*_FIELDS: Final[frozenset[str]]` catalogs that S4-04's AST-walk fence consumes. |
| `src/codegenie/primitives/vuln_provenance/__init__.py` | EXTENDED | Adds three sorted-alphabetical re-exports (`SyftArtifact`, `SyftLocation`, `SyftSbom`). Internal `_KNOWN_*_FIELDS` deliberately NOT re-exported (per AC-7; fences read via direct-module import). |
| `tests/fixtures/syft/minimal_alpine.json` | NEW | Realistic syft JSON shape — one artifact, one `layerID`-bearing location, three unknown top-level fields (`schema`, `descriptor`, `source`). Drives the round-trip + unknown-preservation tests. |
| `tests/unit/primitives/vuln_provenance/test_syft_reader.py` | NEW | 24 tests, one or more per AC: extra-allow admission (AC-2), empty-SBOM happy path (AC-2.5), known-field validation + multi-location (AC-3), round-trip + full encode→decode→encode cycle (AC-4), `layerID` camelCase pin (AC-5), `_KNOWN_*_FIELDS` immutability + content (AC-6), public re-export + private-catalog absence (AC-7). |
| `tests/unit/primitives/vuln_provenance/test_syft_reader_module_purity.py` | NEW | Module-purity AST fence (AC-8) + `model_construct()`-bypass fence (AC-8.5). |
| `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` | EXTENDED | `_EXPECTED_PUBLIC_ALL` grew by three names (`SyftArtifact`, `SyftLocation`, `SyftSbom`), preserving sorted order. |
| `tests/fence/test_vuln_provenance_frozen_base.py` | EXTENDED | Added `_DELIBERATE_EXTRA_ALLOW_RECORDS` allowlist (per-`(filename, class_name)` carve-out for the three syft models, with rationale comment naming the Phase 2 deliberate decision + S4-04 mitigation). Added `test_s1_05_carve_out_actually_carries_extra_allow` — pins the *intent* of the carve-out so a future maintainer who flips `extra="allow"` → `"forbid"` without removing the carve-out trips a fence. |

### Decisions made

1. **Per-`(filename, class_name)` carve-out, not a name-only or
   module-wide one.** The frozen-base fence anticipated this scenario
   (its assertion message literally says "or — if intentional — amend
   ADR-0004 and update `_ADMITTED_FROZEN_BASES`"). I used the narrowest
   shape that admits the three known cases — keying on the full
   `(filename, class_name)` tuple means a future class accidentally
   named `SyftSbom` in a different file would still trip the fence.

2. **Carve-out is intent-pinned, not just shape-pinned.** Rule 9: tests
   verify why, not just what. The companion test
   `test_s1_05_carve_out_actually_carries_extra_allow` AST-walks each
   admitted class and asserts it literally declares
   `ConfigDict(extra="allow")`. If a maintainer removes the `extra`
   posture (the reason the carve-out exists) without removing the
   carve-out entry, the test fails loudly — the class should rejoin the
   `_Frozen` tree.

3. **Did NOT touch `protocols.py`.** The S1-05 Notes mention "verify
   after both land: a quick smoke test that the forward reference
   resolves" but the story's Files-to-touch list does not include
   `protocols.py`. The existing
   `test_attribute_sbom_param_is_forward_reference_today` continues to
   assert the bare-string annotation (matches today's
   `from __future__ import annotations` + `TYPE_CHECKING` placeholder
   shape, which my changes do not modify). Tightening the forward
   reference into a real import + `get_type_hints` resolution is left
   for a follow-up (file a story or roll into S2-01 / S3-01 when an
   adapter actually consumes it). Rule 3 (surgical changes).

4. **`tests/unit/primitives/vuln_provenance/test_types_dunder_all.py`
   counted as a touched file.** Not in the story's Files-to-touch but
   AC-7 (re-exports) cannot land without growing the public `__all__`,
   and the existing `_EXPECTED_PUBLIC_ALL` tuple in that test pins
   exactness. Surgical update — three new names, alphabetical order
   preserved.

5. **Lint-imports env-only failures matched S1-04's baseline.** Same
   shape: `tests/unit/test_lint_imports_canary.py` × 2 fails locally
   because `lint-imports` is on `.venv/bin/` only, not the shell PATH;
   passes when `.venv/bin` is prepended (which CI does). Not a
   regression. Documented in the S1-04 attempt log.

### Gates run

| Gate | Result |
|---|---|
| `pytest tests/unit/primitives/vuln_provenance/` (174 tests, +21 from S1-04) | PASS |
| `pytest tests/fence/test_vuln_provenance_frozen_base.py` (7 tests, +1 intent-pinning) | PASS |
| `pytest tests/unit tests/fence tests/unit/test_pyproject_fence.py` (5167 tests; lint-imports canary excluded — env-only) | PASS |
| `mypy --strict src/codegenie/primitives/vuln_provenance/` | PASS (5 source files clean) |
| `ruff check` repo-wide | PASS |
| `ruff format --check` repo-wide | PASS (3785 files) |
| `lint-imports --config pyproject.toml --no-cache` | PASS (4 kept, 0 broken) |

### Acceptance criteria evidence

| AC | Evidence |
|---|---|
| AC-1 | `src/codegenie/primitives/vuln_provenance/syft_reader.py` — three models, each with `model_config = ConfigDict(extra="allow")` and the four known fields. |
| AC-2 | `test_syft_sbom_admits_unknown_fields`, `test_syft_artifact_admits_unknown_fields`, `test_syft_location_admits_unknown_fields`. |
| AC-2.5 | `test_empty_sbom_happy_path`, `test_empty_artifact_list_default`, `test_empty_locations_default`. |
| AC-3 | `test_syft_artifact_happy_path`, `test_syft_artifact_multi_location_preserves_order_and_optional_layer_id`, `test_syft_artifact_rejects_invalid[0..3]`, `test_syft_location_rejects_invalid[0,1]`, `test_syft_location_layer_id_optional`. |
| AC-4 | `test_minimal_alpine_fixture_round_trips`, `test_minimal_alpine_fixture_lossless_for_known_fields`, `test_full_encode_decode_encode_cycle_preserves_unknowns`. |
| AC-5 | `test_location_layer_id_field_name_is_camelcase`. |
| AC-6 | `test_known_location_fields_pinned`, `test_known_artifact_fields_pinned`, `test_known_fields_are_frozenset_not_set`. |
| AC-7 | `test_public_reexports_succeed`, `test_private_catalogs_not_in_public_all`, plus `test_public_init_all_is_exact_and_sorted_and_omits_private` (extended `_EXPECTED_PUBLIC_ALL`). |
| AC-8 | `test_syft_reader_imports_are_subset_of_allowlist`, `test_syft_reader_has_no_relative_imports`. |
| AC-8.5 | `test_syft_reader_has_no_model_construct_call_sites`. |
| AC-9 | All gates above PASS. |

### Out of scope (deferred to later stories)

- **`SyftSource`, `SyftDistro`, `descriptor` typed parsing** — deferred
  until a Phase 7 consumer needs them. Today's adapter set
  (S3-02 / S4-02 / S4-03) reads only `name`, `version`, `locations[].path`,
  `locations[].layerID`. The `# TODO(future)` marker in the module
  docstring names the deferral.
- **`sbom_verifier.py` cross-check function** — S4-01.
- **Concrete adapters that consume `SyftSbom`** — S3-02 (npm),
  S4-02 (alpine), S4-03 (distroless).
- **The "adapters read only `_KNOWN_*_FIELDS`" AST-walk fence** —
  S4-04 (consumes this story's `_KNOWN_*_FIELDS` catalogs).
- **Reading SBOMs from disk / `docker syft` stdout** — types-only at
  this stage per the story.
- **Forward-reference resolution to the concrete `SyftSbom` in
  `protocols.py`** — deferred; today's bare-string annotation
  (PEP 563 via `from __future__ import annotations`) continues to
  satisfy the Protocol shape test. A follow-up story can tighten
  this when an adapter actually imports `SyftSbom` from the Protocol
  surface.

### Lessons (also appended to `_lessons.md`)

- **Fences with documented carve-out paths are easier to extend than
  fences that take only a binary yes/no.** The frozen-base fence's
  error message literally pointed at the resolution shape — "amend ADR
  and update the allowlist". A fence whose extension path is obvious is
  a fence that gets respected; a fence whose only extension path is "go
  edit the AST walk" gets skipped or deleted.
- **Carve-outs should be intent-pinned, not just shape-pinned.** The
  `_DELIBERATE_EXTRA_ALLOW_RECORDS` companion test that AST-checks each
  admitted class literally declares `extra="allow"` is what keeps the
  carve-out honest. Without that companion, the allowlist becomes "a
  trust-me list that grows over time" — exactly the failure mode the
  fence was designed to prevent.
