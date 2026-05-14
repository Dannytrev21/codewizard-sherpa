# Story S4-07 — Layer B sub-schemas + explicit additive imports

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Status:** Ready
**Effort:** S
**Depends on:** S4-01 (`IndexHealthProbe` shipping the `index_health` slice shape), S4-05 (`DepGraphProbe` shipping the `dep_graph` slice and `DepGraphProbeOutput` Pydantic model), S4-06 (the three marker probes shipping `generated_code`/`reflection`/`semantic_index_meta` slices)
**ADRs honored:** Phase 1 ADR-0004 (`additionalProperties: false` at sub-schema root + every nested block — the per-probe sub-schema convention), Phase 1 ADR-0007 (warning/error ID pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` enforced on `warnings[]` and `errors[]`), Phase 1 ADR-0010 (slice optional at envelope), [`02-ADR-0006`](../ADRs/0006-index-freshness-sum-type-location.md) (the `index_health` sub-schema references the `IndexFreshness` Pydantic JSON Schema generated from `codegenie.indices.freshness`)

## Context

Phase 1 ADR-0004 established the per-probe sub-schema convention: every probe ships a JSON Schema at `src/codegenie/schema/probes/<probe_name>.schema.json` with `additionalProperties: false` at **the root and every nested object level**. The envelope validator (Phase 0) loads the sub-schemas and validates each slice against its named schema before persisting `repo-context.yaml`. A slice with an unknown field fails validation at the precise JSON Pointer (`/probes/<name>/<bad_field>`), making schema drift loud at PR time.

This story lands the seven Layer B sub-schemas — one per probe shipped in S4-01, S4-03, S4-04, S4-05, S4-06 (three) — and updates `src/codegenie/probes/__init__.py` with the explicit additive imports for each. The sub-schemas were intentionally deferred from the per-probe stories to consolidate the schema-drift discipline in one place. The probes emit the slices; this story validates them.

**`additionalProperties: false` discipline.** Every sub-schema sets it at the root AND at every nested object. The `index_health` sub-schema is the deepest: `{<index_name>: {freshness: {kind: "fresh"|"stale", reason: {kind: "commits_behind"|"digest_mismatch"|...}}, ...}}` — three nested object levels, each `additionalProperties: false`. Without this, a future contributor adding `freshness.metadata: <unstructured>` would slip past validation. The `IndexFreshness` sub-schema content is **generated from the Pydantic model** via `Fresh.model_json_schema()` / `Stale.model_json_schema()` — not hand-written, so a Pydantic-model change ripples to the JSON Schema automatically.

**Per-probe sub-schema rejection test.** Each schema is exercised by a unit test that constructs a synthetic envelope with **one extra field** at a specified JSON Pointer and asserts `SchemaValidationError` fires at exactly that pointer. This is the structural defense against "the schema exists but doesn't actually validate anything." Phase 1 ADR-0004 line — "the schema is paired with a rejection test." S4-07 lands seven such tests.

**Explicit additive imports** in `src/codegenie/probes/__init__.py`. Each Layer B probe story added one line; this story confirms all seven are present, in stable alphabetical order, with `# noqa: F401` to silence linter "unused import" (the import side-effect is the `@register_probe` decorator's registration). A unit test (`test_layer_b_probes_explicit_additive_imports`) reads the `__init__.py` source and asserts the seven import statements appear.

## References — where to look

- **Phase 1 ADRs:**
  - [`docs/phases/01-context-gather-layer-a-node/ADRs/0004-per-probe-subschema-additional-properties-false.md`](../../01-context-gather-layer-a-node/ADRs/0004-per-probe-subschema-additional-properties-false.md) — the convention.
  - [`docs/phases/01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md`](../../01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md) — `warnings[]` and `errors[]` `pattern` constraint.
  - [`docs/phases/01-context-gather-layer-a-node/ADRs/0010-slice-optional-at-envelope.md`](../../01-context-gather-layer-a-node/ADRs/0010-slice-optional-at-envelope.md) — slices are optional at envelope level.
- **Phase 2 architecture:**
  - [`../phase-arch-design.md §"Data model"`](../phase-arch-design.md) lines 660–691 — the `IndexFreshness` Pydantic shape that drives the `index_health` sub-schema.
  - [`../phase-arch-design.md §"Component design"`](../phase-arch-design.md) — every probe's slice shape (the contract this story validates).
- **Phase 1 precedent:**
  - `src/codegenie/schema/probes/node_build_system.schema.json` (from S2-02) — the canonical example to mirror in style.
  - `tests/unit/probes/test_node_build_system_subschema.py` — the rejection-test precedent.
- **Source design:**
  - [`docs/localv2.md §5.2`](../../../localv2.md) — slice field documentation for Layer B.

## Goal

Seven JSON Schema files exist at `src/codegenie/schema/probes/`, one per Layer B probe. Each schema sets `additionalProperties: false` at every object level, declares `warnings[]` and `errors[]` with the ADR-0007 `pattern` constraint, and is exercised by a rejection test that asserts an extra-field envelope fails validation at the precise JSON Pointer. `src/codegenie/probes/__init__.py` lists the seven Layer B probe imports as additive lines in stable order. The envelope validator round-trip-tests each Layer B probe's actual slice output against its sub-schema and accepts it.

## Acceptance criteria

- [ ] **AC-1 — Seven sub-schema files exist.** Under `src/codegenie/schema/probes/`:
  - `index_health.schema.json`
  - `scip_index.schema.json`
  - `tree_sitter_import_graph.schema.json`
  - `dep_graph.schema.json`
  - `generated_code.schema.json`
  - `node_reflection.schema.json`
  - `semantic_index_meta.schema.json`
  Each is a valid JSON Schema 2020-12 document (`$schema: "https://json-schema.org/draft/2020-12/schema"`), self-contained (no `$ref` to external schemas in Phase 2 — the `IndexFreshness` sub-schema is **embedded** rather than `$ref`'d to defer the cross-schema-ref convention to Phase 3+), and Phase-1-ADR-0004 compliant.

- [ ] **AC-2 — `additionalProperties: false` at root AND every nested object.** Each sub-schema sets `additionalProperties: false`:
  - At the document root (the slice object).
  - At every nested `type: "object"` block (e.g., `index_health.<index_name>.freshness`, `index_health.<index_name>.freshness.reason`, `generated_code.files[*]`, `node_reflection.decorator_usage`, `semantic_index_meta` is single-level so root is sufficient).
  A unit test (`test_additional_properties_false_at_every_object_level`) parametrized over the seven schemas walks each schema with a recursive `_find_object_nodes_without_additional_properties_false` helper and asserts the returned list is empty.

- [ ] **AC-3 — `warnings[]` and `errors[]` are ADR-0007-pattern-constrained.** Each sub-schema declares `warnings: {type: "array", items: {type: "string", pattern: "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"}}` and analogously for `errors[]`. The pattern matches every warning/error ID emitted by the probe (a per-probe assertion test loads the probe module's `_WARNING_IDS` / `_ERROR_IDS` frozensets and asserts each member matches the pattern — Rule 12 — fail loud, NOT silently regex-stripped).

- [ ] **AC-4 — Slice optional at envelope level.** Each sub-schema does NOT add an entry to the envelope's `properties.probes.required` array (Phase 1 ADR-0010). A unit test (`test_layer_b_slices_optional_at_envelope`) parses the envelope schema and asserts the seven Layer B probe names are NOT in the required list.

- [ ] **AC-5 — `index_health` sub-schema embeds the `IndexFreshness` JSON Schema.** The `index_health.schema.json` contains a `$defs` block with `Fresh`, `Stale`, `CommitsBehind`, `DigestMismatch`, `CoverageGap`, `IndexerError` definitions — **generated** at sub-schema build time from the Pydantic models (`Fresh.model_json_schema()`, etc.) via a small `tools/regenerate_layer_b_schemas.py` script. The script is reviewed-as-code; running it on a clean tree must produce byte-identical sub-schemas to those committed. A unit test (`test_index_health_subschema_regenerates_identically`) shells out to the script and diffs.

- [ ] **AC-6 — Per-probe sub-schema rejection test.** Each of the seven schemas has a dedicated test in `tests/unit/probes/layer_b/test_subschemas.py`. The pattern:
  ```python
  @pytest.mark.parametrize("probe_name, slice_field, extra_field, pointer", [
      ("index_health",            None,           "rogue_field",   "/probes/index_health/rogue_field"),
      ("scip_index",              None,           "rogue_field",   "/probes/scip_index/rogue_field"),
      ("tree_sitter_import_graph", None,           "rogue_field",   "/probes/tree_sitter_import_graph/rogue_field"),
      ("dep_graph",               None,           "rogue_field",   "/probes/dep_graph/rogue_field"),
      ("generated_code",          "files",        None,            "/probes/generated_code/files/0/rogue_field"),  # nested
      ("node_reflection",         "decorator_usage", "rogue_field", "/probes/node_reflection/decorator_usage/rogue_field"),
      ("semantic_index_meta",     None,           "rogue_field",   "/probes/semantic_index_meta/rogue_field"),
  ])
  def test_subschema_rejects_extra_field(...):
      ...
  ```
  Each row exercises **one** extra-field rejection; nested cases (`generated_code`, `node_reflection`) prove `additionalProperties: false` propagates beyond the root. AC-2's recursive test is the **structural** check; AC-6 is the **behavioral** check — both are needed (one catches the missing flag, the other catches the validator-not-actually-running case).

- [ ] **AC-7 — Round-trip validation of real probe outputs.** A unit test (`test_layer_b_probe_outputs_round_trip_against_subschemas`) for each of the seven probes:
  1. Invokes the probe against a synthetic `ProbeContext` with valid inputs.
  2. Serializes the slice via `ProbeOutput.model_dump(mode="json")`.
  3. Validates the slice against its sub-schema using `jsonschema.validate`.
  4. Asserts validation succeeds (NO `ValidationError`).
  This is the round-trip discipline — without it, a sub-schema could be too strict and silently reject the probe's actual output, OR a probe could emit a shape the schema doesn't cover.

- [ ] **AC-8 — `src/codegenie/probes/__init__.py` lists seven additive imports in stable alphabetical order.** The Layer B section of `__init__.py` reads:
  ```python
  # Layer B — semantic-index and structural probes.
  from codegenie.probes.layer_b import dep_graph                      # noqa: F401
  from codegenie.probes.layer_b import generated_code                 # noqa: F401
  from codegenie.probes.layer_b import index_health                   # noqa: F401
  from codegenie.probes.layer_b import node_reflection                # noqa: F401
  from codegenie.probes.layer_b import scip_index                     # noqa: F401
  from codegenie.probes.layer_b import semantic_index_meta            # noqa: F401
  from codegenie.probes.layer_b import tree_sitter_import_graph       # noqa: F401
  ```
  A unit test (`test_layer_b_probes_explicit_additive_imports`) reads the file and asserts the seven import statements appear in the specified order (alphabetical by module name). Stable order means git blame is informative — a future PR adding an eighth Layer B probe inserts a single line at the alphabetical position, not a hunk re-ordering.

- [ ] **AC-9 — All seven probes registered in `default_registry`.** A unit test (`test_layer_b_probes_in_default_registry`) imports `default_registry` (forcing module-level decorator runs), enumerates `default_registry.all_probes()`, and asserts the seven probe names are present. **This is a cross-cutting consolidation test** — each probe's individual story has its own membership test; this one asserts collective presence.

- [ ] **AC-10 — Sub-schemas pass JSON Schema meta-schema validation.** A unit test (`test_subschemas_are_valid_json_schema_documents`) loads each of the seven sub-schemas, validates against the JSON Schema 2020-12 meta-schema (`jsonschema.Draft202012Validator.check_schema(...)`), and asserts no exception. **Catches the "malformed schema typo" failure mode.**

- [ ] **AC-11 — Tooling green.** `ruff check`, `ruff format --check`, `mypy --strict tools/regenerate_layer_b_schemas.py`, `pytest tests/unit/probes/layer_b/test_subschemas.py`, `pytest tests/unit/probes/test_init.py` (if the init-shape tests live there) — all pass. Pre-commit hook `jsonlint` (if Phase 0 has one — verify) reports no issues on the seven JSON files.

## Implementation outline

1. **Land `tools/regenerate_layer_b_schemas.py`** — a small Python script (≤ 80 LOC) that:
   - Imports the Pydantic models from `codegenie.indices.freshness` and `codegenie.probes.layer_b.dep_graph` (for `DepGraphProbeOutput`).
   - For each Layer B probe, generates the slice's JSON Schema:
     - `index_health.schema.json` — composes a top-level schema with `additionalProperties: false` at root, declares each known index source as an optional property with the `IndexFreshness` schema embedded in `$defs` (generated via Pydantic).
     - `scip_index.schema.json` — hand-coded per `localv2.md §5.2 B1` slice shape.
     - `tree_sitter_import_graph.schema.json` — hand-coded per S4-04 AC-7.
     - `dep_graph.schema.json` — generated from `DepGraphProbeOutput.model_json_schema()`.
     - `generated_code.schema.json` — hand-coded per `localv2.md §5.2 B4`.
     - `node_reflection.schema.json` — hand-coded per `localv2.md §5.2 B3`.
     - `semantic_index_meta.schema.json` — hand-coded per S4-06 AC-M3.
   - Sets `additionalProperties: false` recursively (post-process step on the generated schemas — a small `_set_additional_props_false(obj)` walker).
   - Constrains `warnings[]` and `errors[]` items via the ADR-0007 regex (post-process step).
   - Writes each file with stable JSON formatting (`json.dumps(..., indent=2, sort_keys=True) + "\n"` — byte-identical on re-runs).

2. **Run the script once and commit** the seven sub-schemas.

3. **Compose `tests/unit/probes/layer_b/test_subschemas.py`** with:
   - `test_subschemas_exist_and_are_valid_json` (AC-1, AC-10).
   - `test_additional_properties_false_at_every_object_level` (AC-2).
   - `test_warnings_and_errors_pattern_constraints` (AC-3).
   - `test_layer_b_slices_optional_at_envelope` (AC-4).
   - `test_index_health_subschema_regenerates_identically` (AC-5).
   - `test_subschema_rejects_extra_field` (AC-6) — parametrized over seven probes.
   - `test_layer_b_probe_outputs_round_trip_against_subschemas` (AC-7) — parametrized over seven probes.

4. **Compose `tests/unit/probes/test_init.py`** (or extend existing) with:
   - `test_layer_b_probes_explicit_additive_imports` (AC-8).
   - `test_layer_b_probes_in_default_registry` (AC-9).

5. **Confirm `src/codegenie/probes/__init__.py`** has the seven additive imports (each of S4-01, S4-03, S4-04, S4-05, S4-06 added their lines incrementally; this story is the consolidation check + reordering to stable alphabetical).

## TDD plan — red / green / refactor

### RED

- **T-01** `test_subschemas_exist_and_are_valid_json` (AC-1, AC-10): for each of seven, file exists; loads as JSON; passes `Draft202012Validator.check_schema`.
- **T-02** `test_additional_properties_false_at_every_object_level` (AC-2): for each schema, walk recursively; collect any `{"type": "object", ...}` node that lacks `additionalProperties: false`; assert the list is empty. **The recursive walker is the load-bearing utility** — extract to `tests/unit/probes/layer_b/_schema_walkers.py` for reuse.
- **T-03** `test_warnings_and_errors_pattern_constraints` (AC-3): each schema's `properties.warnings.items.pattern` equals `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; same for `errors`.
- **T-04** `test_each_probe_emitted_ids_match_pattern_constraint`: for each probe module, load `_WARNING_IDS` and `_ERROR_IDS`; assert every member matches the regex pinned in its sub-schema (cross-check: the regex AND the IDs both conform).
- **T-05** `test_layer_b_slices_optional_at_envelope` (AC-4): envelope schema does NOT list the seven Layer B probe names in `properties.probes.required`.
- **T-06** `test_index_health_subschema_regenerates_identically` (AC-5): shell out to `tools/regenerate_layer_b_schemas.py` in a tempdir copy; diff `index_health.schema.json` against the committed version; assert byte-identical.
- **T-07** `test_subschema_rejects_extra_field` (AC-6): parametrized; build a minimal-valid envelope for each probe; add an extra field at the specified JSON Pointer; run `jsonschema.validate(envelope, full_schema)`; assert `ValidationError` raised AND `error.absolute_path` matches the expected pointer.
- **T-08** `test_layer_b_probe_outputs_round_trip_against_subschemas` (AC-7): parametrized; invoke each probe against a synthetic `ProbeContext` configured to produce a happy-path slice; validate the slice against its sub-schema; assert success.
- **T-09** `test_layer_b_probes_explicit_additive_imports` (AC-8): read `src/codegenie/probes/__init__.py`; assert the seven import lines appear in alphabetical order in a contiguous block.
- **T-10** `test_layer_b_probes_in_default_registry` (AC-9): `default_registry.all_probes()` contains all seven `Probe` subclasses.

### GREEN

- Write `tools/regenerate_layer_b_schemas.py` per outline.
- Generate the seven sub-schemas.
- Commit.
- Write the test file(s).
- Run; iterate on sub-schema content until every test passes — especially the round-trip test (AC-7), which catches "schema is too strict" failures.

### REFACTOR

- Confirm `tools/regenerate_layer_b_schemas.py` is idempotent (second run produces byte-identical files).
- Confirm `mypy --strict` on the script.
- If the schemas grow unwieldy in size, consider extracting common sub-objects (e.g., `Confidence`) to a shared `$defs` block in a single sub-schema only — DO NOT introduce cross-schema `$ref` in Phase 2 (Rule 7 — surface the pattern decision; cross-schema refs are a Phase 3+ scope choice).

## Files to touch

**Create:**
- `tools/regenerate_layer_b_schemas.py` (executable)
- `src/codegenie/schema/probes/index_health.schema.json`
- `src/codegenie/schema/probes/scip_index.schema.json`
- `src/codegenie/schema/probes/tree_sitter_import_graph.schema.json`
- `src/codegenie/schema/probes/dep_graph.schema.json`
- `src/codegenie/schema/probes/generated_code.schema.json`
- `src/codegenie/schema/probes/node_reflection.schema.json`
- `src/codegenie/schema/probes/semantic_index_meta.schema.json`
- `tests/unit/probes/layer_b/test_subschemas.py`
- `tests/unit/probes/layer_b/_schema_walkers.py` (utility helpers)

**Edit (additive — consolidation):**
- `src/codegenie/probes/__init__.py` — reorder Layer B imports to stable alphabetical order if needed; confirm seven imports present (each predecessor story already added one).
- `tests/unit/probes/test_init.py` (or new file) — add `test_layer_b_probes_explicit_additive_imports`, `test_layer_b_probes_in_default_registry`.

## Out of scope

- **Cross-schema `$ref`.** Phase 2 keeps schemas self-contained (`IndexFreshness` is embedded via `$defs` within `index_health.schema.json`, not `$ref`'d from a separate file). Cross-schema refs introduce a "schema discovery" concern Phase 3+ owns.
- **Schema versioning.** Phase 2 ships `schema_version: 1` implicitly via the sub-schema `$id` (e.g., `https://codewizard.local/schema/probes/index_health.v1.json`); a Phase 3 schema change bumps `v2` and the envelope validator picks based on emitted `schema_version` in the slice. The convention is documented but the version-2 path is unbuilt here.
- **OpenAPI / Swagger emission.** The JSON Schemas are the canonical contract; an OpenAPI rendering is Phase 8+.
- **Sub-schemas for Layer C/D/E/G probes.** Steps 5 and 6 land those probes; their sub-schemas land alongside (S5-07-ish, S6-09-ish — TBD by those stories' authors).
- **Generated `IndexFreshness` shape for Phase 3.** AC-5 generates the **current Phase 2 variant set** — `CommitsBehind | DigestMismatch | CoverageGap | IndexerError`. A Phase 3 ADR amending to a fifth variant requires a re-run of `regenerate_layer_b_schemas.py` and a sub-schema bump. Documented in `tools/regenerate_layer_b_schemas.py`'s docstring.
- **Hand-editing sub-schemas after generation.** Generated portions (the `IndexFreshness` `$defs`, the `DepGraphProbeOutput` shape) are reviewed by re-running the script. Hand edits are admissible **only** for the parts of sub-schemas that are hand-coded (e.g., `scip_index.schema.json`'s `coverage_pct` field is hand-declared because there's no Pydantic source). Document this split inline in the script's docstring.

## Notes for the implementer

- **Why this story is `S` not `M`.** The per-probe sub-schemas are largely hand-coded YAML/JSON guided by the probe stories' AC fields; the discipline is structural (`additionalProperties: false` recursive walker, ADR-0007 regex, rejection tests). The novel work is `tools/regenerate_layer_b_schemas.py` and AC-5's regeneration discipline — both are small. Effort `S` reflects "no architectural decisions, just careful schema authoring."
- **The regeneration script is the discipline.** AC-5 — running `regenerate_layer_b_schemas.py` on a clean tree produces byte-identical output. This catches the "I hand-edited the generated section and didn't update the script" failure mode. Same precedent as `tools/regenerate_grammars_lock.sh` from S4-03.
- **`additionalProperties: false` is the structural defense.** Phase 1 ADR-0004 is emphatic. A future contributor who hand-edits a sub-schema to add `additionalProperties: true` ANYWHERE (root or nested) breaks AC-2. The recursive walker (`_find_object_nodes_without_additional_properties_false`) is the structural test. Resist the urge to "make the test less strict for nested allOf/anyOf cases" — those cases are real and need to be addressed in the schema authoring, not in the test.
- **Round-trip discipline (AC-7) is what catches over-strict schemas.** Without it, a sub-schema requiring `nodes_count: integer` would fail silently when the probe emits `nodes_count: null` on the no-strategy path. The round-trip test invokes the probe AND validates — both arms of the contract are tested in one place.
- **Stable alphabetical import order (AC-8).** Rule 11 — match codebase convention. Phase 1's `__init__.py` likely already uses alphabetical for Layer A imports (verify); Phase 2 extends the convention. A future PR adding `layer_b/example.py` inserts ONE line at the correct alphabetical position — diff is minimal, git blame is informative.
- **The rejection-test parametrization (AC-6) is the load-bearing behavioral check.** AC-2 catches "the schema has `additionalProperties: false` at root." AC-6 catches "the validator actually fires when an extra field is added." Both can fail independently — a future contributor removes `additionalProperties: false` from one nested level but keeps it at root; AC-2 catches the structural omission, AC-6 catches the behavioral consequence. **Both are needed.**
- **Don't $ref across files in Phase 2.** Tempting to factor `Confidence` (`Literal["high", "medium", "low"]`) into a shared schema — DON'T. Cross-schema discovery is a Phase 3+ concern. Embed `Literal` shapes in each sub-schema; duplication is the simplicity tradeoff Phase 2 explicitly takes ([phase-arch-design.md §"Design patterns applied"](../phase-arch-design.md) — Rule 2 over Rule 11 when the cost of one-step indirection is high).
- **Why I made every sub-schema use `$schema: "draft/2020-12"` (AC-1).** Phase 0 used draft-07 (verify); if Phase 2 uses 2020-12, the envelope validator must support both. Validation: load each sub-schema and check via `Draft202012Validator.check_schema`. If Phase 0 is hard-pinned to draft-07 (likely — `python-jsonschema`'s default), then Phase 2 sub-schemas pin to the same draft. **Resolve the conflict (Rule 7) before writing the schemas** — read `src/codegenie/schema/__init__.py` to find the validator's draft pin, then conform. Do NOT mix drafts across sub-schemas.
- **The seven probes' membership test (AC-9) is structural.** It catches the "I forgot to register `dep_graph` in `__init__.py`" mistake — each individual story's per-probe registry test would still pass (it imports the module directly), but the consolidated test fails because `default_registry.all_probes()` doesn't have it. Rule 12 — fail loud.
- **Rule 9 — tests verify intent.** AC-2 (recursive walker) encodes the WHY of `additionalProperties: false` — preventing silent slice drift. AC-5 (regeneration is idempotent) encodes the WHY of the generation script — hand-editing the generated section is the failure mode. AC-7 (round-trip with real probe output) encodes the WHY of both schema AND probe — they must agree. Each test asserts a load-bearing discipline, not just behavior.
