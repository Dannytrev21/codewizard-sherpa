# Story S1-05 — Catalog loader with self-schema + `native_modules.yaml` + `ci_providers.yaml` seed

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready (hardened by phase-story-validator)
**Effort:** M
**Depends on:** S1-02 (consumes `parsers/safe_json` chokepoint precedent), S1-03 (consumes `parsers/safe_yaml` — the actual YAML reader the catalog routes through)
**ADRs honored:** ADR-0006 (catalog versioning), ADR-0008 (in-process parse caps; catalogs route through `safe_yaml.load`); Phase-0 markers-only contract (S1-01)

## Validation notes (phase-story-validator, 2026-05-14)

This story was hardened by the validator from its initial draft. Key changes:

- **Markers-only construction restored (block-tier consistency fix).** The original draft prescribed `CatalogLoadError(path=path, detail=...)` — kwarg construction. That violates the Phase 0 markers-only invariant pinned by `tests/unit/test_errors.py::test_subclasses_are_markers_only` (`cls.__init__ is e.CodegenieError.__init__` + class-dict allowlist) and re-affirmed by S1-01 / S1-02 / S1-03 / S1-04 hardening reports. **Marker subclasses accept exactly one positional `args[0]` message and expose no instance state.** Raise sites must construct via a formatted message string (e.g., `CatalogLoadError(f"{path}: {detail}")`). Adding the prescribed kwargs would `TypeError` at red-commit time against the actual `errors.py` shipped by S1-01 (CV1, TQ1).
- **`tuple[str, ...]` coercion made an AC, not a refactor footnote (block-tier consistency fix).** The arch §"Data model" pins `NativeModuleEntry.system_deps_required: tuple[str, ...]` and `binary_artifacts_glob: tuple[str, ...]`; `CIProviderEntry.marker_paths: tuple[str, ...]`. YAML loads each as `list[str]`. The original draft mentioned the tuple shape only in refactor-note #3 — a refactor footnote, not an AC. A mutation that builds the NamedTuple with `**entry_dict` (passing through the YAML lists) would: (a) pass mypy *if* the NamedTuple field were typed `list[str]` — so it doesn't catch the type drift; (b) silently allow callers to mutate the catalog at runtime (`NATIVE_MODULES["bcrypt"].system_deps_required.append("evil")`), defeating the entire `MappingProxyType` immutability story. Added AC-7 + parametrized `test_named_tuple_sequence_fields_are_tuples` asserting `isinstance(entry.system_deps_required, tuple)` and `assert not isinstance(..., list)` for both sequence fields on both entry types (CV3, TQ2).
- **`parser` field typed as `Literal[...]` (consistency fix).** Arch §"Data model" line 789 pins `CIProviderEntry.parser: Literal["github_actions","gitlab_ci","jenkins","circleci","azure_pipelines"]`. The original draft's NamedTuple shape was vague on this; a mutation that types it `str` would let a typo (`"githb_actions"`) survive at every consumer site. Added AC-8 — the `Literal` annotation is present and `typing.get_type_hints(CIProviderEntry).get("parser")` covers exactly the five-arm set. Schema-level enum is **deliberately not** added (Notes-for-implementer #6 of original draft preserved); the Literal constraint lives at the Python boundary so the YAML schema can stay open for Phase 4+ extension (CN3, CV7).
- **Catalog routes through `parsers.safe_yaml.load` chokepoint (consistency fix).** ADR-0008 requires every YAML read in Phase 1 to go through `safe_yaml.load` (O_NOFOLLOW + size cap + depth walker). The original draft's impl outline #5 prescribed this but no AC pinned it; a mutation using plain `yaml.safe_load(path.read_text())` would silently bypass the symlink + size + depth defenses. Added AC-10 + `test_catalog_routes_through_safe_yaml` (monkey-patch `codegenie.parsers.safe_yaml.load` and assert it is called once per catalog with the catalog path and a `max_bytes` argument ≤ 1 MB) (CN4, TQ7).
- **Module-import is the loader contract, not a side effect to mock around.** The original draft tested `_load_catalog` directly (good) but had no test asserting the **module-level constants** (`NATIVE_MODULES`, `CI_PROVIDERS`, the two `_CATALOG_VERSION` constants) are populated when `codegenie.catalogs` is first imported. A mutation that defines the constants conditionally (`if os.environ.get("CG_LOAD_CATALOGS")`) or lazily (`@functools.cache`'d module getter) would pass every existing test. Added AC-11 + `test_module_level_constants_populated_on_first_import` using a sub-interpreter / `importlib.reload` + `sys.modules.pop` to assert constants exist after a clean import (CV6).
- **Hard-fail propagates uncaught (load-bearing-invariant test, Rule 12).** Edge case #9 says "Hard fail at CLI startup if catalog YAML is malformed or fails self-schema." The original draft's AC said "raises `CatalogLoadError` ... propagated to the CLI" but no test asserted that `catalogs/__init__.py` does **not** catch its own exceptions and fall back to an empty mapping. Added AC-14 + `test_loader_does_not_catch_its_own_errors` (monkey-patch `_load_catalog` to raise `CatalogLoadError`, re-import `codegenie.catalogs`, assert the import itself raises). Mutation #8 (silent fallback to `MappingProxyType({})` with a warning) is caught (CV8, TQ9).
- **`MappingProxyType` immutability extended to defensive-write attempts (`del`, `update`, `pop`, `__setitem__`).** Original draft tested only `__setitem__`. A mutation that returns a `dict` subclass overriding `__setitem__` to raise but allowing `.update()` would pass. Added AC-12 + parametrized `test_mappingproxy_blocks_all_mutation` covering `__setitem__`, `__delitem__`, `.update`, `.pop`, `.clear`, `.setdefault` — each raises `TypeError` (CV2).
- **`additionalProperties: false` at every schema level (consistency fix; ADR-0004 precedent).** ADR-0004 (per-probe sub-schemas) pinned the `additionalProperties: false` discipline. The original draft's `_schema.json` did not declare this at either the top level or per-entry. A mutation that introduces a typo (`cataolg_version`) or a stray field would silently survive validation. Added AC-15 + `test_schema_rejects_unknown_top_level_field`, `test_schema_rejects_unknown_entry_field` (parametrized per catalog) (CN5, CV9, CV10).
- **`minItems: 1` on entries lists.** Empty `entries: []` is a degenerate state every consumer must defensively check for — better to reject at validation time. Added AC-16 + `test_empty_entries_rejected` per catalog (CV12).
- **`catalog_version` and `catalog_entry_version` typed as positive integers in the schema.** Original draft said `catalog_version: int`. JSON Schema `type: integer` allows `0` and negatives. Versions are monotonically increasing positive ints by social contract; the schema can pin `minimum: 1`. Added AC-17 + `test_non_positive_catalog_version_rejected`, `test_non_positive_catalog_entry_version_rejected` (CV11, CN6).
- **Duplicate detection is post-load, not schema-level.** The original AC said "duplicate names rejected (`uniqueItems` on the entries' names, or post-load duplicate detection)". JSON Schema `uniqueItems` applies to entire objects, not a single key — a typo would not catch entries with same `name` but different `notes`. Pin the post-load approach explicitly: AC-18 + `test_duplicate_name_detected_when_entries_differ_in_other_fields` (CV13, TQ4).
- **structlog event assertion via `structlog.testing.capture_logs()` (precedent from S1-02/03/04).** Original AC line 49 said "Emits one `probe.catalog.load` structlog event per catalog at load time" with no test pinning the structured fields. A mutation that emits the event without `catalog_version` (or with the wrong `catalog_name`) would pass. Added AC-19 + `test_catalog_load_event_emitted_with_structured_fields` (per catalog) using the same shape as `test_safe_json.py`'s cap-event tests (CV14, TQ5).
- **`_load_catalog` is the kernel; new catalogs are new callers (Open/Closed, Extension by Addition).** The user-supplied design tradition is honored: a small stable kernel (`_load_catalog(path, entry_cls, schema_subkey) -> tuple[Mapping, int]`) with a registry-via-discriminator pattern (`schema_subkey: Literal["native_modules", "ci_providers"]`). Adding a 3rd catalog (Phase 4 may add `vulnerability_patterns.yaml`, Phase 7 will expand native modules, Phase 8 may add `replacement_catalogs.yaml`) is a new YAML file + new NamedTuple + new `$def` block in `_schema.json` + one new module-scope call to `_load_catalog` — **zero edits to `_load_catalog` itself.** Pinned as AC-20 + `test_kernel_is_closed_for_modification`: a fixture catalog (YAML + NamedTuple + schema fragment, all under `tmp_path`) loads via `_load_catalog` without modifying `catalogs/__init__.py`. Same plugin-shape framing as `parsers/_io.py` (S1-02/03/04 hardening). CLAUDE.md load-bearing commitment — "Extension by addition" — is satisfied (CN7).
- **`schema_subkey: Literal[...]` typed, not bare `str` (consistency fix; make-illegal-states-unrepresentable).** The original draft's `_load_catalog(path, entry_cls, schema_subkey: str)` accepts any string at type-check time — passing `"native_module"` (typo) would `KeyError` at runtime. With the `Literal` constraint, the typo fails mypy --strict. Story sets `schema_subkey: Literal["native_modules", "ci_providers"]` to start. Adding a third catalog widens the `Literal` arms — a deliberate, reviewable edit (this is the **only** edit a new catalog requires inside `catalogs/__init__.py`, and it is the type-level signal that the kernel is being extended). AC-21 pins this; the kernel-is-closed-for-modification AC accommodates the `Literal` widening as the contract-honoring extension shape (not an edit to logic) (CN8).
- **Module docstring + ADR provenance pinned.** Added AC-22 — module docstring references `phase-arch-design.md §"Component design" #10`, ADR-0006 (versioning), ADR-0008 (parser chokepoint), production §2.6 (organizational uniqueness as data).
- **YAML files validate at land-time, not just at runtime.** The 10 native + 5 CI seed entries must pass their own self-schema **at land-time** — a CI test loads the YAMLs and asserts validation. Original draft conflated this with the happy-path unit test. Added AC-23 + `test_shipped_catalogs_validate_against_self_schema` runnable as a sanity check before merge (CV15).
- **`bcrypt`-on-distroless contract honored in seed.** The 10 seed names are non-negotiable (arch §"Component design" #4). Original draft mentioned the names but did not enumerate the `requires_node_gyp` / `system_deps_required` values precedent. The hardened story spells out per-entry seed values to the level of "Phase 7 actually needs this to build a distroless image" (ADR-0006 §"Consequences"). Pinned in implementation outline #4 with researched values; `notes` left to the implementer's judgment (CN9).
- **`probe.catalog.load` event name not hoisted to `Final[str]` in S1-05 — deferred to S1-10 (precedent).** S1-10 lifts every Phase 1 event name to `Final[str]` constants in `codegenie.logging`. S1-05 emits the literal `"probe.catalog.load"` exactly like S1-02 / S1-03 / S1-04 do for `"probe.parser.cap_exceeded"`. Out-of-scope item preserved as a Note for the implementer.
- **AC-style "TDD red test exists, committed, green" demoted from AC.** Process discipline; replaced with a "red→green→refactor commit sequence is documented in the PR description" line under TDD plan, not as an AC (consistent with S1-02 / S1-03 / S1-04 hardenings).

Full report: `_validation/S1-05-catalogs.md`.

## Context

Two catalogs ship in Phase 1 as YAML data files loaded at module import: `native_modules.yaml` (10 seed entries — the load-bearing input for Phase 7's distroless migration) and `ci_providers.yaml` (markers and parser kinds for the CI providers Phase 1 supports). Both are validated against a self-schema at startup and exposed as `MappingProxyType`-wrapped immutable dicts. Each catalog file is listed in `NodeManifestProbe.declared_inputs` (and similar) so editing a catalog cleanly invalidates only the relevant probe's cache entries — that's the ADR-0006 versioning mechanism in action.

The catalogs are organizational uniqueness expressed as data, not prompts (production design §2.6). The Planner queries structured data; it never has to infer your company's rules from prose.

**This story establishes the catalog-loader kernel for the project.** The shape is intentionally the same plugin-pattern framing as `parsers/_io.py` + `parsers/_depth.py` (S1-02/03/04 hardening): a small stable kernel (`_load_catalog`) plus a registry-via-discriminator (`schema_subkey: Literal[...]`). Adding the next catalog (Phase 4's vulnerability patterns, Phase 7's expanded native modules, Phase 8's replacement catalogs) is "new YAML file + new NamedTuple + new schema `$def` + one new module-scope call" — zero edits to `_load_catalog`. The `Literal` widening on `schema_subkey` is the only deliberate per-extension touch and serves as the type-level review signal.

The Phase-0 markers-only invariant (`tests/unit/test_errors.py::test_subclasses_are_markers_only`) means `CatalogLoadError` carries **no instance state**: path and failure detail live in the positional `args[0]` formatted message, recoverable at the catch site by the calling probe (here: the CLI's top-level catch in S4-02 / Phase 0). The slug `"catalogs"` is already in `tests/unit/test_errors.py::DOCUMENTED_MODULE_SLUGS` (S1-01).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #10` — interface (`NATIVE_MODULES`, `CI_PROVIDERS`, the `_CATALOG_VERSION` constants), hard-fail at CLI startup on malformed YAML or schema mismatch, `MappingProxyType` immutability.
  - `../phase-arch-design.md §"Component design" #4` — the seed 10 native modules (`bcrypt`, `sharp`, `better-sqlite3`, `node-canvas`, `node-rdkafka`, `node-pty`, `bufferutil`, `utf-8-validate`, `argon2`, `keytar`) and `NativeModuleEntry` shape (name, requires_node_gyp, system_deps_required, binary_artifacts_glob, notes, catalog_entry_version).
  - `../phase-arch-design.md §"Component design" #5` — `CIProviderEntry` shape (name, marker_paths, parser).
  - `../phase-arch-design.md §"Edge cases"` row 9 — malformed catalog YAML at startup is a hard fail, not a degrade.
  - `../phase-arch-design.md §"Data model"` — `NativeModuleEntry` and `CIProviderEntry` as `NamedTuple`s; `parser: Literal[...]`; sequence fields typed `tuple[str, ...]`.
  - `../phase-arch-design.md §"Harness engineering" → "Logging strategy"` — `probe.catalog.load` event with `catalog_name`, `entries`, `catalog_version` fields; one-shot at startup.
- **Phase ADRs:**
  - `../ADRs/0006-native-module-catalog-versioning.md` — ADR-0006 — `catalog_version` field at file top; catalog YAML in `NodeManifestProbe.declared_inputs`; editing catalog invalidates the probe's cache entries only. Per-entry `catalog_entry_version` for audit trail.
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — ADR-0008 — caps apply at the parser level; catalog YAMLs route through `safe_yaml.load`.
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — ADR-0004 — `additionalProperties: false` discipline at sub-schema roots; catalogs follow the same shape.
- **Source design:**
  - `../final-design.md §"Components" #10` — design statement.
- **Existing code (already on `master` after S1-01..S1-04):**
  - `src/codegenie/parsers/safe_yaml.py` (S1-03) — the YAML chokepoint the catalog loader consumes.
  - `src/codegenie/parsers/_io.py` + `src/codegenie/parsers/_depth.py` (S1-02/03/04 lifted) — kernel precedent for the catalog loader's plugin-shape framing.
  - `src/codegenie/errors.py` (S1-01) — `CatalogLoadError` is a **marker only** (no `__init__`, no class attributes; see module docstring lines 20–26 and `tests/unit/test_errors.py::test_subclasses_are_markers_only`). The slug `"catalogs"` is already in `DOCUMENTED_MODULE_SLUGS`.
  - `src/codegenie/logging.py` (Phase 0) — `structlog` factory used for the `probe.catalog.load` event.
  - `tests/unit/parsers/test_safe_json.py` / `test_safe_yaml.py` (S1-02/S1-03) — precedent for `structlog.testing.capture_logs()` event-field assertions, markers-only parametrized check.
- **S1-02/03/04 hardened story shapes (precedent):**
  - `_validation/S1-02-safe-json-parser.md`, `_validation/S1-03-safe-yaml-parser.md`, `_validation/S1-04-jsonc-parser.md` — kwarg-construction-is-the-block defense, plugin-shape kernel framing, structured-field event assertions, markers-only positional construction.
- **External docs (only if directly relevant):**
  - JSON Schema Draft 2020-12 — `jsonschema.Draft202012Validator` (`Draft202012Validator(schema).iter_errors(data)` shape).

## Goal

Ship `src/codegenie/catalogs/__init__.py` plus seed YAML files + self-schema such that:

1. At first import of `codegenie.catalogs`, `_load_catalog` is invoked twice — once each for `native_modules.yaml` and `ci_providers.yaml` — and binds the four documented module-level constants. Any failure (`SymlinkRefusedError`, `SizeCapExceeded`, `DepthCapExceeded`, `MalformedYAMLError` from `parsers.safe_yaml.load`; schema-mismatch from `jsonschema`; duplicate name from post-load detection) is translated to `CatalogLoadError(f"{path}: {detail}")` and **propagates uncaught** out of the module. The CLI's top-level catch (S4-02 / Phase 0) turns this into exit-code 2 (load-bearing-invariant violation — Edge case #9).
2. `_load_catalog(path: Path, entry_cls: type[T], schema_subkey: Literal["native_modules", "ci_providers"]) -> tuple[Mapping[str, T], int]` is the kernel — pure-of-side-effects-beyond-one-structlog-event; testable in isolation; consumed by the two module-scope calls and by future-catalog stories (Phase 4+, Phase 7) without modification to its body.
3. Each catalog file's bytes route through `parsers.safe_yaml.load(path, max_bytes=1_000_000)` (O_NOFOLLOW + size cap + depth walker — ADR-0008). The catalog loader does **not** open files itself.
4. Validation is `jsonschema.Draft202012Validator(_LOAD_SCHEMA[schema_subkey]).iter_errors(data)`. The first error's `json_path` is included in the translated message; the full validator error is preserved as the `__cause__`.
5. Duplicate names are detected post-load (`len(entries) != len({e["name"] for e in entries})`) and raise `CatalogLoadError(f"{path}: duplicate name: {name}")`.
6. Each entry is constructed as `entry_cls(**coerced)` where `coerced` converts `list[str]` sequence fields to `tuple[str, ...]` — preserving the `NamedTuple`'s structural immutability across **all** fields (not just the top-level mapping).
7. The returned `Mapping[str, T]` is a `MappingProxyType` over `{entry.name: entry for entry in entries}`. Every mutation API on the `MappingProxyType` (`__setitem__`, `__delitem__`, `.update`, `.pop`, `.clear`, `.setdefault`) raises `TypeError`.
8. Exactly one `probe.catalog.load` structlog event fires per catalog, with `event="probe.catalog.load"`, `catalog_name ∈ {"native_modules","ci_providers"}`, `entries=<int>`, `catalog_version=<int>`.
9. `NativeModuleEntry` is `NamedTuple("NativeModuleEntry", [("name", str), ("requires_node_gyp", bool), ("system_deps_required", tuple[str, ...]), ("binary_artifacts_glob", tuple[str, ...]), ("notes", str), ("catalog_entry_version", int)])`. `CIProviderEntry` is `NamedTuple("CIProviderEntry", [("name", str), ("marker_paths", tuple[str, ...]), ("parser", Literal["github_actions","gitlab_ci","jenkins","circleci","azure_pipelines"])])`.
10. The self-schema (`_schema.json`) carries two `$def`s (`native_modules` and `ci_providers`); each declares `additionalProperties: false` at both the top-level catalog root and at every entry-object root. `catalog_version` is required `{type: integer, minimum: 1}`. Sequence fields use `{type: array, items: {type: string}}`. `minItems: 1` on `entries`.

All typed exceptions are constructed as **markers** — single positional formatted-message string — preserving the Phase-0 `test_subclasses_are_markers_only` invariant.

## Acceptance criteria

Module / package shape:

- [ ] **AC-1** — `src/codegenie/catalogs/__init__.py` exports `NATIVE_MODULES`, `CI_PROVIDERS`, `NATIVE_MODULES_CATALOG_VERSION`, `CI_PROVIDERS_CATALOG_VERSION`, `NativeModuleEntry`, `CIProviderEntry`. `__all__` enumerates exactly these six names.
- [ ] **AC-2** — `NativeModuleEntry` is a `typing.NamedTuple` with fields (in order): `name: str`, `requires_node_gyp: bool`, `system_deps_required: tuple[str, ...]`, `binary_artifacts_glob: tuple[str, ...]`, `notes: str`, `catalog_entry_version: int`. `typing.get_type_hints(NativeModuleEntry)` returns annotations exactly matching the arch §"Data model" types.
- [ ] **AC-3** — `CIProviderEntry` is a `typing.NamedTuple` with fields (in order): `name: str`, `marker_paths: tuple[str, ...]`, `parser: Literal["github_actions","gitlab_ci","jenkins","circleci","azure_pipelines"]`. `typing.get_type_hints(CIProviderEntry)` returns annotations exactly matching the arch §"Data model" types.

Catalog content:

- [ ] **AC-4** — `src/codegenie/catalogs/native_modules.yaml` carries `catalog_version: 1` at top level and exactly the 10 seed entries listed in arch §"Component design" #4 (`bcrypt`, `sharp`, `better-sqlite3`, `node-canvas`, `node-rdkafka`, `node-pty`, `bufferutil`, `utf-8-validate`, `argon2`, `keytar`). Each entry carries the six documented fields.
- [ ] **AC-5** — `src/codegenie/catalogs/ci_providers.yaml` carries `catalog_version: 1` at top level and exactly five entries (`github_actions`, `gitlab_ci`, `circleci`, `jenkins`, `azure_pipelines`); each carries `marker_paths` and `parser`. `github_actions.marker_paths` includes both `.github/workflows/*.yml` and `.github/workflows/*.yaml`.

Loader behavior:

- [ ] **AC-6** — `NATIVE_MODULES` and `CI_PROVIDERS` are `MappingProxyType` instances at module scope (`isinstance(cat.NATIVE_MODULES, types.MappingProxyType) is True`). They are also `collections.abc.Mapping` instances (`isinstance(cat.NATIVE_MODULES, Mapping) is True`).
- [ ] **AC-7** — Sequence fields on every NamedTuple are `tuple[str, ...]` at **runtime** (not `list`). For every `NativeModuleEntry` in `NATIVE_MODULES.values()` and every `CIProviderEntry` in `CI_PROVIDERS.values()`: `isinstance(entry.system_deps_required, tuple) is True` and `isinstance(entry.system_deps_required, list) is False`; same for `binary_artifacts_glob` and `marker_paths`.
- [ ] **AC-8** — `CIProviderEntry.parser` is annotated as `Literal["github_actions","gitlab_ci","jenkins","circleci","azure_pipelines"]`; `typing.get_args(typing.get_type_hints(CIProviderEntry)["parser"])` returns exactly the five-arm tuple in declaration order.
- [ ] **AC-9** — `NATIVE_MODULES_CATALOG_VERSION` and `CI_PROVIDERS_CATALOG_VERSION` are `int` with values exactly equal to the `catalog_version` field at the top of each YAML file (today: `1`).
- [ ] **AC-10** — Catalog YAML bytes route through `codegenie.parsers.safe_yaml.load(path, max_bytes=…)`. A monkey-patch that replaces `safe_yaml.load` with a tracking spy observes exactly two calls during the first import of `codegenie.catalogs` — one with the absolute path of `native_modules.yaml`, one with `ci_providers.yaml`, each with `max_bytes ≤ 1_000_000`. The catalog loader does **not** call `os.open`, `pathlib.Path.read_text`, `pathlib.Path.read_bytes`, or `yaml.*` directly.
- [ ] **AC-11** — Module-level constants are populated as a side effect of importing `codegenie.catalogs`. A clean import (`sys.modules.pop("codegenie.catalogs", None); importlib.import_module("codegenie.catalogs")`) results in the four constants being non-`None` and non-empty afterwards.
- [ ] **AC-12** — `MappingProxyType` blocks every mutation API. The parametrized test asserts each of the following raises `TypeError`: `m["x"] = ...`, `del m["bcrypt"]`, `m.update({"x": ...})`, `m.pop("bcrypt")`, `m.clear()`, `m.setdefault("x", ...)`.

Failure modes:

- [ ] **AC-13** — Calling `_load_catalog(path, NativeModuleEntry, schema_subkey="native_modules")` against a malformed YAML file raises `CatalogLoadError`. The exception is constructed as a marker — `exc.args` is a single-element tuple, `exc.args[0]` is a `str` containing `str(path)` — no `.path`, `.detail`, `.warning_id` attributes; `cls.__init__ is CodegenieError.__init__` (already pinned by S1-01's invariant test).
- [ ] **AC-14** — Importing `codegenie.catalogs` does **not** catch its own raised exceptions. If `_load_catalog` raises (e.g., because monkey-patching forces it), the `ImportError` / `CatalogLoadError` propagates out of the `import` statement. There is no fallback to `MappingProxyType({})`; there is no warning-and-continue; the load-bearing-invariant violation surfaces (Rule 12 — Fail Loud).
- [ ] **AC-15** — Schema rejects unknown fields. The schema declares `additionalProperties: false` at (a) the catalog top level, and (b) every entry-object root. An extra top-level field (e.g., `cataolg_version` typo) and an extra entry field (e.g., `nots`) each cause `_load_catalog` to raise `CatalogLoadError` with a message containing the offending JSON path.
- [ ] **AC-16** — Schema rejects an empty entries list (`entries: []`) via `minItems: 1`. `_load_catalog` raises `CatalogLoadError`.
- [ ] **AC-17** — `catalog_version` and `catalog_entry_version` are `{type: integer, minimum: 1}` in the schema. Zero or negative integers cause `_load_catalog` to raise `CatalogLoadError`.
- [ ] **AC-18** — Duplicate names are detected **post-load** (not via schema `uniqueItems`). Two entries with the same `name` but different `notes` / `system_deps_required` are caught; the raised `CatalogLoadError`'s `args[0]` contains the duplicated name.

Event emission:

- [ ] **AC-19** — Exactly one `probe.catalog.load` structlog event fires per catalog (two total during a clean import). Each event carries `event="probe.catalog.load"`, `catalog_name` exactly matching one of `"native_modules" | "ci_providers"`, `entries` equal to `len(returned_mapping)`, and `catalog_version` equal to the int from the YAML. The structured-field assertion uses `structlog.testing.capture_logs()` (S1-02/03/04 precedent). The event does **not** fire on failure paths.

Extension by addition (kernel discipline):

- [ ] **AC-20** — A fixture catalog (a fresh YAML file + new NamedTuple + new schema `$def`, all constructed inside the test under `tmp_path`) loads via `_load_catalog` without modifying the body of `_load_catalog` (the test does not edit `catalogs/__init__.py`). This asserts the kernel is closed for modification, open for extension: future catalogs (Phase 4 vulnerability patterns, Phase 7 expanded native modules) ship as new files + new callers.
- [ ] **AC-21** — `_load_catalog`'s `schema_subkey` parameter is annotated `Literal["native_modules", "ci_providers"]`. `typing.get_args(typing.get_type_hints(_load_catalog)["schema_subkey"])` returns exactly the two-arm tuple. Widening the Literal (adding a third arm) is the **only** deliberate edit a new catalog requires inside `catalogs/__init__.py`; it is a type-level review signal.

Documentation + provenance:

- [ ] **AC-22** — `src/codegenie/catalogs/__init__.py` module docstring references `phase-arch-design.md §"Component design" #10`, ADR-0006 (versioning), ADR-0008 (parser chokepoint), production §2.6 (organizational uniqueness as data). The slug `"catalogs"` is already in `tests/unit/test_errors.py::DOCUMENTED_MODULE_SLUGS` (S1-01) and the per-module-mention contract for `CatalogLoadError` continues to hold (Phase-0 docstring discipline).
- [ ] **AC-23** — A regression test (`test_shipped_catalogs_validate_against_self_schema`) loads `native_modules.yaml` and `ci_providers.yaml` via `_load_catalog` and asserts both succeed. This is the land-time gate so a hand-edit to a shipped YAML cannot regress the catalog.

Quality gates:

- [ ] **AC-24** — `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. **`src/codegenie/catalogs/__init__.py`** — module docstring (provenance per AC-22), `NamedTuple` definitions, `_load_catalog` kernel, two module-scope call sites assigning the four documented constants. Total target: ~120 LOC with docstrings.
2. **`src/codegenie/catalogs/_schema.json`** — JSON Schema Draft 2020-12. Two `$def`s — `native_modules` and `ci_providers`. Each `$def`:
   - `type: object`
   - `additionalProperties: false`
   - `required: ["catalog_version", "entries"]`
   - `catalog_version: {type: integer, minimum: 1}`
   - `entries: {type: array, minItems: 1, items: {<entry-shape>}}`
   - `<entry-shape>` is itself an object with `additionalProperties: false`, all fields `required`, sequence fields typed `{type: array, items: {type: string}}`, `parser` (CI only) typed `{type: string}` (Literal lives in Python; schema stays open per Notes #6), `catalog_entry_version: {type: integer, minimum: 1}` (native modules only).
3. **`src/codegenie/catalogs/native_modules.yaml`** — `catalog_version: 1` plus the 10 seed entries enumerated in arch §"Component design" #4. Seed values (research these on npm/GitHub before committing; defaults below are reasonable starting points and ADR-0006 says Phase 7 will surface gaps):
   - `bcrypt`: `requires_node_gyp: true`, `system_deps_required: [libstdc++]`, `binary_artifacts_glob: ["build/Release/*.node"]`, `notes: "bcrypt — native bindings to OpenBSD's bcrypt"`, `catalog_entry_version: 1`.
   - `sharp`: `requires_node_gyp: true`, `system_deps_required: [libvips]`, `binary_artifacts_glob: ["build/Release/*.node", "vendor/**/*"]`, `notes: "sharp — libvips image-processing wrapper"`, `catalog_entry_version: 1`.
   - `better-sqlite3`: `requires_node_gyp: true`, `system_deps_required: []`, `binary_artifacts_glob: ["build/Release/*.node"]`, `notes: "better-sqlite3 — bundled SQLite; statically linked"`, `catalog_entry_version: 1`.
   - `node-canvas`: `requires_node_gyp: true`, `system_deps_required: [libcairo2, libjpeg, libpango-1.0]`, `binary_artifacts_glob: ["build/Release/*.node"]`, `notes: "node-canvas — Cairo-backed canvas API"`, `catalog_entry_version: 1`.
   - `node-rdkafka`: `requires_node_gyp: true`, `system_deps_required: [librdkafka]`, `binary_artifacts_glob: ["build/Release/*.node"]`, `notes: "node-rdkafka — librdkafka bindings"`, `catalog_entry_version: 1`.
   - `node-pty`: `requires_node_gyp: true`, `system_deps_required: []`, `binary_artifacts_glob: ["build/Release/*.node"]`, `notes: "node-pty — pseudo-terminal forking"`, `catalog_entry_version: 1`.
   - `bufferutil`: `requires_node_gyp: true`, `system_deps_required: []`, `binary_artifacts_glob: ["build/Release/*.node", "prebuilds/**/*.node"]`, `notes: "bufferutil — ws performance helpers"`, `catalog_entry_version: 1`.
   - `utf-8-validate`: `requires_node_gyp: true`, `system_deps_required: []`, `binary_artifacts_glob: ["build/Release/*.node", "prebuilds/**/*.node"]`, `notes: "utf-8-validate — ws performance helpers"`, `catalog_entry_version: 1`.
   - `argon2`: `requires_node_gyp: true`, `system_deps_required: []`, `binary_artifacts_glob: ["build/Release/*.node", "prebuilds/**/*.node"]`, `notes: "argon2 — Argon2 password hashing"`, `catalog_entry_version: 1`.
   - `keytar`: `requires_node_gyp: true`, `system_deps_required: [libsecret-1-0]`, `binary_artifacts_glob: ["build/Release/*.node"]`, `notes: "keytar — OS keychain bindings (Linux: libsecret)"`, `catalog_entry_version: 1`.
4. **`src/codegenie/catalogs/ci_providers.yaml`** — `catalog_version: 1` plus the 5 provider entries:
   - `github_actions`: `marker_paths: [".github/workflows/*.yml", ".github/workflows/*.yaml"]`, `parser: "github_actions"`.
   - `gitlab_ci`: `marker_paths: [".gitlab-ci.yml"]`, `parser: "gitlab_ci"`.
   - `circleci`: `marker_paths: [".circleci/config.yml"]`, `parser: "circleci"`.
   - `jenkins`: `marker_paths: ["Jenkinsfile"]`, `parser: "jenkins"`.
   - `azure_pipelines`: `marker_paths: ["azure-pipelines.yml"]`, `parser: "azure_pipelines"`.
5. **`_load_catalog` body sketch** (the kernel — closed for modification):
   ```python
   _T = TypeVar("_T", bound=NamedTuple)

   def _load_catalog(
       path: Path,
       entry_cls: type[_T],
       schema_subkey: Literal["native_modules", "ci_providers"],
   ) -> tuple[Mapping[str, _T], int]:
       try:
           data = safe_yaml.load(path, max_bytes=1_000_000)
       except CodegenieError as exc:
           raise CatalogLoadError(f"{path}: {exc.args[0]}") from exc
       schema = _LOAD_SCHEMA["$defs"][schema_subkey]
       errors = list(Draft202012Validator(schema).iter_errors(data))
       if errors:
           first = errors[0]
           raise CatalogLoadError(f"{path}: {first.json_path}: {first.message}") from first
       entries = data["entries"]
       names = [e["name"] for e in entries]
       seen: set[str] = set()
       for name in names:
           if name in seen:
               raise CatalogLoadError(f"{path}: duplicate name: {name}")
           seen.add(name)
       built: dict[str, _T] = {}
       for raw in entries:
           coerced = _coerce_sequences(raw, entry_cls)
           built[raw["name"]] = entry_cls(**coerced)
       catalog_version = int(data["catalog_version"])
       _logger.info(
           "probe.catalog.load",
           catalog_name=schema_subkey,
           entries=len(built),
           catalog_version=catalog_version,
       )
       return MappingProxyType(built), catalog_version
   ```
   `_coerce_sequences` inspects `entry_cls`'s annotations (`typing.get_type_hints(entry_cls)`) and replaces any `list[str]` YAML value whose target annotation is `tuple[str, ...]` with `tuple(value)`. Self-contained; ~10 LOC.
6. **Module-scope binding:**
   ```python
   _CATALOG_DIR = Path(__file__).parent
   NATIVE_MODULES, NATIVE_MODULES_CATALOG_VERSION = _load_catalog(
       _CATALOG_DIR / "native_modules.yaml", NativeModuleEntry, schema_subkey="native_modules"
   )
   CI_PROVIDERS, CI_PROVIDERS_CATALOG_VERSION = _load_catalog(
       _CATALOG_DIR / "ci_providers.yaml", CIProviderEntry, schema_subkey="ci_providers"
   )
   ```
   `importlib.resources` is the more-correct API but only at the cost of complexity Rule-2 doesn't justify when the YAMLs ship next to `__init__.py`.

## TDD plan — red / green / refactor

The red→green→refactor commit sequence is documented in the PR description (process discipline; not an AC).

### Red — failing test first

Test file: `tests/unit/catalogs/test_catalog_loader.py`. Each test names its AC and the mutation it catches. ~22 tests total.

```python
# tests/unit/catalogs/test_catalog_loader.py
import importlib
import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Literal, NamedTuple, get_args, get_type_hints

import pytest
import structlog.testing

import codegenie.errors as e


# --- Module shape ----------------------------------------------------------

def test_module_exports_documented_names():
    # AC-1
    import codegenie.catalogs as cat
    assert set(cat.__all__) == {
        "NATIVE_MODULES", "CI_PROVIDERS",
        "NATIVE_MODULES_CATALOG_VERSION", "CI_PROVIDERS_CATALOG_VERSION",
        "NativeModuleEntry", "CIProviderEntry",
    }


def test_native_module_entry_shape():
    # AC-2: tuple[str, ...] sequence fields; Literal-free; 6 fields in order.
    from codegenie.catalogs import NativeModuleEntry
    hints = get_type_hints(NativeModuleEntry)
    assert list(NativeModuleEntry._fields) == [
        "name", "requires_node_gyp", "system_deps_required",
        "binary_artifacts_glob", "notes", "catalog_entry_version",
    ]
    assert hints["name"] is str
    assert hints["requires_node_gyp"] is bool
    assert hints["system_deps_required"] == tuple[str, ...]
    assert hints["binary_artifacts_glob"] == tuple[str, ...]
    assert hints["notes"] is str
    assert hints["catalog_entry_version"] is int


def test_ci_provider_entry_shape():
    # AC-3 + AC-8
    from codegenie.catalogs import CIProviderEntry
    hints = get_type_hints(CIProviderEntry)
    assert list(CIProviderEntry._fields) == ["name", "marker_paths", "parser"]
    assert hints["name"] is str
    assert hints["marker_paths"] == tuple[str, ...]
    assert get_args(hints["parser"]) == (
        "github_actions", "gitlab_ci", "jenkins", "circleci", "azure_pipelines",
    )


# --- Catalog content -------------------------------------------------------

def test_native_modules_seed_complete():
    # AC-4 — exactly 10 seed entries.
    import codegenie.catalogs as cat
    expected = {"bcrypt", "sharp", "better-sqlite3", "node-canvas", "node-rdkafka",
                "node-pty", "bufferutil", "utf-8-validate", "argon2", "keytar"}
    assert set(cat.NATIVE_MODULES) == expected
    bcrypt = cat.NATIVE_MODULES["bcrypt"]
    assert bcrypt.requires_node_gyp is True
    assert isinstance(bcrypt.catalog_entry_version, int)


def test_ci_providers_seed_complete():
    # AC-5
    import codegenie.catalogs as cat
    expected = {"github_actions", "gitlab_ci", "circleci", "jenkins", "azure_pipelines"}
    assert set(cat.CI_PROVIDERS) == expected
    gha = cat.CI_PROVIDERS["github_actions"]
    assert ".github/workflows/*.yml" in gha.marker_paths
    assert ".github/workflows/*.yaml" in gha.marker_paths
    assert gha.parser == "github_actions"


# --- Loader runtime behavior -----------------------------------------------

def test_mappings_are_mappingproxy_and_mapping():
    # AC-6
    import codegenie.catalogs as cat
    assert isinstance(cat.NATIVE_MODULES, MappingProxyType)
    assert isinstance(cat.NATIVE_MODULES, Mapping)
    assert isinstance(cat.CI_PROVIDERS, MappingProxyType)


@pytest.mark.parametrize(
    "catalog_attr, sequence_attr",
    [
        ("NATIVE_MODULES", "system_deps_required"),
        ("NATIVE_MODULES", "binary_artifacts_glob"),
        ("CI_PROVIDERS", "marker_paths"),
    ],
)
def test_named_tuple_sequence_fields_are_tuples(catalog_attr, sequence_attr):
    # AC-7 — catches mutation #2 (forgot the list→tuple coercion).
    import codegenie.catalogs as cat
    catalog = getattr(cat, catalog_attr)
    for entry in catalog.values():
        value = getattr(entry, sequence_attr)
        assert isinstance(value, tuple), f"{sequence_attr} is {type(value).__name__}, not tuple"
        assert not isinstance(value, list)


def test_catalog_version_constants_are_positive_ints():
    # AC-9
    import codegenie.catalogs as cat
    assert isinstance(cat.NATIVE_MODULES_CATALOG_VERSION, int) and cat.NATIVE_MODULES_CATALOG_VERSION >= 1
    assert isinstance(cat.CI_PROVIDERS_CATALOG_VERSION, int) and cat.CI_PROVIDERS_CATALOG_VERSION >= 1


def test_catalog_routes_through_safe_yaml(monkeypatch):
    # AC-10 — catches mutation #7 (bypassing the chokepoint).
    import codegenie.parsers.safe_yaml as syaml
    calls: list[tuple[Path, int]] = []
    real = syaml.load

    def spy(path, *, max_bytes, max_depth=64):
        calls.append((path, max_bytes))
        return real(path, max_bytes=max_bytes, max_depth=max_depth)

    monkeypatch.setattr(syaml, "load", spy)
    sys.modules.pop("codegenie.catalogs", None)
    importlib.import_module("codegenie.catalogs")
    assert len(calls) == 2
    names = {p.name for p, _ in calls}
    assert names == {"native_modules.yaml", "ci_providers.yaml"}
    assert all(mb <= 1_000_000 for _, mb in calls)


def test_module_level_constants_populated_on_first_import():
    # AC-11
    sys.modules.pop("codegenie.catalogs", None)
    cat = importlib.import_module("codegenie.catalogs")
    assert cat.NATIVE_MODULES, "NATIVE_MODULES empty after import"
    assert cat.CI_PROVIDERS, "CI_PROVIDERS empty after import"
    assert cat.NATIVE_MODULES_CATALOG_VERSION
    assert cat.CI_PROVIDERS_CATALOG_VERSION


@pytest.mark.parametrize(
    "mutation",
    [
        lambda m: m.__setitem__("x", None),
        lambda m: m.__delitem__("bcrypt"),
        lambda m: m.update({"x": None}),
        lambda m: m.pop("bcrypt"),
        lambda m: m.clear(),
        lambda m: m.setdefault("x", None),
    ],
)
def test_mappingproxy_blocks_all_mutation(mutation):
    # AC-12
    import codegenie.catalogs as cat
    with pytest.raises(TypeError):
        mutation(cat.NATIVE_MODULES)


# --- Failure modes ---------------------------------------------------------

def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def test_malformed_yaml_translates_to_catalog_load_error(tmp_path):
    # AC-13 — markers-only positional construction.
    from codegenie.catalogs import _load_catalog, NativeModuleEntry  # type: ignore[attr-defined]
    bad = _write(tmp_path, "native_modules.yaml", ":\n:\n:invalid")
    with pytest.raises(e.CatalogLoadError) as ei:
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")
    assert len(ei.value.args) == 1
    assert isinstance(ei.value.args[0], str)
    assert str(bad) in ei.value.args[0]
    assert not hasattr(ei.value, "path")
    assert not hasattr(ei.value, "detail")


def test_catalog_load_error_is_marker():
    # AC-13 — class-shape invariant (re-asserting S1-01 contract locally).
    assert e.CatalogLoadError.__init__ is e.CodegenieError.__init__
    exc = e.CatalogLoadError("some message")
    assert exc.args == ("some message",)


def test_loader_does_not_catch_its_own_errors(monkeypatch):
    # AC-14 — hard fail at import time propagates.
    import codegenie.catalogs as cat_module  # may already be cached
    sys.modules.pop("codegenie.catalogs", None)

    # Force _load_catalog to raise on the first call by routing safe_yaml to
    # raise a MalformedYAMLError on read.
    import codegenie.parsers.safe_yaml as syaml

    def boom(path, *, max_bytes, max_depth=64):
        raise e.MalformedYAMLError(f"{path}: forced failure")

    monkeypatch.setattr(syaml, "load", boom)
    with pytest.raises(e.CatalogLoadError):
        importlib.import_module("codegenie.catalogs")


@pytest.mark.parametrize(
    "extra_top_field, expected_path_fragment",
    [
        ("cataolg_version: 1", "cataolg_version"),
        ("rogue: yes", "rogue"),
    ],
)
def test_schema_rejects_unknown_top_level_field(tmp_path, extra_top_field, expected_path_fragment):
    # AC-15
    from codegenie.catalogs import _load_catalog, NativeModuleEntry  # type: ignore[attr-defined]
    body = (
        "catalog_version: 1\n"
        f"{extra_top_field}\n"
        "entries:\n"
        "  - {name: bcrypt, requires_node_gyp: true, system_deps_required: [],"
        "     binary_artifacts_glob: [], notes: '', catalog_entry_version: 1}\n"
    )
    bad = _write(tmp_path, "native_modules.yaml", body)
    with pytest.raises(e.CatalogLoadError) as ei:
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")
    assert expected_path_fragment in ei.value.args[0] or "additional properties" in ei.value.args[0].lower()


def test_schema_rejects_unknown_entry_field(tmp_path):
    # AC-15
    from codegenie.catalogs import _load_catalog, NativeModuleEntry  # type: ignore[attr-defined]
    body = (
        "catalog_version: 1\n"
        "entries:\n"
        "  - {name: bcrypt, requires_node_gyp: true, system_deps_required: [],"
        "     binary_artifacts_glob: [], notes: '', catalog_entry_version: 1, nots: bogus}\n"
    )
    bad = _write(tmp_path, "native_modules.yaml", body)
    with pytest.raises(e.CatalogLoadError):
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")


def test_empty_entries_rejected(tmp_path):
    # AC-16
    from codegenie.catalogs import _load_catalog, NativeModuleEntry  # type: ignore[attr-defined]
    bad = _write(tmp_path, "native_modules.yaml", "catalog_version: 1\nentries: []\n")
    with pytest.raises(e.CatalogLoadError):
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")


@pytest.mark.parametrize("bad_version", [0, -1])
def test_non_positive_catalog_version_rejected(tmp_path, bad_version):
    # AC-17
    from codegenie.catalogs import _load_catalog, NativeModuleEntry  # type: ignore[attr-defined]
    body = (
        f"catalog_version: {bad_version}\n"
        "entries:\n"
        "  - {name: bcrypt, requires_node_gyp: true, system_deps_required: [],"
        "     binary_artifacts_glob: [], notes: '', catalog_entry_version: 1}\n"
    )
    bad = _write(tmp_path, "native_modules.yaml", body)
    with pytest.raises(e.CatalogLoadError):
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")


def test_duplicate_name_detected_when_entries_differ_in_other_fields(tmp_path):
    # AC-18 — schema uniqueItems would NOT catch this.
    from codegenie.catalogs import _load_catalog, NativeModuleEntry  # type: ignore[attr-defined]
    body = (
        "catalog_version: 1\n"
        "entries:\n"
        "  - {name: bcrypt, requires_node_gyp: true, system_deps_required: [],"
        "     binary_artifacts_glob: [], notes: 'first', catalog_entry_version: 1}\n"
        "  - {name: bcrypt, requires_node_gyp: false, system_deps_required: [foo],"
        "     binary_artifacts_glob: [bar], notes: 'second', catalog_entry_version: 2}\n"
    )
    bad = _write(tmp_path, "native_modules.yaml", body)
    with pytest.raises(e.CatalogLoadError) as ei:
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")
    assert "bcrypt" in ei.value.args[0]


# --- Event emission --------------------------------------------------------

def test_catalog_load_event_emitted_with_structured_fields():
    # AC-19
    sys.modules.pop("codegenie.catalogs", None)
    with structlog.testing.capture_logs() as logs:
        importlib.import_module("codegenie.catalogs")
    events = [e for e in logs if e.get("event") == "probe.catalog.load"]
    assert len(events) == 2
    by_name = {e["catalog_name"]: e for e in events}
    assert set(by_name) == {"native_modules", "ci_providers"}
    for name, ev in by_name.items():
        assert isinstance(ev["entries"], int) and ev["entries"] >= 1
        assert isinstance(ev["catalog_version"], int) and ev["catalog_version"] >= 1


# --- Extension by addition -------------------------------------------------

def test_kernel_is_closed_for_modification(tmp_path):
    # AC-20 — adding a 3rd-style catalog requires zero edits to _load_catalog.
    # The test fakes a new schema subkey by monkey-patching _LOAD_SCHEMA in
    # place; in the future, widening the Literal arms is the only deliberate
    # edit (AC-21).
    from codegenie.catalogs import _load_catalog, _LOAD_SCHEMA  # type: ignore[attr-defined]

    class FixtureEntry(NamedTuple):
        name: str
        tag: str

    fixture_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["catalog_version", "entries"],
        "properties": {
            "catalog_version": {"type": "integer", "minimum": 1},
            "entries": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "tag"],
                    "properties": {"name": {"type": "string"}, "tag": {"type": "string"}},
                },
            },
        },
    }
    _LOAD_SCHEMA["$defs"]["fixture"] = fixture_schema
    try:
        good = _write(
            tmp_path, "fixture.yaml",
            "catalog_version: 1\nentries:\n  - {name: a, tag: x}\n  - {name: b, tag: y}\n",
        )
        mapping, version = _load_catalog(good, FixtureEntry, schema_subkey="fixture")  # type: ignore[arg-type]
        assert version == 1
        assert set(mapping) == {"a", "b"}
        assert mapping["a"].tag == "x"
    finally:
        del _LOAD_SCHEMA["$defs"]["fixture"]


def test_schema_subkey_is_literal_typed():
    # AC-21
    from codegenie.catalogs import _load_catalog  # type: ignore[attr-defined]
    hints = get_type_hints(_load_catalog)
    assert set(get_args(hints["schema_subkey"])) == {"native_modules", "ci_providers"}


# --- Provenance ------------------------------------------------------------

def test_module_docstring_references_arch_and_adrs():
    # AC-22
    import codegenie.catalogs as cat
    doc = cat.__doc__ or ""
    assert "Component design" in doc
    assert "ADR-0006" in doc
    assert "ADR-0008" in doc


# --- Shipped-content sanity ------------------------------------------------

def test_shipped_catalogs_validate_against_self_schema():
    # AC-23 — land-time gate.
    from codegenie.catalogs import (
        _load_catalog, NativeModuleEntry, CIProviderEntry,  # type: ignore[attr-defined]
    )
    pkg_dir = Path(importlib.import_module("codegenie.catalogs").__file__).parent  # type: ignore[arg-type]
    nm, nm_v = _load_catalog(pkg_dir / "native_modules.yaml", NativeModuleEntry, schema_subkey="native_modules")
    ci, ci_v = _load_catalog(pkg_dir / "ci_providers.yaml", CIProviderEntry, schema_subkey="ci_providers")
    assert len(nm) == 10 and nm_v >= 1
    assert len(ci) == 5 and ci_v >= 1
```

Commit at red. Confirm `ImportError` / `AttributeError` / `pytest.fail`.

### Green — minimal impl

Implement per the sketch in implementation outline #5. Use `jsonschema.Draft202012Validator(schema).iter_errors(data)` and raise `CatalogLoadError` from the first error with its `json_path` + `message` formatted into a single `args[0]` string. Duplicate detection: a `set` walk in declaration order — first second-occurrence raises. Coerce sequence fields by inspecting `typing.get_type_hints(entry_cls)` and converting any value whose annotation is `tuple[str, ...]` from the YAML's `list[str]`.

### Refactor — clean up

- Module docstring naming `phase-arch-design.md §"Component design" #10`, ADR-0006 (versioning), ADR-0008 (parser chokepoint), production §2.6 (data, not prompts).
- Expose `_load_catalog`, `_LOAD_SCHEMA`, `NativeModuleEntry`, `CIProviderEntry` for test reuse but prefix kernel helpers with underscore. `_LOAD_SCHEMA` is loaded once at module scope from `_schema.json` via `json.loads(Path(__file__).parent.joinpath("_schema.json").read_text())`.
- `mypy --strict`: `jsonschema` may need typed stubs (`types-jsonschema`); add to `dev` extras if not present.
- The `_logger` is a module-scope `structlog.get_logger(__name__)` so events route through Phase 0's structlog config; no-op until the CLI configures logging.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/catalogs/__init__.py` | New — loader kernel, NamedTuples, module-level constants |
| `src/codegenie/catalogs/native_modules.yaml` | New — 10 seed entries |
| `src/codegenie/catalogs/ci_providers.yaml` | New — 5 provider entries |
| `src/codegenie/catalogs/_schema.json` | New — JSON Schema Draft 2020-12 with two `$def`s (`native_modules`, `ci_providers`); `additionalProperties: false` at every level |
| `tests/unit/catalogs/__init__.py` | New (empty) |
| `tests/unit/catalogs/test_catalog_loader.py` | New — ~22 test cases per the TDD plan |
| `pyproject.toml` | Possibly: add `types-jsonschema` under `dev` if not already pinned |

## Out of scope

- **Catalog-driven cache invalidation** — that's exercised in S3-05 (`NodeManifestProbe.declared_inputs` includes `catalogs/native_modules.yaml`) and tested in S3-06's `test_cache_invalidation_scope.py`. This story loads the catalog; it doesn't wire the probe.
- **`probe.catalog.load` event-name constant** — S1-10 registers it as a `Final[str]`. This story emits the literal `"probe.catalog.load"`.
- **More than 10 native-module entries** — the seed is exactly 10. Adding entries is a YAML PR; resist speculative additions (Rule 2).
- **Catalog versioning across releases** — Phase 1 ships `catalog_version: 1`. Bumping is a future PR concern; ADR-0006 names the mechanism.
- **A third (or fourth) catalog file** — out-of-scope for S1-05; AC-20 / AC-21 prove the extension path is unblocked.
- **Schema-level `enum` for `CIProviderEntry.parser`** — deliberately not added in the YAML schema (Phase 4+ may extend the parser set). The `Literal` constraint lives at the Python boundary so the YAML schema can stay open for extension; the Phase 1 sub-schema for `CIProbe` (S4-01) will close the `provider` Literal type at consumer time.

## Notes for the implementer

- **Hard fail at import time is the load-bearing invariant** (Edge case #9). Don't catch the `CatalogLoadError` inside `catalogs/__init__.py` — let it propagate. The CLI's top-level catch (`cli.unhandled`, Phase 0 S4-02) turns it into exit-code 2. AC-14 codifies this; do not weaken it.
- **The two catalogs use the same `_schema.json` with two `$def`s.** `_LOAD_SCHEMA["$defs"]["native_modules"]` and `_LOAD_SCHEMA["$defs"]["ci_providers"]` are the two relevant sub-schemas; `_load_catalog` indexes by `schema_subkey: Literal[...]`. This is the registry-via-discriminator pattern in its smallest form.
- **`MappingProxyType` only wraps the top level.** Each `NamedTuple` is intrinsically immutable; tuple fields (`system_deps_required`, `binary_artifacts_glob`, `marker_paths`) are also immutable because they're tuples — but only **if** the loader coerces the YAML `list[str]` to `tuple[str, ...]` at construction. AC-7 + `_coerce_sequences` are the load-bearing pair. Don't return `list`s — runtime mutation would be possible and the test parametrized over both sequence fields would fail.
- **`jsonschema.Draft202012Validator`** — Phase 0 already depends on `jsonschema` (Phase 0 S2-05 schema work). Verify the dep is in the closure; don't add a new direct dep. Use `iter_errors(data)` (returns a generator) and take the first; preserve the original `jsonschema.ValidationError` as `__cause__` so debuggers can drill down.
- **Per Rule 12 (Fail loud):** the loader must never silently fall back to "no entries." If `safe_yaml.load` raises, the catalog is unloaded — re-raise `CatalogLoadError`. Don't set `NATIVE_MODULES = MappingProxyType({})` and emit a warning. AC-14 + `test_loader_does_not_catch_its_own_errors` enforce this.
- **Seed catalog values are the contract Phase 7 reads.** The 10 names are non-negotiable. The `requires_node_gyp` and `system_deps_required` values should be accurate to the real packages — look up each on npm/GitHub before committing. If unsure, set `requires_node_gyp: true` (Phase 7 will validate). The values in implementation outline #3 are starting points; researched corrections are welcome at land-time.
- **Plugin / strategy framing (Open/Closed; Extension by Addition).** This is the catalog kernel — a small stable function plus a registry-via-discriminator (`schema_subkey: Literal[...]`). New catalogs are new YAML files + new `NamedTuple` + new `$def` + one new module-scope call. Widening the `Literal` arms is the one deliberate edit a new catalog requires inside `catalogs/__init__.py` (AC-21); the kernel body never changes. Same plugin-shape framing as `parsers/_io.py` (S1-02/03/04 hardening). This honors CLAUDE.md's "Extension by addition" load-bearing commitment and the user-supplied design tradition (small stable kernel + registry + strategy).
- **Don't add an `enum` for `parser`** in `ci_providers.yaml` schema — Phase 4+ may extend the parser set. The Literal constraint lives at the Python boundary; the Phase 1 sub-schema for `CIProbe` (S4-01) will close the `provider` literal at consumer time.
- **No structlog event name constant lifting** — S1-10's job. Emit the literal `"probe.catalog.load"` exactly like S1-02 / S1-03 / S1-04 emit the literal `"probe.parser.cap_exceeded"`. AC-19 covers the structured fields; the event-name `Final[str]` lift is out-of-scope per S1-10.
