# Story S4-08 — Add Python probe sub-schemas + envelope `$ref`s

**Step:** Step 4 — Build the Python Layer A/B probes and the `tree-sitter-python` grammar row
**Status:** Ready
**Effort:** S
**Depends on:** S4-05
**ADRs honored:** ADR-0007

## Context
Every probe's `schema_slice` is validated by a per-probe JSON Schema sub-schema (`additionalProperties: false` at every node) `$ref`-wired into the `RepoContext` envelope's `properties.probes`; the envelope's `probes.*` is `additionalProperties: true` so new probes extend by addition while strictness lives at the sub-schema. The four Python probes from S4-02/S4-04/S4-05/S4-07 each need a sub-schema and an envelope `$ref` — the additive-schema-`$ref` loud edit from the arch's "loud edits" list.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — Python Layer A/B probes` — "Python probe sub-schemas under `src/codegenie/schema/probes/python_*.schema.json` (`additionalProperties: false`), `$ref`-wired into the envelope's `properties.probes`."
- **Architecture:** `../phase-arch-design.md §Control flow` — "the loud edits": "additive schema `$ref`s into the envelope's `properties.probes`" is a compiler/snapshot-policed loud edit, not a violation.
- **Architecture:** `../phase-arch-design.md §Data model` — "the Python probe sub-schemas ... (each `additionalProperties: false`, with a `$ref` wired into the envelope's `properties.probes`) are **contract, persisted**."
- **Architecture:** `../phase-arch-design.md §Edge cases` row 1 — per-probe sub-schema isolation prevents cross-language slice key collision in a polyglot repo.
- **Phase ADRs:** `../ADRs/0007-python-probes-hardened-parse-only-no-exec.md` — ADR-0007 — the probes whose slices these schemas pin.
- **Production ADRs:** `../../../production/adrs/` per-probe-subschema discipline (Phase 1 ADR-0004 precedent — `additionalProperties: false` at every node).
- **Existing code:** `src/codegenie/schema/repo_context.schema.json` — the envelope; `properties.probes` is `additionalProperties: true`, each existing probe wired as a `$ref` (e.g. `node_manifest`, `tree_sitter_import_graph` — lines ~33–135).
- **Existing code:** `src/codegenie/schema/probes/node_manifest.schema.json`, `tree_sitter_import_graph.schema.json` — the precedent sub-schema shapes to mirror.
- **Existing code:** `src/codegenie/schema/probes/_subschema_convention.md` — the documented sub-schema convention (`$id` scheme, `additionalProperties: false`).
- **Existing code:** the probe slice shapes from S4-02/S4-04/S4-05/S4-07 — the sub-schemas must match the slices those probes actually emit.

## Goal
Land the four `python_*` probe sub-schemas (`additionalProperties: false`) and wire their `$ref`s into the `RepoContext` envelope's `properties.probes`.

## Acceptance criteria
- [ ] A red test asserts each Python probe's emitted `schema_slice` validates against its `python_*.schema.json` sub-schema, and that the envelope's `properties.probes` resolves the new `$ref`s; it fails before the sub-schemas exist.
- [ ] Four sub-schemas land under `src/codegenie/schema/probes/` — one each for `PythonProjectProbe`, `PythonBuildSystemProbe`, `PythonManifestProbe`, `PythonImportGraphProbe` — each `additionalProperties: false` at every node and following `_subschema_convention.md`'s `$id` scheme.
- [ ] Each sub-schema's `$ref` is wired into `repo_context.schema.json`'s `properties.probes` (additive — no existing `$ref` removed or edited).
- [ ] A representative slice from each probe validates against its sub-schema; an extra (typo'd) slice key is rejected by `additionalProperties: false`.
- [ ] `make docs` (mkdocs `--strict`) and any schema-validation test stay green; the writer-produced `repo-context.yaml` for a Python fixture is envelope-schema-valid.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest` pass on touched files; Status set to `Done`.

## Implementation outline
1. For each of the four Python probes, capture the exact `schema_slice` shape it emits (from S4-02/S4-04/S4-05/S4-07).
2. Author `python_project.schema.json`, `python_build_system.schema.json`, `python_manifest.schema.json`, `python_import_graph.schema.json` under `src/codegenie/schema/probes/`, mirroring `node_manifest.schema.json`'s structure and the `$id` scheme in `_subschema_convention.md`; set `additionalProperties: false` at every object node.
3. Add a `$ref` per sub-schema into `repo_context.schema.json`'s `properties.probes` block — purely additive rows.
4. Add / extend the schema-validation test so each probe's slice is checked against its sub-schema.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/schema/test_python_probe_subschemas.py` (or extend the existing per-probe-subschema test module).
Test name: `test_python_probe_slices_validate_against_subschemas`.
```python
def test_python_probe_slices_validate_against_subschemas() -> None:
    # arrange: a representative schema_slice for each of the four Python probes;
    #          load python_*.schema.json + the envelope.
    # act: jsonschema-validate each slice against its sub-schema; resolve the envelope $refs.
    # assert: each slice validates; an extra typo'd key fails (additionalProperties: false);
    #         the envelope's properties.probes resolves the new $refs.
```
Fails today: the `python_*.schema.json` files do not exist and the envelope has no `$ref`s for them.

### Green — make it pass
Write the four sub-schemas matching the probe slice shapes; add the four `$ref` rows to the envelope. Smallest schemas that admit the real slices and reject extras.

### Refactor — clean up
Confirm `additionalProperties: false` at *every* nested object, not just the root. Confirm the `$id` values follow the convention's URL scheme. Run the writer against a Python fixture and confirm the produced YAML is envelope-valid.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/schema/probes/python_project.schema.json` | New sub-schema for `PythonProjectProbe`. |
| `src/codegenie/schema/probes/python_build_system.schema.json` | New sub-schema for `PythonBuildSystemProbe`. |
| `src/codegenie/schema/probes/python_manifest.schema.json` | New sub-schema for `PythonManifestProbe`. |
| `src/codegenie/schema/probes/python_import_graph.schema.json` | New sub-schema for `PythonImportGraphProbe`. |
| `src/codegenie/schema/repo_context.schema.json` | Additive `$ref` rows in `properties.probes`. |
| `tests/unit/schema/test_python_probe_subschemas.py` | The red validation test. |

## Out of scope
- The probe implementations — S4-02 / S4-04 / S4-05 / S4-07 (this story pins their slice shapes, it does not change them).
- The dep-graph fact sub-schemas (`UnresolvedDependency` / `IndexOverride`) — Step 5 (those pin the depgraph facts, not the probe slices).
- The `LanguagePack` contract snapshot — S7-05.
- Golden fixtures — S7-04.

## Notes for the implementer
- `additionalProperties: false` must be at **every** object node, not only the root — Phase 1 ADR-0004's discipline; a nested loose object lets a typo'd key through silently.
- The envelope's `probes.*` is `additionalProperties: true` by design (Phase 0 ADR-0013) — do **not** tighten it; strictness lives at the sub-schema. Only *add* `$ref` rows.
- The sub-schemas must match the slices the S4-0x probes *actually emit* — if a probe's slice shape is unclear, read the probe's `schema_slice` construction, do not guess. A schema that does not match the real slice fails the writer at gather time.
- Per-probe sub-schema isolation is what prevents a polyglot repo's Python and Node slices from clobbering each other (edge case #1) — each sub-schema owns its own key namespace under `probes`.
- Match `_subschema_convention.md`'s `$id` URL scheme exactly — a drifting `$id` breaks `$ref` resolution.
