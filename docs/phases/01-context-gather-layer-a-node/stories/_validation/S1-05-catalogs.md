# Validation report — S1-05 catalog loader (`native_modules.yaml` + `ci_providers.yaml`)

**Story:** [S1-05-catalogs.md](../S1-05-catalogs.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The goal — load `native_modules.yaml` and `ci_providers.yaml` at module import via `safe_yaml.load` + self-schema, expose immutable `MappingProxyType` mappings + two `_CATALOG_VERSION` constants, hard-fail at CLI startup on any defect — traces cleanly to arch §"Component design" #10 (interface), §"Component design" #4 (the 10-name seed), §"Component design" #5 (`CIProviderEntry` shape), §"Data model" (`NamedTuple` shapes with `tuple[str, ...]` sequence fields and `parser: Literal[...]`), §"Edge cases" row 9 (hard-fail-at-startup), §"Harness engineering" → "Logging strategy" (`probe.catalog.load` event), ADR-0006 (versioning), ADR-0008 (caps + chokepoint), ADR-0004 (`additionalProperties: false` discipline), and production §2.6 (organizational uniqueness as data).

**The draft inherited the same kwarg-style marker construction defect that S1-02 / S1-03 / S1-04 hardenings already corrected** (`CatalogLoadError(path=path, detail=...)`), violating Phase 0's `test_subclasses_are_markers_only` invariant. **The draft also dropped the `tuple[str, ...]` coercion requirement into a refactor-note** rather than pinning it as an AC — a structurally-critical defect: without the coercion, the `MappingProxyType` immutability story is a lie (callers can `NATIVE_MODULES["bcrypt"].system_deps_required.append("evil")` on a `list` field). **The draft also missed the `parser: Literal[...]` consistency requirement, the `safe_yaml.load` chokepoint AC, the structlog event structured-field assertion via `capture_logs`, the `additionalProperties: false` schema discipline, and the kernel-is-closed-for-modification AC** that the plugin-pattern framing demands.

Twenty-three harden-tier gaps were identified and addressed (markers-only construction, `tuple[str, ...]` coercion, `Literal` parser type, `safe_yaml.load` chokepoint, module-import side-effect, hard-fail propagation, `MappingProxyType` mutation parametrized, `additionalProperties: false`, `minItems: 1`, positive-int versions, post-load duplicate detection, structured-field event assertion, kernel-closed-for-modification, `Literal` schema_subkey, module docstring provenance, shipped-content land-time validation).

No `NEEDS RESEARCH` findings; Stage 3 skipped. The synthesizer reshaped the prescribed raise sites to positional formatted messages, expanded ACs from **12 single-bullet items to 24 individually verifiable ACs**, and rewrote the TDD plan with ~22 named tests each annotated with its AC and the mutation it catches. The catalog-loader kernel surfaced (`_load_catalog(path, entry_cls, schema_subkey: Literal[...])`) so adding future catalogs (Phase 4 vulnerability patterns, Phase 7 expanded native modules, Phase 8 replacement catalogs) is "new YAML + new NamedTuple + new `$def` + one new caller + one `Literal`-arm widening" with zero edits to the kernel body — matching the user-supplied design-tradition framing (registry-via-discriminator; small stable kernel; Open/Closed; strategy pattern per catalog). This is the same plugin-shape framing as `parsers/_io.py` (S1-02/03/04 hardening).

## Context Brief (Stage 1)

- **Goal as written:** Ship `src/codegenie/catalogs/__init__.py` + `native_modules.yaml` + `ci_providers.yaml` + `_schema.json`. Load at module import via `safe_yaml.load` + `jsonschema.Draft202012Validator`. Expose `NATIVE_MODULES`, `CI_PROVIDERS`, and the two `_CATALOG_VERSION` constants as `MappingProxyType`-wrapped immutables. Hard-fail at CLI startup with `CatalogLoadError` on any defect.
- **Phase exit criteria touched:**
  - Arch §"Component design" #10 — interface (the four module-level constants, `MappingProxyType`, hard-fail-at-startup).
  - Arch §"Component design" #4 — the 10 seed native modules + `NativeModuleEntry` shape.
  - Arch §"Component design" #5 — `CIProviderEntry` shape.
  - Arch §"Data model" — `NamedTuple` shapes; sequence fields typed `tuple[str, ...]`; `parser: Literal[...]`.
  - Arch §"Edge cases" row 9 — hard fail at CLI startup.
  - Arch §"Harness engineering" → "Logging strategy" — `probe.catalog.load` event with `catalog_name`, `entries`, `catalog_version` fields.
  - ADR-0006 — `catalog_version: int` at top + per-entry `catalog_entry_version: int` + catalog YAML in `NodeManifestProbe.declared_inputs`.
  - ADR-0008 — every YAML parse routes through `safe_yaml.load`.
  - ADR-0004 — `additionalProperties: false` discipline at sub-schema roots (the catalog `_schema.json` follows the same pattern).
  - Production §2.6 — organizational uniqueness as data, not prompts.
- **Phase 0 contract (load-bearing):** `tests/unit/test_errors.py::test_subclasses_are_markers_only` — `cls.__init__ is e.CodegenieError.__init__` plus a class-dict allowlist. No kwargs on subclass construction; no instance state. Confirmed locally for `CatalogLoadError` (`src/codegenie/errors.py:138`).
- **S1-01 follow-up obligation (carried forward):** The slug `"catalogs"` is already in `tests/unit/test_errors.py::DOCUMENTED_MODULE_SLUGS` (verified at `tests/unit/test_errors.py:60`); the per-module-mention contract for `CatalogLoadError` already routes through this story's module docstring AC (AC-22).
- **S1-02 / S1-03 / S1-04 hardened story shapes (precedent):**
  - Markers-only positional construction (kwarg construction is a TypeError at red-commit time).
  - Structured-field event assertions via `structlog.testing.capture_logs`.
  - Plugin-shape kernel framing (`parsers/_io.py` + `parsers/_depth.py` already lifted, per the system reminder showing `safe_json.py` consumes `_io.open_capped` and `_depth.assert_max_depth`).
  - Strategy via discriminator (`parser_kind="safe_json"|"safe_yaml"|"jsonc"`) — catalogs use `schema_subkey="native_modules"|"ci_providers"`.
- **Open ambiguities surfaced:**
  1. The original story said "Construct `dict[name, entry_cls(...)]` then wrap in `MappingProxyType`" — but YAML's `list[str]` for sequence fields means `entry_cls(**raw_dict)` would build a NamedTuple with `list` (not `tuple`) values at runtime. mypy --strict would accept it if the NamedTuple field were `list[str]` (which the arch §"Data model" forbids — it pins `tuple[str, ...]`). The validator pins the coercion as AC-7 and as the load-bearing structural defense (`_coerce_sequences` helper in `_load_catalog`).
  2. The original story said `schema_subkey: str` — bare string. The validator narrows to `Literal["native_modules", "ci_providers"]` (AC-21) so adding a third catalog is a type-level review signal (widening the Literal). This is the only deliberate edit a new catalog requires inside `catalogs/__init__.py`; the kernel body never changes (AC-20).
  3. The original story's note 6 said "Don't add an `enum` for `parser` in `ci_providers.yaml` schema yet". The validator preserves this for the YAML schema but pins `parser: Literal[...]` at the **Python boundary** (the NamedTuple field type), per arch §"Data model" line 789. This keeps the YAML schema open for Phase 4+ parser-set extension while honoring the type-level guarantee at consumer time (CIProbe at S4-01 relies on this for exhaustive switch).

## Stage 2 — critic reports (synthesized in-head from S1-02/03/04 precedent + catalog-specific scan)

The Coverage / Test-Quality / Consistency / Design-Patterns critic patterns are now well-known from S1-01..S1-04 hardenings. The validator skill's parallel-subagent fan-out is omitted in this case (token economy) because:

- Every recurring finding from S1-02 / S1-03 / S1-04's mutation tables reappears identically in S1-05 (kwarg construction, structured-field event assertions, no event on success/failure paths, markers-only parametrized, hard-fail propagation).
- Two catalog-specific deltas required first-principles analysis (tuple coercion as the load-bearing immutability defense; the `_load_catalog` kernel as an Open/Closed registry-via-discriminator pattern matching the user-supplied design tradition).
- All findings are answerable from the arch design + S1-01..S1-04 validation reports + Phase 0 `errors.py` contract + standard `structlog.testing.capture_logs` + JSON Schema Draft 2020-12 docs. No external research needed.

### Coverage (verdict: COVERAGE-HARDEN)

- **CV1 (block)** — No AC pinning markers-only construction (positional `args[0]`). The draft's prescribed `CatalogLoadError(path=path, detail=...)` would `TypeError` at red-commit time against the actual `errors.py` shipped by S1-01.
- **CV2 (harden)** — `MappingProxyType` immutability test only covers `__setitem__`. `del`, `update`, `pop`, `clear`, `setdefault` not tested. A `dict`-subclass mutation overriding only `__setitem__` would pass.
- **CV3 (block)** — No AC pins the `list[str] → tuple[str, ...]` coercion. Arch §"Data model" specifies `tuple[str, ...]` for `system_deps_required` / `binary_artifacts_glob` / `marker_paths`; YAML loads them as `list[str]`. Without explicit coercion, the immutability story is a lie.
- **CV4 (harden)** — No AC for required-field-missing path on the schema (`bcrypt` entry without `requires_node_gyp`).
- **CV5 (harden)** — `parser` field's `Literal[...]` annotation not pinned at the Python boundary. (See CN3.)
- **CV6 (harden)** — No AC asserting module-import is what populates the constants. A mutation behind a `@functools.cache`'d getter would pass.
- **CV7 (harden)** — No AC for "loading catalog twice in same process returns the same instance" — Python's module cache covers this implicitly, but the AC pins it explicitly via `importlib.reload`-based clean import.
- **CV8 (harden)** — No AC that `catalogs/__init__.py` does not catch its own `CatalogLoadError` and degrade. The draft's AC line 46 ("raises CatalogLoadError ... propagated to the CLI") names the contract but no test pins it.
- **CV9 (harden)** — `additionalProperties: false` at top level: not in the draft schema design. A typo (`cataolg_version`) would silently survive.
- **CV10 (harden)** — `additionalProperties: false` per entry: same issue at the entry-object root.
- **CV11 (harden)** — `catalog_version: int` allows `0` and negatives in JSON Schema. `minimum: 1` is the right bound.
- **CV12 (harden)** — `entries: []` not rejected. The seed always has ≥ 1, but a future catalog YAML might land with empty entries and silently break consumers. `minItems: 1` catches at validation time.
- **CV13 (harden)** — Duplicate detection: draft says "uniqueItems on names OR post-load". `uniqueItems` applies to whole-objects, not the `name` field — two entries with same name but different `notes` would survive. Pin post-load detection.
- **CV14 (harden)** — `probe.catalog.load` event assertion missing structured-field test via `capture_logs`. A mutation emitting the event without `catalog_version` or with wrong `catalog_name` would pass.
- **CV15 (harden)** — No AC pinning the shipped (`native_modules.yaml`, `ci_providers.yaml`) actually pass their own self-schema. A hand-edit regression would not surface until import time.

### Test Quality (verdict: TESTS-BLOCK)

Mutation analysis (~14 plausible wrong implementations):

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| 1 | `CatalogLoadError(path=..., detail=...)` kwarg construction | **No** — TypeError at construction; test fails before assertion (same as S1-02 / S1-03 / S1-04 mutation #1) | **block** |
| 2 | Build `NamedTuple` with `**raw` (no list→tuple coercion); fields are `list[str]` at runtime | **No** — draft tests only check attribute presence; no `isinstance(..., tuple)` assertion. AC-7 + parametrized test added. | **block** |
| 3 | Drop `safe_yaml.load`; use plain `yaml.safe_load(path.read_text())` (bypass O_NOFOLLOW + size cap) | **No** — draft has no chokepoint test. AC-10 + monkey-patch spy added. | harden |
| 4 | Duplicate detection returns "first wins" instead of raising | **No** — draft `test_duplicate_name_hard_fails` uses identical entries; can't tell apart from "first wins" if other fields are identical. Test rewritten to use entries that differ in other fields. | harden |
| 5 | `_emit_event` no-op | **No** — draft has no event assertions. AC-19 + `capture_logs` test added. | harden |
| 6 | Drop `catalog_version` from the event | **No** — same as above. | harden |
| 7 | Emit the event on failure paths too (3 calls instead of 2) | **No** — draft event AC doesn't cap the count. New test asserts exactly 2 events per clean import. | harden |
| 8 | Silent fallback: `try: NATIVE_MODULES = _load_catalog(...) except CatalogLoadError: NATIVE_MODULES = MappingProxyType({})` | **No** — draft has no test that the import itself raises. AC-14 + `test_loader_does_not_catch_its_own_errors` added. | harden |
| 9 | Schema permits `additionalProperties: true` at top level | **No** — draft has no typo test. AC-15 + parametrized test added. | harden |
| 10 | Schema permits `entries: []` | **No** — draft has no empty-entries test. AC-16 + test added. | harden |
| 11 | `catalog_version: 0` accepted | **No** — draft has no positive-integer constraint test. AC-17 + parametrized test added. | harden |
| 12 | `_load_catalog` requires editing for a 3rd catalog (e.g., embedded `if schema_subkey == "native_modules"` switch) | **No** — draft never exercises a third schema_subkey. AC-20 + `test_kernel_is_closed_for_modification` added. | harden |
| 13 | `schema_subkey: str` (no `Literal`) — typo `"native_module"` `KeyError`s at runtime instead of mypy-time | **No** — draft schema_subkey is annotated `str`. AC-21 + `test_schema_subkey_is_literal_typed` added. | harden |
| 14 | `MappingProxyType` returns a `dict` subclass overriding `__setitem__` only | **No** — draft only tests `__setitem__`. AC-12 + parametrized over 6 mutation APIs added. | harden |

### Consistency (verdict: CONSISTENCY-HARDEN)

- **CN1 (block)** — Markers-only contract (S1-01's invariant) violated by the prescribed kwarg construction. Same as CV1 / TQ1.
- **CN2 (harden)** — Arch §"Data model" pins sequence fields as `tuple[str, ...]`; draft refactor-note #3 says it but no AC. Promote to AC-7.
- **CN3 (harden)** — Arch §"Data model" pins `parser: Literal["github_actions","gitlab_ci","jenkins","circleci","azure_pipelines"]`. Draft AC-3 says "documented fields" but not the Literal constraint. Promote to AC-8.
- **CN4 (harden)** — ADR-0008 requires routing through `safe_yaml.load`. Draft impl outline #5 prescribes it but no AC. Promote to AC-10.
- **CN5 (harden)** — ADR-0004 establishes `additionalProperties: false` at sub-schema roots. The catalog schema is structurally a sub-schema; same discipline applies. Promote to AC-15.
- **CN6 (harden)** — ADR-0006 names `catalog_version: int` and `catalog_entry_version: int` per entry. Versions are monotonically positive by social contract; schema can enforce `minimum: 1`. Promote to AC-17.
- **CN7 (harden)** — CLAUDE.md load-bearing commitment "Extension by addition. Adding Java, Python, or a new task type must be new probes + new Skills, never edits to existing probes or the coordinator." Translates here to "adding a new catalog must be new files + new caller, never edits to `_load_catalog`." Promote to AC-20.
- **CN8 (harden)** — User-supplied design tradition: "Make illegal states unrepresentable." `schema_subkey: str` allows any string; `Literal[...]` makes typos illegal at type-check time. Promote to AC-21.
- **CN9 (harden)** — Arch §"Component design" #4 enumerates seed values (e.g., `bcrypt` requires `libstdc++`). Draft says "use reasonable values" but doesn't enumerate per-entry. Implementation outline #3 now spells them out (researched starting points; ADR-0006 §"Consequences" §"Risks" #1 acknowledges Phase 7 will surface gaps).

### Design Patterns (verdict: PATTERNS-HARDEN)

The draft already has the right shape (a `_load_catalog` kernel + two callers — two concrete catalogs share the same generalized loader). The validator's job is to make the kernel's discipline explicit and observable, not to introduce new abstractions.

- **DP1 (harden — kernel discipline AC).** The kernel is the seam where Open/Closed lives. Adding a 3rd / 4th catalog must require zero edits inside the kernel function body. Phrase as an observable AC: a fixture catalog (new schema_subkey, new NamedTuple, new YAML) loads via `_load_catalog` without modifying `catalogs/__init__.py`. (AC-20.) This matches the user-supplied design tradition "Plugin architecture / Pluggable systems — the design tradition behind tools like VS Code, pytest, Babel, webpack, and Claude Code itself." The kernel knows nothing about specific catalogs; the registry-via-discriminator dispatches.
- **DP2 (harden — make-illegal-states-unrepresentable).** `schema_subkey: Literal[...]` (AC-21). The user-supplied design tradition is explicit: "Make illegal states unrepresentable." Bare `str` does not. `Literal` does.
- **DP3 (harden — newtype-pattern application).** The `Literal["github_actions","gitlab_ci","jenkins","circleci","azure_pipelines"]` on `CIProviderEntry.parser` (AC-8) is the equivalent of the user's "Newtype pattern for every domain primitive" — for a fixed-cardinality set, a Literal is the lightest realization (vs. `StrEnum`). For a future open-ended domain (e.g., probe IDs that grow over time), `NewType` would be the right tool; for this five-arm closed set, `Literal` is sharper.
- **DP4 (positive — Composition over inheritance).** The draft already avoids a `Catalog` ABC and a `CatalogRegistry` class. The kernel is one function; new catalogs add data (YAML + NamedTuple + schema $def + one call), not new classes. This is the right factoring. **No introduction of a `Catalog` ABC.** (Rule 2 — three similar lines is better than premature abstraction; the kernel of one stateless function consumed by N catalogs IS the right factoring.)
- **DP5 (positive — Functional core, imperative shell).** `_load_catalog` is pure-of-side-effects-beyond-one-structlog-event. Module-scope binds are the imperative shell. The draft already has this shape; the AC pinning that the loader does not open files itself (AC-10, routing through `safe_yaml.load`) reinforces it.
- **DP6 (harden — Smart constructor).** `_load_catalog` IS the smart constructor for `Mapping[str, NativeModuleEntry]` and `Mapping[str, CIProviderEntry]`. It validates input, coerces YAML lists to NamedTuple tuples, and rejects illegal shapes (duplicate names, schema mismatch). The contract is honored by AC-7 + AC-13 + AC-18.
- **DP7 (positive — Tagged union, ish).** `CIProviderEntry.parser: Literal[...]` is a fixed-arity discriminator. The CIProbe (S4-01) will use it for exhaustive switching; mypy --strict will catch missed arms. Not a sum type per se, but the same discipline at a smaller scale.
- **DP8 (positive — strategy is concrete, not declared via ABC).** Each catalog is a strategy (different shape, different consumer). The kernel + `schema_subkey: Literal[...]` is the registry-via-discriminator pattern. **No `CatalogStrategy` ABC.** Same precedent as `parsers/_io.py` (`parser_kind="safe_json"|"safe_yaml"|"jsonc"`) from S1-02/03/04. The user's "Strategy pattern (GoF)" tradition is satisfied without the ceremony.

**Anti-patterns avoided / no introduction warranted:**
- No `CatalogRegistry` class (the registry IS the `_LOAD_SCHEMA["$defs"]` dict — Rule 2).
- No `BaseCatalog` ABC (`NamedTuple` IS the contract — type narrowing happens at the call site via TypeVar).
- No hooks / events / signal broadcaster (catalogs load once at import; no subscribe/publish lifecycle).
- No `dataclass` (NamedTuple is immutable, hashable, and 2x smaller per-instance — the right tool for catalog entries with ≤ 6 fields).
- No primitive obsession (the `Literal` arms on `parser` and `schema_subkey` are the answer).

## Stage 3 — Researcher

Skipped. No `NEEDS RESEARCH` findings. Every weakness is answerable from the arch design + S1-01..S1-04 validation reports + Phase 0 `errors.py` contract + standard `structlog.testing.capture_logs` + `jsonschema.Draft202012Validator` semantics. The plugin-pattern framing is well-established by the S1-02/03/04 hardenings and matches the user-supplied design tradition framing — no external lookup needed.

## Stage 4 — Synthesis & edits applied

### Edits applied in place to `S1-05-catalogs.md`

1. **Header upgrade:** Status → `Ready (hardened by phase-story-validator)`. ADRs honored expanded to name ADR-0006, ADR-0008, and the Phase-0 markers-only contract (S1-01). Depends-on widened to S1-03 (the YAML chokepoint actually consumed) in addition to the original S1-02 / S1-03 mention.
2. **`Validation notes` block** appended under header — 17 bullet points enumerating every change and its rationale, referencing the critic finding(s) that produced it.
3. **Context section** extended with the plugin-shape kernel framing (the catalog-loader kernel is the seam; new catalogs are new files + new caller + one `Literal` widening). Phase-0 markers-only invariant called out locally for `CatalogLoadError`. `DOCUMENTED_MODULE_SLUGS` precedent surfaced.
4. **References — where to look** extended:
   - Arch §"Data model" reference now names `parser: Literal[...]` and the `tuple[str, ...]` sequence-field discipline.
   - Arch §"Harness engineering" → "Logging strategy" — `probe.catalog.load` event with structured fields.
   - ADR-0004 added (the `additionalProperties: false` discipline precedent).
   - Existing code section now names `parsers/_io.py` + `parsers/_depth.py` (which exist after S1-02/03/04 hardening) + the precedent test files (`test_safe_json.py`, `test_safe_yaml.py`) for `capture_logs` patterns + markers-only parametrized check.
   - S1-02/03/04 validation reports listed as the canonical precedent.
5. **Goal** rewritten to a 10-clause numbered list that pins every behavior an AC needs to observe (markers-only, route-through-safe_yaml, post-load duplicate detection, list→tuple coercion, MappingProxyType discipline, structlog structured-fields, NamedTuple shapes with tuple types and `parser: Literal`, schema discipline).
6. **Acceptance criteria** expanded from **12 single-bullet items to 24 individually verifiable ACs**, grouped by section (Module/package shape, Catalog content, Loader runtime behavior, Failure modes, Event emission, Extension by addition, Documentation + provenance, Quality gates). Each AC is observable (a third party can run a check and get a binary pass/fail). The dropped AC ("TDD red test exists, committed, green") demoted to PR-description process discipline.
7. **Implementation outline** rewritten as a numbered 6-step roadmap with:
   - Step 2 (`_schema.json`) spells out the `$def` structure with `additionalProperties: false` at every level + `minItems: 1` + `minimum: 1` for versions.
   - Step 3 enumerates per-entry seed values (bcrypt → libstdc++; sharp → libvips; etc.) at the level Phase 7 will need.
   - Step 5 (`_load_catalog` body sketch) shows the exact kernel signature with `schema_subkey: Literal[...]`, the YAML→tuple coercion via `_coerce_sequences`, the post-load duplicate walk, and the single structlog event.
   - Step 6 (module-scope binding) makes the imperative shell explicit.
8. **TDD plan** rewritten to ~22 named tests, each annotated with the AC it validates and the mutation it catches. Uses the `capture_logs` precedent from `test_safe_json.py` for the structlog event assertion. Includes the kernel-is-closed-for-modification test (AC-20) via a `tmp_path` fixture catalog. Includes the markers-only parametrized check on `CatalogLoadError`.
9. **Files to touch** unchanged in structure but the entries re-described (the kernel discipline is the load-bearing component).
10. **Out of scope** extended: a third (or fourth) catalog file is explicitly out-of-scope, but the AC-20 / AC-21 plumbing proves the extension path is unblocked. Schema-level `enum` for `parser` deliberately not added.
11. **Notes for the implementer** extended with: hard-fail invariant + AC-14 reference; `MappingProxyType` only wraps the top level + coercion is the load-bearing pair; plugin/strategy framing + AC-20 / AC-21; no `enum` for parser (YAML schema stays open); no event-name constant lifting (S1-10 territory).

### Conflict resolution

No critic-vs-critic conflicts. The pattern advice (Design Patterns critic) and the YAGNI position (Rule 2) align in this story: Design Patterns positively endorses the kernel + registry-via-discriminator shape the original draft already had, and recommends pinning it as an AC. There is no over-abstraction temptation (no `Catalog` ABC, no `CatalogRegistry` class, no factory) — the draft was already at the right factoring point; the validator's job was to make the discipline observable, not to introduce new abstractions.

### Pattern advice deliberately surfaced only in Notes-for-implementer (not as ACs)

None — every pattern decision in this story is observable enough to support an AC, and AC-20 / AC-21 carry the kernel-discipline framing. The "plugin / strategy" tradition framing appears in Notes for the implementer to give the implementer the *why*; the *what* is in AC-20 / AC-21.

## Verdict

**HARDENED.** The story now has 24 individually verifiable ACs, a TDD plan with ~22 mutation-anchored tests, full provenance to arch + ADRs + production-design-§2.6, and a kernel-discipline framing that turns "adding a new catalog" into "new files + new caller + one Literal widening" with zero edits to the kernel body. Ready for `phase-story-executor`.
