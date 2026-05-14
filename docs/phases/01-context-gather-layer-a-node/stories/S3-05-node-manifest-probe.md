# Story S3-05 — `NodeManifestProbe` + sub-schema + native-module catalog cross-reference

**Step:** Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers
**Status:** Ready (HARDENED)
**Effort:** L
**Validated:** 2026-05-14 — see `_validation/S3-05-node-manifest-probe.md`
**Depends on:** S3-01 (`_pnpm`), S3-02 (`_npm`), S3-03 (`_yarn`), S1-05 (`catalogs.NATIVE_MODULES` + `NATIVE_MODULES_CATALOG_VERSION`), S1-09 (`ResourceBudget.raw_artifact_truncate_mb` + `apply_raw_artifact_truncation` writer hook)
**ADRs honored:** ADR-0004 (per-probe sub-schema `additionalProperties: false`), ADR-0006 (native-module catalog versioning via `declared_inputs`), ADR-0007 (warning-ID pattern + `WarningId` constructed at catch site), ADR-0011 (no `npm ls` / no Helm render)

## Validation notes (2026-05-14 — phase-story-validator HARDENED)

Four **block-level** corrections applied (see `_validation/S3-05-node-manifest-probe.md` for full audit):

1. **`declared_raw_artifact_budget_mb` is dead.** The draft prescribed a `Probe`-ABC class attribute. S1-09's hardening **explicitly named S3-05 as the consumer** of the `ResourceBudget` route: `declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)`. ADR-0007 freezes `Probe`; budgets are coordinator-side (`src/codegenie/coordinator/budget.py:13–19`). Phase-arch-design.md Gap 2 prose is stale and flagged for cleanup at the same level S1-09 already surfaced.
2. **`ProbeOutput` API mismatch.** Draft Green-code constructed `ProbeOutput(data=..., …)`. The frozen ABC fields are `schema_slice`, `raw_artifacts`, `confidence`, `duration_ms`, `warnings`, `errors`. Every test assertion now references `out.schema_slice["manifests"][...]`.
3. **Lockfile precedence wrong.** Draft AC-4: `pnpm > package-lock.json > yarn.lock`. Phase-arch-design.md line 801 + `node_build_system._LOCKFILE_PRECEDENCE`: `bun > pnpm > yarn > npm`. yarn/npm reversed; corrected.
4. **`@register_probe` missing.** Draft AC-12 said "explicit import" only; sibling probes use the two-step pattern (`@register_probe` decorator + explicit module import in `probes/__init__.py`).

Sixteen harden-tier additions plus three design-pattern elevations:

- **D-1 / AC-7 — Registry/strategy seam.** S3-05 is the **third concrete consumer** of the lockfile-parser family. S3-01 / S3-02 / S3-03 explicitly deferred the rule-of-three threshold to "the third caller." Threshold reached here. `_FLATTENERS: Mapping[ParserKind, Callable[[Any], Mapping[str, str]]]` registry + `_PARSER_KIND_BY_FILENAME: Mapping[str, ParserKind]` mapping land at module scope; adding a future `_bun.py` is one new entry plus one `ParserKind` Literal addition — zero edits to `run()`. Pinned by an architectural test (AC-7).
- **D-2 — Functional-core split.** `_cross_reference_native_modules(resolved, catalog) -> tuple[NativeModuleHit, ...]` and the three `_flatten_*` helpers are pure module-level functions, testable in isolation.
- **D-3 — `ParserKind = Literal["pnpm", "yarn", "npm"]`** at module scope; drives `_FLATTENERS`, `_PARSER_KIND_BY_FILENAME`, and the `_error_id` prefix. Mirrors S3-03's `_PARSER_KIND` discipline; closes the primitive-obsession smell.

Test-implementation deltas: name-normalization parametrize across pnpm v6/v9 + npm v1/v3 + yarn classic (catches the rule-of-three-threshold defect Phase 7 would otherwise inherit); exact-match-not-substring on the catalog cross-reference (kills `@types/bcrypt → bcrypt` false positive); broader subprocess net (`run`, `Popen`, `os.spawnv`, `os.execv`, `os.execvp`); `os.fstat` monkey-patch replaces 60 MB tmpfs write (S3-01 / S3-02 / S3-03 pattern of record); multi-lockfile boundary assertions split into independent confidence-and-warning mutation tests; sub-schema JSON-Pointer rejection parametrized at three sites; `_lockfiles/__init__.py` non-edit architectural test re-asserted from S3-02 / S3-03.

No `NEEDS RESEARCH` findings. Stage 3 skipped.

## Context

`NodeManifestProbe` is **the load-bearing Phase 1 probe for Phase 7** (Chainguard distroless migration). Its job: parse `package.json` + the single canonical lockfile, cross-reference resolved dependencies against `catalogs/native_modules.yaml`, and produce a `manifests` slice with a `native_modules` block that Phase 7 reads to decide which Chainguard image layer to inherit and which system deps to install. The seam this probe creates — "data-as-code catalog cross-reference, no LLM, no `npm ls`" — is what makes Phase 7's distroless migration deterministic six phases later.

The probe is also the first one in Phase 1 to override the default raw-artifact budget. Real `pnpm-lock.yaml` files can hit 20 MB on monorepos; the parsed dump (stored under `.codegenie/context/raw/node_manifest.json`) needs to fit. The default 5 MB cap from S1-09's `ResourceBudget.raw_artifact_truncate_mb` is too tight; this probe overrides to 25 MB with a 50 MB hard ceiling. Budgets larger than 50 MB would require an ADR amendment.

ADR-0006's invariant is critical: `native_modules.yaml` is in `declared_inputs` so editing the catalog invalidates `node_manifest` cache entries at the file-bytes level. The cross-phase invalidation story (Phase 7 catalog update triggers a fleet-wide re-gather) depends on this.

This is the densest probe in Phase 1 and the **third concrete consumer of the lockfile-parser family** (after S3-01 / S3-02 / S3-03). S3-01 and S3-02 explicitly punted the shared dep-flattening kernel to "the third caller's land time" — that land time is now. The hardened story lands the rule-of-three registry seam in the probe module, not in `_lockfiles/`, so the `_lockfiles/__init__.py` family-init invariant (S3-02 / S3-03's `__all__ = []`) is preserved.

Plan a focused PR with the schema, the probe (with its module-level registry + pure helpers), the unit test, and nothing else — fixtures + integration land in S3-06.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #4 NodeManifestProbe` — full interface spec; the contract for this story.
  - `../phase-arch-design.md §"Data model"` — `ManifestsSlice`, `ManifestEntry`, `NativeModulesBlock`, `NativeModuleHit` Pydantic-shaped definitions.
  - `../phase-arch-design.md §"Edge cases"` rows 1–4, 8 — pnpm depth-cap, multi-lockfile, catalog gap behaviors.
  - `../phase-arch-design.md §"Gap analysis" Gap 2` — raw-artifact budget mechanism; **routed through `ResourceBudget.raw_artifact_truncate_mb` per S1-09 hardening, not via a `Probe`-ABC class attribute.**
- **Phase ADRs:**
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — `additionalProperties: false` at sub-schema root + every nested block.
  - `../ADRs/0006-native-module-catalog-versioning.md` — file-level cache invalidation via `declared_inputs`.
  - `../ADRs/0007-warnings-id-pattern.md` — `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` for warning IDs (`lockfile.multi_present`, etc.); `WarningId` constructed at catch site from `args[0]` (per S3-02 / S3-03 marker discipline).
  - `../ADRs/0011-no-helm-render-no-hcl-no-npm-ls.md` — explicit "no `npm ls`" for this probe.
- **Production ADRs:**
  - `../../../production/adrs/0006-continuous-deterministic-gather.md` — the continuous-gather story Phase 7 depends on; clean cache invalidation is the load-bearing contract.
- **Source design:**
  - `../final-design.md §"Components" #4` — provenance attribution (`[B + S + synth]`).
  - `../final-design.md §"Risks"` #1 — silent catalog staleness; the structural mitigation is this probe + ADR-0006.
  - `../High-level-impl.md §"Step 3"` — features delivered + done criteria for this probe.
- **Existing code (load-bearing patterns to mirror):**
  - `src/codegenie/probes/base.py` — frozen `Probe` ABC, `ProbeContext` (with `parsed_manifest` / `input_snapshot` per S1-06 ADR-0002), `ProbeOutput(schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors)`.
  - `src/codegenie/coordinator/budget.py` — `ResourceBudget(rss_mb=200, raw_artifact_mb=10, wall_clock_s=30, raw_artifact_truncate_mb=5)`, `DEFAULT_RESOURCE_BUDGET`, `BudgetingContext`, `__post_init__` invariant `raw_artifact_truncate_mb <= raw_artifact_mb`.
  - `src/codegenie/probes/node_build_system.py` — sibling-probe pattern of record: `@register_probe`, `EVENT_PROBE_START` / `EVENT_PROBE_FAILURE` / `EVENT_PROBE_SUCCESS` emission, `_LOCKFILE_PRECEDENCE` registry tuple, `_PKG_JSON_FAILURE` mapping table, `ProbeOutput(schema_slice=..., raw_artifacts=[], confidence=..., duration_ms=..., warnings=..., errors=...)`.
  - `src/codegenie/probes/_lockfiles/_pnpm.py`, `_npm.py`, `_yarn.py` — S3-01/02/03; `parse(path) -> <T>Lock` TypedDict; positional-message markers; sibling siblings don't import each other.
  - `src/codegenie/probes/_lockfiles/__init__.py` — **inert** (`__all__: list[str] = []`). S3-02 / S3-03 architectural invariant. **S3-05 must NOT edit this file.**
  - `src/codegenie/catalogs/__init__.py` — `NATIVE_MODULES`, `NATIVE_MODULES_CATALOG_VERSION` from S1-05; `MappingProxyType` immutable.
  - `src/codegenie/probes/registry.py` — `register_probe` decorator; `default_registry`.
  - `src/codegenie/probes/__init__.py` — explicit imports trigger decorator registration.
  - `src/codegenie/schema/probes/language_detection.schema.json`, `node_build_system.schema.json` — sub-schema shape; reference for `additionalProperties: false` at root.
  - `src/codegenie/output/raw_truncation.py` (S1-09) — `apply_raw_artifact_truncation` writer hook for the soft `raw_artifact_truncate_mb` boundary.
- **Validation precedents (the family discipline already settled):**
  - `_validation/S1-09-raw-artifact-budget.md` — `ResourceBudget` route; S3-05 explicitly named as consumer of `ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)`.
  - `_validation/S3-01-pnpm-lockfile-parser.md`, `_validation/S3-02-npm-lockfile-parser.md`, `_validation/S3-03-yarn-lockfile-parser.md` — lockfile-parser family discipline; rule-of-three explicitly deferred to S3-05 (this story).
  - `_validation/S3-04-yarn-parser-parity-oracle.md` — mutation thinking, functional-core helpers.

## Goal

Ship `NodeManifestProbe`, its sub-schema, and the native-module catalog cross-reference so `codegenie gather` on a Node repo produces a valid `manifests` slice with `native_modules.detected` correctly set; multi-lockfile drops `confidence` to `low` AND emits `lockfile.multi_present`; editing `native_modules.yaml` invalidates only this probe's cache (ADR-0006). Land the rule-of-three registry/strategy seam for lockfile dispatch (`_FLATTENERS` + `_PARSER_KIND_BY_FILENAME` + `ParserKind` Literal) so adding a future format is a zero-edit-to-`run()` change.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1. Resource budget via S1-09 surface.** The probe sets `declared_resource_budget: Final[ResourceBudget] = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)` as a class attribute. **No** `declared_raw_artifact_budget_mb` attribute (per S1-09's ADR-0007 freeze hardening). A unit test asserts `cls.declared_resource_budget.raw_artifact_truncate_mb == 25` and `cls.declared_resource_budget.raw_artifact_mb == 50`.
- [ ] **AC-2. Probe contract attributes.** `NodeManifestProbe(Probe)` declares `name = "node_manifest"`, `version = "0.1.0"`, `layer = "A"`, `tier = "base"`, `applies_to_languages = ["javascript", "typescript"]`, `applies_to_tasks = ["*"]`, `requires = ["language_detection"]`, `timeout_seconds = 30`, `declared_inputs = ["package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "src/codegenie/catalogs/native_modules.yaml"]`. **`node_modules/**`** does NOT appear anywhere in `declared_inputs` (arch §"Component design" #4; non-goal #4); a unit test asserts `not any("node_modules" in inp for inp in cls.declared_inputs)`.
- [ ] **AC-3. `package.json` read path.** `run(repo, ctx)` reads `package.json` via `ctx.parsed_manifest(repo.root / "package.json")` when `ctx.parsed_manifest is not None`, else falls back to `safe_json.load(...)` (mirrors `node_build_system.py:566-575`). Existence check uses `pkg_path.exists() or pkg_path.is_symlink()` — a dangling symlink reaches the read path so `safe_json`'s `O_NOFOLLOW` raises `SymlinkRefusedError` cleanly. On any `(SizeCapExceeded, MalformedJSONError, SymlinkRefusedError)`, the probe records `errors=[<typed id>]` and `confidence="low"` and returns immediately with a minimal slice; gather continues.
- [ ] **AC-4. Lockfile selection by precedence — existence-check only, no parse-for-selection.** The dispatch order is the **parsed-formats subset** of `node_build_system._LOCKFILE_PRECEDENCE`: `pnpm-lock.yaml > yarn.lock > package-lock.json`. `bun.lockb` is enumerated for multi-lockfile detection (so a `bun.lockb` co-present with another lockfile still trips `lockfile.multi_present`) but is **never parsed** by this probe (ADR-0011 + arch §"Component design" #4). The precedence is driven by `_PARSER_KIND_BY_FILENAME: Mapping[str, ParserKind]` declared at module scope.
- [ ] **AC-5. Multi-lockfile downgrade — boundary assertions independently pinned.**
  - When ≥2 files among `{pnpm-lock.yaml, yarn.lock, package-lock.json, bun.lockb}` are present, the probe emits the warning `"lockfile.multi_present"` **AND** demotes `confidence` to `"low"`. The selected lockfile (per AC-4 precedence) is still parsed.
  - **Mutation-killing pair (split tests):** one test asserts the warning is present *regardless* of confidence, another asserts confidence is `"low"` *regardless* of warnings — a single conflated test would not kill the "drop warning but keep low" / "drop low but keep warning" mutants.
  - When exactly one lockfile is present, `confidence == "high"` and `"lockfile.multi_present"` is absent — pins the "always-low" mutant.
- [ ] **AC-6. Parser-exception translation.** On any of `(SizeCapExceeded, DepthCapExceeded, MalformedLockfileError, SymlinkRefusedError)` raised by the selected `_lockfiles.<kind>.parse(...)`, the probe catches and emits `ProbeOutput(confidence="low", errors=[<typed warning_id>], ...)`; gather continues. The error-ID is constructed by a pure module-level helper `_error_id(parser_kind: ParserKind, exc: BaseException) -> str` that returns IDs matching the ADR-0007 pattern, drawn from the deterministic table in Notes §6. `WarningId` is constructed from `exc.args[0]` (per S3-02 / S3-03 marker discipline — positional message only).
- [ ] **AC-7. Registry/strategy seam — zero-edit Open/Closed guarantee.** Module declares:
  ```python
  ParserKind = Literal["pnpm", "yarn", "npm"]
  _PARSER_KIND_BY_FILENAME: Mapping[str, ParserKind] = {
      "pnpm-lock.yaml": "pnpm",
      "yarn.lock":      "yarn",
      "package-lock.json": "npm",
  }
  _PARSERS: Mapping[ParserKind, Callable[[Path], Any]] = {
      "pnpm": _pnpm.parse, "yarn": _yarn.parse, "npm": _npm.parse,
  }
  _FLATTENERS: Mapping[ParserKind, Callable[[Any], Mapping[str, str]]] = {
      "pnpm": _flatten_pnpm, "yarn": _flatten_yarn, "npm": _flatten_npm,
  }
  ```
  Adding a future format (e.g., `_bun.py`) is **one new `ParserKind` Literal arm + one entry in each of the three mappings**, with **zero edits to `run()`**. Pinned by an architectural test (`test_run_does_not_branch_on_parser_kind`) that loads `inspect.getsource(NodeManifestProbe.run)` and asserts no string occurrence of `"pnpm" ==`, `"yarn" ==`, `"npm" ==`, `if parser_kind ==`, or per-format `isinstance` checks — `run()` operates only through the registries.
- [ ] **AC-8. Native-module cross-reference as a pure function.** A module-level `_cross_reference_native_modules(resolved: Mapping[str, str], catalog: Mapping[str, NativeModuleEntry]) -> tuple[NativeModuleHit, ...]` is the single source of truth. `run()` calls it; tests exercise it directly. The function performs **exact-name dict lookup** (per AC-15), not substring match. `native_modules.detected` is `True` iff `len(packages) > 0`.
- [ ] **AC-9. `manifests.catalog_version` is the file-level integer.** The slice's `catalog_version` field is populated from `NATIVE_MODULES_CATALOG_VERSION` (the file-top integer in `native_modules.yaml`), **not** from any per-entry `catalog_entry_version`. A test asserts equality against the imported constant — a swap mutant (per-entry → file-level or vice versa) is killed.
- [ ] **AC-10. `optionalDependencies` / `bundledDependencies` extraction.** From the parsed `package.json`: `optional_dependencies: int` is `len(pkg.get("optionalDependencies") or {})`; `bundled_dependencies: list[str]` is `list(pkg.get("bundledDependencies") or [])`. Absent or `null` → `0` and `[]` respectively. Both null and absent paths tested.
- [ ] **AC-11. Sub-schema strictness.** `src/codegenie/schema/probes/node_manifest.schema.json` (JSON Schema Draft 2020-12) sets `additionalProperties: false` **at the slice root AND at every nested block**: `primary`, `lockfile`, `native_modules`, each item of `native_modules.packages` (`NativeModuleHit`), and `direct_dependencies`. The sub-schema is registered as optional at the envelope's `probes.*` level (per ADR-0010) so non-Node repos validate cleanly.
- [ ] **AC-12. `warnings[]` and `errors[]` pattern constraint.** The sub-schema declares both `warnings` and `errors` as arrays of strings each constrained by `pattern: "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"` (ADR-0007). A unit test asserts that emitting `warnings: ["This Helm chart looks production-ready"]` is rejected by the sub-schema validator.
- [ ] **AC-13. Registration — decorator + import.** Two-step pattern (mirrors S2-01 / S2-02):
  - The class is decorated with `@register_probe` from `codegenie.probes.registry`.
  - `src/codegenie/probes/__init__.py` is edited additively to import the module by name (one-line, alphabetical insertion).
  A unit test imports `codegenie.probes` and asserts `"node_manifest"` is in `default_registry.names()`.
- [ ] **AC-14. Sub-schema rejection test parametrized at three JSON Pointer sites.** A synthetic envelope with an injected extra field is rejected with `SchemaValidationError` at the correct JSON Pointer for each of: (a) `/probes/node_manifest/<extra>` (root); (b) `/probes/node_manifest/primary/<extra>`; (c) `/probes/node_manifest/primary/native_modules/packages/0/<extra>`. The assertion is on `exc.absolute_path` (`jsonschema`'s tuple path), not the exception message.
- [ ] **AC-15. Catalog cross-reference exact-match, not substring.** `_cross_reference_native_modules` performs `name in catalog` dict-lookup against the resolved-dep map, **not** `any(c in name for c in catalog)`. Parametrized test exercises false-positive vectors: `{"@types/bcrypt": "1.0.0"}` produces zero hits; `{"bcryptjs": "2.4.3"}` produces zero hits; `{"bcrypt-utils": "1.2.0"}` produces zero hits; `{"bcrypt": "5.1.1"}` produces exactly one hit named `"bcrypt"`.
- [ ] **AC-16. Lockfile-key name normalization across formats.** Three pure module-level helpers — `_flatten_pnpm`, `_flatten_npm`, `_flatten_yarn` — each take the parser's TypedDict output and return a `Mapping[str, str]` of `package_name -> version`, normalizing the format-specific key shapes:
  - **pnpm v6/v9:** keys like `/bcrypt@5.1.1` (v6) and `/bcrypt@5.1.1(other@^1)` (v9) — strip leading `/`, strip everything from the first `@` (excluding scoped-package leading `@`), strip the v9 peer-dep parenthetical suffix.
  - **npm v1/v3:** v1 nested `dependencies` tree (recursive walk; package name = key); v3 flat `packages` with keys like `node_modules/bcrypt`, `node_modules/@types/bcrypt` — strip the `node_modules/` prefix.
  - **yarn classic:** entry keys like `bcrypt@^5.1.0, bcrypt@^5.0` — split on `, `; strip everything from the **last** unescaped `@` (preserves scoped names).
  Parametrized test (`test_flatten_<kind>_normalizes_keys`) covers each shape; a `scoped_package` row covers `@types/foo` is normalized to `@types/foo`, not `types/foo`.
- [ ] **AC-17. Catalog YAML in `declared_inputs` — ADR-0006 invariant.** A unit test asserts `"src/codegenie/catalogs/native_modules.yaml" in cls.declared_inputs`. The unit test docstring names ADR-0006 so a future contributor who removes the line trips the test with the ADR pointer in the failure message.
- [ ] **AC-18. No subprocess for dep resolution — broader net (ADR-0011).** A unit test monkey-patches `subprocess.run`, `subprocess.Popen`, `os.spawnv`, `os.execv`, `os.execvp` and `asyncio.create_subprocess_exec` to record calls; `probe.run(...)` is awaited; the test asserts every recorded call list is empty. (A narrower `subprocess.run`-only patch would silently miss a future contributor reaching for `Popen` / `os.execv`.)
- [ ] **AC-19. TDD discipline.** Red commit: `tests/unit/probes/test_node_manifest.py` cannot import `codegenie.probes.node_manifest` (`ModuleNotFoundError`). Green commit: every failure-path test asserts the specific typed exception class / specific `errors[]` ID, never just `CodegenieError`; every happy-path test asserts dict-shape and the *normalized* package name, not raw lockfile keys.
- [ ] **AC-20. `_lockfiles/__init__.py` non-edit invariant (S3-02 / S3-03 inheritance).** S3-05 does not touch `src/codegenie/probes/_lockfiles/__init__.py`. An architectural test (`test_lockfiles_init_remains_inert`) snapshots the file content and asserts equality against the S3-02 / S3-03 baseline (`__all__: list[str] = []` plus the docstring). The probe imports each sibling parser directly (`from codegenie.probes._lockfiles import _pnpm, _npm, _yarn`).
- [ ] **AC-21. `ResourceBudget` invariant pinned at construction.** `declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)` constructs without raising (`__post_init__` invariant `raw_artifact_truncate_mb <= raw_artifact_mb` holds; 25 <= 50). A unit test additionally asserts that swapping the values (`raw_artifact_mb=25, raw_artifact_truncate_mb=50`) raises `ValueError` at class-attribute construction — pins the "swap" mutant.
- [ ] **AC-22. Param naming.** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:` — mirrors `node_build_system.py:547` and `language_detection.py:424`. Not `(snapshot, ctx)`.
- [ ] **AC-23. Structlog event discipline.** The probe emits `EVENT_PROBE_START` at entry, `EVENT_PROBE_FAILURE` on any caught exception path, `EVENT_PROBE_SUCCESS` on `confidence == "high"` exit — mirroring `node_build_system.py` and `language_detection.py`. Constants imported from `codegenie.logging`. A structlog-capture test asserts at least one `probe.start` event with `probe="node_manifest"`.
- [ ] **AC-24. Hygiene gates.** `ruff format --check`, `ruff check`, `mypy --strict src/codegenie/probes/node_manifest.py`, `mypy --strict tests/unit/probes/test_node_manifest.py`, full unit test suite all pass. Per-probe local coverage report ≥ 90 / 80 (line / branch) included in PR body (cross-cutting convention #6). Module declares `__all__ = ["NodeManifestProbe"]`.

## Implementation outline

1. **Ship the sub-schema first** — `src/codegenie/schema/probes/node_manifest.schema.json` with `additionalProperties: false` at root + every nested block (root → `primary` → `lockfile`, `native_modules` → `native_modules.packages[*]` (`NativeModuleHit`), `direct_dependencies`). Adapt the Python Pydantic shapes from `phase-arch-design.md §"Data model"`. Use Draft 2020-12; `$ref` `NativeModuleHit` as a `$defs` entry. `warnings` and `errors` declared as `array` of `string` with the ADR-0007 pattern. Slice declared **optional** at envelope `probes.*` level.
2. **Write the failing tests** — see TDD plan. Confirm `ModuleNotFoundError` on collection. Commit red.
3. **Module scaffolding for `node_manifest.py`** (in order — registry seam lands first):
   - Module docstring naming arch §"Component design" #4, ADR-0004 / 0006 / 0007 / 0011, and the rule-of-three resolution from S3-01 / S3-02 / S3-03 / S3-04.
   - Imports: stdlib + `codegenie.errors`, `codegenie.parsers.safe_json`, `codegenie.probes._lockfiles._pnpm`/`_npm`/`_yarn`, `codegenie.catalogs.NATIVE_MODULES` + `NATIVE_MODULES_CATALOG_VERSION`, `codegenie.coordinator.budget.ResourceBudget`, `codegenie.probes.base.{Probe, ProbeContext, ProbeOutput, RepoSnapshot}`, `codegenie.probes.registry.register_probe`, `codegenie.logging.{_log, EVENT_PROBE_START, EVENT_PROBE_FAILURE, EVENT_PROBE_SUCCESS}`.
   - Module-scope literals: `ParserKind = Literal["pnpm", "yarn", "npm"]`; `_PARSER_KIND_BY_FILENAME`; `_PARSEABLE_LOCKFILES` (the precedence-ordered tuple of filenames); `_ALL_LOCKFILES` (`_PARSEABLE_LOCKFILES + ("bun.lockb",)`).
   - Pure module-level helpers — declared **before** the class:
     - `_flatten_pnpm(parsed: _pnpm.PnpmLock) -> Mapping[str, str]`
     - `_flatten_npm(parsed: _npm.NpmLock) -> Mapping[str, str]`
     - `_flatten_yarn(parsed: _yarn.YarnLock) -> Mapping[str, str]`
     - `_FLATTENERS: Mapping[ParserKind, Callable[[Any], Mapping[str, str]]]`
     - `_PARSERS: Mapping[ParserKind, Callable[[Path], Any]]`
     - `_ERROR_PREFIX_BY_KIND: Mapping[ParserKind, str]` (`{"pnpm": "pnpm_lock", "yarn": "yarn_lock", "npm": "npm_lock"}`)
     - `_error_id(parser_kind: ParserKind, exc: BaseException) -> str` — closed mapping `(parser_kind, exception_type) -> "<prefix>.<suffix>"`; suffix table in Notes §6.
     - `_cross_reference_native_modules(resolved: Mapping[str, str], catalog: Mapping[str, NativeModuleEntry]) -> tuple[NativeModuleHit, ...]` — exact-match dict lookup; iterates `catalog`, checks `name in resolved`, builds `NativeModuleHit` from the catalog entry (`catalog_entry_version`, `system_deps_required`, `binary_artifacts_glob`, `requires_node_gyp`) plus the resolved `version` from `resolved[name]`.
4. **`NodeManifestProbe(Probe)` class body** (decorated with `@register_probe`):
   - All class attributes per AC-1 / AC-2 / AC-22.
   - `declared_resource_budget: Final[ResourceBudget] = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)`.
   - `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:` — uses ONLY the registries (no per-format `if`/`isinstance` in `run()`):
     - emit `EVENT_PROBE_START`; start perf-counter for `duration_ms`.
     - Read `package.json` via `_read_package_json(repo.root, ctx)` (memo + fallback, mirrors `node_build_system.py`).
     - Detect lockfiles: `present = [f for f in _ALL_LOCKFILES if (repo.root / f).exists()]`.
     - Multi-lockfile: if `len(present) >= 2`, append `"lockfile.multi_present"` to `warnings`; demote `confidence` to `"low"`.
     - Select parseable lockfile: first `f in _PARSEABLE_LOCKFILES if f in present`. Look up `parser_kind = _PARSER_KIND_BY_FILENAME[f]`. Call `_PARSERS[parser_kind](repo.root / f)` inside a `try/except (SizeCapExceeded, DepthCapExceeded, MalformedLockfileError, SymlinkRefusedError)`; on exception, append `_error_id(parser_kind, exc)` to `errors`, demote `confidence`, skip flatten.
     - Flatten: `resolved = _FLATTENERS[parser_kind](parsed)`.
     - Cross-reference: `native_hits = _cross_reference_native_modules(resolved, NATIVE_MODULES)`.
     - Assemble slice (plain dict per S2-02 convention; sub-schema validates at envelope merge).
     - emit `EVENT_PROBE_SUCCESS` (if `confidence == "high"`) or `EVENT_PROBE_FAILURE` (if not).
     - Return `ProbeOutput(schema_slice=..., raw_artifacts=[], confidence=confidence, duration_ms=duration_ms, warnings=warnings, errors=errors)`.
5. **Raw-artifact dump.** Serialize the parsed-and-flattened lockfile (the post-flatten mapping is what's useful downstream) via the coordinator's raw-artifact channel (`ctx.workspace / "node_manifest.json"` then `BudgetingContext.report_bytes(...)` before write; the writer hook `apply_raw_artifact_truncation` from S1-09 enforces the 25 MB soft cap). No `Path.write_text` calls from inside this probe.
6. **Register the probe** — `@register_probe` on the class (AC-13a) + alphabetical-order insertion of `from codegenie.probes import node_manifest` in `probes/__init__.py` (AC-13b).
7. **Run the test suite + local coverage**; verify ≥ 90 / 80 per-module floor.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/test_node_manifest.py`.

```python
# tests/unit/probes/test_node_manifest.py
from __future__ import annotations

import asyncio
import inspect
import os
import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import jsonschema
import pytest

from codegenie.catalogs import NATIVE_MODULES_CATALOG_VERSION
from codegenie.coordinator.budget import ResourceBudget
from codegenie.errors import (
    DepthCapExceeded,
    MalformedJSONError,
    MalformedLockfileError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.probes.base import ProbeOutput, RepoSnapshot


def _make_snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})


def _build_repo(
    tmp_path: Path,
    *,
    pnpm_lock: bool = False,
    npm_lock: bool = False,
    yarn_lock: bool = False,
    bun_lock: bool = False,
    deps: dict[str, str] | None = None,
    optional_deps: dict[str, str] | None = None,
    bundled_deps: list[str] | None = None,
) -> Path:
    pkg = {"name": "x", "version": "1.0.0", "dependencies": deps or {}}
    if optional_deps is not None:
        pkg["optionalDependencies"] = optional_deps
    if bundled_deps is not None:
        pkg["bundledDependencies"] = bundled_deps
    import json
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    if pnpm_lock:
        body = "lockfileVersion: '9.0'\npackages:\n"
        for name, ver in (deps or {}).items():
            body += f"  /{name}@{ver.lstrip('^~')}: {{}}\n"
        (tmp_path / "pnpm-lock.yaml").write_text(body or "lockfileVersion: '9.0'\npackages: {}\n")
    if npm_lock:
        packages: dict = {}
        for name in (deps or {}):
            packages[f"node_modules/{name}"] = {"version": deps[name].lstrip("^~")}
        (tmp_path / "package-lock.json").write_text(
            json.dumps({"lockfileVersion": 3, "packages": packages})
        )
    if yarn_lock:
        body = ""
        for name, ver in (deps or {}).items():
            body += f'{name}@{ver}:\n  version "{ver.lstrip("^~")}"\n'
        (tmp_path / "yarn.lock").write_text(body or "# empty\n")
    if bun_lock:
        (tmp_path / "bun.lockb").write_bytes(b"\x00" * 8)
    return tmp_path


# ---------- AC-1, AC-2, AC-17, AC-21, AC-22 ---------------------------------


def test_probe_contract_attributes_pin_acs():
    from codegenie.probes.node_manifest import NodeManifestProbe

    cls = NodeManifestProbe
    assert cls.name == "node_manifest"
    assert cls.layer == "A"
    assert cls.tier == "base"
    assert cls.applies_to_languages == ["javascript", "typescript"]
    assert cls.applies_to_tasks == ["*"]
    assert cls.requires == ["language_detection"]
    assert cls.timeout_seconds == 30
    assert cls.version == "0.1.0"
    # AC-1
    assert cls.declared_resource_budget == ResourceBudget(
        raw_artifact_mb=50, raw_artifact_truncate_mb=25
    )
    # AC-2 — node_modules forbidden
    assert not any("node_modules" in inp for inp in cls.declared_inputs)
    # AC-17 — ADR-0006 invariant
    assert "src/codegenie/catalogs/native_modules.yaml" in cls.declared_inputs
    # AC-22 — param naming
    sig = inspect.signature(cls.run)
    assert list(sig.parameters)[:3] == ["self", "repo", "ctx"]
    # No dead attribute
    assert not hasattr(cls, "declared_raw_artifact_budget_mb")


def test_resource_budget_swap_raises():
    """AC-21 — ResourceBudget(__post_init__) enforces truncate <= mb."""
    with pytest.raises(ValueError):
        ResourceBudget(raw_artifact_mb=25, raw_artifact_truncate_mb=50)


# ---------- AC-7 — registry/strategy seam -----------------------------------


def test_run_does_not_branch_on_parser_kind():
    """AC-7 architectural test — run() goes through the registries only."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    src = inspect.getsource(NodeManifestProbe.run)
    # No per-format string equality branches.
    for forbidden in ('"pnpm" ==', '"yarn" ==', '"npm" ==', '== "pnpm"', '== "yarn"', '== "npm"'):
        assert forbidden not in src, f"run() branches on {forbidden!r}; AC-7 violated"
    # No per-format isinstance.
    assert not re.search(r"isinstance\([^)]+,\s*PnpmLock\)", src)


def test_register_probe_decorator_populates_default_registry():
    """AC-13 — @register_probe + explicit import wires into default_registry."""
    import codegenie.probes  # noqa: F401 — triggers explicit imports
    from codegenie.probes.registry import default_registry

    names = {p.name for p in default_registry.all()}
    assert "node_manifest" in names


# ---------- AC-13b — non-edit of _lockfiles/__init__.py ---------------------


def test_lockfiles_init_remains_inert():
    """AC-20 — S3-02 / S3-03 invariant re-asserted at S3-05 land."""
    import codegenie.probes._lockfiles as fam

    assert fam.__all__ == []


# ---------- AC-3, AC-5, AC-9, AC-10, AC-23 ---------------------------------


@pytest.mark.asyncio
async def test_happy_path_pnpm_with_bcrypt(tmp_path: Path):
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, deps={"bcrypt": "^5.1.0"})
    ctx = MagicMock(); ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert isinstance(out, ProbeOutput)
    assert out.confidence == "high"
    slc = out.schema_slice["manifests"]
    assert slc["catalog_version"] == NATIVE_MODULES_CATALOG_VERSION  # AC-9
    assert slc["primary"]["native_modules"]["detected"] is True
    pkgs = slc["primary"]["native_modules"]["packages"]
    assert {p["name"] for p in pkgs} == {"bcrypt"}  # AC-16 — normalized name, not "/bcrypt@5.1.1"
    assert pkgs[0]["version"] == "5.1.1"


@pytest.mark.asyncio
async def test_single_lockfile_keeps_confidence_high(tmp_path: Path):
    """AC-5 — kills the always-low mutant."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, deps={"x": "^1.0.0"})
    ctx = MagicMock(); ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert out.confidence == "high"
    assert "lockfile.multi_present" not in out.warnings


@pytest.mark.asyncio
async def test_multi_lockfile_emits_warning_independent_of_confidence(tmp_path: Path):
    """AC-5 — split assertion; kills the 'drop the warning but keep low' mutant."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, npm_lock=True, deps={"x": "^1"})
    ctx = MagicMock(); ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert "lockfile.multi_present" in out.warnings


@pytest.mark.asyncio
async def test_multi_lockfile_downgrades_confidence_independent_of_warning(tmp_path: Path):
    """AC-5 — split assertion; kills the 'drop low but keep warning' mutant."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, yarn_lock=True, deps={"x": "^1"})
    ctx = MagicMock(); ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert out.confidence == "low"


@pytest.mark.asyncio
async def test_bun_lockb_copresent_trips_multi_but_is_not_parsed(tmp_path: Path):
    """AC-4 — bun.lockb counts for multi-detect but is never the selected parsed format."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, bun_lock=True, deps={"bcrypt": "^5.1.0"})
    ctx = MagicMock(); ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert "lockfile.multi_present" in out.warnings
    assert out.schema_slice["manifests"]["primary"]["lockfile"]["name"] == "pnpm-lock.yaml"


@pytest.mark.asyncio
async def test_lockfile_precedence_pnpm_over_yarn_over_npm(tmp_path: Path):
    """AC-4 — kills the 'precedence reordered' mutant."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    # All three parseable lockfiles present.
    repo_root = _build_repo(
        tmp_path, pnpm_lock=True, yarn_lock=True, npm_lock=True, deps={"x": "^1"}
    )
    ctx = MagicMock(); ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert out.schema_slice["manifests"]["primary"]["lockfile"]["name"] == "pnpm-lock.yaml"

    # pnpm removed → yarn beats npm.
    (tmp_path / "pnpm-lock.yaml").unlink()
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert out.schema_slice["manifests"]["primary"]["lockfile"]["name"] == "yarn.lock"


@pytest.mark.asyncio
async def test_optional_and_bundled_deps_extraction(tmp_path: Path):
    """AC-10 — absent → 0/[]; present → length / list."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(
        tmp_path, pnpm_lock=True, deps={"a": "^1"},
        optional_deps={"b": "^2", "c": "^3"},
        bundled_deps=["d", "e"],
    )
    ctx = MagicMock(); ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    primary = out.schema_slice["manifests"]["primary"]
    assert primary["optional_dependencies"] == 2
    assert primary["bundled_dependencies"] == ["d", "e"]


@pytest.mark.asyncio
async def test_optional_and_bundled_deps_absent(tmp_path: Path):
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, deps={"a": "^1"})
    ctx = MagicMock(); ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    primary = out.schema_slice["manifests"]["primary"]
    assert primary["optional_dependencies"] == 0
    assert primary["bundled_dependencies"] == []


# ---------- AC-15 — exact-match cross-reference ----------------------------


@pytest.mark.parametrize(
    "resolved,expected_names",
    [
        ({"bcrypt": "5.1.1"}, {"bcrypt"}),
        ({"@types/bcrypt": "1.0.0"}, set()),
        ({"bcryptjs": "2.4.3"}, set()),
        ({"bcrypt-utils": "1.2.0"}, set()),
        ({"bcrypt": "5.1.1", "bcryptjs": "2.4.3"}, {"bcrypt"}),
    ],
)
def test_cross_reference_exact_match_not_substring(resolved, expected_names):
    from codegenie.catalogs import NATIVE_MODULES
    from codegenie.probes.node_manifest import _cross_reference_native_modules

    hits = _cross_reference_native_modules(resolved, NATIVE_MODULES)
    assert {h["name"] if isinstance(h, dict) else h.name for h in hits} == expected_names


# ---------- AC-16 — flatten helpers normalize keys -------------------------


def test_flatten_pnpm_normalizes_v9_keys():
    from codegenie.probes.node_manifest import _flatten_pnpm

    parsed = {"packages": {"/bcrypt@5.1.1": {}, "/@types/bcrypt@1.0.0(peer@^1)": {}}}
    out = _flatten_pnpm(parsed)
    assert out == {"bcrypt": "5.1.1", "@types/bcrypt": "1.0.0"}


def test_flatten_pnpm_normalizes_v6_keys():
    from codegenie.probes.node_manifest import _flatten_pnpm

    parsed = {"packages": {"/bcrypt/5.1.1": {}}}  # v6 slash variant
    out = _flatten_pnpm(parsed)
    assert out.get("bcrypt") == "5.1.1"


def test_flatten_npm_normalizes_v3_keys():
    from codegenie.probes.node_manifest import _flatten_npm

    parsed = {
        "lockfileVersion": 3,
        "packages": {
            "node_modules/bcrypt": {"version": "5.1.1"},
            "node_modules/@types/bcrypt": {"version": "1.0.0"},
        },
    }
    out = _flatten_npm(parsed)
    assert out == {"bcrypt": "5.1.1", "@types/bcrypt": "1.0.0"}


def test_flatten_npm_walks_v1_dependencies_tree():
    from codegenie.probes.node_manifest import _flatten_npm

    parsed = {
        "lockfileVersion": 1,
        "dependencies": {"bcrypt": {"version": "5.1.1"}},
    }
    out = _flatten_npm(parsed)
    assert out["bcrypt"] == "5.1.1"


def test_flatten_yarn_normalizes_comma_joined_and_scoped():
    from codegenie.probes.node_manifest import _flatten_yarn

    parsed = {
        "entries": {
            "bcrypt@^5.1.0, bcrypt@^5.0": {"version": "5.1.1"},
            "@types/bcrypt@^1.0.0": {"version": "1.0.0"},
        }
    }
    out = _flatten_yarn(parsed)
    assert out == {"bcrypt": "5.1.1", "@types/bcrypt": "1.0.0"}


# ---------- AC-6 — error-ID translation -----------------------------------


@pytest.mark.parametrize(
    "kind,exc_cls,expected",
    [
        ("pnpm", SizeCapExceeded,         "pnpm_lock.size_cap_exceeded"),
        ("pnpm", DepthCapExceeded,        "pnpm_lock.depth_cap_exceeded"),
        ("pnpm", MalformedLockfileError,  "pnpm_lock.malformed"),
        ("pnpm", SymlinkRefusedError,     "pnpm_lock.symlink_refused"),
        ("npm",  SizeCapExceeded,         "npm_lock.size_cap_exceeded"),
        ("npm",  MalformedLockfileError,  "npm_lock.malformed"),
        ("yarn", SizeCapExceeded,         "yarn_lock.size_cap_exceeded"),
        ("yarn", MalformedLockfileError,  "yarn_lock.malformed"),
        ("yarn", SymlinkRefusedError,     "yarn_lock.symlink_refused"),
    ],
)
def test_error_id_table_matches_adr_0007_pattern(kind, exc_cls, expected):
    from codegenie.probes.node_manifest import _error_id

    assert _error_id(kind, exc_cls(f"/p: {exc_cls.__name__}")) == expected
    assert re.fullmatch(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$", expected)


# ---------- AC-18 — no subprocess (broader net) ---------------------------


@pytest.mark.asyncio
async def test_no_subprocess_for_dep_resolution(tmp_path: Path, monkeypatch):
    from codegenie.probes.node_manifest import NodeManifestProbe

    calls: dict[str, list] = {k: [] for k in ("run", "Popen", "spawnv", "execv", "execvp", "create_subprocess_exec")}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls["run"].append((a, k)))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls["Popen"].append((a, k)))
    monkeypatch.setattr(os, "spawnv", lambda *a, **k: calls["spawnv"].append((a, k)))
    monkeypatch.setattr(os, "execv", lambda *a, **k: calls["execv"].append((a, k)))
    monkeypatch.setattr(os, "execvp", lambda *a, **k: calls["execvp"].append((a, k)))
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec",
        lambda *a, **k: calls["create_subprocess_exec"].append((a, k)),
    )

    repo_root = _build_repo(tmp_path, pnpm_lock=True, deps={"x": "^1"})
    ctx = MagicMock(); ctx.parsed_manifest = None
    await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    for kind, recorded in calls.items():
        assert recorded == [], f"forbidden subprocess shape invoked: {kind}"


# ---------- AC-3 — oversized lockfile via os.fstat monkey-patch -----------


@pytest.mark.asyncio
async def test_oversized_lockfile_degrades_gracefully(monkeypatch, tmp_path: Path):
    """AC-6 — SizeCapExceeded → typed error_id → confidence=low, gather continues.

    Forces the size-cap path via ``os.fstat`` monkey-patch (mirrors S3-01 / S3-02 /
    S3-03 hardenings); the 60 MB tmpfs write the original draft prescribed is
    avoided.
    """
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, deps={"x": "^1"})
    real_fstat = os.fstat

    class _BigStat:
        def __init__(self, real):
            self.__dict__.update({a: getattr(real, a) for a in dir(real) if not a.startswith("_")})
            self.st_size = 99 * 1024 * 1024  # 99 MB > 50 MB cap

    def fake_fstat(fd):
        return _BigStat(real_fstat(fd))

    monkeypatch.setattr(os, "fstat", fake_fstat)
    ctx = MagicMock(); ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert out.confidence == "low"
    assert "pnpm_lock.size_cap_exceeded" in out.errors


# ---------- AC-11 / AC-14 — sub-schema rejection at JSON Pointer ----------


@pytest.fixture
def _node_manifest_subschema():
    import json
    from importlib.resources import files

    path = files("codegenie.schema.probes").joinpath("node_manifest.schema.json")
    return json.loads(path.read_text())


@pytest.mark.parametrize(
    "inject_at,expected_pointer_suffix",
    [
        ([], "extra_at_root"),
        (["primary"], "extra_in_primary"),
        (["primary", "native_modules", "packages", 0], "extra_in_hit"),
    ],
)
def test_subschema_rejects_extra_field_at_pointer(_node_manifest_subschema, inject_at, expected_pointer_suffix):
    slice_payload = {
        "primary": {
            "path": "package.json",
            "direct_dependencies": {"runtime": 1, "dev": 0},
            "declared_engines": {},
            "lockfile": {"name": "pnpm-lock.yaml"},
            "native_modules": {
                "detected": True,
                "packages": [{
                    "name": "bcrypt", "version": "5.1.1", "requires_node_gyp": True,
                    "system_deps_required": [], "binary_artifacts_glob": [],
                    "catalog_entry_version": 1,
                }],
            },
            "optional_dependencies": 0,
            "bundled_dependencies": [],
        },
        "catalog_version": 1,
        "warnings": [],
        "errors": [],
    }
    # walk to injection point
    target: object = slice_payload
    for k in inject_at:
        target = target[k]  # type: ignore[index]
    target[expected_pointer_suffix] = "bogus"  # type: ignore[index]

    with pytest.raises(jsonschema.ValidationError) as exc:
        jsonschema.validate(slice_payload, _node_manifest_subschema)
    # The validator's absolute_path includes the injection prefix; the failing key surfaces in exc.message.
    assert expected_pointer_suffix in exc.value.message


# ---------- AC-12 — warnings prose rejection ------------------------------


def test_subschema_rejects_prose_in_warnings(_node_manifest_subschema):
    payload = {
        "primary": None,
        "catalog_version": 1,
        "warnings": ["This Helm chart looks production-ready"],  # prose, not pattern
        "errors": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, _node_manifest_subschema)
```

Confirm collection error. Commit red.

### Green — make it pass

```python
# src/codegenie/probes/node_manifest.py
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final, Literal, TypedDict

from codegenie.catalogs import NATIVE_MODULES, NATIVE_MODULES_CATALOG_VERSION
from codegenie.coordinator.budget import ResourceBudget
from codegenie.errors import (
    DepthCapExceeded,
    MalformedJSONError,
    MalformedLockfileError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.logging import (
    EVENT_PROBE_FAILURE,
    EVENT_PROBE_START,
    EVENT_PROBE_SUCCESS,
    _log,
)
from codegenie.parsers import safe_json
from codegenie.probes._lockfiles import _npm, _pnpm, _yarn
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe

__all__ = ["NodeManifestProbe"]

ParserKind = Literal["pnpm", "yarn", "npm"]

_PARSER_KIND_BY_FILENAME: Final[Mapping[str, ParserKind]] = {
    "pnpm-lock.yaml":    "pnpm",
    "yarn.lock":         "yarn",
    "package-lock.json": "npm",
}
# Parsed-formats precedence (mirrors node_build_system._LOCKFILE_PRECEDENCE
# minus bun, which is presence-only here).
_PARSEABLE_LOCKFILES: Final[tuple[str, ...]] = ("pnpm-lock.yaml", "yarn.lock", "package-lock.json")
_ALL_LOCKFILES:       Final[tuple[str, ...]] = _PARSEABLE_LOCKFILES + ("bun.lockb",)


def _flatten_pnpm(parsed: _pnpm.PnpmLock) -> Mapping[str, str]:
    """Normalize pnpm v6/v9 keys to {name -> version}."""
    out: dict[str, str] = {}
    for raw_key in parsed.get("packages", {}):
        # /bcrypt@5.1.1(peer@^1)  →  bcrypt 5.1.1
        # /@types/bcrypt@1.0.0    →  @types/bcrypt 1.0.0
        # /bcrypt/5.1.1 (v6)      →  bcrypt 5.1.1
        key = raw_key.lstrip("/")
        # strip peer-dep suffix
        if "(" in key:
            key = key.split("(", 1)[0]
        # find separator between name and version
        if "/" in key and key.count("/") == 1 and "@" not in key.split("/")[1]:
            # v6 form name/version
            name, _, version = key.partition("/")
        else:
            # find the last '@' that is NOT the scope leading character
            at_idx = key.rfind("@")
            if at_idx <= 0:
                continue
            name, version = key[:at_idx], key[at_idx + 1:]
        if name and version:
            out[name] = version
    return out


def _flatten_npm(parsed: _npm.NpmLock) -> Mapping[str, str]:
    out: dict[str, str] = {}
    # v2/v3 — flat packages
    for raw_key, entry in parsed.get("packages", {}).items():
        if not raw_key or not isinstance(entry, dict):
            continue
        name = raw_key.split("node_modules/", 1)[-1] if raw_key.startswith("node_modules/") else raw_key
        # If the key chain has nested node_modules/, the LAST segment is the name (the dep-of-dep installed location).
        if "node_modules/" in name:
            name = name.rsplit("node_modules/", 1)[-1]
        ver = entry.get("version")
        if name and isinstance(ver, str):
            out[name] = ver
    # v1 fallback — nested dependencies tree
    if not out and isinstance(parsed.get("dependencies"), dict):
        _walk_v1(parsed["dependencies"], out)
    return out


def _walk_v1(tree: Mapping[str, Any], out: dict[str, str]) -> None:
    for name, entry in tree.items():
        if isinstance(entry, dict):
            ver = entry.get("version")
            if isinstance(ver, str):
                out[name] = ver
            sub = entry.get("dependencies")
            if isinstance(sub, dict):
                _walk_v1(sub, out)


def _flatten_yarn(parsed: _yarn.YarnLock) -> Mapping[str, str]:
    out: dict[str, str] = {}
    for raw_key, entry in parsed.get("entries", {}).items():
        ver = entry.get("version") if isinstance(entry, dict) else None
        if not isinstance(ver, str):
            continue
        for locator in raw_key.split(", "):
            at_idx = locator.rfind("@")
            if at_idx <= 0:
                continue
            name = locator[:at_idx]
            if name:
                out[name] = ver
    return out


_FLATTENERS: Final[Mapping[ParserKind, Callable[[Any], Mapping[str, str]]]] = {
    "pnpm": _flatten_pnpm, "yarn": _flatten_yarn, "npm": _flatten_npm,
}
_PARSERS: Final[Mapping[ParserKind, Callable[[Path], Any]]] = {
    "pnpm": _pnpm.parse, "yarn": _yarn.parse, "npm": _npm.parse,
}
_ERROR_PREFIX_BY_KIND: Final[Mapping[ParserKind, str]] = {
    "pnpm": "pnpm_lock", "yarn": "yarn_lock", "npm": "npm_lock",
}
_ERROR_SUFFIX_BY_EXC: Final[Mapping[type[BaseException], str]] = {
    SizeCapExceeded:        "size_cap_exceeded",
    DepthCapExceeded:       "depth_cap_exceeded",
    MalformedLockfileError: "malformed",
    SymlinkRefusedError:    "symlink_refused",
}


def _error_id(parser_kind: ParserKind, exc: BaseException) -> str:
    suffix = _ERROR_SUFFIX_BY_EXC.get(type(exc), "unknown_error")
    return f"{_ERROR_PREFIX_BY_KIND[parser_kind]}.{suffix}"


class _NativeModuleHit(TypedDict):
    name: str
    version: str
    requires_node_gyp: bool
    system_deps_required: list[str]
    binary_artifacts_glob: list[str]
    catalog_entry_version: int


def _cross_reference_native_modules(
    resolved: Mapping[str, str],
    catalog: Mapping[str, Any],
) -> tuple[_NativeModuleHit, ...]:
    """Exact-name dict lookup (AC-8 / AC-15). No substring match."""
    hits: list[_NativeModuleHit] = []
    for name, entry in catalog.items():
        if name not in resolved:
            continue
        hits.append({
            "name": name,
            "version": resolved[name],
            "requires_node_gyp": bool(entry.requires_node_gyp),
            "system_deps_required": list(entry.system_deps_required),
            "binary_artifacts_glob": list(entry.binary_artifacts_glob),
            "catalog_entry_version": int(entry.catalog_entry_version),
        })
    return tuple(hits)


@register_probe
class NodeManifestProbe(Probe):
    name: str = "node_manifest"
    version: str = "0.1.0"
    layer = "A"
    tier = "base"
    applies_to_languages: list[str] = ["javascript", "typescript"]
    applies_to_tasks: list[str] = ["*"]
    requires: list[str] = ["language_detection"]
    timeout_seconds: int = 30
    declared_inputs: list[str] = [
        "package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock",
        "src/codegenie/catalogs/native_modules.yaml",
    ]
    declared_resource_budget: Final[ResourceBudget] = ResourceBudget(
        raw_artifact_mb=50, raw_artifact_truncate_mb=25,
    )

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        _log.info(EVENT_PROBE_START, probe=self.name)
        t0 = time.perf_counter()
        warnings: list[str] = []
        errors: list[str] = []
        confidence: str = "high"

        # 1) package.json
        pkg = self._read_package_json(repo.root, ctx, errors)
        if pkg is None:
            return self._failure(t0, confidence="low", warnings=warnings, errors=errors)

        # 2) lockfile detection (existence-only)
        present = [f for f in _ALL_LOCKFILES if (repo.root / f).exists()]
        if len(present) >= 2:
            warnings.append("lockfile.multi_present")
            confidence = "low"
        selected = next((f for f in _PARSEABLE_LOCKFILES if f in present), None)

        # 3) parse + flatten via the registries (AC-7 — no per-format branches)
        resolved: Mapping[str, str] = {}
        if selected is not None:
            parser_kind = _PARSER_KIND_BY_FILENAME[selected]
            try:
                parsed = _PARSERS[parser_kind](repo.root / selected)
                resolved = _FLATTENERS[parser_kind](parsed)
            except (SizeCapExceeded, DepthCapExceeded,
                    MalformedLockfileError, SymlinkRefusedError) as exc:
                errors.append(_error_id(parser_kind, exc))
                confidence = "low"

        # 4) catalog cross-reference (pure function)
        native_hits = _cross_reference_native_modules(resolved, NATIVE_MODULES)

        # 5) assemble slice
        slice_payload = {
            "manifests": {
                "primary": {
                    "path": "package.json",
                    "direct_dependencies": {
                        "runtime": len(pkg.get("dependencies") or {}),
                        "dev":     len(pkg.get("devDependencies") or {}),
                    },
                    "declared_engines":      dict(pkg.get("engines") or {}),
                    "lockfile":              {"name": selected} if selected else None,
                    "native_modules":        {
                        "detected": len(native_hits) > 0,
                        "packages": list(native_hits),
                    },
                    "optional_dependencies": len(pkg.get("optionalDependencies") or {}),
                    "bundled_dependencies":  list(pkg.get("bundledDependencies") or []),
                },
                "catalog_version": NATIVE_MODULES_CATALOG_VERSION,
                "warnings":        list(warnings),
                "errors":          list(errors),
            }
        }
        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        event = EVENT_PROBE_SUCCESS if confidence == "high" else EVENT_PROBE_FAILURE
        _log.info(event, probe=self.name, confidence=confidence)
        return ProbeOutput(
            schema_slice=slice_payload, raw_artifacts=[],
            confidence=confidence,  # type: ignore[arg-type]
            duration_ms=duration_ms,
            warnings=warnings, errors=errors,
        )

    # ... _read_package_json + _failure helpers per node_build_system.py pattern.
```

### Refactor

- **`_FLATTENERS` is the rule-of-three resolution.** S3-01, S3-02, S3-03 explicitly punted shared helper extraction to "the third caller"; that caller is S3-05, but the resolution lives in this probe — **not** in `_lockfiles/__init__.py` (which stays inert per S3-02 / S3-03 invariant). The shape (registry mapping `ParserKind → Callable`) mirrors `node_build_system._LOCKFILE_PRECEDENCE`'s tuple-driven dispatch.
- **No `commands` sub-key under `manifests`.** That's `NodeBuildSystemProbe`'s slice (S2-02). Resist the temptation.
- **No `Path.write_text` from inside this probe.** Raw-artifact write goes through `BudgetingContext.report_bytes(...)` and the writer hook chain; the `apply_raw_artifact_truncation` from S1-09 enforces the 25 MB soft cap.
- **Module constants typed `Final[Mapping[...]]`** so a future contributor mutating them in place trips mypy.

## Files to touch

| Path | Status | Why |
|---|---|---|
| `src/codegenie/probes/node_manifest.py` | New | `NodeManifestProbe` + module-level registries + pure helpers + `@register_probe`. |
| `src/codegenie/schema/probes/node_manifest.schema.json` | New | `additionalProperties: false` at root + every nested block; `warnings`/`errors` pattern-constrained. |
| `src/codegenie/probes/__init__.py` | Edit (additive) | One-line `from codegenie.probes import node_manifest` insertion + alphabetical order in `__all__`. |
| `src/codegenie/probes/_lockfiles/__init__.py` | **NOT touched** | S3-02 / S3-03 inert-init invariant; pinned by `test_lockfiles_init_remains_inert`. |
| `tests/unit/probes/test_node_manifest.py` | New | Twenty-plus tests covering AC-1..AC-24. |

## Out of scope

- **Fixtures `node_pnpm_native/`, `node_yarn_legacy/` + integration tests** — S3-06.
- **`tests/unit/test_cache_invalidation_scope.py` extension for the catalog-edit case** — S3-06 (co-locates with the fixtures that demonstrate the scope).
- **`probe.raw_artifact.truncated` event assertion on a 30 MB synthetic lockfile** — S3-06 (the synthetic fixture is the size-cap exercise).
- **`bun.lockb` parsing** — out of scope for Phase 1 entirely (binary format); presence-only detection here.
- **Workspace traversal for monorepos** — `manifests` slice covers the root `package.json` only in Phase 1; workspace expansion is Phase 2's concern.
- **`overrides` / `resolutions` field handling** — surfaced verbatim, not interpreted (Phase 3+ planner's job).

## Notes for the implementer

1. **Per-probe local coverage ≥ 90 / 80 is required in PR body** per cross-cutting convention #6. If borderline, write the missing-branch tests in this PR rather than pushing to S6-02.
2. **The `additionalProperties: false` rejection tests** are parametrized at three JSON Pointer injection sites (AC-14). Assert on `jsonschema.ValidationError.absolute_path` / `.message`, not just the boolean outcome.
3. **`subprocess` test net is broader than `subprocess.run`** (AC-18). ADR-0011 is load-bearing for Phase 7. If a future contributor adds *any* subprocess shape "for richer resolution," one of the five monkey-patches catches it.
4. **ADR-0006's cache-invalidation invariant** is encoded in `declared_inputs` and asserted by AC-17. Phase 7 depends on it. Do not change `declared_inputs` without surfacing the ADR-0006 reference in the PR.
5. **`_error_id` is the SSOT for translated warning IDs.** The full table (matching the ADR-0007 pattern):
   - `pnpm_lock.size_cap_exceeded`, `pnpm_lock.depth_cap_exceeded`, `pnpm_lock.malformed`, `pnpm_lock.symlink_refused`
   - `npm_lock.size_cap_exceeded`, `npm_lock.depth_cap_exceeded`, `npm_lock.malformed`, `npm_lock.symlink_refused`
   - `yarn_lock.size_cap_exceeded`, `yarn_lock.malformed`, `yarn_lock.symlink_refused`
   - `package_json.missing`, `package_json.malformed`, `package_json.size_cap_exceeded`, `package_json.symlink_refused`
6. **`WarningId` is constructed at catch site from `exc.args[0]`** — the path is recoverable from the marker's message (positional only), not from an attribute. Mirrors the S3-02 / S3-03 marker discipline; the `_error_id` helper returns the prefix-suffix, the path is preserved in the structured event payload via `args[0]`.
7. **Memo behavior.** `ctx.parsed_manifest(path)` returns `None` on the parse-failure no-cache path per S1-07's contract. Defensive-check for `None` and fall back to direct `safe_json.load` (which raises the same typed error you can then catalogue).
8. **Lockfile-key name normalization** is the single most likely silent-failure mode for Phase 7 (final-design.md "Risks" #1). The parametrized `test_flatten_<kind>_normalizes_keys` matrix is the load-bearing defense — if you find a fixture in the wild whose keys don't normalize, **add a row to the parametrize**, don't widen the helper.
9. **Catalog cross-reference is exact-match**, not substring (AC-15). `@types/bcrypt`, `bcryptjs`, `bcrypt-utils` are **not** hits for `bcrypt`. Tested in `test_cross_reference_exact_match_not_substring`.
10. **Design-pattern review — `_FLATTENERS` registry is the rule-of-three resolution.** S3-01/02/03 punted. S3-05 is the third concrete consumer. Adding a future `_bun.py` is one new `ParserKind` Literal arm + one entry in each of `_PARSER_KIND_BY_FILENAME` / `_PARSERS` / `_FLATTENERS` / `_ERROR_PREFIX_BY_KIND` — **zero edits to `run()`**. AC-7 pins this as an *observable* "no edit" architectural test (`inspect.getsource(run)` contains no per-format string equality).
11. **Design-pattern review — functional core / imperative shell.** `_flatten_*` and `_cross_reference_native_modules` are pure module-level functions; `run()` is the imperative shell that emits events, demotes confidence, and assembles the slice. Testing isolation: `_cross_reference_native_modules` is tested **directly** without spinning up the probe.
12. **Design-pattern review — `ParserKind = Literal["pnpm", "yarn", "npm"]`** at module scope. Drives every dispatch table. A typo (`"pnp"`) is a mypy error at module-load time, not a runtime `KeyError`. Mirrors S3-03's `_PARSER_KIND: Final[str] = "yarn_lockfile"` discipline and closes the primitive-obsession smell.
13. **Design-pattern review — what was NOT extracted.** A shared `_translate(path, *, parser_kind, cause)` helper was punted to S3-03 and re-punted to S3-05; S3-03's hardening recorded that the asymmetry between pnpm/npm (narrow `MalformedYAMLError`/`MalformedJSONError` catches) and yarn (broader `Exception` catch over the hand-rolled scanner) makes a single helper an over-abstraction — Rule 2. S3-05 **inherits** that decision: the catch in `run()` over `(SizeCapExceeded, DepthCapExceeded, MalformedLockfileError, SymlinkRefusedError)` is the *consumer* layer, not the parser layer, so the asymmetry doesn't apply here. The `_error_id` helper is the registry-driven translation; no shared `_translate` is needed.
14. **`raw_artifact_mb=50, raw_artifact_truncate_mb=25` is the load-bearing first non-default use of the S1-09 mechanism.** Surface in PR body so reviewers know this is the *first* probe with an override; the writer hook chain (`apply_raw_artifact_truncation`) must produce the soft-truncation marker on payloads > 25 MB. S3-06's integration test exercises the boundary.
15. **Sub-schema versioning is deferred to Phase 2** (`High-level-impl.md` open question #2). Ship v1 of the sub-schema here; no `$id` versioning gymnastics.
